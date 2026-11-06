from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auto_mapping import schedule_analysis
from .database import get_db
from .dependencies import require_writer
from .models import Answer, AnswerMappingRevision, AnswerRegionLink, AuditEvent, Document, DocumentLayoutRevision, Page, PageImageRevision, Region
from .router_submissions import _job_summary, _submission_scope
from .schemas import AutoMappingStartInput, AutoMappingConfirmInput, RegionExclusionInput
from .services import publish_job_outbox

router = APIRouter(prefix="/api/v1",tags=["submissions"])


@router.post("/submissions/{submission_id}/auto-map",status_code=202)
def request_auto_mapping(submission_id: str, body: AutoMappingStartInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    submission, assessment = _submission_scope(db,actor,submission_id,lock=True)
    document = db.get(Document,submission.active_document_id) if submission.active_document_id else None
    if (not document or document.id != body.expected_document_id or document.validation_status != "valid"
            or document.active_layout_revision_id != body.expected_layout_revision_id):
        raise HTTPException(409,detail={"code":"STALE_DOCUMENT_INPUT"})
    for answer in db.scalars(select(Answer).where(Answer.submission_id == submission.id)):
        mapping = db.get(AnswerMappingRevision,answer.active_mapping_revision_id) if answer.active_mapping_revision_id else None
        if mapping and mapping.layout_revision_id == document.active_layout_revision_id:
            raise HTTPException(409,detail={"code":"AUTO_MAPPING_EXISTING_WORK"})
    job = schedule_analysis(db,submission,document)
    db.add(AuditEvent(assessment_id=assessment.id,actor_id=actor.id,action="document.auto_mapping_requested",resource_id=document.id))
    db.commit(); publish_job_outbox(db,job.id); db.refresh(job)
    return _job_summary(job)


@router.post("/submissions/{submission_id}/confirm-mapping")
def confirm_auto_mapping(submission_id: str, body: AutoMappingConfirmInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    submission, assessment = _submission_scope(db,actor,submission_id,lock=True)
    document = db.get(Document,submission.active_document_id) if submission.active_document_id else None
    if submission.identity_status != "confirmed":
        raise HTTPException(409,detail={"code":"IDENTITY_AND_DOCUMENT_REQUIRED"})
    if (not document or document.active_layout_revision_id != body.expected_layout_revision_id
            or submission.version != body.expected_submission_version):
        raise HTTPException(409,detail={"code":"STALE_MAPPING"})
    if len(set(body.mapping_revision_ids)) != len(body.mapping_revision_ids):
        raise HTTPException(422,detail={"code":"DUPLICATE_MAPPING_ID"})
    answers = db.scalars(select(Answer).where(Answer.submission_id == submission.id).with_for_update()).all()
    selected = [a for a in answers if a.active_mapping_revision_id in body.mapping_revision_ids]
    if len(selected) != len(body.mapping_revision_ids):
        raise HTTPException(409,detail={"code":"STALE_MAPPING"})
    for answer in selected:
        mapping = db.get(AnswerMappingRevision,answer.active_mapping_revision_id)
        if mapping.layout_revision_id != document.active_layout_revision_id or answer.mapping_status != "auto_mapped":
            raise HTTPException(409,detail={"code":"STALE_MAPPING"})
        answer.mapping_status = "mapped"
    submission.version += 1
    db.add(AuditEvent(assessment_id=assessment.id,actor_id=actor.id,action="answer.auto_mapping_confirmed",resource_id=submission.id,
        metadata_json={"mapping_revision_ids":body.mapping_revision_ids,"layout_revision_id":document.active_layout_revision_id}))
    db.commit()
    from .router_submissions import _enqueue_automatic_grades
    _enqueue_automatic_grades(db,submission.id,actor)
    return {"status":"confirmed","confirmed_count":len(selected),"version":submission.version}


@router.post("/regions/{region_id}/mapping-exclusion")
def exclude_mapping_region(region_id: str, body: RegionExclusionInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    region = db.get(Region,region_id)
    image = db.get(PageImageRevision,region.page_image_revision_id) if region else None
    page = db.get(Page,image.page_id) if image else None
    document = db.get(Document,page.document_id) if page else None
    if not document or not document.submission_id:
        raise HTTPException(404,detail={"code":"RESOURCE_NOT_FOUND"})
    submission,assessment = _submission_scope(db,actor,document.submission_id,lock=True)
    if submission.active_document_id != document.id or document.active_layout_revision_id != body.expected_layout_revision_id:
        raise HTTPException(409,detail={"code":"STALE_DOCUMENT_INPUT"})
    layout = db.get(DocumentLayoutRevision,document.active_layout_revision_id)
    if image.id not in layout.ordered_page_image_revision_ids:
        raise HTTPException(409,detail={"code":"STALE_PAGE_IMAGE_REVISION"})
    linked = db.scalar(select(AnswerRegionLink.id).join(Answer,Answer.id == AnswerRegionLink.answer_id).where(
        Answer.submission_id == submission.id,Answer.active_mapping_revision_id == AnswerRegionLink.mapping_revision_id,
        AnswerRegionLink.region_id == region.id))
    if body.excluded and linked:
        raise HTTPException(409,detail={"code":"REGION_ALREADY_MAPPED"})
    region.excluded_from_mapping = body.excluded
    submission.version += 1
    db.add(AuditEvent(assessment_id=assessment.id,actor_id=actor.id,action="region.mapping_exclusion_reviewed",resource_id=region.id,
        reason=body.reason,metadata_json={"excluded":body.excluded,"layout_revision_id":layout.id}))
    db.commit()
    return {"id":region.id,"excluded_from_mapping":region.excluded_from_mapping}
