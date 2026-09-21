# Production Environment Checklist

Date: 2026-04-30

Use this before switching from demo runtime to paid production.

## Required Mode

- `ENVIRONMENT=production`
- `AUTO_CREATE_DB_TABLES=false`
- `PUBLIC_BASE_URL=https://<production-domain>`
- `DATABASE_URL=postgresql+psycopg://...`
- Redis URL points to production Redis.

## Required Before Live Users

- Alembic migrations pass on a fresh database.
- Existing demo SQLite data is not treated as production data.
- Backend restart path is documented and tested.
- Nginx routes `/`, `/chat`, `/documentation`, `/docs-public/*`, and `/api/*` correctly.
- Health endpoint returns healthy after restart.
- Release smoke passes.

## Secrets To Add Last

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- SMTP credentials for password reset and customer emails.

Do not print secret values in logs or documentation.
