# MVP Gap Report
## AI Workspace Platform — What Remains Before MVP Is Real

**Date:** 2026-04-19

---

## End-to-End MVP Flow Audit

The MVP flow: user opens chat, creates project, creates chat, sends message, gets AI response.

| Step | Status | Blocker |
|---|---|---|
| 1. Open frontend chat page | BLOCKED BY STUB | Page loads but all API calls return 404 |
| 2. Load existing projects | BLOCKED BY ROUTING | `GET /api/projects` → 404, router not registered |
| 3. Create a project | BLOCKED BY ROUTING | `POST /api/projects` → 404 |
| 4. Open/create a chat | BLOCKED BY ROUTING | `POST /api/projects/{id}/chats` → 404 |
| 5. Load message history | BLOCKED BY ROUTING | `GET /api/chats/{id}/messages` → 404 |
| 6. Send a user message | BLOCKED BY STUB | `POST /api/chats/{id}/messages` → 404 |
| 7. Persist the message | BLOCKED BY DATABASE | SQLAlchemy not installed; get_db() raises exception |
| 8. Trigger AI completion | BLOCKED BY STUB | `POST /api/chats/{id}/complete` → 404; ModelRouter is `def file(): pass` |
| 9. Persist assistant response | BLOCKED BY DATABASE | Same as step 7 |
| 10. Refresh and see conversation | BLOCKED BY ALL ABOVE | Nothing is ever persisted |

**Every single step of the MVP flow is broken.**

---

## Gap Inventory — What Must Be Built

All 13 recovery tasks in MVP_RECOVERY_ROADMAP.md remain outstanding.
Status of each (honest):

| Task | Description | Actual Status |
|---|---|---|
| R1 | Uncomment SQLAlchemy in requirements.txt | RETRY_REQUIRED — worker keeps writing docs |
| R2 | Fix db/session.py: real SQLite engine | NOT STARTED |
| R3 | Fix main.py: startup DB init | NOT STARTED |
| R4 | Fix schemas/project.py: UUID id field | NOT STARTED (schema has `id: int`) |
| R5 | Implement project_service.py | NOT STARTED (stub: `def crud(): pass`) |
| R6 | Implement api/projects.py | NOT STARTED (stub: `def fastapi(): pass`) |
| R7 | Implement schemas/chat.py | NOT STARTED (stub: `def main(): pass`) |
| R8 | Implement chat_service.py | NOT STARTED (stub: `def crud(): pass`) |
| R9 | Implement api/chats.py | NOT STARTED (stub: `def chat(): pass`) |
| R10 | Implement model_router.py | NOT STARTED (stub: `def file(): pass`) |
| R11 | Implement api/ai_chat.py | NOT STARTED (stub: `def main(): pass`) |
| R12 | Register all 5 product routers in main.py | NOT STARTED (routers are stubs so registration would also stub) |
| R13 | Create smoke_mvp.py | NOT STARTED |

**13/13 recovery tasks not genuinely complete. 0/13 done.**

---

## Additional Gaps Beyond R1–R13

These are not in the recovery roadmap but are also broken:

1. **schemas/chat.py** — stub. R7 must fix this before R8 can work.
2. **schemas/file.py** — stub. File upload will be blocked.
3. **schemas/project.py** — `id: int` vs model `UUID`. Type mismatch will cause runtime errors even after services are implemented.
4. **User model / auth** — `Project` has a `user_id` FK to `users` table. No user creation flow exists. Either auth must be removed from the MVP scope or a default user must be seeded.
5. **Project.user_id NOT NULL** — the schema requires a user_id on every project. Without auth, every `POST /api/projects` will fail at the DB level.
6. **alembic** — not installed. Tables cannot be created via migration. R2/R3 workaround (create_all at startup) will work for SQLite dev only.
7. **context_builder.py** — stub. AI completion will fail or ignore history.
8. **file_service.py, text_extractor.py** — stubs. File features blocked entirely.
9. **memory_service.py** — stub.

---

## Semantic Validator Gap — Root Cause of All False Accepts

The semantic validator only triggers stub detection when a file has `len(all_defs) >= 2`
pass-only functions. Every falsely-accepted stub has exactly ONE function body (`def crud():
pass`, `def main(): pass`, etc.), which bypasses this guard.

**Fix required:** Remove the `>= 2` guard or add a single-function stub pattern.

---

## Schema / Model Mismatch Summary

| Schema | Field | Schema Type | Model Type | Status |
|---|---|---|---|---|
| ProjectRead.id | id | int | UUID | BROKEN — will fail on real DB rows |
| ChatRead | entire class | stub | real Chat model | MISSING |
| MessageRead | entire class | stub | real Message model | MISSING |
| FileRead | entire class | stub | real File model | MISSING |

---

## Realistic Work Estimate

Assuming the manager can reliably execute 1 stub-to-real task per cycle (after the
stub-detection fix):

- R1: 1 cycle (already on retry, brief is now correct)
- R2–R4: 3 cycles
- R5–R6 (project service + API): 2 cycles
- R7–R9 (chat schemas + service + API): 3 cycles  
- R10–R11 (model_router + ai_chat): 2 cycles
- R12 (main.py router registration): 1 cycle
- R13 (smoke test): 1 cycle
- user_id constraint resolution: 1 cycle
- Semantic validator single-stub fix: manual (30 min)

**Minimum: ~15 cycles to a runnable MVP with clean execution.**

With the current false-accept vulnerability still present (single-function stubs), each
of those cycles risks creating another stub and claiming it done. The validator must be
fixed before running auto-mode.
