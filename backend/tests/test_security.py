"""Unit tests for authentication security primitives."""

from app.core.auth.security import hash_password, hash_refresh_token, verify_password


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    """Password hashes should be one-way and verify correct credentials."""
    password = "Strong-password-123"
    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_refresh_token_hash_is_deterministic_and_not_plaintext() -> None:
    """Only a deterministic digest should be stored for a refresh token."""
    refresh_token = "high-entropy-refresh-secret"
    digest = hash_refresh_token(refresh_token)

    assert digest != refresh_token
    assert len(digest) == 64
    assert hash_refresh_token(refresh_token) == digest
