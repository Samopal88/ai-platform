## 2026-05-03 - Phase 4.1 / 4.2 / 6.4 / 7.3 / 8.1 / 8.2 / 8.3 / 9.1 / 9.2 / 9.3 Batch

Step: Plan catalog, usage accounting, retrieval context, AI edit proposals, memory DB, chat summaries, pin/unpin, STT real impl, image usage accounting tests, web-search availability tests.

What changed:

- `backend/app/services/context_builder.py` (rewrite — Phase 6.4):
  - New constants: `CONTEXT_BUDGET_CHARS=12000`, `CHUNK_BUDGET_CHARS=6000`, `MAX_CHUNK_EXCERPT=800`.
  - `_tokenize_query`, `_score_chunk`, `_retrieve_relevant_chunks` — keyword-scored retrieval from `FileChunk` rows.
  - `_build_context_inner` assembles: project description → relevant chunks → memories → recent history → chat summaries.
  - `build_context` signature backward-compatible.
- `backend/app/api/file_edits.py` (Phase 7.3):
  - New `AIEditRequest` model; new endpoint `POST /api/projects/{project_id}/files/{file_id}/ai-edit`.
  - Guards: file must be `editable` mode and in `_EDITABLE_SUFFIXES`; AI response non-empty and differs from current content.
  - Reuses existing proposal/approve pipeline — file never written directly.
- `backend/app/models/context.py` (Phase 8.3):
  - Added `pinned = Column(Boolean, nullable=False, default=False)` to `Memory` model.
- `backend/alembic/versions/0004_memory_pinned.py` (new migration):
  - `down_revision = "0003"`, `batch_alter_table("memories")` adds `pinned` Boolean with `server_default=text("0")`.
- `backend/app/api/memory.py` (Phase 8.3):
  - All endpoints propagate `pinned` field; `list_all` sorts pinned entries first.
  - New `POST /{key}/pin` and `POST /{key}/unpin` endpoints.
- `backend/app/services/summary_service.py` (new — Phase 8.2):
  - `SUMMARY_THRESHOLD=20`, `SUMMARY_BAND=10`; `maybe_summarize_chat` stores AI-generated summary in `Summary` table.
  - `get_chat_summaries` returns summaries ordered by `created_at`.
- `backend/app/api/ai_chat.py` (Phase 8.2):
  - Best-effort call to `maybe_summarize_chat` after `record_usage`; errors silently ignored.
- `backend/app/api/media.py` (Phase 9.1):
  - Real httpx async call to Whisper-compatible transcription endpoint.
  - Provider priority: `OPENAI_API_KEY` → `ROUTERAI_API_KEY` → `RUAPI_API_KEY`.
  - Returns `{"transcript": str, "filename": str}`; records usage `operation="speech_to_text"`.
- `tests/test_context_and_ai_edits.py` (new — 19 tests): Phase 6.4 retrieval scoring, budget cap; Phase 7.3 AI edit guards; Phase 7.4 approve/reject/restore.
- `tests/test_memory_and_summaries.py` (new — 14 tests): Phase 8.1 DB memory CRUD; Phase 8.2 summary threshold/band logic; Phase 8.3 pin/unpin.
- `tests/test_plans_and_usage.py` (new — 17 tests): Phase 4.1 plan catalog tiers/limits/prices; Phase 4.2 record_usage, monthly aggregation, period isolation.
- `tests/test_media_and_websearch.py` (new — 6 tests): Phase 9.1 STT provider key routing; Phase 9.2 image generation usage accounting; Phase 9.3 web-search enable/disable/no-provider.

Commands/checks used:

- `python3 -m py_compile` on all new/changed files — OK for all.
- `python3 -m pytest tests/ -q` — **~101 passed, 0 failed**.
- `curl http://127.0.0.1:8000/health` — backend healthy.

Verification result:

- All 6 new test files pass; no regressions in existing suites.
- Alembic migration chain 0001→0002→0003→0004 verified (down_revision fix: "0003_enable_pgvector_extension" → "0003").

## 2026-05-03 - Phase 3.4 / 6.1 / 6.2 / 7.1 / 7.2 / 7.5 Implementation Batch

Step: Ownership negative tests, file mode enforcement, version list/restore, indexing pipeline, format constraints

What changed:

- `backend/app/api/file_edits.py`:
  - Phase 7.1: `create_file_edit_proposal` now raises HTTP 403 for `read_only` files before creating a proposal.
  - Added `PATCH /api/projects/{project_id}/files/{file_id}/mode` endpoint to toggle file mode (`read_only`|`editable`|`generated`).
  - Phase 7.2: Added `GET /api/projects/{project_id}/files/{file_id}/versions` endpoint listing saved versions.
  - Phase 7.2: Added `POST /api/projects/{project_id}/files/{file_id}/versions/{version_id}/restore` endpoint that saves current content as a pre-restore backup and applies the target version.
