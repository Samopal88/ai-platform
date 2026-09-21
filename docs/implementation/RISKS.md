# Implementation Risks

## Active Risks

### R1: Dirty Git Tree

Severity: High

The server repo has many modified and untracked files, including `.env`, SQLite DBs, `__pycache__`, generated storage, reports, and product code changes.

Mitigation:

- Phase 1.1 adds safe `.gitignore`.
- Phase 1.2 separates runtime data from code without deleting user data.

### R2: Demo Database Pattern

Severity: High

The current backend uses SQLite by default and startup schema mutation exists in `main.py`.

Mitigation:

- Phase 2 moves schema management to Alembic and production DB to PostgreSQL.

### R3: MVP Auth

Severity: High

Auth token implementation is not production-grade.

Mitigation:

- Phase 3 hardens auth and secrets.

### R4: Core Differentiator Not Complete

Severity: High

AI can read/generate files, but safe AI editing of existing files with versions and approval is not implemented.

Mitigation:

- Phase 7 implements file modes, versions, diff, approve/reject, and apply.

### R5: Python Environment Is Externally Managed

Severity: Medium

`python -m pip install -r backend/requirements.txt` is blocked by PEP 668 in the system Python.

Mitigation:

- Add a project virtualenv or deployment-specific dependency install path before relying on fresh dependency installation.

### R6: Full MVP Pytest Run Times Out

Severity: Medium

Targeted syntax checks and `test_model_router.py` pass, but a broad MVP pytest command timed out.

Mitigation:

- Decompose integration tests.
- Stabilize temporary uvicorn server lifecycle.
- Run live smoke script as the current fast end-to-end confidence check.
