"""Shared lease slots limiting active benchmark jobs across worker processes."""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BenchmarkWorkerSlot(Base):
    """One globally coordinated execution slot shared by all OCR workers."""

    __tablename__ = "benchmark_worker_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
