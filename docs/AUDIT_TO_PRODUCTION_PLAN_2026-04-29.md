# AI Platform Audit To Production Plan

Date: 2026-04-29
Project path: `/opt/ai-workspace/storage/projects/ai-platform`
Local copy: `C:\Users\Samopal3\Documents\New project\AUDIT_TO_PRODUCTION_PLAN_2026-04-29.md`

## 1. Product Vision Baseline

The target product is a multi-user AI workspace platform:

- chat with multiple AI models
- projects as the main unit of work
- project files as AI context
- AI-assisted file creation and editing
- project memory and summaries
- web search
- voice input
- image generation / image context
- token and storage limits
- paid token/storage plans
- transparent agent task execution with approve/reject/continue

The main differentiator is not just "chat with models". It is project workspaces where AI can read and safely edit user files.

## 2. Current Reality

The project is no longer only a stub. A real backend exists now:

- FastAPI app starts and `/health` returns healthy.
- Redis health is OK.
- SQLite-backed SQLAlchemy session exists.
- Users, projects, chats, messages, files, and chat artifacts have real models.
- Auth exists through email/guest MVP tokens.
- Project CRUD exists and is token-scoped.
- Chat/message CRUD exists and is token-scoped.
- File upload/list/download/delete exists.
- AI completion endpoint exists.
- Web search service exists.
- Generated artifacts exist for txt/csv/json/xlsx/docx/pdf/pptx.
- Frontend `chat.html` and dashboard exist.
- Alembic folder exists.
- A short model router test passed: `6 passed, 3 xfailed`.

But it is not production-ready and not sales-ready.

## 3. Biggest Gaps Against Vision

### P0 Blockers

1. No real paid billing.
   There is no Stripe/YooKassa/etc, no invoices, no plan purchase, no subscription status, no payment webhook, no top-up flow.

2. Token accounting is only approximate metadata.
   `ai_chat.py` estimates tokens as `len(text) // 4`. There is no authoritative usage table, no monthly reset, no per-provider cost, no hard blocking when quota is exceeded.

3. Database is demo-grade.
   Default DB is SQLite. `main.py` creates tables at startup and runs manual SQLite `ALTER TABLE` fixes. This is not a production migration strategy.

4. Auth is MVP-only.
   Tokens are HMAC payloads without expiry. Default secret falls back to `dev-insecure-auth-secret`. No password login, no email verification, no OAuth, no session revocation, no refresh tokens.

5. File editing by AI is not implemented as the core product feature.
   AI can generate artifacts and can read uploaded project files into context, but there is no safe "edit existing file with versioning/diff/approval" workflow.

6. File indexing/embeddings/pgvector are missing.
   Current code injects extracted file text directly into the prompt. Vision requires extraction -> chunking -> embeddings -> indexed search. That is not present.

7. Project memory is file-based key-value storage, not the intended DB-backed memory/summaries system.
   It has TTL and substring search, but no semantic memory, no summaries table, no compaction pipeline.

8. Multi-model layer is not OpenCode.
   `ModelRouter` calls Anthropic SDK or OpenAI-compatible HTTP. Gemini is not actually wired. OpenCode abstraction from docs is missing.

9. Streaming is fake.
   Completion is generated fully, saved, then split into chunks for SSE. This gives UI animation, not true provider streaming.

10. Repo state is unsafe.
    Git tree is very dirty: `.env`, DB files, `__pycache__`, generated storage, reports, and many untracked files are mixed with code. This must be cleaned before serious development.

### P1 Major Missing Product Features

1. Project plans/limits are not enforced.
   User model has token/storage fields, but create/upload/complete flows do not consistently block by plan.

2. Storage accounting is partial.
   Project file counters update on upload/delete, but user total storage is not consistently updated/enforced.

3. File versions are missing.
   Vision requires optional versioning, max 3 versions. There is no `file_versions` implementation in current models/API.

