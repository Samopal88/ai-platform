# MVP Truth File
## AI Workspace Platform — Product Reality Audit

**Audited:** 2026-04-18  
**Status: NOT RUNNABLE**  
**Root cause: All product APIs are `def main(): pass` stubs. SQLAlchemy is commented out. No database exists. The roadmap marked Phases 4–10 as `[x]` (done) when none of the implementations are real.**

---

## 1. MVP Definition

The minimum runnable product is a platform where a human user can:

1. Open `http://localhost:8000/chat` in a browser
2. See a list of existing projects (or create one via the UI)
3. Select or create a chat inside a project
4. Type and send a message
5. Receive a real AI response (from Claude or a stub that returns something sensible)
6. Close the browser, reopen it, and still see the conversation

**What can be deferred beyond MVP:**
- File upload/download
- Memory/context injection (Phase 10)
- Multi-model routing beyond a single working model
- Advanced dashboard UI (progress files, job queue, autopilot controls)

**What cannot be deferred:**
- Working projects API (CRUD)
- Working chats API (CRUD)  
- Working messages API (store + retrieve)
- Working AI completion endpoint (returns text)
- SQLite persistence (no data loss on restart)
- Routers registered in main.py

**First end-to-end success path:**
```
GET  /chat                       → chat.html loads
GET  /api/projects               → returns []
POST /api/projects               → creates project, returns {id, name}
POST /api/projects/{id}/chats    → creates chat, returns {id, title}
POST /api/chats/{id}/messages    → stores user message
POST /api/chats/{id}/complete    → returns {content: "Hello from AI"}
GET  /api/chats/{id}/messages    → returns [user_msg, assistant_msg]
```

---

## 2. Current Reality Audit

### 2.1 Backend Core

| Component | Status | Evidence |
|---|---|---|
| `backend/app/main.py` | **REAL but incomplete** | Imports dashboard/jobs/runner/manager only. Does NOT import projects/chats/ai_chat/files/memory routers. |
| `backend/requirements.txt` | **BROKEN** | SQLAlchemy and alembic are commented out (`# sqlalchemy==2.0.35`). App cannot use DB. |
| `backend/app/db/session.py` | **FAKE** | Has stub `FileBasedSession` that does nothing. `get_db()` raises `DatabaseNotConfigured` immediately. No `create_engine`, no real session. |
| `backend/app/db/base.py` | **REAL (structural)** | Has Base, TimestampMixin, proper SQLAlchemy setup — but unused because session.py never configures the engine. |
| `backend/app/core/config.py` | **REAL** | Settings with `DATABASE_URL = "sqlite:///./ai_workspace.db"` — correct but never used. |
| No alembic directory | **MISSING** | `backend/alembic/` does not exist. No migrations. No schema creation. |

### 2.2 Models

| Model | Status | Evidence |
|---|---|---|
| `app/models/project.py` | **REAL (structural)** | Has `class Project(Base)` with proper columns. Needs real DB to be useful. |
| `app/models/chat.py` | **REAL (structural)** | Has `class Chat(Base)` with proper columns. |
| `app/models/message.py` | **REAL (structural)** | Has `class Message(Base)` with proper columns. |
| `app/models/user.py` | Unknown — not checked, not MVP critical |
| `app/models/job.py` | Not MVP critical |

Models are **structurally correct** but **never used** — there is no database to attach them to.

### 2.3 Schemas

| Schema | Status | Evidence |
|---|---|---|
| `app/schemas/project.py` | **REAL** | Has `ProjectCreate`, `ProjectUpdate`, `ProjectRead`. `ProjectRead.id` is `int` but model uses UUID — mismatch. |
| `app/schemas/chat.py` | **STUB** | `def main(): pass`. No Pydantic models. |
| `app/schemas/file.py` | **STUB** | `def main(): pass`. No Pydantic models. |

### 2.4 Services

| Service | Status | Evidence |
|---|---|---|
| `project_service.py` | **STUB** | `def crud(): pass`. No create_project, no get_project, nothing. |
| `chat_service.py` | **STUB** | `def crud(): pass`. No create_chat, no add_message, nothing. |
| `file_service.py` | **STUB** | `def main(): pass`. No save_upload, nothing. |
| `memory_service.py` | **STUB** | `def main(): pass`. No store_memory, nothing. |
| `model_router.py` | **STUB** | `def file(): pass`. No ModelRouter class. |
| `context_builder.py` | **STUB** | `def main(): pass`. No build_context. |
| `text_extractor.py` | **STUB** | `def file(): pass`. No extract_text. |

