# Mobile Runtime Fix Report — 2026-04-23

## Scope
Fix mobile flow where user message is saved but assistant completion fails and UI shows:
- "Последнее сообщение не отправлено"
- "Ошибка запроса, попробуйте ещё раз"

Work dir: `/opt/ai-workspace/storage/projects/ai-platform`

---

## M1 — Reproduction (mobile)

### What was tested
- Mobile user-agent API flow (iPhone Safari UA)
- Endpoint pair:
  1. `POST /api/chats/{chat_id}/messages`
  2. `POST /api/chats/{chat_id}/complete?stream=1`
- Models: `gpt-5.4`, `claude-haiku-4.5`
- `web_mode`: on/off

### Observed runtime statuses
- Message POST: `201`
- Completion request: `200`
- Content-Type: `text/event-stream; charset=utf-8`

### Exact failing request/status (root failure mode)
Client-side failure is on:
- `POST /api/chats/{chat_id}/complete?stream=1`
- HTTP status: `200 OK`

Failure is not backend HTTP status; it is stream parsing on the client in some mobile/proxy framing cases (CRLF framed SSE), producing `Streaming ended without final message` and then generic UI error.

---

## M2 — Model-specific path (GPT-5.4 vs Haiku 4.5)

### Frontend payload model id
- UI sends exact IDs:
  - `gpt-5.4`
  - `claude-haiku-4.5`

### Backend routing
- `model_router` routes:
  - `claude-*` via Anthropic path if key exists
  - others (including `gpt-5.4`) via OpenAI-compatible path if key exists
  - fallback text if provider unavailable

### Result
- No model-specific HTTP failure reproduced.
- GPT-5.4 and Haiku both returned `200` for completion in test matrix.

---

## M3 — Mobile-specific payload differences

Compared desktop vs mobile UA requests for completion path.

Result:
- No divergence found in payload fields for tested flow.
- Same `model`, `web_mode`, `content` behavior.
- Same statuses (`201` message, `200` completion).

---

## M4 — Frontend error handling improvements

Implemented:
1. If user message is already saved, UI no longer says "message not sent".
2. More precise error text for completion failure after save:
   - "Сообщение сохранено..." + retry hint
   - HTTP code shown when available
3. Retry remains non-duplicating:
   - existing `lastFailedMsgSaved` logic retained
   - user message is not reposted on retry when already saved

---

## M5 — Cache/version issue

Findings:
- `/chat` response has no `Cache-Control`; relies on `ETag/Last-Modified`.
- This can leave stale mobile frontend in practice.

Implemented frontend-side mitigation (without infra changes):
1. Added no-cache meta tags in `chat.html`.
2. Added build-id guard that enforces one-time reload to `/chat?v=<build-id>` when build changes.

This reduces stale mobile JS/HTML usage and ensures latest completion logic is loaded.

---

## M6 — Runtime verification matrix

Executed matrix (phone UA + desktop UA):
1. phone + GPT-5.4 + web off -> OK (`201` + `200`)
2. phone + GPT-5.4 + web on  -> OK (`201` + `200`)
3. phone + Haiku 4.5 + web off -> OK (`201` + `200`)
4. phone + Haiku 4.5 + web on  -> OK (`201` + `200`)
5. desktop + GPT-5.4 + web off -> OK (`201` + `200`)
6. desktop + GPT-5.4 + web on  -> OK (`201` + `200`)
7. desktop + Haiku 4.5 + web off -> OK (`201` + `200`)
8. desktop + Haiku 4.5 + web on  -> OK (`201` + `200`)

---

## Root Cause

Primary root cause in mobile failure path:
- brittle SSE parser in frontend expected only `\n\n` framing and strict single-line `data: ` extraction.
- with CRLF/proxy/mobile framing variants, final `done` event could be missed.
- frontend then threw `Streaming ended without final message` despite `200 OK` completion response.
- catch block always showed "Последнее сообщение не отправлено", even when message POST had already succeeded.

Secondary UX contributor:
- stale mobile frontend risk due cache behavior and missing explicit version guard.

---

## Files Changed

1. `/opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html`
   - robust SSE parsing (CRLF + trailing frame support)
   - improved completion error messaging when message already saved
   - frontend build-id freshness guard + no-cache meta tags

2. `/opt/ai-workspace/storage/projects/ai-platform/docs/progress/mobile_runtime_fix_report_2026-04-23.md`
   - this report

