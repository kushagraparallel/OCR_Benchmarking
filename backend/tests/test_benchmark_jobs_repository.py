"""Unit tests for durable benchmark queue claim and lease behavior."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401 — register ORM metadata.
from app.db.base import Base
from app.db.repositories.benchmark_job_repository import BenchmarkJobRepository
from app.models.document import DocumentRecord
from app.models.user import User


def test_claim_commits_running_state_and_renews_lease() -> None:
    """A claimed job is visible to other sessions and retains a renewable lease."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    user_id = None
    document_id = str(uuid4())

    try:
        with factory() as session:
            user = User(email="queue-test@example.com", password_hash="test-hash")
            session.add(user)
            session.flush()
            user_id = user.id
            session.add(
                DocumentRecord(
                    id=document_id,
                    user_id=user.id,
                    original_filename="queue.pdf",
                    storage_key="queue-test.pdf",
                    sha256="a" * 64,
                    size_bytes=128,
                    page_count=1,
                    status="uploaded",
                )
            )
            session.commit()
            repository = BenchmarkJobRepository(session)
            job = repository.create(user.id, document_id, ["tesseract"])
            job_id = job.id
            session.commit()

        with factory() as worker_session:
            claimed = BenchmarkJobRepository(worker_session).claim_next(60)
            assert claimed is not None
            assert claimed.id == job_id
            assert claimed.status == "running"
            assert claimed.attempt_count == 1

        with factory() as observer_session:
            visible = observer_session.get(_models.BenchmarkJob, job_id)
            assert visible is not None
            assert visible.status == "running"
            original_expiry = visible.lease_expires_at

        with factory() as worker_session:
            assert BenchmarkJobRepository(worker_session).claim_next(60) is None
            assert BenchmarkJobRepository(worker_session).renew_lease(job_id, 120)

        with factory() as observer_session:
            renewed = observer_session.get(_models.BenchmarkJob, job_id)
            assert renewed is not None
            assert renewed.lease_expires_at is not None
            assert original_expiry is not None
            # SQLite stores timezone-aware datetimes as naive UTC values.
            original = original_expiry.replace(tzinfo=timezone.utc)
            renewed_expiry = renewed.lease_expires_at.replace(tzinfo=timezone.utc)
            assert renewed_expiry > original
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
