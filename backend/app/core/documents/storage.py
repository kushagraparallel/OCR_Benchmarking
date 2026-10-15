"""Private, filesystem-backed storage for staged and validated PDF uploads."""

import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.documents.errors import DocumentStorageError, DocumentTooLargeError

logger = logging.getLogger(__name__)
CHUNK_SIZE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class StagedUpload:
    """Temporary upload details produced while enforcing the byte limit."""

    temporary_path: Path
    size_bytes: int
    sha256: str


class LocalDocumentStorage:
    """Store PDFs under generated names outside the frontend's public directory."""

    def __init__(self, storage_root: Path, max_upload_bytes: int) -> None:
        self._storage_root = storage_root.expanduser().resolve()
        self._max_upload_bytes = max_upload_bytes
        self._staging_root = self._storage_root / ".staging"
        self._storage_root.mkdir(parents=True, exist_ok=True)
        self._staging_root.mkdir(parents=True, exist_ok=True)

    def stage_upload(self, source: BinaryIO) -> StagedUpload:
        """Stream an upload to a private temporary file and calculate its digest."""
        temporary_path: Path | None = None
        digest = hashlib.sha256()
        total_bytes = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix="upload-", suffix=".part", dir=self._staging_root, delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                while True:
                    chunk = source.read(CHUNK_SIZE_BYTES)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > self._max_upload_bytes:
                        raise DocumentTooLargeError(
                            f"The upload exceeds the {self._max_upload_bytes}-byte limit."
                        )
                    digest.update(chunk)
                    temporary_file.write(chunk)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            if total_bytes == 0:
                raise DocumentStorageError("The uploaded file is empty.")
            return StagedUpload(temporary_path, total_bytes, digest.hexdigest())
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def finalize_upload(self, staged_upload: StagedUpload, document_id: str) -> str:
        """Atomically move a validated staged file to a generated storage key."""
        storage_key = f"{uuid4().hex}.pdf"
        destination_path = self._storage_root / storage_key
        try:
            os.replace(staged_upload.temporary_path, destination_path)
            return storage_key
        except OSError as exc:
            logger.exception("Failed to finalize document upload %s", document_id)
            raise DocumentStorageError("The document could not be stored.") from exc

    def resolve_storage_key(self, storage_key: str) -> Path:
        """Resolve a generated storage key and reject path traversal attempts."""
        if (
            not storage_key
            or Path(storage_key).name != storage_key
            or storage_key in {".", ".."}
            or not storage_key.endswith(".pdf")
        ):
            raise DocumentStorageError("The stored document key is invalid.")
        resolved_path = (self._storage_root / storage_key).resolve()
        if resolved_path.parent != self._storage_root:
            raise DocumentStorageError("The stored document path is invalid.")
        return resolved_path

    def delete(self, storage_key: str) -> None:
        """Remove a stored document, treating an already absent file as deleted."""
        try:
            self.resolve_storage_key(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            logger.exception("Failed to delete stored document")
            raise DocumentStorageError("The stored document could not be deleted.") from exc

    def discard_staged_upload(self, staged_upload: StagedUpload) -> None:
        """Remove temporary data regardless of whether validation succeeded."""
        try:
            staged_upload.temporary_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to clean staged PDF upload")