4. Voice input is missing.
   No speech-to-text upload/API pipeline was found in implemented backend.

5. Image generation is missing.
   Vision requires image generation/editing. Current image support is mainly vision input and artifact generation, not image model generation.

6. Agent task runner exists as operator/autopilot layer, but not as safe user-facing project file editor.
   There is lots of autonomous-development machinery, but it is not cleanly productized for end users.

7. Legal/privacy is minimal.
   Terms/privacy pages exist, and acceptance is file-stored. Production needs proper DB audit trail, policy text review, cookie/security posture.

8. Tests are inconsistent with auth.
   Some tests still call old `user_id` query patterns while current API requires Bearer token. This caused large test runs to hang/time out.

9. Requirements are incomplete for runtime behavior.
   Code imports `anthropic`, `httpx`, `requests`, `python-docx`, `python-pptx`, `reportlab`, `pdfplumber`, `pypdf`, `python-multipart`, but `backend/requirements.txt` only lists a small base set.

10. Frontend is static HTML/JS.
    It may be acceptable for an MVP demo, but not for a polished paid product without strong QA.

## 4. What Is Good

- Backend is now real enough to keep and harden.
- Core CRUD foundation exists.
- Ownership checks are present in project/chat/file routes.
- Health endpoint is useful and includes runtime stamp.
- Web search provider chain is practical: SearxNG, Yandex XML, SerpAPI, Serper.
- Artifact generation covers useful office formats.
- The project has strong internal documentation and an explicit AI-agent workflow.
- The product direction is coherent.

## 5. What Is Wrong Architecturally

1. The platform mixed "build automation for this repo" with "the user-facing AI workspace product".
   These must be separated: operator/autopilot can remain internal, but product routes and user flows must be clean.

2. There is no production boundary between demo state and paid state.
   SQLite, file JSON memory, manual migrations, wildcard CORS, insecure secret fallback, and local storage are all demo patterns.

3. The differentiator is underbuilt.
   The key product promise is "AI works with project files and edits them". Current implementation reads/generates files, but does not safely edit existing files.

4. Docs overstate completion.
   Older progress docs mark tasks as complete that were historically stubs. Current code improved, but docs are no longer a reliable source of truth.

## 6. Step-by-Step Plan To Sales-Ready Production

### Phase 1: Stabilize Repo And Runtime

1. Create a clean branch.
2. Add `.gitignore` for `__pycache__`, SQLite DBs, `.env`, runtime storage, reports.
3. Move existing runtime DB/storage out of git scope or explicitly ignore.
4. Freeze current working backend state in an audit checkpoint.
5. Make `requirements.txt` complete.
6. Make tests deterministic and auth-aware.
7. Replace startup `create_all` and manual ALTERs with Alembic-only migrations.

Acceptance:
- clean `git status`
- backend starts from fresh checkout
- tests run without hanging

### Phase 2: Production Auth And Multi-User Isolation

1. Replace insecure dev token fallback with mandatory secret.
2. Add token expiry and refresh/revocation.
3. Decide auth method: email magic link, password, OAuth, or hybrid.
4. Store legal acceptance in DB.
5. Add user deletion/export basics.
6. Audit every API route for user ownership.

Acceptance:
- no endpoint leaks cross-user data
- auth tokens expire
- missing secrets prevent app start in production

### Phase 3: Postgres, Migrations, Data Model

1. Move default production DB to PostgreSQL.
2. Add migrations for users/projects/chats/messages/files/file_versions/memories/summaries/usage/tasks.
3. Add pgvector migration.
4. Add seed/admin scripts.
5. Add backup/restore notes.

Acceptance:
- fresh Postgres deploy migrates cleanly
- SQLite only allowed for local/dev

### Phase 4: Billing, Tokens, Limits