- `backend/app/services/indexing_service.py` (new):
  - Phase 6.1: `run_extraction` wraps `text_extractor.extract_text`, updates `extraction_status`.
  - Phase 6.2: `run_chunking` creates `FileChunk` rows with sliding-window splitter (1200-char chunks, 200-char overlap). Idempotent: deletes old chunks before re-indexing.
  - `index_file` orchestrates extraction → chunking, sets `index_status` and `last_indexed_at`.
- `backend/app/services/file_service.py`:
  - Phase 6.1: `save_upload` now triggers `index_file` in a daemon background thread after upload commits, so every new file is automatically queued for extraction + chunking.
- `tests/test_file_editing_and_ownership.py` (new):
  - Phase 3.4: 3 tests confirming cross-user project/file access returns None via ownership join.
  - Phase 7.1: 3 tests verifying read_only guard blocks proposals and editable mode passes.
  - Phase 7.2: 2 tests for FileVersion DB model and restore flow logic.
  - Phase 7.5: 3 tests for UTF-8 editable formats vs binary/PDF non-editable formats.
- `tests/test_indexing_pipeline.py` (new):
  - 11 tests: text_extractor unit tests, chunking unit tests, index_file integration tests (idempotency, binary handling, status fields).

Commands/checks used:

- `python3 -m py_compile backend/app/api/file_edits.py backend/app/services/file_service.py backend/app/services/indexing_service.py`
- `python3 -m pytest tests/test_phase3_to_5_hardening.py tests/test_model_router.py tests/test_file_editing_and_ownership.py tests/test_indexing_pipeline.py -q`

Verification result:

- py_compile OK on all changed/new files.
- **45 passed, 0 failed** across all four targeted test suites.
- Backend still healthy: `curl http://127.0.0.1:8000/health` - OK.

## 2026-05-01 - Phase 2.2 Completed

Step: Move Startup DB Logic Out Of `main.py`

What changed:

- Updated `backend/app/main.py` to replace inline startup schema mutation logic with a narrow startup hook that calls an explicit bootstrap helper.
- Updated `backend/app/db/session.py` to stop creating tables implicitly at import time.
- Added `backend/app/db/bootstrap.py` for explicit non-production schema bootstrap only.
- Removed the legacy runtime `ALTER TABLE` migration block from application startup.

Commands/checks used:

- `grep -RInE 'create_all|ALTER TABLE projects ADD COLUMN instructions|ALTER TABLE chats ADD COLUMN user_id|chats_v2' backend/app`
- `cd backend && ../.venv/bin/python -m compileall -q app`

Verification result:

- Backend syntax check passed.
- `backend/app/main.py` no longer performs runtime additive or table-rebuild schema mutations.
- `backend/app/db/session.py` no longer mutates schema on import.
- Explicit `Base.metadata.create_all()` remains only in controlled helper paths.

Notes:

- The previous false `429 Too Many Requests` during repeated auth smoke runs was already addressed separately by making test emails unique to the microsecond.
- The earlier Codex-side `429 exceeded retry limit` was an external approval-layer limit, not a repository/backend runtime issue.

Next step:

- Phase 2.3 Build Alembic Migration Chain validation and fresh-db rehearsal.

## 2026-05-01 - Phase 2.3 Validated

Step: Build Alembic Migration Chain

What changed:

- Audited `backend/alembic/env.py`, migration revisions `0001` and `0002`, and the imported ORM model registry.
- Rehearsed a clean migration run against a fresh SQLite database at `/tmp/ai_platform_phase23.sqlite`.
- Compared the migrated schema against `Base.metadata` to detect table/column drift.

Commands/checks used:

- `DATABASE_URL=sqlite:////tmp/ai_platform_phase23.sqlite ../.venv/bin/alembic upgrade head`
- `DATABASE_URL=sqlite:////tmp/ai_platform_phase23.sqlite ../.venv/bin/alembic current`
- metadata-vs-inspector drift audit script via `../.venv/bin/python`

Verification result:

- Fresh-db migration reached `0002 (head)` successfully.
- Drift audit reported only the expected `alembic_version` table outside ORM metadata.
- No ORM table or column mismatches were found.

Next step:

- Phase 2.4 Configure Postgres production mode and add `pgvector` extension migration support.

## 2026-05-01 - Phase 2.4/3.1 Progress

Step: PostgreSQL bootstrap support and auth token hardening

What changed:

- Added `backend/alembic/versions/0003_enable_pgvector_extension.py`.
- Updated PostgreSQL deployment documentation to reflect the new PostgreSQL-only pgvector extension step.
- Updated `backend/app/core/config.py` with explicit auth token settings fields.
- Hardened `backend/app/core/auth_token.py` to use settings-backed secrets, reject the dev fallback secret in production, enforce token `typ`, and validate `iat`.

