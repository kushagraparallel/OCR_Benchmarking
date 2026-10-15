# OCRLab Backend

## Requirements

- Python 3.11
- PostgreSQL for application persistence
- pip and Git

## Local setup

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
$env:PYTHONPATH = "backend"
uvicorn app.main:app --app-dir backend --reload
```

Set `DATABASE_URL` and `JWT_SECRET_KEY` in `backend/.env`. The supplied signing secret is development-only. Configure a unique, high-entropy secret for every deployment; production startup rejects the development placeholder. Never commit `.env` or production secrets.

Open API documentation at `http://127.0.0.1:8000/docs`; health check: `http://127.0.0.1:8000/api/v1/health`.

## Implemented API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Authenticate and set HttpOnly refresh cookie |
| POST | `/api/v1/auth/refresh` | Rotate refresh token and issue access token |
| POST | `/api/v1/auth/logout` | Revoke the session represented by the refresh cookie |
| POST | `/api/v1/auth/logout-all` | Revoke all sessions for the authenticated user |
| GET | `/api/v1/auth/me` | Return the authenticated user's public profile |
| GET | `/api/v1/sessions` | List sessions belonging to the authenticated user |
| DELETE | `/api/v1/sessions/{session_id}` | Revoke an owned session |
| GET | `/api/v1/health` | API liveness check |

Protected endpoints require an `Authorization: Bearer <access_token>` header. Login/refresh return access tokens in JSON; refresh tokens are only sent as HttpOnly cookies and are never returned in JSON. Browser clients must send credentials for refresh/logout requests.

## Database and migrations

- `app/db/base.py`: shared SQLAlchemy declarative base.
- `app/db/database.py`: reusable engine, session factory and request-scoped session dependency.
- `app/db/repositories/auth_repository.py`: authentication persistence queries.
- `app/models/`: user, session and refresh-token ORM models.
- `migrations/versions/20261015_0001_auth_tables.py`: initial authentication schema.
- `app/core/auth/service.py`: authentication use cases and transaction boundaries.

Run migrations from `backend/` after configuring a reachable development database:

```powershell
$env:PYTHONPATH = "."
alembic upgrade head
```

Review migration scripts before applying them. To inspect history, run `alembic history`. CI validates offline SQL generation, but PostgreSQL migration upgrade/downgrade has not yet been verified against a live PostgreSQL instance.

## Validation

GitHub Actions passed on commit `6322d4c293ff78ca6f0ae5bb867c04fe016972c2`:
- Python compilation of application, tests and migrations.
- Offline Alembic SQL generation.
- 14 backend tests passed.

Run the same checks locally from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m compileall -q backend/app backend/tests backend/migrations
python -m pytest backend/tests -q
```

The tests use an isolated in-memory SQLite database. They do not establish PostgreSQL connectivity, migration compatibility, or concurrent refresh-token behavior on PostgreSQL.

## Security boundaries and known gaps

- Passwords use Argon2id; refresh tokens are high-entropy opaque values stored only as SHA-256 digests.
- Access JWTs expire quickly and are checked against database account/session state on every protected request.
- Refresh-token reuse revokes its session.
- Refresh cookie is HttpOnly, SameSite=Strict, and Secure in production. Current assumptions are same-site frontend/API. Cross-site deployment needs explicit CSRF/cookie review.
- Login/register rate limiting, email verification, password reset, audit events, and production monitoring are not yet implemented.
- Do not expose the API publicly until rate limiting, HTTPS, production secret management, PostgreSQL migration tests and operational controls are in place.
