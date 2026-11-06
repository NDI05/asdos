"""End-to-end API test for the manual, no-model scoring path using a synthetic PDF."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

EXTERNAL_COMPOSE = os.getenv("ASDOS_TEST_COMPOSE") == "true"
TEST_ROOT: Path | None = None
if not EXTERNAL_COMPOSE:
    TEST_ROOT = Path(tempfile.mkdtemp(prefix="asdos-e2e-"))
    os.environ["ASDOS_DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'database.sqlite3'}"
    os.environ["ASDOS_ARTIFACT_DIR"] = str(TEST_ROOT / "private")
    os.environ["ASDOS_CELERY_EAGER"] = "true"
    os.environ["ASDOS_AUTO_CREATE"] = "true"
    os.environ["ASDOS_SESSION_SECRET"] = "test-only-session-secret-with-48-characters"
    os.environ["ASDOS_RENDER_DPI"] = "90"

from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.asdos_api.main import app
from apps.api.asdos_api.database import SessionLocal
from apps.api.asdos_api.models import Artifact, Assessment, User
from apps.api.asdos_api.security import hash_password
from apps.api.asdos_api.storage import artifact_store


def one_page_pdf() -> bytes:
    stream = b"BT /F1 16 Tf 72 720 Td (Synthetic ASDOS answer sheet) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode())
        result.extend(obj)
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


class TestManualWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessment_ids = []
        cls.created_user_ids = []
        cls.username = f"lecturer-{uuid4().hex[:10]}"
        cls.password = f"test-password-{uuid4().hex}"
        cls.other_username = f"other-{uuid4().hex[:10]}"
        cls.other_password = f"other-password-{uuid4().hex}"
        cls.client = TestClient(app)
        cls.client.__enter__()
        db = SessionLocal()
        try:
            owner = User(username=cls.username, display_name="Dosen Sintetis", password_hash=hash_password(cls.password), role="owner")
            db.add(owner)
            db.flush()
            cls.owner_id = owner.id
            db.commit()
        finally:
            db.close()
        response = cls.client.post("/api/v1/auth/login", json={"username":cls.username, "password":cls.password})
        if response.status_code != 200:
            raise AssertionError(response.text)
        cls.client.headers.update({"X-CSRF-Token": response.json()["csrf_token"]})

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        if EXTERNAL_COMPOSE:
            cls._cleanup_compose_fixtures()
        elif TEST_ROOT:
            shutil.rmtree(TEST_ROOT, ignore_errors=True)

    @classmethod
    def _cleanup_compose_fixtures(cls):
        db = SessionLocal()
        try:
            for assessment_id in cls.assessment_ids:
                artifacts = db.scalars(select(Artifact).where(Artifact.assessment_id == assessment_id)).all()
                for artifact in artifacts:
                    artifact_store.delete(artifact.storage_key)
                assessment = db.get(Assessment, assessment_id)
                if assessment:
                    db.delete(assessment)
            db.flush()
            for user_id in [cls.owner_id, *cls.created_user_ids]:
                user = db.get(User, user_id)
                if user:
                    db.delete(user)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @classmethod
    def wait_for_job(cls, job_id: str, timeout: float = 180) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = cls.client.get(f"/api/v1/jobs/{job_id}")
            if response.status_code != 200:
                raise AssertionError(response.text)
            job = response.json()
            if job["status"] == "succeeded":
                return
            if job["status"] in {"failed", "cancelled"}:
                raise AssertionError(f"Compose worker ended job as {job['status']}: {job.get('error_code')}")
            time.sleep(0.5)
        raise AssertionError(f"Compose worker did not finish job {job_id} within {timeout} seconds")

    def test_assessment_pdf_manual_review_final_snapshot_and_excel(self):
        client = self.client
        assessment = client.post("/api/v1/assessments", json={"title":"Ujian Sintetis","course_label":"Fixture","language":"id"})
        self.assertEqual(assessment.status_code,201,assessment.text)
        assessment_data = assessment.json()
        self.assessment_ids.append(assessment_data["id"])
        revision = assessment_data["revision"]
        levels = [str(i/10).rstrip("0").rstrip(".") if i else "0" for i in range(11)]
        anchors = {level: ("Tidak ada" if level == "0" else "Lengkap" if level == "1" else f"Parsial {level}") for level in levels}
        questions = []
        for index, (label, weight) in enumerate(zip(("1","2","3"),("20","30","50")), start=1):
            questions.append({"stable_question_id":f"q{index}","label":label,"order":index,
                "text":f"Jelaskan konsep sintetis {index}.","answer_type":"short_text","weight":weight,
                "reference_answer":f"Konsep {index}.","alternatives":[],"criteria":[{"id":"concept",
                "description":"Konsep inti sesuai jawaban acuan","max_points":"10","credit_levels":levels,"anchors":anchors}]})
        saved = client.put(f"/api/v1/assessment-revisions/{revision['id']}/questions", json={"expected_version":1,"questions":questions})
        self.assertEqual(saved.status_code,200,saved.text)
        revision_version=saved.json()["version"]
        approved=client.post(f"/api/v1/assessment-revisions/{revision['id']}/approve",json={"expected_version":revision_version,"confirmation":True})
        self.assertEqual(approved.status_code,200,approved.text)
        submission=client.post(f"/api/v1/assessments/{assessment_data['id']}/submissions",json={"external_student_id":"0012345678","display_name":"Mahasiswa Sintetis","attempt_no":1})
        self.assertEqual(submission.status_code,201,submission.text)
        submission_id=submission.json()["id"]
        upload=client.post(f"/api/v1/submissions/{submission_id}/documents",data={"auto_process":"false"},files={"file":("synthetic.pdf",one_page_pdf(),"application/pdf")})
        self.assertEqual(upload.status_code,202,upload.text)
        document_id=upload.json()["document_id"]
        if EXTERNAL_COMPOSE:
            self.wait_for_job(upload.json()["job"]["id"])
            document_state = client.get(f"/api/v1/documents/{document_id}").json()
            self.assertEqual(document_state["validation_status"], "valid")
        else:
            self.assertEqual(upload.json()["validation_status"],"valid")
        current=client.get(f"/api/v1/submissions/{submission_id}").json()
        self.assertEqual(current["pipeline_jobs"][0]["id"],upload.json()["job"]["id"])
        self.assertEqual(current["pipeline_jobs"][0]["status"],"succeeded")
        self.assertEqual(current["pipeline_jobs"][0]["document_id"],document_id)
        identity=client.post(f"/api/v1/submissions/{submission_id}/confirm-identity",json={
            "document_id":document_id,"document_hash":upload.json()["sha256"],"external_student_id":"0012345678",
            "display_name":"Mahasiswa Sintetis","expected_submission_version":current["version"]})
        self.assertEqual(identity.status_code,200,identity.text)
        current=client.get(f"/api/v1/submissions/{submission_id}").json()
        self.assertEqual(current["pages"][0]["page_index"],0)
        credits={"q1":"0.8","q2":"0.6","q3":"0.9"}
        review_id=None
        review_version=1
        for index in range(1,4):
            question_id=f"q{index}"
            page=current["pages"][0]
            region=client.post(f"/api/v1/page-image-revisions/{page['page_image_revision_id']}/regions",json={
                "polygon":[[0.1,0.1],[0.5,0.1],[0.5,0.2],[0.1,0.2]],"region_type":"answer"})
            self.assertEqual(region.status_code,201,region.text)
            from apps.api.asdos_api.models import Answer
            db=SessionLocal()
            try:
                answer=db.scalar(select(Answer).where(Answer.submission_id==submission_id,Answer.stable_question_id==question_id))
                answer_id=answer.id
            finally: db.close()
            mapped=client.post(f"/api/v1/answers/{answer_id}/mapping-revisions",json={"region_ids":[region.json()["id"]],"expected_transcript_revision":0,"expected_mapping_revision_id":None})
            self.assertEqual(mapped.status_code,201,mapped.text)
            text=f"Synthetic answer for question {index}."
            transcript=client.post(f"/api/v1/submissions/{submission_id}/answers/{question_id}/transcription-revisions",json={"literal_text":text,"status":"transcribed","flags":[],"expected_revision":0})
            self.assertEqual(transcript.status_code,201,transcript.text)
            decision=client.put(f"/api/v1/submissions/{submission_id}/review/{question_id}",json={
                "expected_review_id":review_id,"expected_version":review_version,"answer_status":"partially_correct",
                "accepted_criteria":[{"criterion_id":"concept","credit":credits[question_id],"evidence_refs":[{"segment_id":"seg-1","start":0,"end":len(text),"region_id":region.json()["id"]}],"rationale":"Bukti sesuai konsep rubrik.","source":"human"}],"override_raw":None,"reason":None})
            self.assertEqual(decision.status_code,200,decision.text)
            review_id=decision.json()["review_id"]
            review_version=decision.json()["version"]
        finalized=client.post(f"/api/v1/submissions/{submission_id}/finalize",json={"expected_review_id":review_id,"expected_version":review_version})
        self.assertEqual(finalized.status_code,200,finalized.text)
        self.assertEqual(finalized.json()["score"],"79.00")
        exported=client.post(f"/api/v1/assessments/{assessment_data['id']}/exports",json={"mode":"final","submission_ids":[submission_id]})
        self.assertEqual(exported.status_code,201,exported.text)
        workbook=client.get(exported.json()["download_url"])
        self.assertEqual(workbook.status_code,200,workbook.text[:200])
        with zipfile.ZipFile(BytesIO(workbook.content)) as archive:
            import xml.etree.ElementTree as ET
            root=ET.fromstring(archive.read("xl/workbook.xml"))
            ns={"x":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_names={sheet.attrib["name"] for sheet in root.findall("x:sheets/x:sheet",ns)}
            self.assertTrue({"Informasi","Rekap_Nilai","Detail_Nomor","Detail_Kriteria","Transkripsi","Rubrik","Riwayat","Metadata"}.issubset(sheet_names))

        other = TestClient(app)
        try:
            db = SessionLocal()
            try:
                other_user = User(username=self.other_username, display_name="Dosen Lain", password_hash=hash_password(self.other_password), role="owner")
                db.add(other_user)
                db.flush()
                self.created_user_ids.append(other_user.id)
                db.commit()
            finally:
                db.close()
            login = other.post("/api/v1/auth/login", json={"username":self.other_username, "password":self.other_password})
            self.assertEqual(login.status_code, 200, login.text)
            self.assertEqual(other.get(f"/api/v1/submissions/{submission_id}").status_code, 404)
            self.assertEqual(other.get(f"/api/v1/exports/{exported.json()['id']}/download").status_code, 404)
        finally:
            other.close()
        self.assertEqual(assessment_data["title"],"Ujian Sintetis")

    def test_mutations_require_a_csrf_token(self):
        token = self.client.headers.pop("X-CSRF-Token")
        try:
            response = self.client.post("/api/v1/assessments", json={"title":"Blocked", "course_label":"", "language":"id"})
            self.assertEqual(response.status_code, 403)
        finally:
            self.client.headers["X-CSRF-Token"] = token


    def _ai_draft(self):
        created = self.client.post("/api/v1/assessments", json={"title":"AI rubric test", "language":"id"}).json()
        self.assessment_ids.append(created["id"])
        seed = {"stable_question_id":"q1", "label":"1", "order":1, "text":"Jelaskan fungsi RAM.", "weight":"25", "answer_type":"essay"}
        rubric = {"reference_answer":"RAM menyimpan data kerja sementara.", "alternatives":[], "criteria":[{
            "id":"ram", "description":"Fungsi dan volatilitas RAM", "max_points":"10", "credit_levels":["0","0.5","1"],
            "anchors":{"0":"Salah", "0.5":"Sebagian tepat", "1":"Lengkap"}}]}
        return created, seed, rubric

    def _auto_fixture(self, title="Automatic mapping fixture"):
        created, seed, rubric = self._ai_draft()
        rid = created['revision']['id']
        questions=[{**seed,**rubric},{**seed,**rubric,'stable_question_id':'q2','label':'2','order':2,'text':'Jelaskan SSD.'}]
        saved=self.client.put(f'/api/v1/assessment-revisions/{rid}/questions',json={'expected_version':1,'questions':questions}).json()
        self.client.post(f'/api/v1/assessment-revisions/{rid}/approve',json={'expected_version':saved['version'],'confirmation':True})
        sid=self.client.post(f"/api/v1/assessments/{created['id']}/submissions",json={
            'external_student_id':f'SYNTHETIC-{uuid4().hex[:8]}','display_name':title,'attempt_no':1}).json()['id']
        return sid

    @unittest.skipIf(EXTERNAL_COMPOSE,"Synthetic batch uses isolated eager runtime")
    def test_fifty_unidentified_uploads_keep_distinct_documents_and_jobs(self):
        from unittest.mock import patch
        created, seed, rubric = self._ai_draft()
        rid = created['revision']['id']
        saved=self.client.put(f'/api/v1/assessment-revisions/{rid}/questions',json={'expected_version':1,'questions':[{**seed,**rubric}]}).json()
        self.client.post(f'/api/v1/assessment-revisions/{rid}/approve',json={'expected_version':saved['version'],'confirmation':True})
        submissions, documents, jobs = set(), set(), set()
        with patch('apps.api.asdos_api.router_submissions.publish_job_outbox'):
            for _ in range(50):
                made=self.client.post(f"/api/v1/assessments/{created['id']}/submissions/unidentified")
                self.assertEqual(made.status_code,201,made.text)
                sid=made.json()['id']; submissions.add(sid)
                uploaded=self.client.post(f'/api/v1/submissions/{sid}/documents',data={'auto_process':'true','auto_grade':'true'},
                    files={'file':('fixture.pdf',one_page_pdf(),'application/pdf')})
                self.assertEqual(uploaded.status_code,202,uploaded.text)
                documents.add(uploaded.json()['document_id']);jobs.add(uploaded.json()['job']['id'])
                state=self.client.get(f'/api/v1/submissions/{sid}').json()
                self.assertEqual(state['claimed_identity'],{'external_student_id':'','display_name':''})
                self.assertEqual(state['identity_status'],'pending')
        self.assertEqual((len(submissions),len(documents),len(jobs)),(50,50,50))

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses isolated eager runtime")
    def test_batch_identity_is_unconfirmed_and_grade_waits_for_human_mapping(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.auto_mapping import LocatedPage
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        created,seed,rubric=self._ai_draft();rid=created['revision']['id']
        saved=self.client.put(f'/api/v1/assessment-revisions/{rid}/questions',json={'expected_version':1,'questions':[{**seed,**rubric}]}).json()
        self.client.post(f'/api/v1/assessment-revisions/{rid}/approve',json={'expected_version':saved['version'],'confirmation':True})
        sid=self.client.post(f"/api/v1/assessments/{created['id']}/submissions/unidentified").json()['id']
        located=LocatedPage.model_validate({'regions':[{'label':'1','bbox':[10,100,990,400],'continuation':False,'flags':[]}],'flags':[]})
        provenance=SimpleNamespace(device='explicit-fake',checkpoint_sha256='0'*64)
        text='RAM menyimpan data sementara.'
        proposal={'schema_version':'grade-proposal.v1','question_id':'q1','status':'proposed','flags':[],
            'criteria':[{'criterion_id':'ram','credit':'0','label':'not_met','evidence_refs':[],'rationale':'Synthetic'}]}
        with patch('apps.worker.auto_answers.qwen_adapter.propose_identity',return_value=({'name':'Test Student','student_id':'0000123'},provenance)), \
             patch('apps.worker.auto_answers.qwen_adapter.locate_answers',return_value=(located,provenance)), \
             patch('apps.worker.auto_answers.qwen_adapter.transcribe',return_value=([TranscriptSegment(text)],provenance)), \
             patch('apps.worker.tasks.qwen_adapter.grade',return_value=(proposal,provenance)) as grade:
            upload=self.client.post(f'/api/v1/submissions/{sid}/documents',data={'auto_process':'true','auto_grade':'true'},
                files={'file':('fixture.pdf',one_page_pdf(),'application/pdf')}).json()
            state=self.client.get(f'/api/v1/submissions/{sid}').json()
            self.assertEqual(state['claimed_identity'],{'external_student_id':'0000123','display_name':'Test Student'})
            self.assertEqual(state['identity_status'],'pending');grade.assert_not_called()
            confirmed=self.client.post(f'/api/v1/submissions/{sid}/confirm-identity',json={'document_id':upload['document_id'],
                'document_hash':upload['sha256'],'external_student_id':'0000123','display_name':'Test Student','expected_submission_version':state['version']})
            self.assertEqual(confirmed.status_code,200,confirmed.text);grade.assert_not_called()
            state=self.client.get(f'/api/v1/submissions/{sid}').json()
            mapping=self.client.post(f'/api/v1/submissions/{sid}/confirm-mapping',json={'expected_layout_revision_id':state['document']['layout_revision_id'],
                'expected_submission_version':state['version'],'mapping_revision_ids':[state['answers'][0]['mapping_revision_id']]})
            self.assertEqual(mapping.status_code,200,mapping.text);grade.assert_called_once()
            state=self.client.get(f'/api/v1/submissions/{sid}').json()
            self.assertIsNotNone(state['answers'][0]['proposal_id']);self.assertIsNone(state['final_snapshot'])

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses isolated eager runtime")
    def test_failed_identity_ocr_does_not_guess_or_stop_answer_processing(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.auto_mapping import LocatedPage
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        created,seed,rubric=self._ai_draft();rid=created['revision']['id']
        saved=self.client.put(f'/api/v1/assessment-revisions/{rid}/questions',json={'expected_version':1,'questions':[{**seed,**rubric}]}).json()
        self.client.post(f'/api/v1/assessment-revisions/{rid}/approve',json={'expected_version':saved['version'],'confirmation':True})
        sid=self.client.post(f"/api/v1/assessments/{created['id']}/submissions/unidentified").json()['id']
        located=LocatedPage.model_validate({'regions':[{'label':'1','bbox':[10,100,990,400],'continuation':False,'flags':[]}],'flags':[]})
        provenance=SimpleNamespace(device='explicit-fake',checkpoint_sha256='0'*64)
        with patch('apps.worker.auto_answers.qwen_adapter.propose_identity',side_effect=ValueError('invalid identity')), \
             patch('apps.worker.auto_answers.qwen_adapter.locate_answers',return_value=(located,provenance)), \
             patch('apps.worker.auto_answers.qwen_adapter.transcribe',return_value=([TranscriptSegment('Jawaban uji')],provenance)):
            upload=self.client.post(f'/api/v1/submissions/{sid}/documents',data={'auto_grade':'true'},
                files={'file':('fixture.pdf',one_page_pdf(),'application/pdf')})
        self.assertEqual(upload.status_code,202,upload.text)
        state=self.client.get(f'/api/v1/submissions/{sid}').json()
        self.assertEqual(state['identity_status'],'pending')
        self.assertEqual(state['claimed_identity'],{'external_student_id':'','display_name':''})
        self.assertEqual(state['answers'][0]['transcript'],'Jawaban uji')

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses isolated eager runtime")
    def test_batch_manual_mapping_schedules_grade_after_reusing_ocr(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.auto_mapping import LocatedPage
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        created,seed,rubric=self._ai_draft();rid=created['revision']['id']
        saved=self.client.put(f'/api/v1/assessment-revisions/{rid}/questions',json={'expected_version':1,'questions':[{**seed,**rubric}]}).json()
        self.client.post(f'/api/v1/assessment-revisions/{rid}/approve',json={'expected_version':saved['version'],'confirmation':True})
        sid=self.client.post(f"/api/v1/assessments/{created['id']}/submissions/unidentified").json()['id']
        located=LocatedPage.model_validate({'regions':[{'label':None,'bbox':[10,100,990,400],'continuation':False,'flags':['uncertain_number']}],'flags':[]})
        provenance=SimpleNamespace(device='explicit-fake',checkpoint_sha256='0'*64)
        proposal={'schema_version':'grade-proposal.v1','question_id':'q1','status':'proposed','flags':[],
            'criteria':[{'criterion_id':'ram','credit':'0','label':'not_met','evidence_refs':[],'rationale':'Synthetic'}]}
        with patch('apps.worker.auto_answers.qwen_adapter.propose_identity',return_value=({'name':'Fixture','student_id':'00009'},provenance)), \
             patch('apps.worker.auto_answers.qwen_adapter.locate_answers',return_value=(located,provenance)), \
             patch('apps.worker.auto_answers.qwen_adapter.transcribe',return_value=([TranscriptSegment('Jawaban uji')],provenance)), \
             patch('apps.worker.tasks.qwen_adapter.grade',return_value=(proposal,provenance)) as grade:
            upload=self.client.post(f'/api/v1/submissions/{sid}/documents',data={'auto_grade':'true'},files={'file':('fixture.pdf',one_page_pdf(),'application/pdf')}).json()
            state=self.client.get(f'/api/v1/submissions/{sid}').json()
            self.client.post(f'/api/v1/submissions/{sid}/confirm-identity',json={'document_id':upload['document_id'],
                'document_hash':upload['sha256'],'external_student_id':'00009','display_name':'Fixture','expected_submission_version':state['version']})
            state=self.client.get(f'/api/v1/submissions/{sid}').json();answer=state['answers'][0]
            result=self.client.post(f"/api/v1/answers/{answer['id']}/mapping-revisions",json={'region_ids':state['unassigned_region_ids'],
                'expected_transcript_revision':answer['transcript_revision_no'],'expected_mapping_revision_id':answer['mapping_revision_id']})
            self.assertEqual(result.status_code,201,result.text);self.assertTrue(result.json()['reused_ocr'])
            grade.assert_called_once()
            state=self.client.get(f'/api/v1/submissions/{sid}').json()
            self.assertIsNotNone(state['answers'][0]['proposal_id']);self.assertIsNone(state['final_snapshot'])
            # A freshly drawn region needs a new OCR job; its completion queues the new proposal too.
            answer=state['answers'][0]
            region=self.client.post(f"/api/v1/page-image-revisions/{state['pages'][0]['page_image_revision_id']}/regions",
                json={'polygon':[[.1,.5],[.8,.5],[.8,.8],[.1,.8]]}).json()
            changed=self.client.post(f"/api/v1/answers/{answer['id']}/mapping-revisions",json={'region_ids':[region['id']],
                'expected_transcript_revision':answer['transcript_revision_no'],'expected_mapping_revision_id':answer['mapping_revision_id']})
            self.assertFalse(changed.json()['reused_ocr']);self.assertEqual(grade.call_count,1)
            ocr=self.client.post(f'/api/v1/submissions/{sid}/answers/q1/transcribe')
            self.assertEqual(ocr.json()['status'],'succeeded',ocr.text)
            self.assertEqual(grade.call_count,2)

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses the eager synthetic test runtime")
    def test_upload_automatically_reads_maps_and_retains_unknown_regions_for_review(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.auto_mapping import LocatedPage
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        from apps.worker.auto_answers import analyze_answers
        sid=self._auto_fixture()
        located=LocatedPage.model_validate({'regions':[
            {'label':'2','bbox':[10,100,990,250],'continuation':False,'flags':[]},
            {'label':'1','bbox':[10,300,990,450],'continuation':False,'flags':[]},
            {'label':'9','bbox':[10,500,990,650],'continuation':False,'flags':[]}],'flags':[]})
        provenance=SimpleNamespace(device='explicit-test-fake',checkpoint_sha256='0'*64)
        with patch('apps.worker.auto_answers.qwen_adapter.locate_answers',return_value=(located,provenance)) as locator, patch(
            'apps.worker.auto_answers.qwen_adapter.transcribe',side_effect=[([TranscriptSegment(t)],provenance) for t in ['SSD literal','RAM literal','Area tambahan literal']]) as ocr:
            uploaded=self.client.post(f'/api/v1/submissions/{sid}/documents',files={'file':('synthetic.pdf',one_page_pdf(),'application/pdf')})
            self.assertEqual(uploaded.status_code,202,uploaded.text)
            current=self.client.get(f'/api/v1/submissions/{sid}').json()
            jobs=current['pipeline_jobs']; automatic=next(j for j in jobs if j['kind']=='analyze_answers')
            self.assertEqual(automatic['status'],'succeeded',automatic)
            self.assertEqual(current['identity_status'],'pending')
            by_q={a['question_id']:a for a in current['answers']}
            self.assertEqual(by_q['q1']['transcript'],'RAM literal')
            self.assertEqual(by_q['q2']['transcript'],'SSD literal')
            self.assertTrue(all(a['mapping_status']=='auto_mapped' for a in by_q.values()))
            self.assertEqual(len(current['unassigned_region_ids']),1)
            self.assertEqual(locator.call_count,1);self.assertEqual(ocr.call_count,3)
            self.assertEqual(analyze_answers.run(automatic['id'])['status'],'skipped')
            self.assertEqual(locator.call_count,1)
            confirmation={'expected_layout_revision_id':current['document']['layout_revision_id'],
                'expected_submission_version':current['version'],'mapping_revision_ids':[a['mapping_revision_id'] for a in current['answers']]}
            self.assertEqual(self.client.post(f'/api/v1/submissions/{sid}/confirm-mapping',json=confirmation).status_code,409)
            self.client.post(f'/api/v1/submissions/{sid}/confirm-identity',json={'document_id':current['document']['id'],
                'document_hash':current['document']['sha256'],'external_student_id':'SYNTHETIC-AUTO-001',
                'display_name':'Synthetic automatic test','expected_submission_version':current['version']})
            denied=self.client.post(f'/api/v1/submissions/{sid}/answers/q1/propose')
            self.assertEqual(denied.json()['error']['code'],'AUTO_MAPPING_REVIEW_REQUIRED')
            current=self.client.get(f'/api/v1/submissions/{sid}').json();confirmation['expected_submission_version']=current['version']
            self.assertEqual(self.client.post(f'/api/v1/submissions/{sid}/confirm-mapping',json=confirmation).status_code,200)
            current=self.client.get(f'/api/v1/submissions/{sid}').json();answer=next(a for a in current['answers'] if a['question_id']=='q1')
            unknown=current['unassigned_region_ids'][0]
            mapped=self.client.post(f"/api/v1/answers/{answer['id']}/mapping-revisions",json={'region_ids':[unknown],
                'expected_transcript_revision':answer['transcript_revision_no'],'expected_mapping_revision_id':answer['mapping_revision_id']})
            self.assertEqual(mapped.status_code,201,mapped.text);self.assertTrue(mapped.json()['reused_ocr'])
            current=self.client.get(f'/api/v1/submissions/{sid}').json()
            self.assertEqual(next(a for a in current['answers'] if a['question_id']=='q1')['transcript'],'Area tambahan literal')
            self.assertEqual(ocr.call_count,3)
            # Empty mapping revisions make a wrong assignment correctable without deleting OCR.
            second=next(a for a in current['answers'] if a['question_id']=='q2')
            cleared=self.client.post(f"/api/v1/answers/{second['id']}/mapping-revisions",json={'region_ids':[],
                'expected_transcript_revision':second['transcript_revision_no'],'expected_mapping_revision_id':second['mapping_revision_id']})
            self.assertEqual(cleared.status_code,201,cleared.text)
            cleared_state=self.client.get(f'/api/v1/submissions/{sid}').json()
            empty=next(a for a in cleared_state['answers'] if a['question_id']=='q2')
            self.assertEqual(empty['mapping_status'],'unmapped');self.assertFalse(empty['transcript'])
            rejected=self.client.post(f'/api/v1/submissions/{sid}/answers/q2/transcribe')
            self.assertEqual(rejected.status_code,409,rejected.text)
            self.assertEqual(rejected.json()['error']['code'],'ANSWER_MAPPING_REQUIRED')
            restored=self.client.post(f"/api/v1/answers/{second['id']}/mapping-revisions",json={'region_ids':second['region_ids'],
                'expected_transcript_revision':empty['transcript_revision_no'],'expected_mapping_revision_id':empty['mapping_revision_id']})
            self.assertEqual(restored.status_code,201,restored.text)
            self.assertTrue(restored.json()['reused_ocr']);self.assertEqual(ocr.call_count,3)
            current=self.client.get(f'/api/v1/submissions/{sid}').json()
        # Human review cannot silently discard the area displaced by a mapping correction.
        review=None
        for question_id in ['q1','q2']:
            body={'expected_review_id':review['review_id'] if review else None,'expected_version':review['version'] if review else 1,
                  'answer_status':'reviewed','accepted_criteria':None,'override_raw':'10','reason':'Synthetic manual test decision'}
            response=self.client.put(f'/api/v1/submissions/{sid}/review/{question_id}',json=body)
            self.assertEqual(response.status_code,200,response.text);review=response.json()
            if question_id == 'q1':
                early=self.client.post(f'/api/v1/submissions/{sid}/finalize',json={
                    'expected_review_id':review['review_id'],'expected_version':review['version']})
                self.assertEqual(early.status_code,409,early.text)
                blockers=early.json()['error']['details']['blockers']
                self.assertIn('2:needs_review',blockers)
                self.assertNotIn('2:missing_answer',blockers)
        final_body={'expected_review_id':review['review_id'],'expected_version':review['version']}
        blocked=self.client.post(f'/api/v1/submissions/{sid}/finalize',json=final_body)
        self.assertEqual(blocked.status_code,409)
        self.assertIn('unassigned',blocked.text)
        leftover=current['unassigned_region_ids'][0]
        excluded=self.client.post(f'/api/v1/regions/{leftover}/mapping-exclusion',json={'excluded':True,
            'reason':'Synthetic fixture area intentionally excluded after inspection',
            'expected_layout_revision_id':current['document']['layout_revision_id']})
        self.assertEqual(excluded.status_code,200,excluded.text)
        final=self.client.post(f'/api/v1/submissions/{sid}/finalize',json=final_body)
        self.assertEqual(final.status_code,200,final.text)
        # Replacing the PDF must never show the old document's mapping or OCR as current.
        replacement=self.client.post(f'/api/v1/submissions/{sid}/documents',data={'auto_process':'false'},
            files={'file':('replacement.pdf',one_page_pdf(),'application/pdf')})
        self.assertEqual(replacement.status_code,202)
        changed=self.client.get(f'/api/v1/submissions/{sid}').json()
        self.assertTrue(all(a['mapping_revision_id'] is None and not a['transcript'] for a in changed['answers']))
        self.assertEqual(changed['identity_status'],'pending')

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses the eager synthetic test runtime")
    def test_automatic_mapping_rejects_stale_input_and_keeps_manual_work(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.auto_mapping import LocatedPage
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        from apps.api.asdos_api.models import Document, Page, PageImageRevision, Region
        sid=self._auto_fixture()
        provenance=SimpleNamespace(device='explicit-test-fake',checkpoint_sha256='0'*64)
        def locate(*args):
            with SessionLocal.begin() as db:
                image=db.scalar(select(PageImageRevision).join(Page,Page.id==PageImageRevision.page_id).join(
                    Document,
                    Document.id==Page.document_id).where(
                    Document.submission_id==sid))
                db.add(Region(page_image_revision_id=image.id,polygon=[[0,0],[.2,0],[.2,.2],[0,.2]],region_type='answer',created_by=self.owner_id))
            return LocatedPage.model_validate({'regions':[{'label':'1','bbox':[10,300,990,450],'continuation':False,'flags':[]}],'flags':[]}),provenance
        with patch('apps.worker.auto_answers.qwen_adapter.locate_answers',side_effect=locate),patch(
            'apps.worker.auto_answers.qwen_adapter.transcribe',return_value=([TranscriptSegment('Model draft')],provenance)):
            self.client.post(f'/api/v1/submissions/{sid}/documents',files={'file':('synthetic.pdf',one_page_pdf(),'application/pdf')})
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        job=next(j for j in current['pipeline_jobs'] if j['kind']=='analyze_answers')
        self.assertEqual(job['error_code'],'STALE_AUTO_MAPPING_INPUT',job)
        self.assertEqual(current['document']['status'],'valid')
        self.assertEqual(len(current['pages'][0]['regions']),1)
        self.assertTrue(all(not a['mapping_revision_id'] and not a['transcript'] for a in current['answers']))

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses the eager synthetic test runtime")
    def test_cancelled_auto_analysis_does_not_promote_partial_regions(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.auto_mapping import LocatedPage
        from apps.api.asdos_api.models import PipelineJob
        sid=self._auto_fixture()
        def cancelled(*args):
            with SessionLocal.begin() as db:
                job=db.scalar(select(PipelineJob).where(PipelineJob.submission_id==sid,PipelineJob.kind=='analyze_answers'))
                job.cancel_requested=True
            return LocatedPage.model_validate({'regions':[{'label':'1','bbox':[10,100,990,200],
                'continuation':False,'flags':[]}],'flags':[]}),SimpleNamespace(device='explicit-fake',checkpoint_sha256='0'*64)
        with patch('apps.worker.auto_answers.qwen_adapter.locate_answers',side_effect=cancelled),patch(
                'apps.worker.auto_answers.qwen_adapter.transcribe') as transcribe:
            self.client.post(f'/api/v1/submissions/{sid}/documents',files={'file':('synthetic.pdf',one_page_pdf(),'application/pdf')})
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        automatic=next(j for j in current['pipeline_jobs'] if j['kind']=='analyze_answers')
        self.assertEqual(automatic['status'],'cancelled',automatic)
        self.assertFalse(current['pages'][0]['regions'])
        self.assertTrue(all(not a['mapping_revision_id'] for a in current['answers']))
        transcribe.assert_not_called()

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses the eager synthetic test runtime")
    def test_repaired_detection_keeps_text_for_review_without_auto_mapping(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.auto_mapping import LocatedPage
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        sid=self._auto_fixture()
        result=LocatedPage.model_validate({'regions':[{'label':'1','bbox':[10,100,990,400],
            'continuation':False,'flags':[]}],'flags':['localization_repair_review']})
        provenance=SimpleNamespace(device='explicit-fake',checkpoint_sha256='0'*64)
        with patch('apps.worker.auto_answers.qwen_adapter.locate_answers',return_value=(result,provenance)), patch(
            'apps.worker.auto_answers.qwen_adapter.transcribe',return_value=([TranscriptSegment('Jawaban sintetis')],provenance)):
            self.client.post(f'/api/v1/submissions/{sid}/documents',files={'file':('synthetic.pdf',one_page_pdf(),'application/pdf')})
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        self.assertEqual(len(current['unassigned_region_ids']),1)
        region=current['pages'][0]['regions'][0]
        self.assertEqual(region['analysis']['text'],'Jawaban sintetis')
        self.assertIn('localization_repair_review',region['analysis']['mapping_flags'])
        self.assertTrue(all(not answer['mapping_revision_id'] for answer in current['answers']))

    @unittest.skipIf(EXTERNAL_COMPOSE,"Fake model contract uses the eager synthetic test runtime")
    def test_missing_model_does_not_turn_successful_render_into_a_failed_upload(self):
        from unittest.mock import patch
        from apps.api.asdos_api.model_adapters import ModelUnavailable
        sid=self._auto_fixture()
        with patch('apps.worker.auto_answers.qwen_adapter.locate_answers',side_effect=ModelUnavailable('MODEL_UNAVAILABLE','Explicit fixture')):
            upload=self.client.post(f'/api/v1/submissions/{sid}/documents',files={'file':('synthetic.pdf',one_page_pdf(),'application/pdf')})
        self.assertEqual(upload.status_code,202,upload.text)
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        self.assertEqual(current['document']['status'],'valid')
        automatic=next(j for j in current['pipeline_jobs'] if j['kind']=='analyze_answers')
        self.assertEqual(automatic['error_code'],'MODEL_UNAVAILABLE')
        self.assertFalse(current['pages'][0]['regions'])
        self.assertTrue(all(not a['transcript_revision_id'] for a in current['answers']))

    def test_submission_restores_latest_jobs_only_for_active_document(self):
        from apps.api.asdos_api.models import Answer, Document, PipelineJob, now_utc
        from datetime import timedelta
        created, seed, rubric = self._ai_draft()
        rid = created['revision']['id']
        saved = self.client.put(f'/api/v1/assessment-revisions/{rid}/questions',json={
            'expected_version':1,'questions':[{**seed,**rubric}]}).json()
        approved = self.client.post(f'/api/v1/assessment-revisions/{rid}/approve',json={
            'expected_version':saved['version'],'confirmation':True})
        self.assertEqual(approved.status_code,200,approved.text)
        sid = self.client.post(f"/api/v1/assessments/{created['id']}/submissions",json={
            'external_student_id':'SYNTHETIC-PROGRESS','display_name':'Progress fixture','attempt_no':1}).json()['id']
        upload = self.client.post(f'/api/v1/submissions/{sid}/documents',data={"auto_process":"false"},files={
            'file':('synthetic.pdf',one_page_pdf(),'application/pdf')}).json()
        if EXTERNAL_COMPOSE:
            self.wait_for_job(upload['job']['id'])
        with SessionLocal.begin() as db:
            answer = db.scalar(select(Answer).where(Answer.submission_id==sid))
            earlier = now_utc() - timedelta(minutes=2)
            for attempt,status in [(1,'failed'),(2,'running')]:
                db.add(PipelineJob(assessment_id=created['id'],submission_id=sid,answer_id=answer.id,
                    document_id=upload['document_id'],kind='transcribe_answer',stage='transcribe_answer',
                    input_fingerprint='c'*64,attempt=attempt,status=status,
                    created_at=earlier+timedelta(seconds=attempt),progress_current=0,progress_total=1))
            old_doc = Document(assessment_id=created['id'],submission_id=sid,kind='student_answer',
                storage_key='synthetic-old-private',sha256='d'*64,byte_size=1,original_filename='old.pdf')
            db.add(old_doc); db.flush()
            db.add(PipelineJob(assessment_id=created['id'],submission_id=sid,document_id=old_doc.id,
                kind='document_render',stage='document_render',input_fingerprint='e'*64,status='failed'))
        detail = self.client.get(f'/api/v1/submissions/{sid}').json()
        jobs = detail['pipeline_jobs']
        self.assertEqual(len(jobs),2)
        ocr = next(j for j in jobs if j['kind']=='transcribe_answer')
        self.assertEqual((ocr['status'],ocr['attempt']),('running',2))
        self.assertEqual(ocr['progress'],{'completed':0,'total':1,'unit':'answers'})
        self.assertTrue(all(j['document_id']==upload['document_id'] for j in jobs))

    def _fake_generate(self, created, seed, rubric):
        from unittest.mock import patch
        from types import SimpleNamespace
        with patch("apps.api.asdos_api.model_adapters.model_status", return_value={"available":True}), patch(
                "apps.worker.tasks.qwen_adapter.generate_rubrics", return_value=([rubric], SimpleNamespace(device="test-fake", checkpoint_sha256="0"*64))):
            response = self.client.post(f"/api/v1/assessment-revisions/{created['revision']['id']}/generate-rubric",
                json={"expected_version":1,"questions":[seed]})
        self.assertEqual(response.status_code,202,response.text)
        return response.json()

    def test_only_questions_and_weights_generate_a_reviewable_draft(self):
        created, seed, rubric = self._ai_draft()
        result = self._fake_generate(created,seed,rubric)
        self.assertEqual(result["status"],"succeeded",result)
        revision = self.client.get(f"/api/v1/assessment-revisions/{created['revision']['id']}").json()
        self.assertEqual(revision["status"],"draft")
        self.assertEqual(revision["questions"][0]["weight"],"25.0000")
        self.assertEqual(revision["questions"][0]["reference_answer"],rubric["reference_answer"])
        approved = self.client.post(f"/api/v1/assessment-revisions/{revision['id']}/approve",json={"expected_version":revision['version'],"confirmation":True})
        self.assertEqual(approved.status_code,200,approved.text)
        attempt = self.client.put(f"/api/v1/assessment-revisions/{revision['id']}/question-seeds",json={"expected_version":revision['version'],"questions":[seed]})
        self.assertEqual(attempt.status_code,409)

    def test_incomplete_draft_cannot_be_approved_and_missing_model_does_not_mutate(self):
        from unittest.mock import patch
        created,seed,_ = self._ai_draft()
        path = f"/api/v1/assessment-revisions/{created['revision']['id']}"
        saved = self.client.put(path+"/question-seeds",json={"expected_version":1,"questions":[seed]})
        self.assertEqual(saved.status_code,200,saved.text)
        before=self.client.get(path).json()
        self.assertEqual(self.client.post(path+"/approve",json={"expected_version":before['version']}).status_code,409)
        with patch("apps.api.asdos_api.model_adapters.model_status",return_value={"available":False}):
            response=self.client.post(path+"/generate-rubric",json={"expected_version":before['version'],"questions":[{**seed,"text":"Changed"}]})
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(self.client.get(path).json(),before)

    def test_invalid_generated_output_never_becomes_an_approved_rubric(self):
        created,seed,_ = self._ai_draft()
        result=self._fake_generate(created,seed,{"reference_answer":"bad","criteria":[]})
        self.assertEqual(result['status'],'failed',result)
        self.assertEqual(result['error_code'],'RUBRIC_GENERATION_INVALID')
        from apps.worker.tasks import generate_rubric
        from unittest.mock import patch
        with patch('apps.worker.tasks.qwen_adapter.generate_rubrics') as model:
            self.assertEqual(generate_rubric.run(result['job_id'])['status'],'skipped')
            model.assert_not_called()

        revision=self.client.get(f"/api/v1/assessment-revisions/{created['revision']['id']}").json()
        self.assertEqual(revision['status'],'draft')
        self.assertEqual(revision['questions'][0]['reference_answer'],'')

    def test_stale_generation_cannot_overwrite_new_question_edits(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        created,seed,rubric=self._ai_draft()
        path=f"/api/v1/assessment-revisions/{created['revision']['id']}"
        def model_response(*args):
            current=self.client.get(path).json()
            changed=self.client.put(path+'/question-seeds',json={'expected_version':current['version'],'questions':[{**seed,'text':'New question after generation started'}]})
            self.assertEqual(changed.status_code,200,changed.text)
            return [rubric],SimpleNamespace(device='test-fake',checkpoint_sha256='0'*64)
        with patch('apps.api.asdos_api.model_adapters.model_status',return_value={'available':True}), patch('apps.worker.tasks.qwen_adapter.generate_rubrics',side_effect=model_response):
            response=self.client.post(path+'/generate-rubric',json={'expected_version':1,'questions':[seed]})
        self.assertEqual(response.json()['error_code'],'STALE_RUBRIC_INPUT',response.text)
        revision=self.client.get(path).json()
        self.assertEqual(revision['questions'][0]['text'],'New question after generation started')
        self.assertEqual(revision['questions'][0]['reference_answer'],'')

    def test_unreadable_model_output_blocks_proposal_and_finalization(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        created,seed,rubric=self._ai_draft()
        self._fake_generate(created,seed,rubric)
        path=f"/api/v1/assessment-revisions/{created['revision']['id']}"
        revision=self.client.get(path).json()
        self.client.post(path+'/approve',json={'expected_version':revision['version']})
        sub=self.client.post(f"/api/v1/assessments/{created['id']}/submissions",json={'external_student_id':'SYNTHETIC-001','display_name':'Fixture','attempt_no':1}).json()
        sid=sub['id']
        upload=self.client.post(f'/api/v1/submissions/{sid}/documents',data={"auto_process":"false"},files={'file':('synthetic.pdf',one_page_pdf(),'application/pdf')}).json()
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        self.assertEqual(current['identity_status'],'pending')
        self.client.post(f'/api/v1/submissions/{sid}/confirm-identity',json={'document_id':upload['document_id'],'document_hash':upload['sha256'],'external_student_id':'SYNTHETIC-001','display_name':'Fixture','expected_submission_version':current['version']})
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        region=self.client.post(f"/api/v1/page-image-revisions/{current['pages'][0]['page_image_revision_id']}/regions",json={'polygon':[[.1,.1],[.8,.1],[.8,.8],[.1,.8]]}).json()
        answer=current['answers'][0]
        self.client.post(f"/api/v1/answers/{answer['id']}/mapping-revisions",json={'region_ids':[region['id']],'expected_transcript_revision':0})
        provenance=SimpleNamespace(device='test-fake',checkpoint_sha256='0'*64)
        with patch('apps.worker.tasks.qwen_adapter.transcribe',return_value=([TranscriptSegment('[tidak terbaca]',flags=('unreadable_text',))],provenance)):
            response=self.client.post(f'/api/v1/submissions/{sid}/answers/q1/transcribe')
        self.assertEqual(response.json()['status'],'succeeded',response.text)
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        self.assertEqual(current['answers'][0]['transcript_status'],'unreadable')
        self.assertEqual(self.client.post(f'/api/v1/submissions/{sid}/answers/q1/propose').status_code,409)
        wrong_review=self.client.put(f'/api/v1/submissions/{sid}/review/q1',json={'expected_review_id':None,'expected_version':1,'answer_status':'incorrect','accepted_criteria':[{'criterion_id':'ram','credit':'0','evidence_refs':[],'rationale':'No answer'}]})
        self.assertEqual(wrong_review.status_code,409,wrong_review.text)

        review=self.client.put(f'/api/v1/submissions/{sid}/review/q1',json={'expected_review_id':None,'expected_version':1,'answer_status':'unreadable','reason':'Tulisan fixture tidak terbaca'}).json()
        final=self.client.post(f'/api/v1/submissions/{sid}/finalize',json={'expected_review_id':review['review_id'],'expected_version':review['version']})
        self.assertEqual(final.status_code,409,final.text)


    def test_cancelling_generation_keeps_draft_unapproved(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        created,seed,rubric=self._ai_draft()
        def cancel_during_generation(*args):
            from apps.api.asdos_api.models import PipelineJob
            with SessionLocal() as db:
                job=db.scalar(select(PipelineJob).where(PipelineJob.assessment_id==created['id'],PipelineJob.kind=='rubric_generate'))
                job_id=job.id
            cancelled=self.client.post(f'/api/v1/jobs/{job_id}/cancel')
            self.assertEqual(cancelled.status_code,202,cancelled.text)
            return [rubric],SimpleNamespace(device='test-fake',checkpoint_sha256='0'*64)
        with patch('apps.api.asdos_api.model_adapters.model_status',return_value={'available':True}), patch('apps.worker.tasks.qwen_adapter.generate_rubrics',side_effect=cancel_during_generation):
            result=self.client.post(f"/api/v1/assessment-revisions/{created['revision']['id']}/generate-rubric",json={'expected_version':1,'questions':[seed]})
        self.assertEqual(result.json()['status'],'cancelled',result.text)
        revision=self.client.get(f"/api/v1/assessment-revisions/{created['revision']['id']}").json()
        self.assertEqual(revision['status'],'draft')
        self.assertEqual(revision['questions'][0]['reference_answer'],'')

    def test_weight_only_input_rejects_invalid_decimal_values(self):
        created,seed,_=self._ai_draft()
        path=f"/api/v1/assessment-revisions/{created['revision']['id']}/question-seeds"
        for value in ['NaN','Infinity','0','-1','100000000','1.00001']:
            result=self.client.put(path,json={'expected_version':1,'questions':[{**seed,'weight':value}]})
            self.assertEqual(result.status_code,422,(value,result.text))


    def test_weight_only_ai_draft_to_review_to_excel_with_explicit_fake_model(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from apps.api.asdos_api.model_adapters import TranscriptSegment
        from openpyxl import load_workbook
        created,seed,rubric=self._ai_draft()
        self._fake_generate(created,seed,rubric)
        revision=self.client.get(f"/api/v1/assessment-revisions/{created['revision']['id']}").json()
        response=self.client.post(f"/api/v1/assessment-revisions/{revision['id']}/approve",json={'expected_version':revision['version']})
        self.assertEqual(response.status_code,200,response.text)
        sid=self.client.post(f"/api/v1/assessments/{created['id']}/submissions",json={'external_student_id':'0012345678','display_name':'Synthetic AI path'}).json()['id']
        upload=self.client.post(f'/api/v1/submissions/{sid}/documents',data={"auto_process":"false"},files={'file':('synthetic.pdf',one_page_pdf(),'application/pdf')}).json()
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        self.assertEqual(current['identity_status'],'pending')
        self.client.post(f'/api/v1/submissions/{sid}/confirm-identity',json={'document_id':upload['document_id'],'document_hash':upload['sha256'],'external_student_id':'0012345678','display_name':'Synthetic AI path','expected_submission_version':current['version']})
        current=self.client.get(f'/api/v1/submissions/{sid}').json()
        region=self.client.post(f"/api/v1/page-image-revisions/{current['pages'][0]['page_image_revision_id']}/regions",json={'polygon':[[.1,.1],[.8,.1],[.8,.8],[.1,.8]]}).json()
        answer=current['answers'][0]
        self.client.post(f"/api/v1/answers/{answer['id']}/mapping-revisions",json={'region_ids':[region['id']],'expected_transcript_revision':0})
        text='RAM menyimpan data sementara.'
        provenance=SimpleNamespace(device='test-fake',checkpoint_sha256='0'*64)
        with patch('apps.worker.tasks.qwen_adapter.transcribe',return_value=([TranscriptSegment(text)],provenance)):
            response=self.client.post(f'/api/v1/submissions/{sid}/answers/q1/transcribe')
        self.assertEqual(response.json()['status'],'succeeded',response.text)
        # Human corrections in legacy and current transcripts do not include page_index.
        answer=self.client.get(f'/api/v1/submissions/{sid}').json()['answers'][0]
        corrected=self.client.post(f'/api/v1/submissions/{sid}/answers/q1/transcription-revisions',json={
            'literal_text':text,'status':'transcribed','flags':[],'expected_revision':answer['transcript_revision_no']})
        self.assertEqual(corrected.status_code,201,corrected.text)
        self.assertNotIn('page_index',corrected.json()['segments'][0])
        refs=[{'segment_id':'seg-1','region_id':region['id'],'start':0,'end':len(text)}]
        proposal={'schema_version':'grade-proposal.v1','question_id':'q1','status':'proposed','flags':[],
                  'criteria':[{'criterion_id':'ram','credit':'1','label':'met','evidence_refs':refs,'rationale':'Fixture concept met'}]}
        # Evidence pointing outside the current mapping is rejected before invoking the model.
        from apps.api.asdos_api.models import PipelineJob, QuestionRevision, TranscriptionRevision
        from apps.api.asdos_api.model_adapters import GRADER_PROMPT_VERSION, MODEL_REVISION
        from apps.api.asdos_api.services import canonical_hash
        with SessionLocal.begin() as db:
            transcript=db.get(TranscriptionRevision,corrected.json()['id'])
            original_segments=transcript.segments
            transcript.segments=[{**original_segments[0],'region_id':'not-a-real-region'}]
            question=db.scalar(select(QuestionRevision).where(QuestionRevision.assessment_revision_id==revision['id']))
            old_fingerprint=canonical_hash({'prompt_version':GRADER_PROMPT_VERSION,'model_revision':MODEL_REVISION,
                'answer_id':answer['id'],'transcript_revision':transcript.id,
                'assessment_revision':revision['id'],'question_id':question.id})
            for attempt in range(1,4):
                db.add(PipelineJob(assessment_id=created['id'],submission_id=sid,answer_id=answer['id'],
                    document_id=upload['document_id'],kind='grade_answer',stage='grade_answer',
                    input_fingerprint=old_fingerprint,attempt=attempt,status='failed',error_code='GRADING_FAILED'))
        with patch('apps.worker.tasks.qwen_adapter.grade') as not_called:
            rejected=self.client.post(f'/api/v1/submissions/{sid}/answers/q1/propose')
        self.assertEqual(rejected.json()['error_code'],'TRANSCRIPT_EVIDENCE_INVALID',rejected.text)
        not_called.assert_not_called()
        with SessionLocal.begin() as db:
            db.get(TranscriptionRevision,corrected.json()['id']).segments=original_segments
        with patch('apps.worker.tasks.qwen_adapter.grade',return_value=(proposal,provenance)) as grader:
            response=self.client.post(f'/api/v1/submissions/{sid}/answers/q1/propose')
        self.assertEqual(response.json()['status'],'succeeded',response.text)
        self.assertEqual(grader.call_args.kwargs['evidence_catalog'][0]['page_index'],0)
        self.assertEqual(grader.call_args.kwargs['evidence_catalog'][0]['region_id'],region['id'])
        review=self.client.put(f'/api/v1/submissions/{sid}/review/q1',json={'expected_review_id':None,'expected_version':1,'answer_status':'correct',
            'accepted_criteria':[{'criterion_id':'ram','credit':'1','evidence_refs':refs,'rationale':'Fixture decision','source':'model_accepted'}]})
        self.assertEqual(review.status_code,200,review.text)
        final=self.client.post(f'/api/v1/submissions/{sid}/finalize',json={'expected_review_id':review.json()['review_id'],'expected_version':review.json()['version']})
        self.assertEqual(final.json()['score'],'100.00',final.text)
        export=self.client.post(f"/api/v1/assessments/{created['id']}/exports",json={'mode':'final','submission_ids':[sid]})
        self.assertEqual(export.status_code,201,export.text)
        content=self.client.get(export.json()['download_url']).content
        book=load_workbook(BytesIO(content),data_only=True)
        self.assertEqual(len(book.sheetnames),8)
        rows=list(book['Rekap_Nilai'].values)
        header=list(rows[0])
        self.assertEqual(rows[1][header.index('NIM')],'0012345678')
        self.assertEqual(rows[1][header.index('Nilai_Akhir')],100)


if __name__ == "__main__":
    unittest.main()
