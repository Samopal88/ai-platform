# Conversational UX Sprint Report (2026-04-23)

## Scope
Implemented UX-1..UX-6 for:
- context retention across follow-up turns
- automatic web routing for current/time-sensitive queries
- compact source presentation model for frontend rendering
- product-level behavior on web-search failure
- query rewriting from recent dialogue context

## Changed Files
1. `/opt/ai-workspace/storage/projects/ai-platform/backend/app/api/ai_chat.py`
2. `/opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html`

## What Was Implemented

### UX-1 Context retention across turns
- Added follow-up resolution logic that reconstructs underspecified user turns using recent user+assistant context.
- Added `resolved_user_query` usage in:
  - project context builder input
  - memory search input
  - web-query generation
- Added system hint for underspecified turns to keep the model on the active topic.

### UX-2 Automatic web decision
- Added automatic web routing heuristics in backend.
- Web is auto-triggered for time-sensitive/current intents (weather/news/prices/rates and words like today/tomorrow/current/latest).
- Manual web toggle remains optional override (`web_mode=true` forces web).
- Default requests no longer require manual web toggle.

### UX-3 Clean sources
- Removed raw source-dump appending to answer text.
- Backend now returns structured source metadata in `extra_data.sources` (`title`, `url`, `domain`).
- Frontend renders sources in a compact collapsible block "Показать источники".
- Block defaults to collapsed when sources count > 2.

### UX-4 Web-mode answer policy
- Updated web-assisted system instructions:
  - respond naturally
  - no provider/internet capability meta explanation in user text
  - uncertainty only when data is weak/conflicting
- On web failure, backend returns a product-level non-breaking message instead of provider internals.

### UX-5 Query rewriting
- Added query builder that combines current user text with recent dialogue context.
- Handles ellipsis/follow-ups like:
  - "в Соболево" -> `погода в Соболево завтра`
  - "а так?" keeps active weather+location context

## UX-6 Live verification

Verification run against live updated app instance on `http://127.0.0.1:8012`.

Dialogue tested:
1. "Какая погода на завтра?"
2. "в Соболево"
3. "а так?"
4. "Новости за сегодня"
5. "Что такое FastAPI?"

Observed:
- #1 auto-web: yes (`web_auto=true`), query: `погода завтра`
- #2 auto-web: yes (`web_auto=true`), query: `погода в Соболево завтра`
- #3 auto-web: yes (`web_auto=true`), query: `погода в Соболево завтра`
- #4 auto-web: yes (`web_auto=true`), query: `новости сегодня`
- #5 auto-web: no (`web_auto=false`), stayed offline (timeless/general question)

Context preservation verdict:
- Preserved for weather follow-ups (#2 and #3), including location and time hint inheritance.

Web provider availability during verification:
- `web_available=false` in this local run, so product-level fallback response was returned for time-sensitive queries.
- Chat flow remained non-breaking.

## Notes
- Existing non-restarted deployment instances can still show old behavior until restart.
- Updated logic verified on fresh runtime with current code.
