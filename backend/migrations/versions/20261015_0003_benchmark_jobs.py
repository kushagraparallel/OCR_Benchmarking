"""Create durable OCR benchmark job queue and result storage.

Revision ID: 20261015_0003
Revises: 20261015_0002
Create Date: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261015_0003"
down_revision: str | None = "20261015_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create benchmark jobs and indexes used for queue claims and history."""
    op.create_table(
        "benchmark_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_names", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_benchmark_jobs_document_id", "benchmark_jobs", ["document_id"])
    op.create_index(
        "ix_benchmark_jobs_queue",
        "benchmark_jobs",
        ["status", "lease_expires_at", "created_at"],
    )
    op.create_index(
        "ix_benchmark_jobs_user_created",
        "benchmark_jobs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Remove benchmark queue indexes and persisted jobs."""
    op.drop_index("ix_benchmark_jobs_user_created", table_name="benchmark_jobs")
    op.drop_index("ix_benchmark_jobs_queue", table_name="benchmark_jobs")
    op.drop_index("ix_benchmark_jobs_document_id", table_name="benchmark_jobs")
    op.drop_table("benchmark_jobs")
