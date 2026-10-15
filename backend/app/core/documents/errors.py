"""Domain errors raised by PDF document ingestion and storage."""


class DocumentError(Exception):
    """Base class for expected document-domain failures."""


class InvalidPdfError(DocumentError):
    """The uploaded file is not a valid, readable, unencrypted PDF."""


class DocumentTooLargeError(DocumentError):
    """The upload exceeds the configured maximum byte size."""


class PdfLimitExceededError(DocumentError):
    """The PDF exceeds configured page-count or page-dimension limits."""


class DocumentNotFoundError(DocumentError):
    """The requested document does not exist or is not owned by the caller."""


class DocumentStorageError(DocumentError):
    """Private document storage could not safely complete an operation."""
