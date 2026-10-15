# OCRLab Backend

## Requirements

- Python 3.11
- PostgreSQL for application persistence
- pip and Git

## Local setup

From the repository root:

\`\`\`powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
$env:PYTHONPATH = "backend"
uvicorn app.main:app --app-dir backend --reload
\`\`\`

Set \`DATABASE_URL\` and \`JWT_SECRET_KEY\` in \`backend/.env\`. The supplied signing secret is development-only. Configure a unique, high-entropy secret for every deployment; production startup rejects the development placeholder. Never commit \`.env\` or production secrets.

Open API documentation at \`http://127.0.0.1:8000/docs\`; health check: \`http://127.0.0.1:8000/api/v1/health\`.

## Implemented API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | \`/api/v1/auth/register\` | Create account |
| POST | \`/api/v1/auth/login\` | Authenticate and set HttpOnly refresh cookie |
| POST | \`/api/v1/auth/refresh\` | Rotate refresh token and issue access token |
| POST | \`/api/v1/auth/logout\` | Revoke the session represented by the refresh cookie |
| POST | \`/api/v1/auth/logout-all\` | Revoke all sessions for the authenticated user |
| GET | \`/api/v1/auth/me\` | Return the authenticated user's public profile |
| GET | \`/api/v1/sessions\` | List sessions belonging to the authenticated user |
| DELETE | \`/api/v1/sessions/{session_id}\` | Revoke an owned session |
| POST | \`/api/v1/documents\` | Validate and upload a PDF |
| GET | \`/api/v1/documents\` | List owned documents with pagination |
| GET | \`/api/v1/documents/{document_id}\` | Retrieve owned document metadata |
| DELETE | \`/api/v1/documents/{document_id}\` | Delete an owned document |
| GET | \`/api/v1/health\` | API liveness check |

Protected endpoints require an \`Authorization: Bearer <access_token>\` header. Login/refresh return access tokens in JSON; refresh tokens are only sent as HttpOnly cookies and are never returned in JSON. Browser clients must send credentials for refresh/logout requests.

## OCR adapter foundation

The OCR layer under `app/core/ocr/` defines a shared adapter contract, implements Tesseract, and includes bounded incremental PDF-to-PNG page rendering. The renderer enforces configurable DPI, page-count, dimension, and pixel limits. Python packages are installed from the pinned requirements file, but the native Tesseract executable and language data must be installed separately. See [OCR adapter documentation](app/core/ocr/README.md) for setup and validation details.

## PDF ingestion

- Upload uses multipart/form-data with the field name \`file\`.
- The file's extension and MIME type are not trusted; the backend checks the PDF signature and parses the document with PyMuPDF.
- Uploads are copied to private staging storage in bounded chunks. Size is enforced while streaming, and SHA-256 is calculated in the same pass.
- Empty, malformed, encrypted, zero-page, too-many-page, and excessive-page-dimension PDFs are rejected.
- The backend stores generated storage keys, not client-provided paths. Responses never expose the internal storage key or content digest.
- Document metadata is scoped to the authenticated user. Other users receive a not-found response when they request a document by ID.
- Local file storage is a development/single-instance adapter. Production multi-instance deployment should use a private object-storage adapter.

Default limits:
- Maximum upload size: 25 MiB.
- Maximum page count: 100.
- Maximum width or height: 14,400 PDF points.

Configure these with \`DOCUMENT_STORAGE_ROOT\`, \`MAX_DOCUMENT_UPLOAD_BYTES\`, \`MAX_PDF_PAGES\`, and \`MAX_PDF_PAGE_DIMENSION_POINTS\`.

## Database and migrations

- \`app/db/base.py\`: shared SQLAlchemy declarative base.
- \`app/db/database.py\`: reusable engine, session factory and request-scoped session dependency.
- \`app/db/repositories/\`: persistence queries.
- \`app/models/\`: user, session, refresh-token, and document ORM models.
- \`migrations/versions/20261015_0001_auth_tables.py\`: initial authentication schema.
- \`migrations/versions/20261015_0002_documents.py\`: document metadata schema.
- \`app/core/auth/service.py\` and \`app/core/documents/service.py\`: domain use cases and transaction boundaries.

Run migrations from \`backend/\` after configuring a reachable development database:

\`\`\`powershell
$env:PYTHONPATH = "."
alembic upgrade head
\`\`\`

Review migration scripts before applying them. To inspect history, run \`alembic history\`. CI validates offline SQL generation, but PostgreSQL migration upgrade/downgrade has not yet been verified against a live PostgreSQL instance.

## Validation

From the repository root:

\`\`\`powershell
$env:PYTHONPATH = "backend"
python -m compileall -q backend/app backend/tests backend/migrations
python -m pytest backend/tests -q
\`\`\`

GitHub Actions passed on commit `c862ecbab097837ca3c529ec5d0feafbedcb918e`: Python compilation, offline Alembic SQL generation, and 21 tests passed. Run: https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38724195724. Document API tests use an isolated in-memory SQLite database and temporary private storage. They do not establish PostgreSQL migration compatibility or production filesystem durability.

## Security boundaries and known gaps

- Passwords use Argon2id; refresh tokens are high-entropy opaque values stored only as SHA-256 digests.
- Access JWTs expire quickly and are checked against database account/session state on every protected request.
- Refresh-token reuse revokes its session.
- Refresh cookie is HttpOnly, SameSite=Strict, and Secure in production. Current assumptions are same-site frontend/API. Cross-site deployment needs explicit CSRF/cookie review.
- Login/register rate limiting, email verification, password reset, audit events, malware scanning, retention automation, and production monitoring are not yet implemented.
- A process crash can leave an orphan file between file finalization and database commit. Deletion can also leave an inaccessible orphan if the filesystem is unavailable after metadata commit. Add a reconciliation job before production deployment.
- Local filesystem storage is not suitable for horizontally scaled API instances without shared private storage and coordination.
- Do not expose the API publicly until rate limiting, HTTPS, production secret management, PostgreSQL migration tests and operational controls are in place.
