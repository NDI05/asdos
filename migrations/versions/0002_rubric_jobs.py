"""Allow assessment-scoped generation jobs without a student document."""
from alembic import op
from sqlalchemy import inspect, String

revision = "0002_rubric_jobs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    column = next(c for c in inspect(op.get_bind()).get_columns("pipeline_jobs") if c["name"] == "document_id")
    if not column["nullable"]:
        with op.batch_alter_table("pipeline_jobs") as batch:
            batch.alter_column("document_id", existing_type=String(36), nullable=True)


def downgrade():
    # Refuse destructive removal of assessment-scoped jobs.
    if op.get_bind().exec_driver_sql("SELECT COUNT(*) FROM pipeline_jobs WHERE document_id IS NULL").scalar():
        raise RuntimeError("Assessment generation jobs exist; retain this migration.")
    with op.batch_alter_table("pipeline_jobs") as batch:
        batch.alter_column("document_id", existing_type=String(36), nullable=False)
