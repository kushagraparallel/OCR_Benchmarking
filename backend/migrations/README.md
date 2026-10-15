# Database Migrations

Alembic tracks schema changes as versioned Python scripts. The current metadata is empty because application ORM models have not been introduced yet.

- Keep migration scripts committed alongside the model change they represent.
- Review generated `upgrade()` and `downgrade()` operations before applying them.
- Do not call `Base.metadata.create_all()` from application startup; schema changes must be explicit migrations.
- Import every model module from `env.py` before generating migrations.
- Use a development database for migration testing before applying changes to shared environments.
