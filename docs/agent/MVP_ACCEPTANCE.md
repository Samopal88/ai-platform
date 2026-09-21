# MVP Acceptance Criteria
## AI Workspace Platform — End-to-End MVP Flow

**Version:** 1.0  
**Authority:** A task is not accepted as complete unless it moves the MVP flow forward.  
**Applies to:** All tasks executed in MVP_RECOVERY_MODE

---

## The MVP Flow

The single end-to-end path that defines MVP success:

```
1. User opens /chat
2. User creates a project
3. User creates a chat inside the project
4. User sends a message
5. Backend stores the message in the database
6. Backend calls AI model and gets a response
7. Response is stored and returned to frontend
8. User sees the response in the chat UI
9. User refreshes — conversation is still there
```

Every task in the recovery roadmap must advance one or more of these steps.

---

## Step-by-Step Acceptance Criteria

### Step 1: User opens /chat

**What must work:**
- `GET /chat` returns `frontend/chat.html` with HTTP 200
- Page renders without JavaScript errors in console
- Project panel, chat panel, message area are all visible
- No "Failed" or "Error" banners appear on initial load (empty state is OK)

**Backend dependencies:** `main.py` serves the file  
**Frontend dependencies:** `chat.html` has valid HTML/CSS/JS structure  
**Structural check:** File exists at `frontend/chat.html`, served at `/chat`  
**Semantic check:** Title is "AI Chat", not "Generated Content"; three-panel layout present  
**Integration check:** Page loads without 500 or CORS errors

---

### Step 2: User creates a project

**What must work:**
- `GET /api/projects` returns `200 []` (empty list is fine)
- `POST /api/projects {"name": "Test Project", "description": ""}` returns `201` or `200` with `{id, name, created_at}`
- The returned `id` is usable in subsequent requests
- Project survives a server restart

**Backend dependencies:**
- `project_service.create_project()` executes a real DB insert
- `api/projects.py` has real `POST /api/projects` route
- Router registered in `main.py`
- SQLite DB is initialized with `projects` table
- `schemas/project.py` `ProjectRead.id` is `UUID` not `int`

**Structural check:** `api/projects.py` has `APIRouter`, at least 2 routes (`GET`, `POST`)  
**Semantic check:** Route handlers call `project_service`, not `pass`  
**Integration check:** `POST /api/projects {"name": "Test"}` → `{id: "...", name: "Test"}`

---

### Step 3: User creates a chat

**What must work:**
- `POST /api/projects/{project_id}/chats {"title": "Chat 1", "model": "claude-sonnet-4-20250514"}` returns `{id, title, project_id, created_at}`
- `GET /api/projects/{project_id}/chats` returns list including the new chat
- Chat is associated with the correct project

**Backend dependencies:**
- `schemas/chat.py` has `ChatCreate`, `ChatRead`
- `chat_service.create_chat()`, `chat_service.list_chats()` are real
- `api/chats.py` has real routes
- Router registered in `main.py`
- `chats` table exists in SQLite DB

**Structural check:** `api/chats.py` has `APIRouter`, routes for POST and GET  
**Semantic check:** Route handlers use `chat_service`, return Pydantic models  
**Integration check:** `POST /api/projects/{id}/chats` → `{id, title}`; `GET /api/projects/{id}/chats` → `[{id, title}]`

---

### Step 4: User sends a message

**What must work:**
- `POST /api/chats/{chat_id}/messages {"role": "user", "content": "Hello"}` returns `{id, chat_id, role, content, created_at}`
- Message is stored in the database

**Backend dependencies:**
- `chat_service.add_message()` does a real DB insert
- `api/chats.py` has `POST /api/chats/{chat_id}/messages` route

**Structural check:** Route exists in `api/chats.py`  
**Semantic check:** Handler calls `chat_service.add_message()` with real body  
**Integration check:** `POST /api/chats/{id}/messages {"role":"user","content":"Hello"}` → `{id, content}`

---

### Step 5: Backend stores the message

**What must work:**
- After Step 4, `GET /api/chats/{chat_id}/messages` returns the user message
- Message content is correct (not empty, not corrupted)

**Backend dependencies:**
- `chat_service.get_messages()` queries real DB
- `api/chats.py` has `GET /api/chats/{chat_id}/messages`

**Integration check:** `GET /api/chats/{id}/messages` → `[{role: "user", content: "Hello"}]`

---

### Step 6: AI model is called and responds

**What must work:**
- `POST /api/chats/{chat_id}/complete` calls a model and returns `{content: "<AI response>", role: "assistant"}`
- Response is non-empty and not a placeholder like "AI response here"
- Acceptable for MVP: Anthropic API call OR a deterministic stub that returns a real-looking response