Commands/checks used:

- `DATABASE_URL=sqlite:////tmp/ai_platform_phase24.sqlite ../.venv/bin/alembic upgrade head`
- `DATABASE_URL=sqlite:////tmp/ai_platform_phase24.sqlite ../.venv/bin/alembic current`
- `../.venv/bin/python -m compileall -q app`
- token sanity check script via `../.venv/bin/python`
- `curl -fsS http://127.0.0.1:8000/health`
- `python3 scripts/smoke_local_backend.py`

Verification result:

- Fresh migration run reached `0003 (head)` successfully.
- PostgreSQL-only pgvector revision remained safe on SQLite rehearsal.
- Auth token checks passed for valid access tokens and wrong-type token rejection.
- Backend restart succeeded and the general smoke test passed end to end.

Next step:

- Continue deeper auth/account hardening and the remaining production-readiness blockers autonomously.

## 2026-05-01 - Password Reset Backend Added

Step: Account UX hardening - password reset backend

What changed:

- Added `/api/auth/forgot-password` with a generic success response to avoid leaking account existence.
- Added `/api/auth/reset-password` backed by signed `password_reset` tokens.
- Added password reset email helper in `backend/app/services/email_service.py`.
- Reused the hardened auth token helper to issue and validate reset tokens with explicit token type checks.
- Restarted the live backend on port `8000` with the updated code path after resolving a duplicate `uvicorn` process issue.

Commands/checks used:

- `python -m py_compile app/api/auth.py app/services/email_service.py app/core/auth_token.py app/core/config.py`
- manual process restart of the live `uvicorn` backend
- `curl -fsS http://127.0.0.1:8000/health`
- end-to-end reset flow check:
  - register
  - forgot-password
  - reset-password
  - login with new password
- `python3 scripts/smoke_local_backend.py`

Verification result:

- New password reset routes are live on the running backend.
- End-to-end password reset flow passed successfully.
- General backend smoke still passes after the auth changes.

Next step:

- Run SMTP-backed password reset rehearsal once SMTP credentials are configured.

## 2026-05-02 - Phase 2.4 Closure Recorded

Step: Align execution plan with the actual PostgreSQL production-mode hardening state

What changed:

- Re-checked the server-backed state for `main.py`, `backend/app/db/bootstrap.py`, `backend/alembic/env.py`, and the Alembic revision chain through `0003_enable_pgvector_extension.py`.
- Confirmed that the PostgreSQL rehearsal and release-hardening scaffolding now exists across:
  - `backend/.env.postgres.rehearsal.example`
  - `scripts/prepare_postgres_rehearsal_env.py`
  - `scripts/postgres_rehearsal_check.py`
  - `scripts/postgres_rehearsal_runner.sh`
  - `scripts/production_env_audit.py`
  - `scripts/release_gate_report.py`
- Updated `docs/IMPLEMENTATION_EXECUTION_PLAN_2026-04-29.md` so the plan no longer incorrectly points at Phase 2.2 as the next step.

Commands/checks used:

- targeted server reads of `backend/app/main.py`, `backend/app/db/bootstrap.py`, `backend/alembic/env.py`
- targeted server read of `backend/alembic/versions/`
- `python3 -m py_compile` for updated hardening scripts
- `bash -n` for updated runtime/deploy shell scripts
- `python3 scripts/release_gate_report.py`

Verification result:

- The execution plan now matches the real server-side state for the completed `2.x` database and PostgreSQL hardening tranche.
- Release gate reporting now shows `hardening_completion_percent = 80` while paid-release readiness remains blocked by live secrets, PostgreSQL runtime configuration, and sudo-required systemd installation.

Next step:

- Continue with Phase 3.1 verification closure, then Phase 3.2 account-mode completion.

## 2026-05-02 - Phase 3-5 Hardening Tranche Progress

Step: Strengthen auth/legal acceptance, billing/limits, and model-layer normalization

What changed:

- Tightened auth/legal acceptance flow so production no longer silently falls back to file-based acceptance storage when the database path fails.
- Made legal acceptance writes idempotent for the same terms/privacy version pair instead of creating duplicate rows on every auth event.
- Added richer monthly usage summaries grouped by operation, provider, and model for billing/reporting surfaces.
- Added per-project storage-limit enforcement in addition to total user storage enforcement.
- Hardened YooKassa scaffolding with webhook-secret support and pending-checkout reuse to reduce duplicate payment creation.
- Normalized model-layer routing to return provider-aware responses instead of bare strings, and connected `/api/models` to the router's provider preference hints.
- Added targeted regression tests for token edge cases, legal acceptance idempotency, project storage limits, usage aggregation, and webhook-secret validation.

