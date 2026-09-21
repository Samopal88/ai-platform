# MVP Recovery Roadmap
## AI Workspace Platform — Repair-First Plan to Runnable MVP

**Created:** 2026-04-18  
**Status:** ACTIVE — replaces normal roadmap ordering until MVP is achieved  
**Authority:** All autonomous manager cycles must draw from this roadmap first.  
**Reference:** `docs/agent/MVP_TRUTH.md`, `docs/agent/MVP_ACCEPTANCE.md`

---

## Context

All 24 product-critical roadmap tasks (Phases 4–10) were falsely accepted as done.
Every product API is a `def func(): pass` stub. SQLAlchemy is commented out.
No database exists. No data is persisted. The chat UI calls endpoints that all return 404.

This roadmap repairs the foundation before adding any new surface area.

---

## Scope Rules

- Do NOT add new features until tasks R1–R13 are all genuinely complete
- Do NOT accept a file as done unless it has real function bodies calling real layers
- Do NOT accept a service unless it touches a real DB session
- Do NOT accept an API unless its routes return real data shapes
- The smoke test in `docs/agent/MVP_ACCEPTANCE.md` must pass before this roadmap is retired

---

## Phase R: Foundation Recovery (MUST DO FIRST)

### R1 — Fix requirements.txt: uncomment SQLAlchemy
**Priority:** CRITICAL — nothing else can proceed  
**Files:** `backend/requirements.txt`  
**Change:** Uncomment `sqlalchemy==2.0.35` and add `aiosqlite` for async SQLite support. Keep fastapi, uvicorn, pydantic lines as-is.  
**Why:** All DB-backed services fail to import without SQLAlchemy installed.  
**Acceptance:**
- File contains `sqlalchemy==2.0.35` (no leading `#`)
- `pip install -r requirements.txt` completes without error (when run)
- No other dependency is removed

---

### R2 — Fix db/session.py: real SQLite engine
**Priority:** CRITICAL  
**Files:** `backend/app/db/session.py`  
**Change:** Replace FileBasedSession stub with real SQLAlchemy setup:
- `create_engine(DATABASE_URL, connect_args={"check_same_thread": False})` for SQLite
- `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`
- `Base.metadata.create_all(bind=engine)` called to create tables
- `get_db()` yields a real `SessionLocal()` session
- No more `DatabaseNotConfigured` exception
- No `configure_database()` required — configure from `settings.DATABASE_URL` at module level
  
**Why:** Every service needs `get_db()` to return a real session.  
**Acceptance:**
- File contains `create_engine`
- File contains `SessionLocal`
- `get_db()` is a generator that yields a real session and closes it in finally
- No `FileBasedSession` class remains

---

### R3 — Fix main.py: call DB init at startup
**Priority:** CRITICAL  
**Files:** `backend/app/main.py`  
**Change:** Add a startup event that ensures tables are created. Add imports for the 5 product routers (once those files are real — coordinate with R5, R8, R11 tasks).  
**Why:** Database tables must exist before any request hits a service.  
**Note:** This task is split — Part A (startup event) can run now; Part B (router registration) runs after R5/R8/R11.  
**Acceptance (Part A):**
- `app.add_event_handler("startup", ...)` or `@app.on_event("startup")` present
- Startup calls `Base.metadata.create_all(bind=engine)` or equivalent
- Existing routes (dashboard, jobs, runner, manager) still registered and working

---

### R4 — Fix schemas/project.py: UUID id field
**Priority:** CRITICAL  
**Files:** `backend/app/schemas/project.py`  
**Change:** Change `ProjectRead.id` from `int` to `UUID`. Add missing `import uuid` and `from uuid import UUID`. Ensure `model_config = {"from_attributes": True}` is present.  
**Why:** `models/project.py` uses `UUID(as_uuid=True)` primary key. Schema must match.  
**Acceptance:**
- `ProjectRead.id` type is `UUID`
- `from uuid import UUID` imported
- `model_config = {"from_attributes": True}` present

---