**Backend dependencies:**
- `model_router.ModelRouter.route(messages, model_id)` returns a real response
- `api/ai_chat.py` has real `POST /api/chats/{chat_id}/complete` route
- Router registered in `main.py`
- Route fetches last N messages from DB, calls model_router, stores response

**Structural check:** `api/ai_chat.py` has `APIRouter`, `POST /api/chats/{chat_id}/complete`  
**Semantic check:** Handler reads messages from DB, calls `model_router`, stores result as assistant message  
**Integration check:** `POST /api/chats/{id}/complete` → `{content: "...", role: "assistant"}` (content non-empty, not a hardcoded stub string)

---

### Step 7: Response is returned and displayed

**What must work:**
- Frontend `sendMessage()` receives `result.content` from the `/complete` endpoint
- Assistant message is appended to the chat UI
- Spinner disappears, input is re-enabled

**Frontend dependencies:** `chat.html` `sendMessage()` already handles this correctly (no change needed)  
**Integration check:** Manual test — type a message, press Enter, see assistant reply within 5 seconds

---

### Step 8: Refresh preserves conversation

**What must work:**
- After sending a message and refreshing the page
- Projects list still shows the project
- Chat list still shows the chat
- Message history is restored via `GET /api/chats/{chat_id}/messages`

**Backend dependencies:** SQLite persistence (data not in memory only)  
**Integration check:** Sequence: send message → refresh → `GET /api/chats/{id}/messages` → messages present

---

## Structural vs Semantic vs Integration Levels

| Level | What it checks | Automated? |
|---|---|---|
| Structural | File exists, is non-empty, has `APIRouter`, has route decorators, no `pass`-only bodies | Yes — file_executor + semantic_validator |
| Semantic | Route handlers call real service functions, models return correct types, DB is configured | Partial — semantic_validator stubs + manual |
| Integration | HTTP response codes and bodies are correct, data persists, frontend JS receives expected shapes | Manual curl test or smoke test script |

---

## Integration Smoke Test (target for manager to run post-MVP)

```bash
BASE=http://localhost:8000

# Step 1
curl -s $BASE/health | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['status']=='healthy'"

# Step 2
PROJECT=$(curl -s -X POST $BASE/api/projects -H 'Content-Type: application/json' -d '{"name":"Smoke Test"}')
PID=$(echo $PROJECT | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# Step 3
CHAT=$(curl -s -X POST $BASE/api/projects/$PID/chats -H 'Content-Type: application/json' -d '{"title":"Chat 1","model":"claude-sonnet-4-20250514"}')
CID=$(echo $CHAT | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# Step 4+5
curl -s -X POST $BASE/api/chats/$CID/messages -H 'Content-Type: application/json' -d '{"role":"user","content":"Hello"}'
MSGS=$(curl -s $BASE/api/chats/$CID/messages)
echo $MSGS | python3 -c "import json,sys; msgs=json.load(sys.stdin); assert len(msgs)>=1"

# Step 6
REPLY=$(curl -s -X POST $BASE/api/chats/$CID/complete)
echo $REPLY | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('content')"

echo "MVP smoke test PASSED"
```

This smoke test script must pass before the MVP is declared complete.

---

## What the Manager Must NOT Accept

In MVP_RECOVERY_MODE, the following must be rejected regardless of structural checks:

| Pattern | Reason to reject |
|---|---|
| `def main(): pass` or `def crud(): pass` | Stub — not real |
| `def route_handler(): return {}` | Empty response — not integrated |
| Route that doesn't call a service function | Missing layer |
| Service that doesn't touch the DB | Fake persistence |
| `configure_database()` not called in startup | DB never opens |
| `ProjectRead.id: int` (should be `UUID`) | Schema mismatch |
| SQLAlchemy still commented in requirements.txt | DB cannot be imported |
| Router not appearing in `/openapi.json` | Not registered |

---

## MVP Done Definition

The MVP is complete when:

1. `backend/requirements.txt` has `sqlalchemy` and `fastapi` uncommented
2. `backend/app/db/session.py` calls `create_engine` and provides real `get_db()`
3. `backend/app/main.py` calls `configure_database(settings.DATABASE_URL)` at startup
4. `backend/app/main.py` imports and registers all 5 product routers
5. `GET /api/projects` returns a valid JSON array
6. `POST /api/projects` creates and persists a project
7. `POST /api/projects/{id}/chats` creates and persists a chat
8. `POST /api/chats/{id}/messages` persists a message
9. `GET /api/chats/{id}/messages` returns the stored messages
10. `POST /api/chats/{id}/complete` returns a non-empty `{content}` response
11. All of steps 1–10 survive a server restart (data persists in SQLite)
12. `frontend/chat.html` successfully completes the full flow without errors

Items 1–12 must all be true simultaneously. Partial credit does not count.
