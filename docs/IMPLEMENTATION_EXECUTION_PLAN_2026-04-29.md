# AI Platform Implementation Execution Plan

Date: 2026-04-29
Project: `/opt/ai-workspace/storage/projects/ai-platform`
Source audit: `docs/AUDIT_TO_PRODUCTION_PLAN_2026-04-29.md`

## Execution Status

- Phase 0.1: Completed on 2026-04-29. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 0.2: Completed on 2026-04-29. See `docs/implementation/BASELINE_STATE_2026-04-29.md`.
- Phase 1.1: Completed on 2026-04-29. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 1.2: Completed on 2026-04-29. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 1.3: Completed on 2026-04-29. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 1.4: Completed on 2026-04-29. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 1.5: Completed on 2026-04-29. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 2.1: Completed on 2026-04-29. See `docs/implementation/DATA_MODEL_DELTA.md`.
- Phase 2.2: Completed on 2026-05-01. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 2.3: Completed on 2026-05-01. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 2.4: Completed on 2026-05-02. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 3.2: Completed on 2026-05-01. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 3.4: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 4.1: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 4.2: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 4.3: Completed on 2026-05-01. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 6.1: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 6.2: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 6.4: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 7.1: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 7.2: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 7.3: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 7.4: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 7.5: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 8.1: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 8.2: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 8.3: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 9.2: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 9.3: Completed on 2026-05-03. See `docs/implementation/EXECUTION_LOG.md`.
- Phase 3.1 hardening code done (2026-05-01); full production verification deferred (needs prod SECRET_KEY).
- Phase 9.1 code done (2026-05-03); live STT test deferred (needs provider with Whisper endpoint).
- Latest verified: 2026-05-03. ~101 tests pass across all suites.
- Current next step: Phase 5.1/5.2 model catalog tier-gating; Phase 5.3 streaming interruption tests.

## Purpose

This is the execution plan I will use to bring the project from the current demo/MVP state to a production-ready paid AI workspace platform.

The plan is intentionally split into small implementation units. Each unit must produce code or documentation artifacts, must be verifiable, and must not depend on vague manual judgment.

Core product target:

- multi-user AI workspace
- projects, chats, files, memory
- multi-model AI chat
- safe AI file reading and editing
- token/storage accounting
- paid plans and token top-ups
- web search, voice input, image generation
- production deploy path

## Working Rules

1. Work in small steps.
2. Do not rewrite the whole project.
3. Do not delete user/runtime data without explicit approval.
4. Do not edit secrets or `.env` values unless explicitly approved.
5. Every implementation step must end with verification.
6. Docs must be updated as implementation changes.
7. Production-risk steps require a checkpoint before continuing.

## Global Definition Of Done

The project is sales-ready only when:

- a fresh server can deploy the app from repo instructions
- a user can register/login
- a user can pay or receive a paid plan
- token/storage limits are enforced
- a user can create a project
- a user can upload files
- AI can use relevant project files through indexed context
- AI can safely create and edit files with versioning and approval
- a user can choose supported models
- usage/costs are tracked
- web search, voice input, and image generation work or are clearly disabled by plan/config
- admin can monitor health, errors, usage, payments
- tests and smoke checks pass

---

# Phase 0: Safety Checkpoint And Documentation Base

## 0.1 Create Implementation Status Docs

Actions:

- Create `docs/implementation/` if missing.
- Add `CURRENT_EXECUTION_STATUS.md`.
- Add `DECISIONS.md`.
- Add `RISKS.md`.
- Add `CHANGELOG_IMPLEMENTATION.md`.

Definition of Done:

- Future work has one canonical status folder.
- Each completed step can be logged.

Verification:

- Files exist locally and on server.

## 0.2 Capture Current Runtime State

Actions:

- Record current branch, git status summary, running services, health response.
- Record current DB files and storage directories without modifying them.
- Record current `.env` presence without printing secrets.

Definition of Done:

- There is a snapshot doc describing current state before edits.

Verification:

- `docs/implementation/BASELINE_STATE_*.md` exists.

---