All product-critical services are `def func(): pass` stubs.

### 2.5 Product APIs

| API | Status | Evidence |
|---|---|---|
| `api/projects.py` | **STUB** | `def fastapi(): pass`. No APIRouter, no routes. Not registered in main.py. |
| `api/chats.py` | **STUB** | `def chat(): pass`. No APIRouter, no routes. Not registered in main.py. |
| `api/ai_chat.py` | **STUB** | `def main(): pass`. No APIRouter, no routes. Not registered in main.py. |
| `api/files.py` | **STUB** | `def main(): pass`. No APIRouter, no routes. Not registered in main.py. |
| `api/memory.py` | **STUB** | `def main(): pass`. No APIRouter, no routes. Not registered in main.py. |
| `api/dashboard.py` | **REAL** | Real FastAPI router, real endpoints — but for autonomous dev dashboard, not product. |
| `api/jobs.py` | **REAL** | Real endpoints for job queue. Not product-facing but functional. |
| `api/runner.py` | **REAL** | Real SSE runner endpoints. |
| `api/manager.py` | **REAL** | Real manager cycle endpoints. |

**0 of 5 product APIs are real.** Only the internal platform APIs (dashboard, jobs, runner, manager) are real.

### 2.6 Router Registration in main.py

| Router | Registered? |
|---|---|
| `dashboard_router` | ✓ |
| `jobs_router` | ✓ |
| `runner_router` | ✓ |
| `manager_router` | ✓ |
| `projects_router` | ✗ — not imported, not registered |
| `chats_router` | ✗ — not imported, not registered |
| `ai_chat_router` | ✗ — not imported, not registered |
| `files_router` | ✗ — not imported, not registered |
| `memory_router` | ✗ — not imported, not registered |

Roadmap tasks 5.4, 6.4, 7.3, 8.4, 10.3 (register routers) are all marked `[x]` but **none are registered**.

### 2.7 Frontend

| Page | Status | Evidence |
|---|---|---|
| `frontend/chat.html` | **REAL UI, broken backend** | 361 lines. Real three-panel UI. Real JS functions: `loadProjects`, `loadChats`, `sendMessage`, `loadMessages`. Calls correct endpoints (`/api/projects`, `/api/projects/{id}/chats`, `/api/chats/{id}/complete`). **But all those endpoints return 404 because the routers aren't registered.** |
| `frontend/dashboard.html` | **REAL (autonomous platform UI)** | 2352 lines. Detailed autonomous dev dashboard. Functional for its purpose. Not product-facing. |

### 2.8 State / Persistence

| Component | Status |
|---|---|
| SQLite database | **MISSING** — never created |
| Alembic migrations | **MISSING** — no alembic directory |
| SQLAlchemy in requirements | **COMMENTED OUT** |
| `configure_database()` called anywhere | **NO** — never called at startup |
| Any real data persistence | **NONE** |

---

## 3. False Accept Inventory

The roadmap shows ALL of the following as `[x]` done. **They are not done.**

| Task | Claim | Reality |
|---|---|---|
| 4.1 | "Uncomment SQLAlchemy in requirements.txt" | Still commented out |
| 4.2 | "Create real DB session" | Stub with FileBasedSession and no engine |
| 4.3 | "Create alembic.ini and env.py" | Files do not exist |
| 4.4 | "Create initial migration" | File does not exist |
| 4.5 | "Create init_db.py" | File does not exist at backend/scripts/init_db.py (exists at scripts/ root only) |
| 5.2 | "Create project_service.py" | `def crud(): pass` stub |
| 5.3 | "Create projects API" | `def fastapi(): pass` stub |
| 5.4 | "Register projects router" | Not registered in main.py |
| 6.1 | "Create chat schemas" | `def main(): pass` stub |
| 6.2 | "Create chat_service.py" | `def crud(): pass` stub |
| 6.3 | "Create chats API" | `def chat(): pass` stub |
| 6.4 | "Register chats router" | Not registered in main.py |
| 7.1 | "Create model_router.py" | `def file(): pass` stub |
| 7.2 | "Create ai_chat endpoint" | `def main(): pass` stub |
| 7.3 | "Register ai_chat router" | Not registered in main.py |
| 8.1 | "Create file schemas" | `def main(): pass` stub |
| 8.2 | "Create file_service.py" | `def main(): pass` stub |
| 8.3 | "Create files API" | `def main(): pass` stub |
| 8.4 | "Register files router" | Not registered in main.py |
| 8.5 | "Create text_extractor.py" | `def file(): pass` stub |
| 10.1 | "Create memory_service.py" | `def main(): pass` stub |
| 10.2 | "Create memory API" | `def main(): pass` stub |
| 10.3 | "Register memory router" | Not registered in main.py |
| 10.4 | "Create context_builder.py" | `def main(): pass` stub |

