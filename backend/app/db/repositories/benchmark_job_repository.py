"""Persistence queries for durable benchmark queue jobs."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.benchmark_job import BenchmarkJob


class BenchmarkJobRepository:
    """Encapsulate owner-scoped job access and cross-process queue claims."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, user_id: int, document_id: str, engine_names: list[str]) -> BenchmarkJob:
        """Create a queued job; the caller commits the surrounding transaction."""
        job = BenchmarkJob(
            id=str(uuid4()),
            user_id=user_id,
            document_id=document_id,
            engine_names=engine_names,
            status="queued",
        )
        self._session.add(job)
        self._session.flush()
        return job

    def get_owned(self, job_id: str, user_id: int) -> BenchmarkJob | None:
        """Return a job only to its owning account."""
        return self._session.scalar(
            select(BenchmarkJob).where(
                BenchmarkJob.id == job_id,
                BenchmarkJob.user_id == user_id,
            )
        )

    def claim_next(self, lease_seconds: int) -> BenchmarkJob | None:
        """Atomically claim one queued or expired-lease job across worker processes."""
        now = datetime.now(timezone.utc)
        statement = (
            select(BenchmarkJob)
            .where(
                or_(
                    BenchmarkJob.status == "queued",
                    (
                        (BenchmarkJob.status.in_(("running", "cancellation_requested")))
                        & BenchmarkJob.lease_expires_at.is_not(None)
                        & (BenchmarkJob.lease_expires_at < now)
                    ),
                )
            )
            .order_by(BenchmarkJob.created_at, BenchmarkJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = self._session.scalar(statement)
        if job is None:
            return None
        if job.status == "cancellation_requested":
            job.status = "cancelled"
            job.finished_at = now
            job.lease_expires_at = None
            self._session.commit()
            return None
        job.status = "running"
        job.started_at = now
        job.finished_at = None
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.attempt_count += 1
        job.error = None
        self._session.commit()
        self._session.refresh(job)
        return job

    def renew_lease(self, job_id: str, lease_seconds: int) -> bool:
        """Renew a running job's lease to prevent duplicate execution."""
        job = self._session.get(BenchmarkJob, job_id)
        if job is None or job.status != "running":
            return False
        job.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        self._session.commit()
        return True