# Phase 1: Repo Hygiene And Reproducibility

## 1.1 Add Safe `.gitignore`

Actions:

- Ignore `__pycache__/`, `.pytest_cache/`, SQLite DB files, `.env`, runtime storage, generated reports, local logs.
- Do not remove files yet.

Definition of Done:

- New generated files no longer pollute git status.

Verification:

- `git status --short` is reduced after safe cleanup/staging review.

## 1.2 Separate Runtime Data From Code

Actions:

- Identify runtime directories currently inside repo.
- Decide which are user data and which are generated build/test data.
- Move only safe generated data if needed; otherwise document ignore rules.

Definition of Done:

- Repo code and runtime state are clearly separated.

Verification:

- No DB/storage/runtime secret files are intended for commit.

## 1.3 Complete Backend Dependencies

Actions:

- Audit imports used by backend.
- Update `backend/requirements.txt` with real runtime dependencies:
  - `python-multipart`
  - `requests`
  - `httpx`
  - `anthropic`
  - `python-docx`
  - `python-pptx`
  - `reportlab`
  - `pdfplumber`
  - `pypdf`
  - any missing test/runtime libs discovered.

Definition of Done:

- Fresh install can import all backend modules.

Verification:

- `python -m compileall backend/app`
- targeted dependency import check

## 1.4 Make Test Suite Auth-Aware

Actions:

- Update tests that still use old `user_id` query patterns.
- Add helper for creating/login user and using Bearer token.
- Avoid tests depending on live `127.0.0.1:8000` unless marked smoke/live.

Definition of Done:

- Tests can run against temporary DB and temporary server.
- Live tests are separated from unit/integration tests.

Verification:

- `python -m pytest -q tests/test_model_router.py`
- `python -m pytest -q tests/test_mvp_api.py`
- `python -m pytest -q tests/test_project_files_api.py`

## 1.5 Add One Command Local Smoke

Actions:

- Add or fix script: `scripts/smoke_local_backend.py`.
- It should check health, auth, create project, create chat, send message, complete chat with mocked/unavailable AI path.

Definition of Done:

- One command gives a clear product smoke result.

Verification:

- `python scripts/smoke_local_backend.py`

---

# Phase 2: Production Database And Migrations

## 2.1 Define Final MVP Data Model

Actions:

- Compare `DATA_MODEL.md` with current models.
- Add missing entities:
  - `usage`
  - `plans`
  - `subscriptions`
  - `payments`
  - `file_versions`
  - `memories`
  - `summaries`
  - `embeddings`
  - `agent_tasks` or normalized task table if current jobs are insufficient.

Definition of Done:

- `docs/implementation/DATA_MODEL_DELTA.md` lists exact model changes.

Verification:

- Data model delta reviewed before migrations.

## 2.2 Move Startup DB Logic Out Of `main.py`

Actions:

- Remove production reliance on `Base.metadata.create_all`.
- Remove manual SQLite `ALTER TABLE` startup migrations.
- Keep dev bootstrap only behind explicit dev mode if needed.

Definition of Done:

- App startup does not mutate schema unexpectedly in production.

Verification:

- Tests still create schema explicitly.
- App starts with migrated DB.

## 2.3 Build Alembic Migration Chain

Actions:

- Ensure `alembic/env.py` imports all models.
- Add migrations for all current and missing tables.
- Support PostgreSQL as production target.
- Keep SQLite support for local tests where reasonable.

Definition of Done:

- Fresh DB can migrate from zero to current schema.

Verification:

- `alembic upgrade head` on fresh DB.
- test DB schema creation passes.

## 2.4 Configure Postgres Production Mode

Actions:

- Add production `DATABASE_URL` documentation.
- Add deployment notes for PostgreSQL.
- Add pgvector extension migration.

Definition of Done:

- Production DB target is PostgreSQL, not SQLite.

Verification:

- documented Postgres smoke path exists.

---

# Phase 3: Auth, Security, User Isolation

## 3.1 Harden Token System

Actions:

