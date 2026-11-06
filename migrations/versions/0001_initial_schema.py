"""Initial ASDOS persistence schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-03
"""
from alembic import op

from apps.api.asdos_api.database import Base
from apps.api.asdos_api import models  # noqa: F401 - register model metadata

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