### R5 — Implement project_service.py
**Priority:** CRITICAL  
**Files:** `backend/app/services/project_service.py`  
**Change:** Real implementation with:
- `create_project(db: Session, data: ProjectCreate, user_id: UUID = None) -> Project`
- `get_project(db: Session, project_id: UUID) -> Optional[Project]`
- `list_projects(db: Session) -> list[Project]`
- `update_project(db: Session, project_id: UUID, data: ProjectUpdate) -> Optional[Project]`
- `delete_project(db: Session, project_id: UUID) -> bool`
- All functions use SQLAlchemy `db.add()`, `db.commit()`, `db.refresh()`, `db.query()`  
**Why:** Projects API depends on this service.  
**Acceptance:**
- No `def crud(): pass` or `def main(): pass`
- All 5 functions present with real bodies
- Functions import `Project` from `app.models.project`
- Functions accept `Session` as first argument

---

### R6 — Implement api/projects.py
**Priority:** CRITICAL  
**Files:** `backend/app/api/projects.py`  
**Change:** Real FastAPI router:
- `router = APIRouter(prefix="/api/projects", tags=["Projects"])`
- `POST /api/projects` → create project
- `GET /api/projects` → list projects
- `GET /api/projects/{project_id}` → get project
- `PUT /api/projects/{project_id}` → update
- `DELETE /api/projects/{project_id}` → delete
- All routes use `db: Session = Depends(get_db)` and call `project_service`
- Return `ProjectRead` schemas  
**Why:** Frontend calls `/api/projects`. 404 today.  
**Acceptance:**
- `router = APIRouter(...)` present
- At least `POST` and `GET` routes with real handler bodies
- No `def fastapi(): pass`
- No route body consisting only of `pass`

---

### R7 — Implement schemas/chat.py
**Priority:** CRITICAL  
**Files:** `backend/app/schemas/chat.py`  
**Change:** Real Pydantic models:
- `ChatCreate(project_id: UUID, title: str, model: str = "claude-sonnet-4-20250514")`
- `ChatRead(id: UUID, project_id: UUID, title: str, model: str, created_at: datetime)`
- `MessageCreate(role: str, content: str)`
- `MessageRead(id: UUID, chat_id: UUID, role: str, content: str, created_at: datetime, model: Optional[str])`
- `model_config = {"from_attributes": True}` on Read schemas  
**Acceptance:**
- No `def main(): pass`
- All 4 classes present
- `from uuid import UUID`, `from datetime import datetime` imported

---

### R8 — Implement chat_service.py
**Priority:** CRITICAL  
**Files:** `backend/app/services/chat_service.py`  
**Change:** Real implementation:
- `create_chat(db: Session, project_id: UUID, data: ChatCreate) -> Chat`
- `get_chat(db: Session, chat_id: UUID) -> Optional[Chat]`
- `list_chats(db: Session, project_id: UUID) -> list[Chat]`
- `add_message(db: Session, chat_id: UUID, role: str, content: str, model: str = None) -> Message`
- `get_messages(db: Session, chat_id: UUID, limit: int = 50) -> list[Message]`
- All use real SQLAlchemy session operations  
**Acceptance:**
- No `def crud(): pass`
- All 5 functions present with real bodies
- `Message` imported from `app.models.message`
- `Chat` imported from `app.models.chat`

---

### R9 — Implement api/chats.py
**Priority:** CRITICAL  
**Files:** `backend/app/api/chats.py`  
**Change:** Real FastAPI router:
- `router = APIRouter(tags=["Chats"])`
- `POST /api/projects/{project_id}/chats` → create chat
- `GET /api/projects/{project_id}/chats` → list chats
- `GET /api/chats/{chat_id}` → get chat
- `POST /api/chats/{chat_id}/messages` → add message
- `GET /api/chats/{chat_id}/messages` → get messages
- All routes use `Depends(get_db)` and call `chat_service`  
**Acceptance:**
- `router = APIRouter(...)` present
- All 5 routes present with real bodies
- No `def chat(): pass`

---

### R10 — Implement model_router.py
**Priority:** CRITICAL  
**Files:** `backend/app/services/model_router.py`  
**Change:** Real implementation:
- `class ModelRouter`
- `route(messages: list[dict], model_id: str) -> str` method
- If `ANTHROPIC_API_KEY` env var is set: call Anthropic API using `anthropic` SDK
- If key not set: return a canned response like `f"[MVP stub] You said: {messages[-1]['content']}"`
- Uses `anthropic.Anthropic().messages.create(...)` when key available  
**Why:** ai_chat endpoint needs this to produce a response.  
**Acceptance:**
- `class ModelRouter` present
- `route()` method present with real body
- No `def file(): pass`
- If no API key, returns a non-empty string (not empty, not `None`)

---