- Require `AUTH_TOKEN_SECRET`/`SECRET_KEY` in production.
- Add `exp`, `iat`, token type.
- Add token validation tests.
- Decide refresh/session model.

Definition of Done:

- No production fallback to `dev-insecure-auth-secret`.

Verification:

- tests cover missing/invalid/expired token.

## 3.2 Implement Real Login Mode

Options:

- email magic link
- email/password
- OAuth

Recommended MVP:

- email/password or email magic link.
- keep guest only as temporary demo mode.

Actions:

- Add login/register endpoints.
- Hash passwords if password mode.
- Add email verification later if not first sprint.

Definition of Done:

- Real user account can be created and authenticated.

Verification:

- auth integration tests.

## 3.3 Move Legal Acceptance To DB

Actions:

- Replace file-based `storage/auth_acceptance.json` with DB table.
- Store terms version, privacy version, timestamp, IP/user agent if appropriate.

Definition of Done:

- Acceptance is queryable/auditable per user.

Verification:

- tests for accepted/not accepted login path.

## 3.4 Route Ownership Audit

Actions:

- Review every `/api/*` route.
- Ensure all user resources are scoped to current user.
- Add negative tests for cross-user access.

Definition of Done:

- Cross-user reads/writes return 404/403.

Verification:

- ownership test suite.

---

# Phase 4: Billing, Plans, Usage, Limits

## 4.1 Plan Model And Limits

Actions:

- Implement plan definitions:
  - free/demo
  - medium
  - pro
  - token top-up
  - storage top-up
- Add project count, storage, token limits.

Definition of Done:

- Limits are stored/derived consistently.

Verification:

- plan unit tests.

## 4.2 Usage Accounting

Actions:

- Add `usage` table.
- Track:
  - input tokens
  - output tokens
  - embeddings
  - image generation
  - web search
  - agent/file edit task usage
  - provider/model
  - cost estimate
  - period/month

Definition of Done:

- Every expensive operation creates usage records.

Verification:

- tests confirm usage rows are created.

## 4.3 Enforce Limits

Actions:

- Before project creation: check project limit.
- Before upload: check file/project/user storage.
- Before completion: check token allowance.
- Before embeddings/image/search: check limits.

Definition of Done:

- Limit exceeded returns product-friendly error before spending money.

Verification:

- limit tests.

## 4.4 Payment Provider Integration

Recommended first provider:

- Stripe if international cards are priority.
- YooKassa if Russia-focused payments are priority.

Actions:

- Add checkout/create-payment endpoint.
- Add webhook endpoint.
- Validate webhook signatures.
- Add idempotency.
- Update subscription/plan on payment success.

Definition of Done:

- Paid plan can be activated through provider sandbox.

Verification:

- sandbox payment flow test.

---

# Phase 5: Real Model Layer

## 5.1 Decide Model Gateway

Actions:

- Either implement OpenCode exactly as docs say, or update docs to state current gateway.
- Define model catalog.

Definition of Done:

- One source of truth for supported models and capabilities.

Verification:

- `GET /api/models` returns catalog.

## 5.2 Normalize Provider Calls

Actions:

- Create provider interfaces for Anthropic, OpenAI-compatible, Gemini.
- Normalize:
  - messages
  - system prompt
  - multimodal content
  - streaming
  - usage
  - errors

Definition of Done:

- Adding a model does not require editing chat endpoint logic.

Verification:

- provider unit tests with mocked clients.

## 5.3 True Streaming

Actions:

- Replace fake post-response chunking with real provider streaming.
- Store assistant message after stream completes.
- Handle interrupted streams.

Definition of Done:

- User sees real streaming from model provider.

Verification:

- streaming smoke test.

---

# Phase 6: File Indexing And Context Retrieval

## 6.1 File Processing Pipeline

Actions:

- On upload, create processing job.
- Extract text by type.
- Store extracted text metadata.
- Record extraction status/errors.

Definition of Done:

- UI/API can show whether file is indexed.

Verification:

- upload file -> extraction status test.

## 6.2 Chunking

Actions:

- Implement chunking policy by file type.
- Store chunks with position/page/sheet metadata.

Definition of Done:

