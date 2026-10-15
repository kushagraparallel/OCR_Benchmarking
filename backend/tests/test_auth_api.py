"""Integration tests for authentication flows using an isolated SQLite database."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.database import get_database_session
from app.main import app
from app import models as _models  # noqa: F401 — register ORM models.


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Provide a clean application client backed by an isolated in-memory database."""
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


def register_user(client: TestClient, email: str = "tester@example.com") -> dict[str, object]:
    """Register a test account and return its public response."""
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "Strong-password-123"})
    assert response.status_code == 201
    return response.json()


def test_registration_normalizes_email_and_rejects_duplicates(client: TestClient) -> None:
    """Registration should normalize email and reject duplicate accounts."""
    register_user(client, "Tester@Example.com")
    duplicate_response = client.post(
        "/api/v1/auth/register",
        json={"email": "tester@example.com", "password": "Strong-password-123"},
    )
    assert duplicate_response.status_code == 409


def test_login_me_refresh_and_logout(client: TestClient) -> None:
    """A valid login creates a session, rotates refresh tokens, and supports logout."""
    register_user(client)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@example.com", "password": "Strong-password-123"},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["token_type"] == "bearer"
    assert "password_hash" not in login_payload["user"]
    original_refresh_cookie = login_response.cookies.get("ocrlab_refresh")
    assert original_refresh_cookie

    access_token = login_payload["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    refresh_response = client.post("/api/v1/auth/refresh", cookies={"ocrlab_refresh": original_refresh_cookie})
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"] != access_token
    rotated_cookie = refresh_response.cookies.get("ocrlab_refresh")
    assert rotated_cookie and rotated_cookie != original_refresh_cookie

    logout_response = client.post("/api/v1/auth/logout", cookies={"ocrlab_refresh": rotated_cookie})
    assert logout_response.status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_reuse_of_consumed_refresh_token_revokes_session(client: TestClient) -> None:
    """Replaying a consumed refresh token should revoke its associated session."""
    register_user(client)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@example.com", "password": "Strong-password-123"},
    )
    old_cookie = login_response.cookies.get("ocrlab_refresh")
    access_token = login_response.json()["access_token"]
    assert old_cookie

    first_refresh = client.post("/api/v1/auth/refresh", cookies={"ocrlab_refresh": old_cookie})
    assert first_refresh.status_code == 200
    replay_response = client.post("/api/v1/auth/refresh", cookies={"ocrlab_refresh": old_cookie})
    assert replay_response.status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}).status_code == 401


def test_session_endpoints_are_authenticated_and_scoped(client: TestClient) -> None:
    """Session listing requires authentication and does not expose refresh secrets."""
    register_user(client)
    assert client.get("/api/v1/sessions").status_code == 401
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@example.com", "password": "Strong-password-123"},
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
    sessions_response = client.get("/api/v1/sessions", headers=headers)
    assert sessions_response.status_code == 200
    assert len(sessions_response.json()["items"]) == 1
    assert "token_hash" not in sessions_response.text


def test_login_rejects_incorrect_password(client: TestClient) -> None:
    """Incorrect credentials should return a generic unauthorized response."""
    register_user(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@example.com", "password": "incorrect-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_user_cannot_revoke_another_users_session(client: TestClient) -> None:
    """A user must not be able to revoke a session owned by another account."""
    register_user(client, "first@example.com")
    first_login = client.post(
        "/api/v1/auth/login",
        json={"email": "first@example.com", "password": "Strong-password-123"},
    )
    first_headers = {"Authorization": f"Bearer {first_login.json()['access_token']}"}
    first_sessions = client.get("/api/v1/sessions", headers=first_headers).json()["items"]
    first_session_id = first_sessions[0]["id"]

    register_user(client, "second@example.com")
    second_login = client.post(
        "/api/v1/auth/login",
        json={"email": "second@example.com", "password": "Strong-password-123"},
    )
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
    revoke_response = client.delete(f"/api/v1/sessions/{first_session_id}", headers=second_headers)

    assert revoke_response.status_code == 404
    assert client.get("/api/v1/auth/me", headers=first_headers).status_code == 200


def test_logout_all_revokes_every_access_session(client: TestClient) -> None:
    """Logout-all should invalidate access tokens from all sessions for the account."""
    register_user(client)
    first_login = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@example.com", "password": "Strong-password-123"},
    )
    second_login = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@example.com", "password": "Strong-password-123"},
    )
    first_headers = {"Authorization": f"Bearer {first_login.json()['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}

    logout_response = client.post("/api/v1/auth/logout-all", headers=first_headers)

    assert logout_response.status_code == 200
    assert client.get("/api/v1/auth/me", headers=first_headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second_headers).status_code == 401

