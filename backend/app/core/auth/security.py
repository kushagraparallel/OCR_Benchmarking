"""Password hashing and token primitives for authentication services."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.config import get_settings

PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id defaults."""
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password without exposing hash verification errors to callers."""
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerificationError, VerifyMismatchError):
        return False


def create_access_token(user_id: int, session_id: str) -> tuple[str, int]:
    """Create a signed short-lived JWT and return its lifetime in seconds."""
    settings = get_settings()
    lifetime_seconds = settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "sid": session_id,
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=lifetime_seconds),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, lifetime_seconds


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate JWT signature, algorithm, issuer, audience, and expiry."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["sub", "sid", "jti", "iat", "exp", "iss", "aud"]},
    )


def create_refresh_token() -> str:
    """Create a cryptographically random opaque refresh token."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 digest stored instead of a refresh token secret."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
