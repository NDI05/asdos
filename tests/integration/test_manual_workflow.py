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
        upload=client.post(f"/api/v1/submissions/{submission_id}/documents",files={"file":("synthetic.pdf",one_page_pdf(),"application/pdf")})
        self.assertEqual(upload.status_code,202,upload.text)
        document_id=upload.json()["document_id"]
        if EXTERNAL_COMPOSE:
            self.wait_for_job(upload.json()["job"]["id"])
            document_state = client.get(f"/api/v1/documents/{document_id}").json()
            self.assertEqual(document_state["validation_status"], "valid")
        else:
            self.assertEqual(upload.json()["validation_status"],"valid")
        current=client.get(f"/api/v1/submissions/{submission_id}").json()
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


if __name__ == "__main__":
    unittest.main()