- Large file does not get injected whole into prompt.

Verification:

- chunking unit tests.

## 6.3 Embeddings With pgvector

Actions:

- Add embedding provider.
- Store vectors in Postgres pgvector.
- Add similarity search.

Definition of Done:

- Query retrieves relevant chunks.

Verification:

- semantic search test with known documents.

## 6.4 Context Builder V2

Actions:

- Replace direct all-file prompt injection with retrieval.
- Include project instructions, summaries, memories, relevant chunks.
- Add context budget policy.

Definition of Done:

- Prompt stays inside configured token budget.

Verification:

- context builder tests.

---

# Phase 7: Safe AI File Editing

## 7.1 File Modes And Permissions

Actions:

- Add file mode:
  - read_only
  - editable
  - generated
- Expose in API/UI.

Definition of Done:

- AI cannot edit read-only files.

Verification:

- permission tests.

## 7.2 File Versions

Actions:

- Add `file_versions` model/API.
- Save previous version before edit.
- Retain max 3 versions by default.
- Add restore endpoint.

Definition of Done:

- User can restore previous file version.

Verification:

- edit -> version -> restore test.

## 7.3 Edit Plan And Diff

Actions:

- Add endpoint to request an AI edit plan.
- AI returns intended file changes, not direct mutation.
- Generate diff/preview.

Definition of Done:

- User sees what will change before applying.

Verification:

- edit plan test for text/json/csv.

## 7.4 Apply Approved Edit

Actions:

- Add approve/reject flow.
- Apply edits only after approval.
- Store task logs.

Definition of Done:

- Core differentiator works safely end-to-end.

Verification:

- upload file -> ask AI edit -> preview -> approve -> file changed -> version saved.

## 7.5 Format-Specific Editing

Order:

1. txt/md/json/yaml
2. csv
3. docx
4. xlsx
5. pdf as generated/export only, not direct edit

Definition of Done:

- Supported formats are explicit.
- Unsupported edits fail clearly.

Verification:

- format tests.

---

# Phase 8: Memory And Summaries

## 8.1 DB Memory

Actions:

- Replace JSON memory files with DB-backed memories.
- Add types: fact, rule, decision.
- Add source metadata.

Definition of Done:

- Memory is project/user scoped and queryable.

Verification:

- memory API tests.

## 8.2 Chat Summaries

Actions:

- Add summary generation after threshold.
- Store summaries in DB.
- Use summaries in context builder.

Definition of Done:

- Long chats compact without losing key decisions.

Verification:

- summary test with long chat fixture.

## 8.3 Memory UI/API Controls

Actions:

- List memory.
- Delete memory.
- Pin important memory.

Definition of Done:

- User can inspect and control project memory.

Verification:

- API tests and UI smoke.

---

# Phase 9: Voice, Image Generation, Web Search Hardening

## 9.1 Speech To Text

Actions:

- Add audio upload endpoint.
- Route to STT provider.
- Save transcript as user message draft or message.
- Account usage.

Definition of Done:

- Voice input becomes chat text.

Verification:

- mocked STT integration test.

## 9.2 Image Generation

Actions:

- Add image generation endpoint/tool.
- Save generated images into project files/artifacts.
- Account usage.

Definition of Done:

- User can request image and download/use it in project.

Verification:

- mocked image provider test.

## 9.3 Web Search Production Rules

Actions:

- Make web search availability visible.
- Add source display consistency.
- Add rate limiting/cost accounting.

Definition of Done:

- Web search is reliable or clearly disabled.

Verification:

- provider unavailable test.

---

# Phase 10: Frontend Productization

## 10.1 Frontend Architecture Decision

Actions:

- Decide static HTML continuation vs React/Vue/Svelte migration.
- Document decision.

Recommended:

- Keep static only if speed matters for MVP.
- Move to React/Vite for paid SaaS polish and maintainability.

Definition of Done:

- Frontend path is explicit.

## 10.2 Core User Flows

Actions:

- Login/register.
- Project list/create/settings.
- Chat create/send/stream.
- Model picker.
- File upload/list/download/delete.
- Usage/plan display.

