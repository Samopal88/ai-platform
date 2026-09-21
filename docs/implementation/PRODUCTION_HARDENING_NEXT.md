# Production Hardening Next Steps

Date: 2026-04-30

This checklist is intentionally limited to work that can be completed before live provider/payment keys are available.

## Phase 5.1 Runtime Mode And Database

- Keep current demo server on SQLite while product UX is still moving quickly.
- Prepare production environment variables:
  - `ENVIRONMENT=production`
  - `AUTO_CREATE_DB_TABLES=false`
  - `DATABASE_URL=postgresql+psycopg://...`
  - `PUBLIC_BASE_URL=https://...`
- Verify Alembic upgrade against a fresh database.
- Keep startup `create_all` only for local/demo mode.

## Phase 5.2 Deploy Reliability

- Add a clear restart script or service file for backend.
- Add a smoke script that checks:
  - `/health`
  - `/chat`
  - `/documentation`
  - `/api/models`
  - auth guest/register/login
  - create chat and complete fallback
  - billing summary
  - media disabled fallback
- Document rollback steps before changing nginx/systemd.

## Phase 5.3 Account UX

- Improve login/register modal copy.
- Add forgot-password placeholder state.
- Add clear guest/account status in sidebar.
- Verify that logout and guest session do not mix histories.

## Phase 5.4 Billing And Limits

- Verify token accounting for chat completions.
- Verify project/file storage limits.
- Verify plan downgrade/upgrade display states.
- Keep checkout disabled until YooKassa keys are configured.

## Phase 5.5 Browser QA

- Desktop smoke: open sidebar, choose model, create chat, send message, open docs, open tariffs.
- Mobile smoke: sidebar drawer, composer, model picker, tariff modal.
- Check that text does not overflow buttons/cards.
- Check that provider-disabled states are understandable.

## Phase 5.6 Git/Runtime Cleanup

- Do not delete runtime data from disk without explicit approval.
- Ensure `.env`, SQLite DB, `__pycache__`, runtime jobs, and storage are ignored.
- Produce a clean commit-ready diff list after separating runtime files from code changes.
