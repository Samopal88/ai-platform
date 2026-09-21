# PostgreSQL Deployment Path

Date: 2026-04-29

## Target

Production must use PostgreSQL. SQLite remains acceptable only for local demo/dev and temporary tests.

## Required Environment

```text
ENVIRONMENT=production
AUTO_CREATE_DB_TABLES=false
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
AUTH_TOKEN_SECRET=<strong secret>
```

## Migration Command

Run from `backend/` using the project virtualenv:

```bash
../.venv/bin/python -m alembic upgrade head
```

The current head includes a PostgreSQL-only pgvector bootstrap revision:

- `0003_enable_pgvector_extension.py`
- It is a no-op on SQLite/dev rehearsal databases.
- On PostgreSQL it runs `CREATE EXTENSION IF NOT EXISTS vector`.

## Verification

1. Fresh DB:

```bash
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME ../.venv/bin/python -m alembic upgrade head
```

2. Backend compile:

```bash
../.venv/bin/python -m compileall -q app
```

3. Smoke after service start/restart:

```bash
cd /opt/ai-workspace/storage/projects/ai-platform
python scripts/smoke_local_backend.py
```

## Rollback

Before production migration:

1. Create DB backup.
2. Record current git commit/status.
3. Keep previous service unit command.

If migration fails:

1. Stop app service.
2. Restore DB backup.
3. Restore previous code revision.
4. Start service.
5. Run smoke.

## Notes

- Do not rely on `Base.metadata.create_all()` in production.
- Do not run manual schema `ALTER TABLE` blocks from app startup in production.
- `AUTO_CREATE_DB_TABLES` must be `false` in production.
- Keep the `vector` extension available before enabling pgvector-backed embedding storage.
