"""Add shared worker slots for deployment-wide benchmark concurrency.

Revision ID: 20261015_0004
Revises: 20261015_0003
Create Date: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261015_0004"
down_revision: str | None = "20261015_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create shared worker slots and owner lookup index."""
    op.create_table(
        "benchmark_worker_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_benchmark_worker_slots_owner_id",
        "benchmark_worker_slots",
        ["owner_id"],
    )


def downgrade() -> None:
    """Remove the global worker-slot table."""
    op.drop_index("ix_benchmark_worker_slots_owner_id", table_name="benchmark_worker_slots")
    op.drop_table("benchmark_worker_slots")
