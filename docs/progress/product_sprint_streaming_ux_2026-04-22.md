# Product Sprint Report — Streaming Response UX (2026-04-22)

## Files changed
- `backend/app/api/ai_chat.py`
- `frontend/chat.html`

## What was implemented

### P4.1 — Optional streaming completion mode
- Added optional query flag on completion endpoint:
  - `POST /api/chats/{chat_id}/complete?stream=1`
- Backend behavior:
  - Generates assistant reply and stores message as before.
  - If stream requested and model is stream-capable (`claude*` / `gpt*`), returns SSE (`text/event-stream`) with chunked deltas.
  - If stream requested but model is not stream-capable, falls back to regular JSON completion response.
- Frontend behavior:
  - Requests `?stream=1`.
  - Parses SSE chunks and updates optimistic assistant message progressively.
  - Falls back to JSON path if response is not SSE.

### P4.2 — Generation status indicator
- During completion, status banner now shows:
  - `AI думает...`
- Status is cleared when final response is received.

### P4.3 — Disable send while generating
- Existing `state.sending` + `syncComposerState()` flow remains active and blocks duplicate submit.
- Streaming path reuses same lock, so duplicate sends are prevented during generation.

### P4.4 — Basic token usage display
- Backend:
  - Adds usage metadata in assistant message `extra_data.usage`:
    - `prompt_tokens`
    - `completion_tokens`
  - Values are lightweight estimates when provider-native usage is unavailable.
- Frontend:
  - Renders compact usage line under assistant response:
    - `tokens: prompt X · completion Y`

## Example streaming response format

SSE frames (`Content-Type: text/event-stream`):

```text
data: {"type":"delta","delta":"Первая часть ответа"}

data: {"type":"delta","delta":" вторая часть ответа"}

data: {"type":"done","message":{"id":"...","chat_id":"...","role":"assistant","content":"Полный ответ","tokens_used":0,"model":"claude-sonnet-4.6","extra_data":{"usage":{"prompt_tokens":123,"completion_tokens":45}},"created_at":"2026-04-22T..."},"usage":{"prompt_tokens":123,"completion_tokens":45}}

```

Fallback JSON format (non-stream):

```json
{
  "id": "....",
  "chat_id": "....",
  "role": "assistant",
  "content": "Полный ответ",
  "model": "claude-sonnet-4.6",
  "extra_data": {
    "usage": {
      "prompt_tokens": 123,
      "completion_tokens": 45
    }
  }
}
```

## Smoke checks
- Syntax:
  - `python -m py_compile backend/app/api/ai_chat.py`
- Wiring checks:
  - `stream=1` request path in frontend.
  - SSE `text/event-stream` handling in frontend.
  - Backend SSE events `delta` and `done`.
  - `AI думает...` indicator.
  - Usage fields `prompt_tokens` / `completion_tokens` rendered under response.