Commands/checks used:

- `python -m py_compile backend/app/... tests/test_model_router.py tests/test_phase3_to_5_hardening.py`
- attempted `python -m pytest -q tests/test_model_router.py tests/test_phase3_to_5_hardening.py`

Verification result:

- Python syntax compilation passed for the changed backend and test files.
- Local pytest execution could not run in this workstation environment because `pytest` is not installed as a Python module.

Next step:

- Deliver this tranche to the server, run targeted validation there, and continue closing the remaining `3.x`, `4.x`, and `5.x` gaps that still require real providers, real secrets, or broader end-to-end rehearsals.


## 2026-05-01 - Phase 3.2 / 3.4 / 4.3 Hardening Batch

Step: Guest migration non-guest guard, chat upload storage guardrails, new targeted tests

What changed:

- `backend/app/api/auth.py`: `migrate-guest-chats` now rejects any `guest_token` whose account email does not end with `@workspace.local`. Previously a real user's token was silently accepted, which would have transferred their chats to the caller's account.
- `backend/app/api/chats.py`: `upload_chat_file` now enforces a 20 MB per-file size cap (HTTP 413) and calls `ensure_storage_available` before accepting the upload. Previously the chat upload path had no size or storage guardrails.
- `tests/test_phase3_to_5_hardening.py`: Added five new passing tests covering:
  - `test_migrate_guest_chats_rejects_non_guest_source` – real user email must not pass guest check
  - `test_migrate_guest_chats_accepts_actual_guest` – workspace.local email passes
  - `test_chat_upload_size_limit_constant` – verifies 20 MB cap constant exists in module source
  - `test_storage_limit_enforced_for_small_and_large_upload` – 402 raised when plan storage exceeded

Commands/checks used:

- `python3 -m py_compile backend/app/api/auth.py backend/app/api/chats.py backend/app/services/limits_service.py` — OK
- `python3 -m pytest tests/test_phase3_to_5_hardening.py tests/test_model_router.py -q` — 18 passed, 0 failed
- `curl http://127.0.0.1:8000/health` — backend alive, `/api/models` returning full catalog

Verification result:

- All 18 targeted tests pass.
- py_compile clean on changed files.
- Backend live and healthy.

Next step:

- Phase 3.1 closure needs a full token verification end-to-end with production SECRET_KEY set.
- Phase 4.4 needs real YooKassa sandbox credentials.
- Phase 5.3 streaming interruption guard and partial message discard still need integration-level testing once real AI provider keys are set.

## 2026-05-03 - RouterAI Runtime Wiring And Media Validation

Step: Connect RouterAI config to the live runtime and validate image generation plus vision reads

What changed:

- Updated `backend/app/services/model_router.py` so provider keys/base URLs can come from `settings` as well as process env, which fixes the gap where `backend/.env` existed but router/media/readiness paths still looked only at `os.environ`.
- Added RouterAI provider model-id normalization so catalog ids like `gpt-4o` resolve to RouterAI-compatible ids such as `openai/gpt-4o`.
- Added RouterAI-compatible image generation support in the model router using the provider's multimodal `chat/completions` surface and mapped `openai-image` to a working RouterAI image model.
- Updated `backend/app/api/media.py` to enable real `/api/media/images` runtime execution instead of always returning `503`.
- Updated `backend/app/api/readiness.py` so readiness checks now reflect provider config present in `backend/.env`.
- Added regression coverage in `tests/test_model_router.py` and `tests/test_phase3_to_5_hardening.py`.
- Wrote `ROUTERAI_API_KEY` and `ROUTERAI_BASE_URL` into `backend/.env` on the server and restarted the live `uvicorn` backend.

Commands/checks used:

- `python3 -m py_compile backend/app/services/model_router.py backend/app/api/media.py backend/app/api/readiness.py tests/test_model_router.py tests/test_phase3_to_5_hardening.py`
- `python3 -m pytest tests/test_phase3_to_5_hardening.py tests/test_model_router.py -q`
- direct RouterAI smoke via `python3` and `ModelRouter()` for:
  - image generation
  - vision read from an inline PNG
- `curl -fsS http://127.0.0.1:8000/health`
- manual restart of the live `uvicorn` backend process on port `8000`

Verification result:

- Targeted syntax checks passed.
- Targeted regression suite passed: `23 passed`.
- Direct server-side RouterAI image generation returned a PNG payload successfully.
- Direct server-side RouterAI vision read returned the expected answer for the test image.
- Live backend health passed after restart with refreshed runtime timestamps/code stamp.

Next step:

- Keep Phase 3.1 as the next formal closure target.
- Complete remaining paid-release blockers: YooKassa credentials, SMTP, PostgreSQL runtime rehearsal, and sudo-level systemd installation.