1. Choose provider: Stripe or YooKassa.
2. Add plans table and user subscription state.
3. Add usage table with provider/model/request/response/embedding/image/search costs.
4. Use real provider token usage when available.
5. Enforce token and storage limits before expensive work.
6. Add top-up purchases.
7. Add webhook signature validation and idempotency.

Acceptance:
- user can pay
- limits block reliably
- usage is visible and auditable

### Phase 5: Real Model Layer

1. Decide whether to implement OpenCode as docs say, or document a different supported router.
2. Add Claude/OpenAI/Gemini support with normalized request/response/usage.
3. Add true streaming.
4. Add model catalog with capability flags: text, vision, image, tools, file edit.
5. Add provider error taxonomy and retries.

Acceptance:
- user can choose models per chat/message
- streaming is real
- costs are attributed per model

### Phase 6: File Indexing And Project Context

1. Implement extraction pipeline per file type.
2. Add chunking.
3. Add embeddings creation.
4. Store vectors in pgvector.
5. Search relevant chunks per query instead of injecting all files.
6. Add reindex on upload/edit/delete.

Acceptance:
- large projects work without prompt bloat
- AI cites/uses relevant file chunks

### Phase 7: Safe AI File Editing

1. Add editable/read-only/generated modes to DB/API/UI.
2. Add file versions with max 3 retained.
3. Add edit plan generation.
4. Show diff/preview before applying changes.
5. Require approve for destructive/high-risk edits.
6. Implement format-specific editors for txt/md/json/csv/docx/xlsx.
7. Add rollback.

Acceptance:
- AI can edit an existing file safely
- user can approve/reject
- previous version can be restored

### Phase 8: Memory And Summaries

1. Move memory from JSON files to DB.
2. Add summary generation by chat.
3. Add context compaction policy.
4. Add project facts/rules/decisions memory types.
5. Add UI for viewing/deleting memory.

Acceptance:
- long chats stay useful
- memory is user/project scoped

### Phase 9: Voice, Images, Web

1. Add speech-to-text endpoint.
2. Add image generation endpoint.
3. Add image edit endpoint if in MVP scope.
4. Harden web search availability and source display.
5. Add usage accounting for each tool.

Acceptance:
- voice -> text -> chat works
- image generation saves into project
- web search cites sources in UI

### Phase 10: Frontend Productization

1. Decide whether to keep static HTML or migrate to React/Vue/Svelte.
2. Build polished flows: login, projects, chat, files, usage, billing, settings.
3. Add file editor/diff UI.
4. Add model picker with capability labels.
5. Add responsive/mobile QA.

Acceptance:
- a paying user can self-serve without developer help

### Phase 11: Security And Ops

1. Remove wildcard CORS for production.
2. Add rate limits to expensive routes.
3. Add request size limits.
4. Add logging without secrets.
5. Add monitoring and alerting.
6. Add systemd/deploy docs.
7. Add backups.
8. Add vulnerability/dependency checks.

Acceptance:
- deploy is repeatable
- production failures are observable

### Phase 12: Launch Readiness

1. Run end-to-end QA: signup, pay, create project, upload files, chat, edit file, download result.
2. Add landing/pricing/help pages.
3. Add onboarding demo project.
4. Add admin/support tools.
5. Beta test with real users.

Acceptance:
- first sale can happen without manual database/server intervention

## 7. Immediate Next Implementation Order

I should execute in this order:

1. Clean repo hygiene without deleting user data.
2. Fix dependencies and test suite.
3. Make DB/migrations production-shaped.
4. Harden auth.
5. Implement real usage/billing limits.
6. Build file indexing.
7. Build safe AI file editing/versioning.
8. Add missing voice/image.
9. Productize frontend.
10. Final production deploy QA.

## 8. Current Production Readiness Score

- Demo backend: 55%
- MVP product: 35%
- Paid SaaS readiness: 15%
- Core differentiator readiness: 25%

The project is worth continuing. It has a real skeleton and several useful working parts. But it should not be sold yet.

