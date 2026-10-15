"""Request-independent response schemas for uploaded PDF documents."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    """Public document metadata; internal storage paths and hashes are not exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Opaque identifier for the uploaded document.")
    original_filename: str = Field(..., description="Sanitized original filename for display.")
    size_bytes: int = Field(..., ge=1, description="Size of the stored PDF in bytes.")
    page_count: int = Field(..., ge=1, description="Number of validated pages in the PDF.")
    pdf_title: str | None = Field(None, description="Optional title from PDF metadata.")
    pdf_author: str | None = Field(None, description="Optional author from PDF metadata.")
    status: str = Field(..., description="Document processing state.")
    created_at: datetime = Field(..., description="UTC timestamp when the document was registered.")


class DocumentListResponse(BaseModel):
    """Paginated document metadata belonging to the authenticated user."""

    items: list[DocumentResponse]
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
