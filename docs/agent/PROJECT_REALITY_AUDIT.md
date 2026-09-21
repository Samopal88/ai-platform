# Project Reality Audit
## AI Workspace Platform — Brutally Honest Technical Assessment

**Audit Date:** 2026-04-19  
**Auditor:** Claude Code (automated + code inspection)  
**Method:** Direct file reads, content analysis, manager state inspection, end-to-end flow trace

---

## TL;DR

The project has a real, working autonomous development system built on top of a product
that is entirely unimplemented stubs. Every product API, every product service, and the
database layer are `def func(): pass` placeholders. The manager accepted them as complete.
The autonomous system is real. The product it was supposed to build is not.

---

## Layer 1 — Product Backend

### requirements.txt
**BROKEN**  
SQLAlchemy is commented out (`# sqlalchemy==2.0.35`). No aiosqlite. No alembic.  
The app cannot persist anything. R1 in MVP_RECOVERY_ROADMAP addresses this but has not
been completed (currently stuck in retry_required with the worker writing to docs instead).

### backend/app/db/session.py
**STUB / BROKEN**  
`get_db()` raises `DatabaseNotConfigured` immediately if `configure_database()` was never
called. `configure_database()` is never called anywhere in main.py or at startup.  
`FileBasedSession` exists but its `.query().all()` returns `[]`, `.first()` returns `None`,
`.add()` is a no-op, `.commit()` is a no-op. It is cosmetic dead code.

### backend/app/db/base.py
**REAL BUT NOT WIRED**  
`Base`, `TimestampMixin`, `get_engine`, `get_session_factory`, `create_all_tables` are
real SQLAlchemy code. But `create_all_tables()` is never called. No engine is created at
startup. The code exists but is never executed.

### backend/app/models/ (project, chat, message, user)
**REAL BUT NOT WIRED**  
All four models are complete, well-formed SQLAlchemy declarative models with correct
columns, types (UUID primary keys), relationships commented-out-but-present, and proper
inheritance from Base/TimestampMixin. The models are good.  
**However:** they are never imported in main.py, never registered against the Base
metadata for table creation, and never called from any service (because all services are stubs).

### backend/app/schemas/project.py
**REAL BUT WRONG**  
`ProjectRead.id` is typed `int`. The `Project` model uses `UUID(as_uuid=True)` primary key.
These are incompatible. Any serialization of a real project row would fail or silently
truncate the UUID.

### backend/app/schemas/chat.py
**STUB**  
`def main(): pass`. The file exists with a task description docstring and nothing else.

### backend/app/schemas/file.py
**STUB**  
`def main(): pass`.

### backend/app/api/projects.py
**STUB**  
`def fastapi(): pass`. No APIRouter. No routes. Not imported anywhere in main.py.

### backend/app/api/chats.py
**STUB**  
`def chat(): pass`. No APIRouter. No routes. Not registered.

### backend/app/api/ai_chat.py
**STUB**  
`def main(): pass`. No APIRouter. No routes. Not registered.

### backend/app/api/files.py
**STUB**  
`def main(): pass`. No APIRouter. No routes. Not registered.

### backend/app/api/memory.py
**STUB**  
`def main(): pass`. No APIRouter. No routes. Not registered.

### backend/app/services/project_service.py
**STUB**  
`def crud(): pass`.

### backend/app/services/chat_service.py
**STUB**  
`def crud(): pass`.

### backend/app/services/model_router.py
**STUB**  
`def file(): pass`. No ModelRouter class.

### backend/app/services/file_service.py
**STUB**  
`def main(): pass`.

### backend/app/services/memory_service.py
**STUB**  
`def main(): pass`.

### backend/app/services/context_builder.py
**STUB**  
`def main(): pass`.

### backend/app/services/text_extractor.py
**STUB**  
`def file(): pass`.

### backend/app/main.py
**REAL BUT PARTIAL**  
The file is a real FastAPI app. It registers: dashboard, jobs, runner, manager routers.
It does NOT register: projects, chats, ai_chat, files, memory routers — because tasks
6.4, 7.3, 8.4, 10.3 (which claimed to register them) all wrote only to docs/system_architecture.md
and never touched main.py. The "router registration" tasks were falsely accepted.

### Migrations / Alembic
**MISSING**  
No alembic directory. No migration scripts. No migration history.

---

## Layer 2 — Product Frontend

