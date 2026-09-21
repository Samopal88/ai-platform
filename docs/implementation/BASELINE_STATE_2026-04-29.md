# Baseline State

Date: 2026-04-29
Project path: `/opt/ai-workspace/storage/projects/ai-platform`

## Git

Current branch:

```text
main
```

Git status:

```text
Very dirty.

Includes modified product code, docs, frontend files, tests, runtime DB files,
pycache files, and many untracked generated/runtime files.

Important examples:
- backend/.env modified
- backend/ai_workspace.db modified
- storage/app.db untracked
- storage/auth_acceptance.json untracked
- many __pycache__ files modified/untracked
- backend/app/api/auth.py untracked
- backend/app/core/auth_token.py untracked
- backend/alembic/ untracked
- frontend/privacy.html and frontend/terms.html untracked
- docs/AUDIT_TO_PRODUCTION_PLAN_2026-04-29.md untracked
- docs/IMPLEMENTATION_EXECUTION_PLAN_2026-04-29.md untracked
```

## Runtime Health

Backend health response:

```json
{"status":"healthy","redis":"ok","version":"0.1.0","service":"AI Workspace Platform","timestamp":"2026-04-29T09:05:07.035150+00:00","runtime_started_at":"2026-04-23T11:50:59.388681+00:00","runtime_code_stamp":"2c64b8ba97b6a2c9"}
```

Service checks:

```text
ai-platform systemd service: inactive
redis service: active
```

Interpretation:

- Backend is reachable on `127.0.0.1:8000`.
- The named `ai-platform` systemd service is not the active backend service or is not currently running.
- Redis is active and backend health can ping it.

## File Counts

```text
backend/app Python files: 78
frontend top-level files: 8
tests/test_*.py files: 8
```

## Runtime/Data Files Present

These files exist and must not be deleted casually:

```text
backend/.env
backend/ai_workspace.db
storage/app.db
storage/auth_acceptance.json
```

## Baseline Conclusion

The project has a live backend and a large amount of useful implementation work, but the repository is not clean enough for production development. Phase 1 must stabilize git hygiene and reproducibility before feature work.

