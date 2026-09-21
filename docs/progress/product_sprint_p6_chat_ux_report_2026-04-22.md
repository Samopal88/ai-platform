# Product Sprint Report — P6 Chat UX Polish

Date: 2026-04-22
Scope: P6.1–P6.6
Project root: /opt/ai-workspace/storage/projects/ai-platform

## Files changed
- /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html

## Implemented change (this run)
### P6.1 — show what AI used
Updated assistant message metadata rendering in frontend chat UI.

- Displays `Использовано:` block after assistant messages.
- Shows only non-zero counters:
  - `memory: N entries` (if N > 0)
  - `files: N files` (if N > 0)
- Data source: `message.extra_data.context_usage` (provided by completion response metadata).

## Before / after behavior
- Before:
  - Context usage could show zero counters (`memory: 0 · files: 0`) and add visual noise.
- After:
  - Block appears only when context was actually used (non-zero memory/files).
  - Format aligns with requested minimal UX copy.

## P6.2–P6.6 status
Validated as already present in current codebase:

- P6.2 Loading state:
  - `AI думает...` status + spinner during send/completion.
  - Input/send disabled while request is in progress.
- P6.3 Chat rename:
  - Backend: `PATCH /api/chats/{chat_id}` exists.
  - Frontend: rename action via prompt, updates list and selected chat title.
- P6.4 Chat delete:
  - Backend: `DELETE /api/chats/{chat_id}` exists.
  - Frontend: delete action removes chat from list and handles fallback selection.
- P6.5 Better chat list:
  - Displays chat title and last message preview (trimmed to 50 chars).
  - Active chat is highlighted.
- P6.6 Scroll behavior:
  - Auto-scroll to bottom on new messages.
  - Keeps stable position when loading unless near bottom/force-scroll conditions apply.

## Screens improved
- Chat conversation screen:
  - Assistant message meta section (`Использовано`) now cleaner and conditional.
- Confirmed polished behavior on:
  - Composer loading/disabled state.
  - Chat list metadata and active highlighting.

## Smoke checks
- Syntax:
  - `python -m py_compile backend/app/api/chats.py backend/app/api/ai_chat.py` — OK
- Endpoint presence:
  - `PATCH /api/chats/{chat_id}` — present
  - `DELETE /api/chats/{chat_id}` — present
- Frontend markers verified in code:
  - `AI думает...`
  - input disable/enable logic
  - auto-scroll + near-bottom logic
  - 50-char preview rendering
  - active chat class
  - conditional `Использовано` rendering