### frontend/chat.html
**STRUCTURALLY PRESENT BUT UNPROVEN**  
The chat UI is a real three-panel layout (projects, chats, messages). The JavaScript
calls real endpoint paths:
- `GET /api/projects` → 404 (router not registered)
- `POST /api/projects` → 404
- `GET /api/projects/{id}/chats` → 404
- `POST /api/projects/{id}/chats` → 404
- `GET /api/chats/{id}/messages` → 404
- `POST /api/chats/{id}/messages` → 404
- `POST /api/chats/{id}/complete` → 404

The frontend is correct in what it tries to call. But every call returns 404.
A user opening chat.html sees a blank panel with "No projects yet" forever.

### frontend/dashboard.html
**REAL AND WORKING** (operator layer)  
The dashboard correctly polls `/api/manager/human-status`, renders manager state,
provides Run Cycle / Run Auto / Reset buttons. This is the operator interface,
not the product. It works for its intended purpose.

---

## Layer 3 — Autonomous Development System

### manager_loop.py
**REAL AND WORKING**  
Full lifecycle: selecting → planning → executing → reviewing → verdict.
Fix task builder on retry is real. State persistence is real.

### task_intake.py
**REAL AND WORKING** (with recent fix)  
Roadmap parsing, recovery roadmap parsing, task selection with repair-queue priority,
`resolve_product_context`, `build_execution_prompt`. The `_build_must_not_touch` bug
(target file listed as protected) was fixed in this session but the manager_state.json
still contains the old broken brief as `current_step`.

### reference_pack.py
**REAL AND WORKING** (with recent fix)  
Doc excerpt extraction, interface signature extraction, protected_paths bug fixed.

### false_accept_auditor.py
**REAL BUT INSUFFICIENT**  
`check_doc_only_acceptance` correctly detects when only docs changed. However, it did
not prevent the false accepts of tasks 6.x–10.x because those stubs did have the
target file listed in files_changed (the worker created stub files). The stub detection
path in semantic_validator only catches stubs when ALL functions in the file have pass
bodies — but single-function stubs (`def crud(): pass`) have exactly that pattern and
the `len(all_defs) >= 2` guard requires at least 2 functions to trigger.

### semantic_validator.py
**REAL BUT HAS A CRITICAL GAP**  
The single-function stub guard is disabled by the `len(all_defs) >= 2` condition (line ~394).
A file with exactly one `def crud(): pass` passes validation. This is how all the task
6.x–10.x stubs were accepted: they each have exactly one stub function.

### repair_queue.py
**REAL AND WORKING**  
Queue structure, add/consume, priority ordering function correctly.

### executive_memory.py
**REAL AND WORKING**  
JSON-backed memory, MVP recovery mode detection, get_implemented_summary work.

### phase_gate.py
**STRUCTURALLY PRESENT BUT UNPROVEN**  
Code exists and is called. Whether its verdicts are accurate depends on what it checks —
it cannot verify runtime behavior, only file existence.

### manager_human_status.py
**REAL AND WORKING** (created this session)  
Rule-based operator status with all 8 cases. Verified producing correct output.

---

## Layer 4 — State and Progress Tracking

### docs/progress/manager_state.json
**MISLEADING**  
`accepted_tasks` lists 20 tasks as accepted. The actual files created were stubs or docs.
The `current_step` still contains the old broken brief (with `backend/requirements.txt`
in Must Not Touch) even though the code was fixed — because the state was saved before
the fix and the broken brief will be used on the next retry cycle.

### docs/progress/CURRENT_STATUS.md
**MISLEADING**  
Claims "Verified Complete" for tasks. Those tasks created stubs. The orchestrator
completed sandbox tasks (print statements, queue tests) and claims them as progress.
The "33 jobs" includes trivial sandbox file creation.

### docs/agent/ROADMAP.md
**STRUCTURALLY PRESENT BUT MISLEADING**  
Tasks marked `[x]` (done) include router registration tasks that only changed docs.
The roadmap believes phases 5–10 are mostly complete. They are not.

---

## Layer 5 — Recovery and False-Accept Handling

### MVP Recovery Mode
**REAL AND PARTIALLY FUNCTIONAL**  
The system correctly detects mvp_recovery mode, loads MVP_RECOVERY_ROADMAP.md, and
selects R1 as the first task. The issue is the worker keeps modifying docs. The
`current_step` stored in state still has the pre-fix brief. The next cycle will use
the fix_task path (retry_count=1) which correctly excludes requirements.txt from
Must Not Touch in `_build_fix_task`, so R1 may succeed on the next manual trigger.

### False-Accept Prevention
**REAL BUT INCOMPLETE**  
The doc-only guard works. The stub detection works for multi-function files.
Single-function stubs bypass it. This is the root cause of all the false accepts.
