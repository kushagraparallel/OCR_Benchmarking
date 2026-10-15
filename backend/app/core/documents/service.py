"""Use cases for secure PDF upload, listing, retrieval, and deletion."""

import logging
import re
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.documents.errors import DocumentNotFoundError, DocumentStorageError, InvalidPdfError
from app.core.documents.pdf_inspector import PdfInspector
from app.core.documents.storage import LocalDocumentStorage, StagedUpload
from app.db.repositories.document_repository import DocumentRepository
from app.models.document import DocumentRecord

logger = logging.getLogger(__name__)
_UNSAFE_FILENAME_CHARACTERS = re.compile(r"[\\x00-\\x1f\\x7f]")


class DocumentService:
    """Coordinate PDF validation, private storage, and metadata transactions."""

    def __init__(self, database_session: Session) -> None:
        settings = get_settings()
        self._session = database_session
        self._repository = DocumentRepository(database_session)
        self._storage = LocalDocumentStorage(settings.document_storage_root, settings.max_document_upload_bytes)
        self._inspector = PdfInspector(settings.max_pdf_pages, settings.max_pdf_page_dimension_points)

    def upload(self, source: BinaryIO, original_filename: str, user_id: int) -> DocumentRecord:
        """Validate and persist one PDF; clean up files if any step fails."""
        safe_filename = self._sanitize_filename(original_filename)
        staged_upload: StagedUpload | None = None
        storage_key: str | None = None
        try:
            staged_upload = self._storage.stage_upload(source)
            inspection = self._inspector.inspect(staged_upload.temporary_path)
            document_id = str(uuid4())
            storage_key = self._storage.finalize_upload(staged_upload, document_id)
            document = DocumentRecord(
                id=document_id,
                user_id=user_id,
                original_filename=safe_filename,
                storage_key=storage_key,
                sha256=staged_upload.sha256,
                size_bytes=staged_upload.size_bytes,
                page_count=inspection.page_count,
                pdf_title=inspection.title,
                pdf_author=inspection.author,
                status="uploaded",
            )
            self._repository.create(document)
            self._session.commit()
            self._session.refresh(document)
            return document
        except Exception as exc:
            self._session.rollback()
            if storage_key is not None:
                try:
                    self._storage.delete(storage_key)
                except DocumentStorageError:
                    logger.exception("Could not clean up a file after failed document persistence")
            if not isinstance(exc, (InvalidPdfError, DocumentStorageError)):
                logger.exception("Unexpected document upload failure")
            raise
        finally:
            if staged_upload is not None:
                self._storage.discard_staged_upload(staged_upload)

    def get_owned(self, document_id: str, user_id: int) -> DocumentRecord:
        """Return document metadata only to its owner."""
        document = self._repository.get_owned(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError
        return document

    def list_owned(self, user_id: int, limit: int, offset: int) -> list[DocumentRecord]:
        """Return a bounded page of metadata belonging to the current user."""
        return self._repository.list_owned(user_id, limit, offset)

    def delete_owned(self, document_id: str, user_id: int) -> None:
        """Delete an owned document and its metadata, reporting storage failures."""
        document = self.get_owned(document_id, user_id)
        storage_key = document.storage_key
        try:
            self._repository.delete(document)
            self._session.commit()
        except Exception:
            self._session.rollback()
            logger.exception("Failed to delete document metadata %s", document_id)
            raise
        # Metadata is removed first, so a storage outage can leave only an inaccessible
        # orphan file; periodic reconciliation will clean these up. The inverse order
        # could leave a live database record pointing to a missing file after rollback.
        self._storage.delete(storage_key)

    @staticmethod
    def _sanitize_filename(original_filename: str) -> str:
        """Keep a bounded display filename without trusting path components."""
        normalized_filename = original_filename.replace("\\", "/").split("/")[-1]
        sanitized_filename = _UNSAFE_FILENAME_CHARACTERS.sub("_", normalized_filename).strip(" .")
        if not sanitized_filename:
            raise InvalidPdfError("A valid filename is required.")
        return sanitized_filename[:255]
