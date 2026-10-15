# OCRLab Backend

## Requirements

- Python 3.11
- pip
- Git
- PostgreSQL for local application persistence (optional for the current SQLite-backed unit tests)

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

Configure `DATABASE_URL` in `backend/.env` for your PostgreSQL instance before adding database-backed features. The example credentials are for local development only. The application engine is created lazily with respect to network access: importing the app does not itself prove the database is reachable.

Open API documentation at `http://127.0.0.1:8000/docs` and check `http://127.0.0.1:8000/api/v1/health`.

## Database and migrations

Database infrastructure is in `app/db/`:

- `base.py` contains the shared SQLAlchemy declarative base.
- `database.py` provides the reusable engine, session factory, and request-scoped session dependency.
- `config.py` exposes `DATABASE_URL` through typed settings.

Alembic configuration and scripts live in `alembic.ini` and `migrations/`. From the repository root:

```powershell
Set-Location backend
$env:PYTHONPATH = "."
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Review generated migrations before applying them. No application tables have been added yet; domain models and migrations will be implemented in later phases.

## Tests and syntax checks

From the repository root with the virtual environment activated:

```powershell
$env:PYTHONPATH = "backend"
python -m compileall -q backend/app backend/tests backend/migrations
python -m pytest backend/tests -q
```

Database infrastructure tests use an in-memory SQLite database and do not require a running PostgreSQL server. A successful test run does not confirm PostgreSQL credentials or connectivity.
