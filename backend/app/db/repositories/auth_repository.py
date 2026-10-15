"""Database operations for users, sessions, and refresh-token records."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models import RefreshToken, User, UserSession


class AuthRepository:
    """Encapsulate authentication persistence queries and mutations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user_by_email(self, email: str) -> User | None:
        """Find an account by its normalized email address."""
        return self._session.scalar(select(User).where(User.email == email))

    def get_user_by_id(self, user_id: int) -> User | None:
        """Find an account by primary key."""
        return self._session.get(User, user_id)

    def create_user(self, email: str, password_hash: str) -> User:
        """Persist a new user account and flush to obtain its identifier."""
        user = User(email=email, password_hash=password_hash)
        self._session.add(user)
        self._session.flush()
        return user

    def create_session(self, user_id: int, session_id: str, expires_at: datetime, user_agent: str | None) -> UserSession:
        """Persist a new authenticated session."""
        user_session = UserSession(id=session_id, user_id=user_id, expires_at=expires_at, user_agent=user_agent)
        self._session.add(user_session)
        self._session.flush()
        return user_session

    def add_refresh_token(self, session_id: str, token_hash: str, expires_at: datetime) -> RefreshToken:
        """Persist a hashed refresh token."""
        token_record = RefreshToken(session_id=session_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token_record)
        self._session.flush()
        return token_record

    def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        """Load and lock a refresh token and its session/account when supported."""
        statement = (
            select(RefreshToken)
            .options(selectinload(RefreshToken.session).selectinload(UserSession.user))
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
        return self._session.scalar(statement)

    def get_session(self, session_id: str) -> UserSession | None:
        """Find a session by identifier."""
        return self._session.get(UserSession, session_id)

    def list_sessions(self, user_id: int) -> list[UserSession]:
        """Return sessions owned by a user, newest first."""
        statement = select(UserSession).where(UserSession.user_id == user_id).order_by(UserSession.created_at.desc())
        return list(self._session.scalars(statement).all())

    def revoke_session(self, user_session: UserSession, revoked_at: datetime) -> None:
        """Revoke a session and all active refresh tokens for it."""
        user_session.revoked_at = revoked_at
        self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == user_session.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
            .execution_options(synchronize_session="fetch")
        )

    def revoke_all_sessions(self, user_id: int, revoked_at: datetime) -> None:
        """Revoke every active session owned by a user."""
        sessions = self._session.scalars(
            select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        ).all()
        for user_session in sessions:
            self.revoke_session(user_session, revoked_at)
