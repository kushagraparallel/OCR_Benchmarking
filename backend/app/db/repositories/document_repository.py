"""Persistence operations for user-owned document metadata."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import DocumentRecord


class DocumentRepository:
    """Encapsulate document queries and writes, including ownership scoping."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, document: DocumentRecord) -> DocumentRecord:
        """Add a new document record and flush to validate database constraints."""
        self._session.add(document)
        self._session.flush()
        return document

    def get_owned(self, document_id: str, user_id: int) -> DocumentRecord | None:
        """Find a document only when it belongs to the requesting account."""
        statement = select(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.user_id == user_id,
        )
        return self._session.scalar(statement)

    def list_owned(self, user_id: int, limit: int, offset: int) -> list[DocumentRecord]:
        """Return a stable, newest-first page of documents for one account."""
        statement = (
            select(DocumentRecord)
            .where(DocumentRecord.user_id == user_id)
            .order_by(DocumentRecord.created_at.desc(), DocumentRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())

    def delete(self, document: DocumentRecord) -> None:
        """Delete a previously ownership-checked document record."""
        self._session.delete(document)
