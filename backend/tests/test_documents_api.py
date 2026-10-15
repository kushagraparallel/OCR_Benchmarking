"""API tests for PDF validation, ownership, and private storage cleanup."""

from collections.abc import Generator
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401 — register ORM models.
from app.db.base import Base
from app.db.database import get_database_session
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """Provide an isolated database and private document directory for each test."""
    from app.core.documents import service as document_service_module

    monkeypatch.setattr(
        document_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            document_storage_root=tmp_path / "private-documents",
            max_document_upload_bytes=4096,
            max_pdf_pages=3,
            max_pdf_page_dimension_points=14400.0,
        ),
    )
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    test_session_factory = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)

    def override_database_session() -> Generator[Session, None, None]:
        with test_session_factory() as database_session:
            yield database_session

    app.dependency_overrides[get_database_session] = override_database_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def create_valid_pdf() -> bytes:
    """Build a small deterministic PDF without storing test fixtures on disk."""
    with fitz.open() as pdf_document:
        page = pdf_document.new_page(width=612, height=792)
        page.insert_text((72, 72), "OCRLab PDF ingestion test")
        return pdf_document.tobytes()


def create_authenticated_user(client: TestClient, email: str) -> dict[str, str]:
    """Register and authenticate a test account, returning its bearer headers."""
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Strong-password-123"},
    )
    assert register_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Strong-password-123"},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def test_upload_list_get_and_delete_pdf(client: TestClient) -> None:
    """A valid PDF should persist metadata and support owner-scoped CRUD operations."""
    headers = create_authenticated_user(client, "document-owner@example.com")
    upload_response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("sample.pdf", create_valid_pdf(), "application/pdf")},
    )

    assert upload_response.status_code == 201
    document = upload_response.json()
    assert document["original_filename"] == "sample.pdf"
    assert document["page_count"] == 1
    assert document["size_bytes"] > 0
    assert "storage_key" not in document
    assert "sha256" not in document

    list_response = client.get("/api/v1/documents?limit=10&offset=0", headers=headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [document["id"]]

    get_response = client.get(f"/api/v1/documents/{document['id']}", headers=headers)
    assert get_response.status_code == 200

    delete_response = client.delete(f"/api/v1/documents/{document['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert client.get(f"/api/v1/documents/{document['id']}", headers=headers).status_code == 404


def test_rejects_non_pdf_content(client: TestClient) -> None:
    """A .pdf filename and PDF MIME type must not bypass parser validation."""
    headers = create_authenticated_user(client, "invalid-pdf@example.com")
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("fake.pdf", b"this is not a PDF", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "The uploaded file is not a PDF."


def test_rejects_upload_over_configured_size_limit(client: TestClient) -> None:
    """The storage layer must reject oversize data before parsing or finalizing it."""
    headers = create_authenticated_user(client, "large-pdf@example.com")
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("large.pdf", b"x" * 4097, "application/pdf")},
    )

    assert response.status_code == 413
    assert client.get("/api/v1/documents", headers=headers).json()["items"] == []


def test_rejects_pdf_above_page_count_limit(client: TestClient) -> None:
    """PDF page-count limits should be enforced independently of file size."""
    headers = create_authenticated_user(client, "many-pages@example.com")
    with fitz.open() as pdf_document:
        for _ in range(4):
            pdf_document.new_page()
        pdf_bytes = pdf_document.tobytes()

    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("many-pages.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 413
    assert "maximum of 3 pages" in response.json()["detail"]


def test_user_cannot_read_or_delete_another_users_document(client: TestClient) -> None:
    """Document identifiers must not allow cross-account metadata or file access."""
    owner_headers = create_authenticated_user(client, "pdf-owner@example.com")
    other_headers = create_authenticated_user(client, "pdf-other@example.com")
    upload_response = client.post(
        "/api/v1/documents",
        headers=owner_headers,
        files={"file": ("private.pdf", create_valid_pdf(), "application/pdf")},
    )
    document_id = upload_response.json()["id"]

    assert client.get(f"/api/v1/documents/{document_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/documents/{document_id}", headers=other_headers).status_code == 404
    assert len(client.get("/api/v1/documents", headers=owner_headers).json()["items"]) == 1
    assert client.get("/api/v1/documents", headers=other_headers).json()["items"] == []


def test_document_routes_require_authentication(client: TestClient) -> None:
    """Uploads and metadata queries must reject unauthenticated callers."""
    assert client.get("/api/v1/documents").status_code == 401
    assert client.post(
        "/api/v1/documents",
        files={"file": ("sample.pdf", create_valid_pdf(), "application/pdf")},
    ).status_code == 401


def test_document_id_must_be_a_uuid(client: TestClient) -> None:
    """Malformed identifiers should be rejected by request validation."""
    headers = create_authenticated_user(client, "bad-id@example.com")
    assert client.get("/api/v1/documents/not-a-uuid", headers=headers).status_code == 422
