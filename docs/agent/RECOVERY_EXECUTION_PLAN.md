# Recovery Execution Plan
## AI Workspace Platform — Concrete Steps to Runnable MVP

**Date:** 2026-04-19  
**Prerequisite:** All fixes from this session are now in place (see AUTONOMY_READINESS_REPORT.md)

---

## Immediate Next Steps (Before Any Auto-Run)

### Step 0 — Manual: fix user_id constraint
The `Project` model has `user_id = Column(UUID, ForeignKey("users.id"), nullable=False)`.
This blocks every `POST /api/projects`. Either:
- (a) Add a nullable=True to user_id in the model and schema for MVP scope, OR
- (b) Add user_id=None default path in project_service, OR
- (c) Add this fix as task R0.5 in the recovery roadmap before R5

**Recommended:** Add a recovery task R0.5 to make user_id nullable in the Project model
for the SQLite MVP. This is a 5-line change. Without it, every project creation will fail.

---

## Recovery Task Sequence

Execute in strict order. Verify after each before proceeding.

### R1 — Fix requirements.txt
**Run:** `POST /api/manager/run-cycle-sync`  
**Verify:** `grep "^sqlalchemy" backend/requirements.txt` → should show `sqlalchemy==2.0.35`  
**If fails again:** The fix_task retry path (retry_count=1) now uses the corrected brief.
The worker should not write to docs this time. If it does, check file_executor keyword
matching logic.

### R2 — Fix db/session.py
**After R1 succeeds.**  
**Verify:** `grep "create_engine\|SessionLocal" backend/app/db/session.py`

### R3 — Fix main.py: startup DB init
**Verify:** `grep "startup\|create_all" backend/app/main.py`

### R4 — Fix schemas/project.py: UUID id
**Verify:** `grep "UUID" backend/app/schemas/project.py`

### R0.5 (add this) — Fix Project model: make user_id nullable
**Target:** `backend/app/models/project.py`  
**Change:** `user_id = Column(UUID(as_uuid=True), nullable=True, index=True)`  
**Remove:** `ForeignKey("users.id")` reference (no users table in SQLite MVP)

### R5 — Implement project_service.py
**Verify:** `grep "def create_project\|def list_projects" backend/app/services/project_service.py`  
**Must NOT be:** `def crud(): pass`

### R6 — Implement api/projects.py
**Verify:** `grep "APIRouter\|@router" backend/app/api/projects.py`

### R7 — Implement schemas/chat.py  
**Verify:** `grep "class ChatCreate\|class ChatRead" backend/app/schemas/chat.py`

### R8 — Implement chat_service.py
**Verify:** `grep "def create_chat\|def add_message" backend/app/services/chat_service.py`

### R9 — Implement api/chats.py
**Verify:** `grep "APIRouter\|@router" backend/app/api/chats.py`

### R10 — Implement model_router.py
**Verify:** `grep "class ModelRouter\|def route" backend/app/services/model_router.py`

### R11 — Implement api/ai_chat.py
**Verify:** `grep "APIRouter\|@router.post" backend/app/api/ai_chat.py`

### R12 — Register all 5 product routers in main.py
**Verify:** `grep "include_router.*projects\|include_router.*chats\|include_router.*ai_chat" backend/app/main.py`

### R13 — Create smoke_mvp.py and run it
**Verify:** `python3 sandbox/smoke_mvp.py` → prints "MVP smoke test PASSED"

---

## Acceptance Gate (Do Not Call MVP Done Until This Passes)

```bash
# 1. Start the server
cd backend && uvicorn app.main:app --reload &

# 2. Run smoke test
python3 sandbox/smoke_mvp.py

# 3. Manually open chat UI
# curl http://localhost:8000/chat → should load chat.html
# Create a project, create a chat, send a message, get AI response
# Refresh page → conversation still visible
```

If `smoke_mvp.py` prints PASSED AND the manual browser test works, the MVP is real.

---

## Do Not Proceed To New Features Until

- [ ] `requirements.txt` has `sqlalchemy==2.0.35` uncommented
- [ ] `db/session.py` has real `create_engine` / `SessionLocal`  
- [ ] `main.py` calls `create_all` at startup
- [ ] `api/projects.py` has real routes (not `def fastapi(): pass`)
- [ ] `api/chats.py` has real routes
- [ ] `api/ai_chat.py` has real `/complete` route
- [ ] All 5 product routers registered in `main.py`
- [ ] `smoke_mvp.py` passes
