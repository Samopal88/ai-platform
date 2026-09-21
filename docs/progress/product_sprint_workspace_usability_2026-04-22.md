# Product Sprint Report — Workspace Usability Completion (2026-04-22)

## Files changed
- `frontend/chat.html`

Note:
- `GET /api/projects/{project_id}/files` already existed in `backend/app/api/files.py`.
- `GET /api/projects/{project_id}/memory` already existed in `backend/app/api/memory.py`.
- Sprint updates reused these existing product endpoints; no autonomous infrastructure files were modified.

## Completed items

### P5.1 — project file list endpoint
- Reused existing endpoint:
  - `GET /api/projects/{project_id}/files`
- Endpoint already returns required fields in each file item:
  - `id`, `filename`, `size`, `created_at`
  - (plus additional fields such as `project_id`, `mime_type`).

### P5.2 — show project files in UI
- Confirmed and kept simple project files section in `chat.html`.
- Ensured visibility and usability in project mode:
  - project context now shown immediately after project selection (not only after selecting a chat).
  - file count and list remain live and update after uploads.

### P5.3 — memory visibility endpoint
- Reused existing endpoint:
  - `GET /api/projects/{project_id}/memory`
- Endpoint returns stored memory entries used by context builder storage.

### P5.4 — show project memory in UI
- Added minimal `Project memory` section in project context panel:
  - memory count badge
  - memory entries list (`key` + compact value preview)
  - loading/empty/error states
- Added frontend loader:
  - `loadProjectMemory(projectId)` calls `/api/projects/{projectId}/memory`.

### P5.5 — clearer empty project state
- Added targeted empty-state in workspace:
  - when selected project has no chats and no files,
  - message shown: **"Начните с инструкции или вопроса"**
  - with CTA to create project chat.

### P5.6 — create project flow clarity
- After project creation:
  - project is selected (existing behavior retained),
  - first project chat is created automatically,
  - chat is selected and input focus is moved to composer,
  - hint shown in status: **"Опишите задачу проекта"**.

## Example responses

### `GET /api/projects/{project_id}/files`
```json
{
  "files": [
    {
      "id": "c7e95d09-63a7-4ad4-a6f8-961cf5e47853",
      "project_id": "2fcb8f2d-3b4a-4c9e-9f4e-d4d5f1bbf8c0",
      "filename": "brief.md",
      "size": 1821,
      "mime_type": "text/markdown",
      "created_at": "2026-04-22T10:12:43.102938"
    }
  ],
  "total": 1
}
```

### `GET /api/projects/{project_id}/memory`
```json
[
  {
    "key": "target_audience",
    "value": "SMB teams with async workflows",
    "created_at": "2026-04-22T09:15:00.000000",
    "expires_at": "2026-05-22T09:15:00.000000"
  },
  {
    "key": "tone",
    "value": "brief and practical",
    "created_at": "2026-04-22T09:16:00.000000",
    "expires_at": null
  }
]
```

## Screens affected
- `chat.html` workspace main panel:
  - project context visibility behavior in project mode
  - project files section usability
  - new `Project memory` section
  - project empty-state message
  - post-project-create guidance/focus flow

## Smoke checks
- Presence/wiring checks in `frontend/chat.html`:
  - `Project memory` section and counters (`memoryList`, `memoryCount`)
  - `loadProjectMemory(projectId)` integration on project selection
  - empty-state text: `"Начните с инструкции или вопроса"`
  - post-create hint: `"Опишите задачу проекта"`
- Existing backend endpoints verified as available:
  - `/api/projects/{project_id}/files`
  - `/api/projects/{project_id}/memory`
