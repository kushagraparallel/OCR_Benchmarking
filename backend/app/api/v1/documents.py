"""HTTP endpoints for uploading and managing private PDF documents."""

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.core.auth.dependencies import CurrentUser, DatabaseSession
from app.core.documents.errors import (
    DocumentNotFoundError,
    DocumentStorageError,
    DocumentTooLargeError,
    InvalidPdfError,
    PdfLimitExceededError,
)
from app.core.documents.service import DocumentService
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.schemas.auth import MessageResponse

router = APIRouter(prefix="/documents", tags=["documents"])


def _raise_document_http_error(error: Exception) -> None:
    """Translate expected document-domain failures into stable HTTP responses."""
    if isinstance(error, DocumentNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from None
    if isinstance(error, DocumentTooLargeError):
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(error)) from None
    if isinstance(error, PdfLimitExceededError):
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(error)) from None
    if isinstance(error, InvalidPdfError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
    if isinstance(error, DocumentStorageError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document storage operation failed.") from None
    raise error


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_pdf_document(
    user: CurrentUser,
    database_session: DatabaseSession,
    file: UploadFile = File(..., description="PDF document to validate and store."),
) -> DocumentResponse:
    """Upload a PDF after streaming size checks and parser-based validation."""
    try:
        document = DocumentService(database_session).upload(file.file, file.filename or "", user.id)
    except (DocumentNotFoundError, DocumentStorageError, DocumentTooLargeError, InvalidPdfError, PdfLimitExceededError) as exc:
        _raise_document_http_error(exc)
    finally:
        file.file.close()
    return DocumentResponse.model_validate(document)


@router.get("", response_model=DocumentListResponse)
def list_pdf_documents(
    user: CurrentUser,
    database_session: DatabaseSession,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of documents to return."),
    offset: int = Query(default=0, ge=0, description="Number of documents to skip."),
) -> DocumentListResponse:
    """List only the authenticated user's documents with bounded pagination."""
    documents = DocumentService(database_session).list_owned(user.id, limit, offset)
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in documents],
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_pdf_document(
    document_id: UUID,
    user: CurrentUser,
    database_session: DatabaseSession,
) -> DocumentResponse:
    """Return metadata for an owned document without exposing its storage path."""
    try:
        document = DocumentService(database_session).get_owned(str(document_id), user.id)
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from None
    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}", response_model=MessageResponse)
def delete_pdf_document(
    document_id: UUID,
    user: CurrentUser,
    database_session: DatabaseSession,
) -> MessageResponse:
    """Delete an owned document and its private file."""
    try:
        DocumentService(database_session).delete_owned(str(document_id), user.id)
    except (DocumentNotFoundError, DocumentStorageError) as exc:
        _raise_document_http_error(exc)
    return MessageResponse(message="Document deleted.")
