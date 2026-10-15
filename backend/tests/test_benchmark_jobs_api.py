"""Integration tests for authenticated benchmark job submission and lifecycle."""

from collections.abc import Generator
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401 — register ORM metadata.
from app.db.base import Base
from app.db.database import get_database_session
from app.main import app


def create_pdf() -> bytes:
    """Create a small valid PDF fixture in memory."""
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Benchmark queue integration")
        return document.tobytes()


def authenticate(client: TestClient, email: str) -> dict[str, str]:
    """Register and log in a user, returning bearer authorization headers."""
    password = "Strong-password-123"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert logged_in.status_code == 200
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


def upload_pdf(client: TestClient, headers: dict[str, str]) -> str:
    """Upload a PDF using the existing owner-scoped document endpoint."""
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("benchmark.pdf", create_pdf(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_authenticated_benchmark_job_lifecycle(tmp_path: Path) -> None:
    """A user can queue, inspect, and cancel a benchmark for their own PDF."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    try:
        with TestClient(app) as client:
            owner_headers = authenticate(client, "benchmark-owner@example.com")
            other_headers = authenticate(client, "benchmark-other@example.com")
            document_id = upload_pdf(client, owner_headers)

            engines = client.get("/api/v1/benchmarks/engines", headers=owner_headers)
            assert engines.status_code == 200
            assert "tesseract" in engines.json()

            submitted = client.post(
                "/api/v1/benchmarks",
                headers=owner_headers,
                json={"document_id": document_id, "engine_names": ["TESSERACT"]},
            )
            assert submitted.status_code == 202
            job = submitted.json()
            assert job["status"] == "queued"
            assert job["engine_names"] == ["tesseract"]
            job_id = job["id"]

            listed = client.get("/api/v1/benchmarks", headers=owner_headers)
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["items"]] == [job_id]

            forbidden = client.get(
                f"/api/v1/benchmarks/{job_id}", headers=other_headers
            )
            assert forbidden.status_code == 404

            cancelled = client.delete(
                f"/api/v1/benchmarks/{job_id}", headers=owner_headers
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"

            unknown_engine = client.post(
                "/api/v1/benchmarks",
                headers=owner_headers,
                json={"document_id": document_id, "engine_names": ["not-an-engine"]},
            )
            assert unknown_engine.status_code == 422
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
