"""Business logic for registration, login, token rotation, and sessions."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth.errors import EmailAlreadyRegisteredError, InvalidCredentialsError, InvalidRefreshTokenError, SessionNotFoundError
from app.core.auth.security import create_access_token, create_refresh_token, hash_password, hash_refresh_token, verify_password
from app.db.repositories.auth_repository import AuthRepository
from app.models import User, UserSession


def _utc_now() -> datetime:
    """Return an aware UTC timestamp for security-sensitive comparisons."""
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize database timestamps that may be naive under SQLite tests."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class AuthenticationService:
    """Coordinate authentication use cases over a request-scoped SQLAlchemy session."""

    def __init__(self, database_session: Session) -> None:
        self._session = database_session
        self._repository = AuthRepository(database_session)
        self._settings = get_settings()

    def register(self, email: str, password: str) -> User:
        """Create a user account with a normalized email and Argon2id password hash."""
        normalized_email = email.strip().casefold()
        if self._repository.get_user_by_email(normalized_email) is not None:
            raise EmailAlreadyRegisteredError
        try:
            user = self._repository.create_user(normalized_email, hash_password(password))
            self._session.commit()
            self._session.refresh(user)
            return user
        except IntegrityError as exc:
            self._session.rollback()
            raise EmailAlreadyRegisteredError from exc
        except Exception:
            self._session.rollback()
            raise

    def login(self, email: str, password: str, user_agent: str | None) -> tuple[User, str, str, int]:
        """Authenticate credentials and create a session with its first refresh token."""
        normalized_email = email.strip().casefold()
        user = self._repository.get_user_by_email(normalized_email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        now = _utc_now()
        session_id = str(uuid4())
        refresh_token = create_refresh_token()
        session_expires_at = now + timedelta(days=self._settings.refresh_token_expire_days)
        try:
            self._repository.create_session(user.id, session_id, session_expires_at, user_agent)
            self._repository.add_refresh_token(
                session_id,
                hash_refresh_token(refresh_token),
                session_expires_at,
            )
            self._session.commit()
            self._session.refresh(user)
            access_token, access_lifetime = create_access_token(user.id, session_id)
            return user, access_token, refresh_token, access_lifetime
        except Exception:
            self._session.rollback()
            raise

    def refresh(self, raw_refresh_token: str) -> tuple[User, str, str, int, str]:
        """Rotate a refresh token and revoke its session if token reuse is detected."""
        token_record = self._repository.get_refresh_token(hash_refresh_token(raw_refresh_token))
        now = _utc_now()
        if token_record is None:
            raise InvalidRefreshTokenError
        user_session = token_record.session
        if token_record.used_at is not None:
            self._repository.revoke_session(user_session, now)
            self._session.commit()
            raise InvalidRefreshTokenError
        if (
            token_record.revoked_at is not None
            or user_session.revoked_at is not None
            or _as_utc(token_record.expires_at) <= now
            or _as_utc(user_session.expires_at) <= now
            or not user_session.user.is_active
        ):
            raise InvalidRefreshTokenError

        new_refresh_token = create_refresh_token()
        try:
            token_record.used_at = now
            self._repository.add_refresh_token(
                user_session.id,
                hash_refresh_token(new_refresh_token),
                user_session.expires_at,
            )
            user_session.last_used_at = now
            self._session.commit()
            access_token, access_lifetime = create_access_token(user_session.user_id, user_session.id)
            return user_session.user, access_token, new_refresh_token, access_lifetime, user_session.id
        except Exception:
            self._session.rollback()
            raise

    def logout(self, raw_refresh_token: str | None, session_id: str | None = None) -> None:
        """Revoke the current session using its refresh token or authenticated session ID."""
        user_session: UserSession | None = None
        if raw_refresh_token:
            token_record = self._repository.get_refresh_token(hash_refresh_token(raw_refresh_token))
            if token_record is not None:
                user_session = token_record.session
        if user_session is None and session_id:
            user_session = self._repository.get_session(session_id)
        if user_session is not None and user_session.revoked_at is None:
            self._repository.revoke_session(user_session, _utc_now())
            self._session.commit()

    def logout_all(self, user_id: int) -> None:
        """Revoke every session for the authenticated user."""
        self._repository.revoke_all_sessions(user_id, _utc_now())
        self._session.commit()

    def list_sessions(self, user_id: int) -> list[UserSession]:
        """List sessions owned by a user."""
        return self._repository.list_sessions(user_id)

    def revoke_owned_session(self, user_id: int, session_id: str) -> None:
        """Revoke a session only when it belongs to the authenticated user."""
        user_session = self._repository.get_session(session_id)
        if user_session is None or user_session.user_id != user_id:
            raise SessionNotFoundError
        if user_session.revoked_at is None:
            self._repository.revoke_session(user_session, _utc_now())
            self._session.commit()
