from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from apps.api.asdos_api.database import Base
from apps.api.asdos_api.models import Assessment, Document, OutboxEvent, PipelineJob, User, now_utc
from apps.worker import tasks


class TestJobRecovery(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patcher = patch.object(tasks, "SessionLocal", self.sessions)
        self.patcher.start()
        with self.sessions.begin() as db:
            owner = User(username="recovery-test", display_name="Synthetic", password_hash="test-only")
            db.add(owner)
            db.flush()
            assessment = Assessment(owner_id=owner.id, title="Synthetic", course_label="", language="id")
            db.add(assessment)
            db.flush()
            document = Document(
                assessment_id=assessment.id,
                submission_id=None,
                draft_assessment_revision_id=None,
                kind="question_source",
                storage_key=f"aa/{uuid4()}",
                sha256="b" * 64,
                byte_size=1,
                original_filename="synthetic.pdf",
            )
            db.add(document)
            db.flush()
            self.assessment_id = assessment.id
            self.document_id = document.id

    def tearDown(self):
        self.patcher.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_job(
        self,
        *,
        status: str,
        attempt: int = 1,
        lease_until=None,
        cancel_requested: bool = False,
    ) -> str:
        job_id = str(uuid4())
        with self.sessions.begin() as db:
            db.add(PipelineJob(
                id=job_id,
                assessment_id=self.assessment_id,
                document_id=self.document_id,
                kind="question_import",
                stage="render",
                input_fingerprint=uuid4().hex + uuid4().hex,
                attempt=attempt,
                status=status,
                lease_owner="worker-a" if status == "running" else None,
                lease_until=lease_until,
                cancel_requested=cancel_requested,
            ))
        return job_id

    def get_job(self, job_id: str) -> PipelineJob:
        with self.sessions() as db:
            return db.get(PipelineJob, job_id)

    def test_expired_lease_requeues_once_and_increments_attempt(self):
        job_id = self.add_job(status="running", lease_until=now_utc() - timedelta(seconds=5))
        first = tasks.recover_expired_jobs.run()
        second = tasks.recover_expired_jobs.run()
        job = self.get_job(job_id)
        with self.sessions() as db:
            events = db.scalars(select(OutboxEvent).where(OutboxEvent.job_id == job_id)).all()
        self.assertEqual(first["requeued"], 1)
        self.assertEqual(second["requeued"], 0)
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.attempt, 2)
        self.assertIsNone(job.lease_owner)
        self.assertEqual(len(events), 1)

    def test_live_lease_is_not_recovered(self):
        job_id = self.add_job(status="running", lease_until=now_utc() + timedelta(minutes=5))
        result = tasks.recover_expired_jobs.run()
        self.assertEqual(result["requeued"], 0)
        self.assertEqual(self.get_job(job_id).status, "running")

    def test_cancelled_queued_job_is_terminal_without_outbox(self):
        job_id = self.add_job(status="queued", cancel_requested=True)
        tasks.recover_expired_jobs.run()
        job = self.get_job(job_id)
        with self.sessions() as db:
            event_count = len(db.scalars(select(OutboxEvent).where(OutboxEvent.job_id == job_id)).all())
        self.assertEqual(job.status, "cancelled")
        self.assertIsNotNone(job.finished_at)
        self.assertEqual(event_count, 0)

    def test_expired_job_at_attempt_limit_fails_instead_of_looping(self):
        job_id = self.add_job(status="running", attempt=tasks.MAX_AUTO_ATTEMPTS,
                              lease_until=now_utc() - timedelta(seconds=5))
        tasks.recover_expired_jobs.run()
        job = self.get_job(job_id)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error_code, "WORKER_RESTART_RETRY_EXHAUSTED")
        self.assertIsNotNone(job.finished_at)


if __name__ == "__main__":
    unittest.main()
