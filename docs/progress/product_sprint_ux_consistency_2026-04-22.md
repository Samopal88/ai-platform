# Product Sprint Report — Project/Chat UX Consistency (2026-04-22)

## Files changed
- `backend/app/api/chats.py`
- `backend/app/services/project_service.py`
- `backend/app/schemas/project.py`
- `frontend/chat.html`

## Completed scope

### P2.2 — personal chat user_id consistency
- Backend:
  - `POST /api/chats` now requires explicit `user_id`.
  - Returns `422` if `user_id` is missing.
- Frontend:
  - Personal chat creation now always sends `user_id: state.userId`.

Result:
- personal chats are consistently user-bound and persist across reload/user-scoped list loading.

### P2.3 — create chat inside project flow
- Frontend:
  - Added minimal modal toggle:
    - “Создать в текущем проекте: <project>”
  - If enabled and project selected:
    - create chat via `POST /api/projects/{project_id}/chats`
  - Otherwise:
    - create personal chat via `POST /api/chats`
  - Newly created project chat is inserted into project sidebar list and selected.
- Backend:
  - Project chat create endpoint now accepts optional `user_id` in body and passes through.

Result:
- chat can be created directly inside selected project and appears in project sidebar.

### P3.1 — retry failed completion UI
- Frontend:
  - Added compact retry banner with button `Повторить последний запрос`.
  - On failed send/completion:
    - stores last failed prompt + chat id
    - shows retry button
  - Retry action:
    - restores prompt to input and re-sends.

Result:
- user can retry last failed prompt directly from UI.

### P3.2 — project activity metadata
- Schema:
  - `ProjectRead` extended (backward-compatible) with:
    - `chat_count: int = 0`
    - `last_message_at: Optional[datetime] = None`
- Service:
  - `list_projects(...)` now populates:
    - chat count per project
    - latest message timestamp per project

Result:
- `GET /api/projects` includes project activity metadata.

### P3.3 — improve project list sorting
- Service:
  - `list_projects(...)` now sorts by `last_message_at desc` (projects with no message activity last).

Result:
- active projects appear first.

## Example responses

```json
{
  "detail": "'user_id' is required for personal chat"
}
```

```json
[
  {
    "id": "2fcb8f2d-3b4a-4c9e-9f4e-d4d5f1bbf8c0",
    "name": "Workspace",
    "description": "Main product project",
    "instructions": "Answer briefly",
    "created_at": "2026-04-22T09:10:11.000000",
    "updated_at": "2026-04-22T10:20:30.000000",
    "file_count": 4,
    "storage_used": 221340,
    "chat_count": 7,
    "last_message_at": "2026-04-22T10:18:54.000000"
  }
]
```

```json
{
  "id": "1f4e9c8d-6a2e-4f17-8f70-9d56be9712aa",
  "project_id": "2fcb8f2d-3b4a-4c9e-9f4e-d4d5f1bbf8c0",
  "title": "Новый чат",
  "model": "claude-sonnet-4.6",
  "context_tokens": 0,
  "summary": null,
  "message_count": 0,
  "last_message_at": null,
  "last_message_preview": null,
  "created_at": "2026-04-22T10:22:00.000000",
  "updated_at": "2026-04-22T10:22:00.000000"
}
```

## Smoke checks
- Syntax checks passed:
  - `python -m py_compile backend/app/api/chats.py backend/app/services/project_service.py backend/app/schemas/project.py`
- Feature checks passed via grep:
  - required `user_id` guard for personal chat create
  - create-in-project modal toggle + logic
  - retry-last-prompt handler and button
  - `chat_count` / `last_message_at` in project schema + service
  - sorting by `last_message_at` in project service
