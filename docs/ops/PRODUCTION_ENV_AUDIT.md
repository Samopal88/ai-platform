# Production Environment Audit

This runbook covers the environment gates that must be true before paid release and the scaffolding state that can be prepared before real secrets are available.

## Core command

```bash
cd /opt/ai-workspace/storage/projects/ai-platform
python3 scripts/production_env_audit.py
```

## What the audit checks

- active backend env file exists
- PostgreSQL rehearsal env file exists
- required paid-release keys are present in the active env file
- placeholder secret values are detected and reported explicitly
- `DATABASE_URL` points to PostgreSQL
- YooKassa credentials are present
- SMTP host and sender are present
- `ENVIRONMENT=production`
- `AUTO_CREATE_DB_TABLES=false`
- RuAPI gateway variables are available when using RuAPI as the primary model provider path
- action items are emitted in the order an operator should close them

## Expected paid-release target

- `ok_for_paid_release_env = true`
- `database_url_family = postgresql`
- `environment = production`
- `auto_create_db_tables = false`
- no `missing_required`
- no `placeholder_required`

## Notes

- The audit intentionally does not print secret values.
- Use `backend/.env.postgres.rehearsal` to prepare the PostgreSQL migration rehearsal before changing the main runtime `.env`.
- `BACKEND_ENV_FILE=/path/to/file python3 scripts/production_env_audit.py` can be used to audit a non-default env file such as the rehearsal config.
