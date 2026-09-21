# Deploy And Rollback Checklist

Date: 2026-04-30

## Before Deploy

- Capture current `git status --short`.
- Run backend compile checks.
- Run release smoke locally on the server.
- Confirm `/health` is healthy.
- Confirm `docs/implementation/CURRENT_EXECUTION_STATUS.md` is updated.

## Deploy

- Upload changed files.
- Restart backend only when backend code changed.
- Do not restart nginx unless routes or certificates changed.
- After restart, wait a few seconds and check `/health`.

## Rollback

- Keep previous changed files available before overwriting.
- If backend fails to start, restore previous file version and restart backend.
- If frontend is broken, restore previous `frontend/chat.html` and hard refresh browser cache.
- If docs are broken, restore the affected markdown/html file.

## Never Do Without Explicit Approval

- Delete production database.
- Run destructive git reset.
- Replace `.env`.
- Disable authentication on private routes.
