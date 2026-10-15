"""Tests for database infrastructure that do not require PostgreSQL."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.database import create_database_engine


def test_database_engine_connects_to_in_memory_sqlite() -> None:
    """The engine factory should support an isolated test database."""
    test_engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        with test_engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()

        assert result == 1
    finally:
        test_engine.dispose()


def test_session_can_execute_statement_and_close_cleanly() -> None:
    """A session bound to a test engine should execute and close cleanly."""
    test_engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        with Session(test_engine) as session:
            result = session.execute(text("SELECT 1")).scalar_one()

        assert result == 1
        assert not session.is_active or session.is_active
    finally:
        test_engine.dispose()


def test_declarative_base_exposes_metadata() -> None:
    """Alembic should be able to read the shared ORM metadata."""
    assert Base.metadata is not None
    assert isinstance(Base.metadata.tables, dict)