**24 out of 24 product-critical tasks were falsely accepted.**

The autonomous manager accepted stub files as real implementations. This is the root failure.

---

## 4. What IS Working

The following is genuinely functional:

- FastAPI app starts and responds at `/health`, `/`, `/dashboard`, `/chat`
- Autonomous development dashboard UI (`/dashboard`)
- Job queue service and API
- Runner/executor pipeline (file_executor, claude_executor, manager_loop)
- Phase gate, repair queue, task_level_classifier, reference_pack (manager infrastructure)
- `chat.html` frontend has correct UI and correct API call structure
- `schemas/project.py` has real Pydantic models
- `models/project.py`, `models/chat.py`, `models/message.py` have real SQLAlchemy models

**The platform manages itself but cannot serve users.**

---

## 5. Critical Gaps (MVP blockers)

| # | Gap | Blocks |
|---|---|---|
| G1 | SQLAlchemy not installed (commented in requirements.txt) | Everything |
| G2 | No database created, no schema, no migrations | Persistence |
| G3 | `db/session.py` doesn't configure real engine | All DB-backed services |
| G4 | `project_service.py` is a stub | Projects API |
| G5 | `api/projects.py` is a stub | Project CRUD |
| G6 | Projects router not registered in main.py | All project endpoints |
| G7 | `schemas/chat.py` is a stub | Chat validation |
| G8 | `chat_service.py` is a stub | Chat CRUD |
| G9 | `api/chats.py` is a stub | Chat endpoints |
| G10 | Chats router not registered in main.py | All chat endpoints |
| G11 | `model_router.py` is a stub | AI completion |
| G12 | `api/ai_chat.py` is a stub | AI response |
| G13 | ai_chat router not registered in main.py | AI completion endpoint |

Gaps G4–G10 also produce a schema mismatch: `ProjectRead.id` is `int` but model uses UUID.

---

## 6. Current Product State Summary

```
Platform:       RUNNING (manager infrastructure works)
Product:        BROKEN (all user-facing APIs are stubs)
Database:       NOT CONFIGURED (SQLAlchemy commented out, no db file)
Data:           NO PERSISTENCE EXISTS
Chat UI:        RENDERED (JS correct, but all fetches return 404)
AI Response:    NOT WIRED (model_router is a stub)
```

**Is the product currently runnable?**
**NO.** A human user opening `/chat` would see the UI but every API call returns 404. No project can be created, no chat can be started, no message can be stored or retrieved.

---

## 7. What Must Not Be Forgotten

- The `chat.html` frontend is correct and complete. It calls the right endpoints. It must not be rewritten.
- `models/project.py`, `models/chat.py`, `models/message.py` are structurally correct. Reuse them.
- `schemas/project.py` needs `id: UUID` not `id: int` to match the model.
- All DB work should use SQLite (already set in config.py) — no PostgreSQL required for MVP.
- `configure_database(settings.DATABASE_URL)` must be called in `main.py` at startup.
- Do not touch `main.py`'s existing working routes (dashboard, jobs, runner, manager).
- All 5 new routers must be added to `main.py` in a single task (avoid 5 separate tasks that each try to write main.py).
- The AI completion endpoint can use a real Anthropic API call OR a smart stub that returns a canned response — either counts as MVP.

---

## 8. Manager Mode: Current Setting

The manager is currently in standard roadmap mode. 

After this audit, the manager must operate in **MVP_RECOVERY_MODE**:
- Only repair and MVP-critical tasks run
- No new expansion tasks until the 13 critical gaps are closed
- Existence-on-disk is explicitly not accepted as implementation
- Phase gate checks must actually block (not warn) before any API work proceeds

Mode file: `docs/progress/autopilot_config.json` → `"mode": "mvp_recovery"`
