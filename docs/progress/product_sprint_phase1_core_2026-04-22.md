# Product Sprint — Phase 1 Core Improvements (2026-04-22)

## Files changed
- `backend/app/api/ai_chat.py`
- `backend/app/services/chat_service.py`
- `backend/app/schemas/chat.py`
- `backend/app/api/projects.py`
- `frontend/chat.html`

## Summary per task

### P1.1 — Wire `context_builder` into AI completion
- In `backend/app/api/ai_chat.py`:
  - Added import: `from app.services.context_builder import build_context`
  - Added `build_context(project_id, chat_id, query)` call when building prompt context.
  - Added context block into system prompt.
  - Existing project instructions + project files remain included.
  - Memory entries are included through `context_builder`.

### P1.2 — Fix message ordering
- In `backend/app/services/chat_service.py`:
  - `get_messages(limit=N)` now fetches newest `N` (`ORDER BY created_at DESC LIMIT N`) and reverses in-memory to chronological order.
  - Result: latest dialog window is used in chat context.

### P1.3 — Activity metadata in chat schema and service
- In `backend/app/schemas/chat.py`:
  - Added fields: `message_count`, `last_message_at`, `last_message_preview`.
- In `backend/app/services/chat_service.py`:
  - Added metadata population for list endpoints (`list_chats`, `list_personal_chats`) via `_attach_activity_metadata(...)`.
  - `GET /api/chats` now includes activity metadata.

### P1.4 — PATCH project instructions
- In `backend/app/api/projects.py`:
  - Added endpoint: `PATCH /api/projects/{project_id}`
  - Endpoint updates only `instructions` field using `ProjectUpdate(instructions=...)`.
  - Other project fields are not overwritten.

### P2.1 — Completion robustness
- In `backend/app/api/ai_chat.py`:
  - Context-builder failures are isolated and do not fail whole completion.
  - Per-file processing for project files wrapped with local exception handling.
  - One broken attachment/file no longer breaks full response.
  - Added fallback for router error or empty model output.

## Smoke checks
- Syntax checks passed:
  - `python -m py_compile backend/app/api/ai_chat.py backend/app/services/chat_service.py backend/app/schemas/chat.py backend/app/api/projects.py`
- Feature wiring verified by search:
  - `build_context` usage in `ai_chat.py`
  - `@router.patch("/{project_id}")` in `projects.py`
  - `message_count/last_message_at/last_message_preview` in schema/service
  - `get_messages` uses newest-N then reverse

## Example curl requests

```bash
# PATCH instructions only
curl -sS -X PATCH "http://localhost:8000/api/projects/<project_id>" \
  -H "Content-Type: application/json" \
  -d '{"instructions":"Always answer in bullet points."}'

# List chats with activity metadata
curl -sS "http://localhost:8000/api/chats?user_id=<user_id>"

# Add user message
curl -sS -X POST "http://localhost:8000/api/chats/<chat_id>/messages" \
  -H "Content-Type: application/json" \
  -d '{"role":"user","content":"Summarize project context"}'

# Trigger completion
curl -sS -X POST "http://localhost:8000/api/chats/<chat_id>/complete"
```
