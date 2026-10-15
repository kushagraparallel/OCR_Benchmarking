# PDF Documents

## Responsibilities

This domain validates user-supplied PDFs, writes files to private local storage, and persists user-owned metadata. Routers handle HTTP transport and error translation; services coordinate validation, storage and repository operations.

## Upload safety

- The client filename and MIME type are untrusted. The stored filename is a generated UUID-based key; the original filename is retained only as sanitized display metadata.
- Uploads are streamed in bounded chunks to a private staging directory while enforcing the configured byte limit and computing SHA-256.
- PDF header and parser validation are performed before the file is finalized. Empty, malformed, encrypted, zero-page, oversized-page-count, and excessive-page-dimension PDFs are rejected.
- The service uses an atomic rename from a staging file to the final generated key. If database persistence fails, it attempts to remove the finalized file.
- Document metadata and deletion are scoped by authenticated user ID. A caller cannot retrieve or delete another user's record.
- Storage paths are resolved and validated to prevent path traversal.

## API

- POST /api/v1/documents — upload a PDF as multipart/form-data field \`file\`.
- GET /api/v1/documents — list the current user's documents with pagination.
- GET /api/v1/documents/{document_id} — retrieve owned document metadata.
- DELETE /api/v1/documents/{document_id} — delete an owned document and its metadata.

## Configuration

- \`DOCUMENT_STORAGE_ROOT\`: private filesystem root (default \`./var/ocrlab/documents\`).
- \`MAX_DOCUMENT_UPLOAD_BYTES\`: maximum PDF size (default 25 MiB).
- \`MAX_PDF_PAGES\`: maximum pages per PDF (default 100).
- \`MAX_PDF_PAGE_DIMENSION_POINTS\`: maximum width/height per page in PDF points (default 14,400).

The storage root must be mounted on persistent private storage in deployed environments. The local storage adapter is intended for single-instance development. Multi-instance deployment should replace it with a private object-storage adapter behind the same service boundary.

## Known limitations

- Upload parsing and filesystem operations are synchronous; FastAPI executes synchronous route functions in its thread pool.
- A process crash between file finalization and database commit can leave an orphan file. Deletion can also leave an orphan if the filesystem fails after metadata is committed. Add periodic reconciliation before production deployment.
- Multipart parsing occurs before route-level streaming limits are enforced; configure request-body limits at the reverse proxy/application ingress as well.
- Malware scanning, encrypted PDF support, document retention automation, page rendering, and scanned/digital page classification are not implemented yet.
