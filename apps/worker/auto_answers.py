"""Recoverable, document-scoped visual localization → literal OCR → draft mapping."""
from __future__ import annotations

import hashlib
from io import BytesIO
import math

from PIL import Image
from sqlalchemy import select

from apps.api.asdos_api.auto_mapping import (
    AUTO_MAPPING_VERSION, LOCATOR_PREPROCESSING, LOCATOR_PROMPT_VERSION, analysis_fingerprint, flag_number_disagreement, match_regions,
)
from apps.api.asdos_api.database import SessionLocal
from apps.api.asdos_api.model_adapters import ModelUnavailable, get_transcriber, qwen_adapter, transcription_status_for_flags
from apps.api.asdos_api.models import (
    Answer, AnswerMappingRevision, AnswerRegionLink, Assessment, AuditEvent, Document,
    DocumentLayoutRevision, ModelRun, Page, PageImageRevision, PipelineJob, Region, Submission,
    TranscriptionRevision, now_utc,
)
from apps.api.asdos_api.services import canonical_hash, question_json
from apps.worker.celery_app import celery_app
from apps.worker.tasks import _begin, _failed, _finish, _heartbeat, store


def input_state(db, submission, layout):
    answers = db.scalars(select(Answer).where(Answer.submission_id == submission.id).order_by(Answer.id)).all()
    regions = db.scalars(select(Region.id).where(Region.page_image_revision_id.in_(layout.ordered_page_image_revision_ids)).order_by(Region.id)).all()
    return canonical_hash({"document":submission.active_document_id, "layout":layout.id,
        "answers":[(a.id,a.active_mapping_revision_id,a.active_transcription_revision_id,a.active_proposal_id) for a in answers],
        "regions":list(regions)})


def _progress(job_id, owner, stage, completed, total):
    with SessionLocal.begin() as db:
        job = db.get(PipelineJob, job_id)
        if not job or job.status != "running" or job.lease_owner != owner or job.cancel_requested:
            raise ModelUnavailable("AUTO_ANALYSIS_INTERRUPTED", "Analisis berhenti atau lease berubah.")
        job.stage, job.progress_current, job.progress_total = stage, completed, total


def _run_record(db, task_type, prompt, schema, fingerprint, preprocessing, adapter=qwen_adapter):
    run = ModelRun(task_type=task_type, checkpoint=adapter.model_id, checkpoint_revision=adapter.revision,
        runtime=adapter.runtime, prompt_version=prompt, schema_version=schema,
        preprocessing_version=preprocessing, input_fingerprint=fingerprint, status="running")
    db.add(run); db.commit()
    return run


def _completed_run(db, run, provenance):
    run.status, run.device, run.checkpoint_sha256 = "succeeded", provenance.device, provenance.checkpoint_sha256
    db.commit()