### R11 — Implement api/ai_chat.py
**Priority:** CRITICAL  
**Files:** `backend/app/api/ai_chat.py`  
**Change:** Real FastAPI router:
- `router = APIRouter(tags=["AI Chat"])`
- `POST /api/chats/{chat_id}/complete`
  - Loads last 20 messages from DB via `chat_service.get_messages()`
  - Formats as `[{"role": m.role, "content": m.content}]`
  - Calls `ModelRouter().route(messages, chat.model)`
  - Stores AI response via `chat_service.add_message()` with `role="assistant"`
  - Returns `{id, content, role, model, created_at}`  
**Acceptance:**
- `router = APIRouter(...)` present
- `POST /api/chats/{chat_id}/complete` route with real body
- Route reads from DB, calls model_router, stores result
- No `def main(): pass`

---

### R12 — Register all 5 product routers in main.py
**Priority:** CRITICAL  
**Files:** `backend/app/main.py`  
**Change:** Add imports and `app.include_router()` calls for:
- `from app.api.projects import router as projects_router`
- `from app.api.chats import router as chats_router`
- `from app.api.ai_chat import router as ai_chat_router`
- (files_router and memory_router can be registered as stubs for now — just not erroring)
- All 5 routers registered after existing dashboard/jobs/runner/manager  
**Why:** Without registration, all endpoints return 404.  
**Acceptance:**
- `app.include_router(projects_router)` present
- `app.include_router(chats_router)` present
- `app.include_router(ai_chat_router)` present
- Existing routers still registered (no regression)
- `GET /openapi.json` shows `/api/projects`, `/api/projects/{project_id}/chats`, `/api/chats/{chat_id}/complete`

---

### R13 — Create sandbox/smoke_mvp.py: integration test
**Priority:** CRITICAL  
**Files:** `sandbox/smoke_mvp.py`  
**Change:** A Python script that runs the full MVP smoke test against `http://localhost:8000`:
- Creates a project
- Creates a chat
- Sends a message
- Calls complete
- Verifies messages endpoint
- Prints PASS or FAIL with details  
**Why:** Provides one-command verification that the MVP works end-to-end.  
**Acceptance:**
- Script exists and is executable Python
- Script covers all 5 API steps
- Script prints "MVP smoke test PASSED" or specific failure detail

---

## Phase S: Safety (run after R1–R13)

### S1 — Add anthropic to requirements.txt
**Priority:** HIGH  
**Files:** `backend/requirements.txt`  
**Change:** Add `anthropic>=0.40.0` to enable real AI responses.  
**Acceptance:** Line present and uncommented.

### S2 — Add startup lifespan handler to main.py
**Priority:** HIGH  
**Files:** `backend/app/main.py`  
**Change:** Use FastAPI lifespan to call `Base.metadata.create_all()` on startup.  
**Note:** May be combined with R3.

---

## Phase D: Deferred (after MVP is verified)

These are real features but blocked by MVP being broken:

- File upload/download (R8.x — file_service, api/files.py)
- Memory/context injection (api/memory.py, memory_service.py, context_builder.py)
- Text extraction from uploaded files
- Multi-project memory search
- User authentication
- Dashboard metrics improvements
- Advanced model routing (beyond single model)

---

## Task Ordering Dependencies

```
R1 (requirements)
  └→ R2 (session.py)
       └→ R5 (project_service) → R6 (api/projects)
       └→ R4 (schema fix)      → R6
       └→ R7 (chat schemas)
       └→ R8 (chat_service)    → R9 (api/chats)
       └→ R10 (model_router)   → R11 (api/ai_chat)
            └→ R12 (main.py registration) ← R6, R9, R11
                 └→ R13 (smoke test)
R3 (startup event) can run in parallel after R2
```

---

## How to Determine Current Recovery Progress

Run:
```bash
python3 sandbox/smoke_mvp.py
```

Or manually check:
```bash
# Is SQLAlchemy uncommented?
grep "^sqlalchemy" backend/requirements.txt

# Is get_db real?
grep "create_engine\|SessionLocal" backend/app/db/session.py

# Are routers registered?
grep "include_router" backend/app/main.py

# Are APIs real (not stubs)?
grep "def fastapi\|def main\|def crud\|def chat\|def file" \
  backend/app/api/projects.py backend/app/api/chats.py \
  backend/app/api/ai_chat.py backend/app/services/project_service.py \
  backend/app/services/chat_service.py
# If any line appears, those files are still stubs.
```
