# Database Infrastructure

## Purpose

This module owns SQLAlchemy engine creation, the declarative ORM base, and request-scoped session lifecycle. API routers should depend on services; services can receive a `Session` dependency or repository abstraction as later phases introduce domain persistence.

## Current implementation

- `base.py` defines the shared SQLAlchemy `DeclarativeBase` used by model classes and Alembic metadata.
- `database.py` creates one application engine and one reusable `sessionmaker` at import time. Creating the engine does not open a network connection.
- `get_database_session()` yields a session and rolls back when an exception escapes the dependency. The context manager closes the session on exit.
- `DATABASE_URL` is read through the typed `Settings` model in `app/config.py`.

The initial default URL is intended only for local development. Override it for your environment and never commit real credentials.

## Migrations

Alembic configuration lives in `backend/alembic.ini`; migration scripts and the environment are under `backend/migrations/`. Import each ORM model module from `migrations/env.py` as domain models are added, so `Base.metadata` contains the expected tables before autogeneration.

Run commands from the `backend/` directory:

```powershell
$env:PYTHONPATH = "."
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
alembic downgrade -1
```

Review every generated migration before applying it. Autogeneration is a draft, not a substitute for schema review.

## Not implemented yet

No application tables or production database connection check are added in this phase. User/session/document/benchmark models will be introduced in their own reviewed changes. SQLite is used only in unit tests to verify SQLAlchemy engine/session behavior without requiring a running PostgreSQL server.
