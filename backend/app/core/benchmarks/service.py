"""Application service for authenticated benchmark job lifecycle operations."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.documents.errors import DocumentNotFoundError
from app.core.ocr.registry import OCREngineFactory
from app.db.repositories.benchmark_job_repository import BenchmarkJobRepository
from app.db.repositories.document_repository import DocumentRepository
from app.models.benchmark_job import BenchmarkJob


class BenchmarkJobNotFoundError(Exception):
    """Raised when a benchmark job is absent or not owned by the requester."""


class InvalidBenchmarkStateError(Exception):
    """Raised when a lifecycle operation is not valid for the current job state."""


class BenchmarkJobService:
    """Validate ownership and persist benchmark queue lifecycle changes."""

    def __init__(self, session: Session, engine_factory: OCREngineFactory) -> None:
        self._session = session
        self._jobs = BenchmarkJobRepository(session)
        self._documents = DocumentRepository(session)
        self._engine_factory = engine_factory

    def submit(self, user_id: int, document_id: str, engine_names: list[str]) -> BenchmarkJob:
        """Validate engine availability and document ownership before queueing."""
        self._engine_factory.create_many(engine_names)
        document = self._documents.get_owned(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError
        job = self._jobs.create(user_id, document_id, engine_names)
        self._session.commit()
        self._session.refresh(job)
        return job

    def get_owned(self, job_id: str, user_id: int) -> BenchmarkJob:
        """Return one job only when it belongs to the authenticated account."""
        job = self._jobs.get_owned(job_id, user_id)
        if job is None:
            raise BenchmarkJobNotFoundError
        return job

    def list_owned(self, user_id: int, limit: int, offset: int) -> list[BenchmarkJob]:
        """Return bounded newest-first benchmark history for the current user."""
        return list(
            self._session.scalars(
                select(BenchmarkJob)
                .where(BenchmarkJob.user_id == user_id)
                .order_by(BenchmarkJob.created_at.desc(), BenchmarkJob.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        )

    def cancel_owned(self, job_id: str, user_id: int) -> BenchmarkJob:
        """Cancel queued work immediately or request stop at the next page boundary."""
        job = self.get_owned(job_id, user_id)
        if job.status == "queued":
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            job.lease_expires_at = None
        elif job.status == "running":
            job.status = "cancellation_requested"
        elif job.status not in {"cancellation_requested", "cancelled"}:
            raise InvalidBenchmarkStateError(
                "Only queued or running benchmark jobs can be cancelled."
            )
        self._session.commit()
        self._session.refresh(job)
        return job
