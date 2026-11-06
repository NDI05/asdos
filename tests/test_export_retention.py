from __future__ import annotations

import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.asdos_api.database import Base
from apps.api.asdos_api.models import Artifact, Assessment, User, now_utc
from scripts.purge_expired_exports import purge_expired_exports


class MemoryStore:
    def __init__(self, *, fail: bool = False):
        self.deleted: list[str] = []
        self.fail = fail

    def delete(self, key: str) -> None:
        if self.fail:
            raise OSError("synthetic unlink failure")
        self.deleted.append(key)


class TestExportRetention(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions.begin() as db:
            owner = User(username="retention-test", display_name="Synthetic", password_hash="test-only")
            db.add(owner)
            db.flush()
            assessment = Assessment(owner_id=owner.id, title="Synthetic", course_label="", language="id")
            db.add(assessment)
            db.flush()
            old = Artifact(assessment_id=assessment.id, storage_key=f"aa/{uuid4()}", kind="export_final",
                           sha256="c" * 64, byte_size=123, retention_class="export",
                           parent_ids=["synthetic-submission"], created_at=now_utc() - timedelta(days=30))
            new = Artifact(assessment_id=assessment.id, storage_key=f"bb/{uuid4()}", kind="export_final",
                           sha256="d" * 64, byte_size=456, retention_class="export", created_at=now_utc())
            db.add_all((old, new))
            db.flush()
            self.old_id, self.new_id = old.id, new.id
            self.old_key = old.storage_key

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_dry_run_preserves_data_and_apply_tombstones_before_file_cleanup(self):
        store = MemoryStore()
        dry = purge_expired_exports(sessions=self.sessions, store=store, retention_days=7)
        self.assertEqual(dry["expired"], 1)
        self.assertEqual(store.deleted, [])
        with self.sessions() as db:
            old = db.get(Artifact, self.old_id)
            self.assertIsNone(old.purged_at)

        applied = purge_expired_exports(sessions=self.sessions, store=store, retention_days=7, apply=True)
        self.assertEqual(applied["expired"], 1)
        self.assertEqual(applied["deleted_files"], 1)
        self.assertEqual(store.deleted, [self.old_key])
        with self.sessions() as db:
            old = db.get(Artifact, self.old_id)
            new = db.get(Artifact, self.new_id)
            self.assertIsNotNone(old.purged_at)
            self.assertEqual(old.sha256, "")
            self.assertEqual(old.byte_size, 0)
            self.assertEqual(old.parent_ids, [])
            self.assertIsNone(new.purged_at)

    def test_zero_retention_disables_purge(self):
        store = MemoryStore()
        result = purge_expired_exports(sessions=self.sessions, store=store, retention_days=0, apply=True)
        self.assertFalse(result["enabled"])
        self.assertEqual(store.deleted, [])

    def test_failed_unlink_is_a_tombstone_and_the_next_run_retries(self):
        failed_store = MemoryStore(fail=True)
        first = purge_expired_exports(sessions=self.sessions, store=failed_store, retention_days=7, apply=True)
        self.assertEqual(first["failed_files"], 1)
        with self.sessions() as db:
            self.assertIsNotNone(db.get(Artifact, self.old_id).purged_at)

        retry_store = MemoryStore()
        second = purge_expired_exports(sessions=self.sessions, store=retry_store, retention_days=7, apply=True)
        self.assertEqual(second["expired"], 0)
        self.assertEqual(second["deleted_files"], 1)
        self.assertEqual(retry_store.deleted, [self.old_key])


if __name__ == "__main__":
    unittest.main()