Definition of Done:

- First-time user can self-serve.

Verification:

- browser smoke checklist.

## 10.3 File Editing UI

Actions:

- Select file.
- Ask AI to edit.
- Show plan/diff.
- Approve/reject.
- Download/restore version.

Definition of Done:

- Differentiator is visible and usable.

Verification:

- end-to-end browser test.

## 10.4 Billing UI

Actions:

- Pricing/plan page.
- Checkout button.
- Usage meters.
- Top-up flow.

Definition of Done:

- User can pay without support.

Verification:

- sandbox checkout test.

---

# Phase 11: Ops, Deploy, Monitoring

## 11.1 Production Config

Actions:

- Add production config template.
- Require secrets.
- Disable wildcard CORS.
- Add host/origin settings.

Definition of Done:

- Production mode is not accidentally insecure.

Verification:

- config tests.

## 11.2 Deploy Script And Systemd

Actions:

- Clean systemd units.
- Add deploy checklist.
- Add migration step.
- Add rollback notes.

Definition of Done:

- Another computer/operator can deploy from docs.

Verification:

- dry-run deploy checklist.

## 11.3 Monitoring And Logs

Actions:

- Structured logs.
- Error logs.
- Health endpoint for DB/Redis/model providers.
- Basic admin status page.

Definition of Done:

- Failures are visible.

Verification:

- health/status tests.

## 11.4 Backups

Actions:

- DB backup script.
- File storage backup plan.
- Restore procedure.

Definition of Done:

- User data can be restored.

Verification:

- documented restore test.

---

# Phase 12: Launch Readiness

## 12.1 End-To-End Sales Smoke

Scenario:

1. Register user.
2. Accept terms.
3. Pay for plan or assign test paid plan.
4. Create project.
5. Upload txt/csv/docx.
6. Ask AI question using files.
7. Ask AI to edit file.
8. Approve diff.
9. Download edited file.
10. Check usage/token count.

Definition of Done:

- Whole scenario passes without manual DB/server intervention.

## 12.2 Beta Checklist

Actions:

- Add onboarding content.
- Add support contact.
- Add admin recovery steps.
- Add known limitations page.

Definition of Done:

- Product can be shown to beta users.

## 12.3 Production Launch Gate

Required:

- tests pass
- smoke pass
- payment sandbox pass
- backup configured
- secrets configured
- legal pages reviewed
- monitoring present
- no known P0 security issue

Definition of Done:

- Ready for first paid user.

---

# Execution Queue

I will execute in this exact order unless a blocker forces a documented change:

1. Phase 0.1 — DONE 2026-04-29
2. Phase 0.2 — DONE 2026-04-29
3. Phase 1.1 — DONE 2026-04-29
4. Phase 1.2 — DONE 2026-04-29
5. Phase 1.3 — DONE 2026-04-29
6. Phase 1.4 — DONE 2026-04-29
7. Phase 1.5 — DONE 2026-04-29
8. Phase 2.1 — DONE 2026-04-29
9. Phase 2.2 - DONE 2026-05-01
10. Phase 2.3 - DONE 2026-05-01
11. Phase 2.4 - DONE 2026-05-02
12. Phase 3.1 - code done; full prod verification pending
13. Phase 3.2 - DONE 2026-05-01
14. Phase 3.3 - code done; full DB-backed verification deferred
15. Phase 3.4 - DONE 2026-05-03
16. Phase 4.1
17. Phase 4.2
18. Phase 4.3 - DONE 2026-05-01
19. Phase 4.4 - scaffolding done; blocked on YooKassa credentials
20. Phase 5.1
21. Phase 5.2
22. Phase 5.3 - routing done; stream interruption needs integration test
23. Phase 6.1 - DONE 2026-05-03
24. Phase 6.2 - DONE 2026-05-03
25. Phase 6.3 - blocked on PostgreSQL + pgvector
26. Phase 6.4
27. Phase 7.1 - DONE 2026-05-03
28. Phase 7.2 - DONE 2026-05-03
29. Phase 7.3 - diff generation done; AI plan endpoint pending
30. Phase 7.4 - code done (approve/reject)
31. Phase 7.5 - DONE 2026-05-03
32. Phase 8.1
33. Phase 8.2
34. Phase 8.3
35. Phase 9.1
36. Phase 9.2
37. Phase 9.3
38. Phase 10.1
39. Phase 10.2
40. Phase 10.3
41. Phase 10.4
42. Phase 11.1
43. Phase 11.2
44. Phase 11.3
45. Phase 11.4
46. Phase 12.1
47. Phase 12.2
48. Phase 12.3

