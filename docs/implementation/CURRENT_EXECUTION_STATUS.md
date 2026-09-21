# Current Execution Status

Date: 2026-05-03
Project: `/opt/ai-workspace/storage/projects/ai-platform`

## Current Focus

Phase 4.1/4.2/6.4/7.3/8.x/9.x batch complete. Next implementable: Phase 5.1/5.2 model catalog hardening, Phase 5.3 streaming integration tests.

## Recently Completed

- Phase 2.2-2.4: DB startup refactor, Alembic migration chain, PostgreSQL rehearsal scaffolding.
- Phase 3.1: Auth token secret hardening; token type/expiry validation.
- Phase 3.2: `migrate-guest-chats` rejects non-guest source accounts.
- Phase 3.3 partial: Legal acceptance idempotent per version pair; production no longer falls back to file store.
- Phase 3.4: Cross-user ownership negative test suite (3 tests pass).
- Phase 4.1: Plan catalog (free/starter_490/medium/pro), get/list definitions, price ordering — 6 tests pass.
- Phase 4.2: `record_usage`, `tokens_used_this_month`, `usage_summary_this_month`, period isolation — 5 tests pass.
- Phase 4.3: Chat upload size/storage guardrails.
- Phase 4.4: YooKassa webhook scaffolding; blocked on real credentials.
- Phase 5.x partial: Provider-aware model routing, RouterAI runtime wiring, image generation + vision validated.
- Phase 6.1: Text extraction triggered on upload; extraction_status tracked.
- Phase 6.2: Sliding-window chunking service; FileChunk rows, idempotent re-index; 11 tests pass.
- Phase 6.4: Keyword-scored retrieval from FileChunk pool; budget-capped context assembly; 19 tests pass.
- Phase 7.1: `read_only` guard + mode PATCH endpoint; tests pass.
- Phase 7.2: Version list + restore endpoint; tests pass.
- Phase 7.3: AI-assisted edit proposal endpoint (`ai-edit`); reuses proposal/approve pipeline; tests pass.
- Phase 7.4: Approve/reject/restore hardening; tests pass.
- Phase 7.5: Format constraint test suite (3 tests pass).
- Phase 8.1: DB-backed memory CRUD (`Memory` model, migration 0004 with `pinned` column); tests pass.
- Phase 8.2: Chat summary service (`summary_service.py`), threshold/band gating, stored in `Summary` table; tests pass.
- Phase 8.3: Memory pin/unpin endpoints; sorted list (pinned first); tests pass.
- Phase 9.1: Real STT via httpx → Whisper endpoint; provider priority chain; usage recorded.
- Phase 9.2: Image generation usage accounting test (units_images=1 row created).
- Phase 9.3: `_web_search_available()` guard tests (disabled/no-provider/enabled).

## Verified (2026-05-03 cumulative)

- `python3 -m py_compile` on all changed/new files — OK
- `python3 -m pytest tests/ -q` — **~101 passed, 0 failed**
- `curl http://127.0.0.1:8000/health` — backend healthy

## Phase Status Summary

| Phase | Status | Notes |
|-------|--------|-------|
| 3.1 | code done, partial verified | needs prod SECRET_KEY smoke to fully close |
| 3.2 | **done, tests pass** | non-guest guard unit-verified |
| 3.3 | code done, partial | full verified only with real DB users |
| 3.4 | **done, tests pass** | cross-user ownership negative suite |
| 4.1 | **done, tests pass** | plan catalog, limits, price ordering — 6 tests |
| 4.2 | **done, tests pass** | record_usage, monthly aggregation, period isolation — 5 tests |
| 4.3 | **done, tests pass** | size cap + storage guard on chat upload |
| 4.4 | scaffolding done | pending real YooKassa sandbox keys |
| 5.1/5.2 | partial | `/api/models` exists, RouterAI wired; catalog hardening pending |
| 5.3 | routing done | interrupted-stream discard needs integration-level confirmation |
| 6.1 | **done, tests pass** | extraction triggered on upload |
| 6.2 | **done, tests pass** | chunking service, 11 tests |
| 6.3 | not started | blocked on live PostgreSQL + pgvector |
| 6.4 | **done, tests pass** | keyword-scored retrieval, budget-capped context; 19 tests |
| 7.1 | **done, tests pass** | read_only guard + mode PATCH |
| 7.2 | **done, tests pass** | version list + restore |
| 7.3 | **done, tests pass** | AI-assisted edit proposal via `ai-edit` endpoint |
| 7.4 | **done, tests pass** | approve/reject/restore hardening |
| 7.5 | **done, tests pass** | format constraint suite |
| 8.1 | **done, tests pass** | DB-backed memory CRUD + migration 0004 |
| 8.2 | **done, tests pass** | summary service, threshold/band logic |
| 8.3 | **done, tests pass** | pin/unpin endpoints, sorted list |
| 9.1 | code done | real STT impl; live test needs provider with Whisper endpoint |
| 9.2 | **done, tests pass** | image usage accounting test |
| 9.3 | **done, tests pass** | web-search availability guard tests |

## Remaining Real Blockers

- `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` — no sandbox credentials yet
- `SMTP_*` — no mail relay configured
- `DATABASE_URL` PostgreSQL — still SQLite on dev; rehearsal scripts ready
- Phase 6.3 (pgvector embeddings) — needs live PostgreSQL + pgvector extension
- Phase 9.1 live STT test — needs provider with Whisper-compatible endpoint
- Phase 10 (frontend), Phase 11 (ops/monitoring), Phase 12 (launch readiness) — not yet started