@celery_app.task(name="asdos.analyze_answers", bind=True, max_retries=0)
def analyze_answers(self, job_id):
    lease = _begin(job_id)
    if not lease:
        return {"job_id":job_id,"status":"skipped"}
    _, owner = lease
    run_id = None
    try:
        with _heartbeat(job_id, owner), SessionLocal() as db:
            job = db.get(PipelineJob, job_id)
            submission = db.get(Submission, job.submission_id) if job else None
            document = db.get(Document, job.document_id) if job else None
            layout = db.get(DocumentLayoutRevision, document.active_layout_revision_id) if document else None
            if (not submission or not document or not layout or document.validation_status != "valid"
                    or document.submission_id != submission.id or submission.active_document_id != document.id):
                return _failed(job_id, owner, "STALE_DOCUMENT_INPUT")
            if analysis_fingerprint(submission,document) != job.input_fingerprint:
                return _failed(job_id,owner,"STALE_AUTO_MAPPING_INPUT")
            for answer in db.scalars(select(Answer).where(Answer.submission_id == submission.id)):
                mapping = db.get(AnswerMappingRevision, answer.active_mapping_revision_id) if answer.active_mapping_revision_id else None
                if mapping and mapping.layout_revision_id == layout.id:
                    return _failed(job_id, owner, "AUTO_MAPPING_EXISTING_WORK")
            baseline, layout_id, sid, doc_id = input_state(db, submission, layout), layout.id, submission.id, document.id
            assessment = db.get(Assessment, submission.assessment_id)
            language, actor_id, assessment_id = assessment.language, assessment.owner_id, assessment.id
            questions = question_json(db, submission.assessment_revision_id)
            located = []
            page_flags = []
            page_images = [(db.get(PageImageRevision, image_id)) for image_id in layout.ordered_page_image_revision_ids]
            image_catalog = {}
            identity_candidate = None
            for index, page_image in enumerate(page_images):
                _progress(job_id, owner, "locate_answers", index, len(page_images))
                page = db.get(Page, page_image.page_id)
                image_data = store.read(page_image.image_storage_key)
                image_catalog[page.page_index] = (page_image.id, image_data)
                if index == 0 and submission.external_student_id.startswith('__asdos_pending__'):
                    identity_run = _run_record(db,"identity_proposal","identity-proposal.v1","identity-proposal.v1",
                        canonical_hash({"job":job.input_fingerprint,"image":page_image.image_sha256}),"identity-page.v1")
                    try:
                        identity_candidate, identity_provenance = qwen_adapter.propose_identity(image_data)
                        _completed_run(db, identity_run, identity_provenance)
                        identity_candidate = {**identity_candidate,"model_run_id":identity_run.id,"page_image_id":page_image.id}
                    except Exception as exc:
                        identity_run.status, identity_run.error_code = 'failed', getattr(exc,'code',None) or 'IDENTITY_OUTPUT_INVALID'
                        db.commit()
                run = _run_record(db, "answer_localization", LOCATOR_PROMPT_VERSION, "located-answers.v1",
                    canonical_hash({"job":job.input_fingerprint,"image":page_image.image_sha256,"page":page.page_index}), LOCATOR_PREPROCESSING)
                run_id = run.id
                result, provenance = qwen_adapter.locate_answers(image_data, language)
                _completed_run(db, run, provenance)
                page_flags.extend({"page_index":page.page_index,"flag":flag} for flag in result.flags)
                for region in result.regions:
                    located.append({**region.model_dump(),"flags":list(region.flags)+list(result.flags),"page_index":page.page_index,
                                    "page_image_id":page_image.id,"locator_run_id":run.id})
                if len(located) > 100:
                    raise ModelUnavailable("AUTO_REGION_LIMIT", "Terlalu banyak area jawaban untuk satu job.")
            candidates = match_regions(located, questions)
            transcriber = get_transcriber()
            for index, candidate in enumerate(candidates):
                _progress(job_id, owner, "transcribe_regions", index, len(candidates))
                with Image.open(BytesIO(image_catalog[candidate["page_index"]][1])) as image:
                    left, top, right, bottom = candidate["bbox"]
                    crop = image.crop((math.floor(left*image.width/1000),math.floor(top*image.height/1000),
                                       math.ceil(right*image.width/1000),math.ceil(bottom*image.height/1000)))
                    buffer = BytesIO(); crop.save(buffer,format="PNG"); crop.close()
                data = buffer.getvalue()
                run = _run_record(db, "transcription", transcriber.prompt_version, transcriber.schema_version,
                    canonical_hash({"job":job.input_fingerprint,"crop":hashlib.sha256(data).hexdigest(),"index":index}),
                    transcriber.preprocessing_version, adapter=transcriber)
                run_id = run.id
                segments, provenance = transcriber.transcribe([data], language)
                if len(segments) != 1:
                    raise ValueError("one region must produce exactly one transcript segment")
                _completed_run(db, run, provenance)
                candidate.update({"text":segments[0].text,"transcription_flags":list(segments[0].flags),
                                  "transcriber_run_id":run.id,"crop_sha256":hashlib.sha256(data).hexdigest()})
            candidates = match_regions([flag_number_disagreement(c) for c in candidates],questions)
            _progress(job_id, owner, "map_answers", 0, len(candidates))
        with SessionLocal.begin() as db:
            job = db.scalar(select(PipelineJob).where(PipelineJob.id == job_id).with_for_update())
            submission = db.scalar(select(Submission).where(Submission.id == sid).with_for_update())
            document = db.get(Document, doc_id)
            layout = db.get(DocumentLayoutRevision, layout_id)
            if not job or job.status != "running" or job.lease_owner != owner:
                return {"job_id":job_id,"status":"stale_lease"}
            if job.cancel_requested:
                job.status, job.finished_at = "cancelled", now_utc()
                job.lease_owner = job.lease_until = None
                return {"job_id":job_id,"status":"cancelled"}
            if (not submission or submission.active_document_id != doc_id or document.active_layout_revision_id != layout_id
                    or input_state(db, submission, layout) != baseline):
                raise ModelUnavailable("STALE_AUTO_MAPPING_INPUT", "Pemetaan/teks berubah selama analisis.")
            by_question = {}
            region_ids = []
            for candidate in candidates:
                l,t,r,b = [v/1000 for v in candidate["bbox"]]
                region = Region(page_image_revision_id=candidate["page_image_id"],polygon=[[l,t],[r,t],[r,b],[l,b]],
                    region_type="answer",created_by=actor_id,analysis={**candidate,"source":"model","job_id":job_id,
                    "matching_version":AUTO_MAPPING_VERSION,"layout_revision_id":layout_id})
                db.add(region); db.flush(); region_ids.append(region.id)
                if candidate["question_id"]:
                    by_question.setdefault(candidate["question_id"],[]).append((region,candidate))
            for answer in db.scalars(select(Answer).where(Answer.submission_id == sid).order_by(Answer.id).with_for_update()):
                entries = by_question.get(answer.stable_question_id,[])
                if not entries:
                    continue
                previous = db.get(AnswerMappingRevision, answer.active_mapping_revision_id) if answer.active_mapping_revision_id else None
                mapping = AnswerMappingRevision(answer_id=answer.id,sequence=(previous.sequence+1 if previous else 1),
                    parent_revision_id=previous.id if previous else None,layout_revision_id=layout_id,
                    ordered_region_ids=[r.id for r,c in entries],created_by=actor_id)
                db.add(mapping); db.flush()
                segments = []
                for order,(region,candidate) in enumerate(entries,start=1):
                    db.add(AnswerRegionLink(answer_id=answer.id,mapping_revision_id=mapping.id,region_id=region.id,order_index=order))
                    segments.append({"segment_id":f"seg-{order}","region_id":region.id,"page_index":candidate["page_index"],
                        "order":order,"text":candidate["text"],"confidence":None,"flags":candidate["transcription_flags"],
                        "model_run_id":candidate["transcriber_run_id"]})
                flags = sorted({f for s in segments for f in s["flags"]})
                transcript = TranscriptionRevision(answer_id=answer.id,mapping_revision_id=mapping.id,
                    revision_no=answer.transcript_revision+1,parent_revision_id=answer.active_transcription_revision_id,
                    literal_text="\n".join(s["text"] for s in segments),segments=segments,
                    status=transcription_status_for_flags(flags),flags=flags,source="model",
                    model_run_id=entries[0][1]["transcriber_run_id"])
                db.add(transcript); db.flush()
                answer.active_mapping_revision_id, answer.mapping_status = mapping.id, "auto_mapped"
                answer.active_transcription_revision_id, answer.transcript_revision = transcript.id, transcript.revision_no
                answer.literal_text, answer.transcript_status = transcript.literal_text, transcript.status
                answer.active_proposal_id = None
            document.analysis_result = {"job_id":job_id,"layout_revision_id":layout_id,"region_ids":region_ids,
                "mapped_questions":len(by_question),"total_regions":len(candidates),"page_flags":page_flags,
                "flags":[] if candidates else ["no_answer_regions"],"matching_version":AUTO_MAPPING_VERSION,
                "identity_candidate":identity_candidate,
                "auto_grade_requested":bool((document.analysis_result or {}).get('auto_grade_requested'))}
            submission.status, submission.version = "needs_mapping_review", submission.version+1
            db.add(AuditEvent(assessment_id=assessment_id,actor_id=actor_id,action="document.auto_mapping_proposed",
                resource_id=doc_id,new_revision=layout_id,metadata_json={"job_id":job_id,"source":"model","regions":len(candidates)}))
            job.status, job.finished_at = "succeeded", now_utc()
            job.progress_current = job.progress_total = len(candidates)
            job.lease_owner = job.lease_until = None
        return {"job_id":job_id,"status":"succeeded","regions":len(candidates),"mapped_questions":len(by_question)}
    except Exception as exc:
        code = getattr(exc,"code",None) or "AUTO_MAPPING_FAILED"
        with SessionLocal.begin() as db:
            run = db.get(ModelRun,run_id) if run_id else None
            if run and run.status == "running":
                run.status,run.error_code = "failed",code
            job = db.get(PipelineJob,job_id)
            cancelled = bool(job and job.cancel_requested and job.lease_owner == owner)
        if cancelled:
            _finish(job_id,owner,status="cancelled")
            return {"job_id":job_id,"status":"cancelled"}
        return _failed(job_id,owner,code)