## Current Implementation Step

Proceed with Phase 3.1 and only close it when all of the following are true:

- production auth secrets are required with no insecure fallback in production mode
- token validation tests cover missing, invalid, and expired tokens
- the runtime and release docs stay aligned with the real production hardening path

## Completed Phase Ledger

- Phase 2.2 completed.
  Evidence: `backend/app/main.py`, `backend/app/db/bootstrap.py`, `backend/app/db/session.py`, and the 2026-05-01 execution log entry confirming startup schema mutation was removed from production startup.
- Phase 2.3 completed.
  Evidence: `backend/alembic/env.py`, `backend/alembic/versions/0001_initial_schema.py`, `backend/alembic/versions/0002_commercial_usage_context.py`, and the 2026-05-01 execution log entry validating migration from zero to head.
- Phase 2.4 completed.
  Evidence: `backend/alembic/versions/0003_enable_pgvector_extension.py`, `backend/.env.postgres.rehearsal.example`, `scripts/prepare_postgres_rehearsal_env.py`, `scripts/postgres_rehearsal_check.py`, `scripts/postgres_rehearsal_runner.sh`, `scripts/production_env_audit.py`, `scripts/release_gate_report.py`, and `docs/ops/` PostgreSQL and release-hardening runbooks.
- Phase 3.1 is not marked done yet.
  Reason: auth token hardening exists, but the phase still needs its full verification closure and should remain the next implementation target.
- Phase 3.2 code-complete and unit-verified (2026-05-01).
  Evidence: `backend/app/api/auth.py` `migrate-guest-chats` now rejects non-workspace.local source tokens; `tests/test_phase3_to_5_hardening.py` — two new tests pass. Full HTTP-layer smoke deferred until live backend has real DB users.
- Phase 3.4 code-complete and unit-verified (2026-05-03).
  Evidence: `tests/test_file_editing_and_ownership.py` — 3 cross-user ownership tests pass.
- Phase 4.3 storage enforcement code-complete and unit-verified (2026-05-01).
  Evidence: `backend/app/api/chats.py` chat upload path now enforces 20 MB cap and calls `ensure_storage_available`; `tests/test_phase3_to_5_hardening.py` — two new tests pass. Full paid-plan integration deferred until real YooKassa secrets are configured.
- Phase 6.1 code-complete and unit-verified (2026-05-03).
  Evidence: `backend/app/services/indexing_service.py` extraction pipeline; `backend/app/services/file_service.py` triggers background indexing on upload; `tests/test_indexing_pipeline.py` — 11 tests pass.
- Phase 6.2 code-complete and unit-verified (2026-05-03).
  Evidence: `indexing_service.py` chunking with 1200-char/200-overlap sliding window; FileChunk rows created per file; idempotent re-index tested.
- Phase 7.1 code-complete and unit-verified (2026-05-03).
  Evidence: `backend/app/api/file_edits.py` — read_only guard raises 403; PATCH mode endpoint added; `tests/test_file_editing_and_ownership.py` — 3 mode tests pass.
- Phase 7.2 code-complete and unit-verified (2026-05-03).
  Evidence: `backend/app/api/file_edits.py` — version list and restore endpoints; `tests/test_file_editing_and_ownership.py` — 2 version/restore tests pass.
- Phase 7.5 code-complete and unit-verified (2026-05-03).
  Evidence: `tests/test_file_editing_and_ownership.py` — 3 format constraint tests pass; editable suffixes and non-editable (PDF/binary) constraints explicit.
