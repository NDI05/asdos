"""Persist automatic answer analysis and separate human region disposition."""
from alembic import op
import sqlalchemy as sa

revision = "0003_auto_mapping"
down_revision = "0002_rubric_jobs"
branch_labels = None
depends_on = None


def upgrade():
    # The historical baseline creates current metadata on a fresh database.
    columns = {
        "documents":[sa.Column("auto_process",sa.Boolean(),nullable=False,server_default=sa.false()),
                     sa.Column("analysis_result",sa.JSON(),nullable=False,server_default=sa.text("'{}'"))],
        "regions":[sa.Column("analysis",sa.JSON(),nullable=False,server_default=sa.text("'{}'")),
                   sa.Column("excluded_from_mapping",sa.Boolean(),nullable=False,server_default=sa.false())],
    }
    for table, additions in columns.items():
        existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        for column in additions:
            if column.name not in existing:
                op.add_column(table,column)


def downgrade():
    raise RuntimeError("Retain automatic mapping provenance; downgrade requires an explicit data migration.")
