"""Purge export artifacts after an explicitly configured retention period.

Dry-run is the default. This command does not purge original PDFs or assessment
records; those require a separately approved institutional retention policy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from apps.api.asdos_api.config import settings
from apps.api.asdos_api.database import SessionLocal
from apps.api.asdos_api.models import Artifact, AuditEvent, ExportSnapshot, now_utc
from apps.api.asdos_api.storage import artifact_store

MAX_BATCH_SIZE = 500


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def purge_expired_exports(*, sessions=SessionLocal, store=artifact_store,
                          retention_days: int, apply: bool = False) -> dict[str, int | bool]:
    if retention_days < 0:
        raise ValueError("retention_days must be zero or positive")
    if retention_days == 0:
        return {"enabled": False, "expired": 0, "tombstones": 0, "deleted_files": 0, "failed_files": 0}

    now = now_utc()
    cutoff = now - timedelta(days=retention_days)
    with sessions.begin() as db:
        rows = db.scalars(select(Artifact).where(
            Artifact.retention_class == "export",
        ).order_by(Artifact.created_at).limit(MAX_BATCH_SIZE).with_for_update(skip_locked=True)).all()
        expired = [row for row in rows if row.purged_at is None and _utc(row.created_at) <= _utc(cutoff)]
        tombstones = [row for row in rows if row.purged_at is not None]
        if not apply:
            return {"enabled": True, "expired": len(expired), "tombstones": len(tombstones),
                    "deleted_files": 0, "failed_files": 0}

        for artifact in expired:
            artifact.purged_at = now
            artifact.sha256 = ""
            artifact.byte_size = 0
            artifact.parent_ids = []
            export = db.scalar(select(ExportSnapshot).where(ExportSnapshot.artifact_key == artifact.storage_key))
            if export:
                export.payload = {}
                export.manifest_hash = ""
                export.artifact_hash = ""
                for event in db.scalars(select(AuditEvent).where(
                    AuditEvent.resource_id == export.id,
                    AuditEvent.action == "grade.export_created",
                )).all():
                    event.metadata_json = {}

        # Persist the tombstone before unlinking. A later run retries any file
        # cleanup left incomplete by a process crash without serving it again.
        db.flush()
        cleanup_keys = [row.storage_key for row in [*expired, *tombstones]]

    deleted_files = failed_files = 0
    for key in cleanup_keys:
        try:
            store.delete(key)
            deleted_files += 1
        except (OSError, ValueError):
            failed_files += 1

    return {"enabled": True, "expired": len(expired), "tombstones": len(tombstones),
            "deleted_files": deleted_files, "failed_files": failed_files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retention-days", type=int, default=settings.export_retention_days)
    parser.add_argument("--apply", action="store_true", help="Mark expired exports as purged and unlink files")
    args = parser.parse_args()
    result = purge_expired_exports(retention_days=args.retention_days, apply=args.apply)
    print(" ".join(f"{key}={value}" for key, value in result.items()))
    return 1 if result["failed_files"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
