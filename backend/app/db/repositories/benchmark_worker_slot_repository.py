"""PostgreSQL-coordinated capacity slots for global benchmark concurrency."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.benchmark_worker_slot import BenchmarkWorkerSlot


class BenchmarkWorkerSlotRepository:
    """Reserve and renew global job-capacity slots with expiring leases."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_capacity(self, max_slots: int) -> None:
        """Ensure slot rows exist; tolerate concurrent worker startup races."""
        try:
            for slot_id in range(1, max_slots + 1):
                if self._session.get(BenchmarkWorkerSlot, slot_id) is None:
                    self._session.add(BenchmarkWorkerSlot(id=slot_id))
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            # Another worker may have inserted the same fixed slot IDs first.

    def acquire(self, owner_id: str, max_slots: int, lease_seconds: int) -> int | None:
        """Atomically reserve one free/expired slot across worker processes."""
        now = datetime.now(timezone.utc)
        statement = (
            select(BenchmarkWorkerSlot)
            .where(
                BenchmarkWorkerSlot.id <= max_slots,
                or_(
                    BenchmarkWorkerSlot.owner_id.is_(None),
                    BenchmarkWorkerSlot.lease_expires_at.is_(None),
                    BenchmarkWorkerSlot.lease_expires_at < now,
                ),
            )
            .order_by(BenchmarkWorkerSlot.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        slot = self._session.scalar(statement)
        if slot is None:
            return None
        slot.owner_id = owner_id
        slot.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self._session.commit()
        return slot.id

    def renew(self, slot_id: int, owner_id: str, lease_seconds: int) -> bool:
        """Renew a slot only when the current worker still owns it."""
        slot = self._session.get(BenchmarkWorkerSlot, slot_id)
        if slot is None or slot.owner_id != owner_id:
            return False
        slot.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        self._session.commit()
        return True

    def release(self, slot_id: int, owner_id: str) -> None:
        """Release a slot only when the caller remains its owner."""
        slot = self._session.get(BenchmarkWorkerSlot, slot_id)
        if slot is None or slot.owner_id != owner_id:
            return
        slot.owner_id = None
        slot.lease_expires_at = None
        self._session.commit()
