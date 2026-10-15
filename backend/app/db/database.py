"""SQLAlchemy engine and request-scoped session lifecycle."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def create_database_engine(database_url: str, **engine_options: Any) -> Engine:
    """Create a SQLAlchemy engine without opening a database connection."""
    return create_engine(
        database_url,
        pool_pre_ping=True,
        **engine_options,
    )


settings = get_settings()
engine = create_database_engine(settings.database_url)
SessionFactory = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_database_session() -> Generator[Session, None, None]:
    """Yield a request-scoped session and reliably close or roll back its work."""
    with SessionFactory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
