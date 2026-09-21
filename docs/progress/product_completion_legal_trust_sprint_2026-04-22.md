# Product Completion Sprint Report — Legal Depth + Trust Signals

Date: 2026-04-22
Project root: /opt/ai-workspace/storage/projects/ai-platform
Scope: L1–L7

## 1. Files changed
- /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html
- /opt/ai-workspace/storage/projects/ai-platform/backend/app/api/auth.py
- /opt/ai-workspace/storage/projects/ai-platform/backend/app/services/auth_acceptance_store.py
- /opt/ai-workspace/storage/projects/ai-platform/frontend/terms.html
- /opt/ai-workspace/storage/projects/ai-platform/frontend/privacy.html

## 2. Exact legal sections added
### Terms (`frontend/terms.html`)
Added sections:
1. Допустимое использование
2. Ограничения ИИ
3. Ответственность пользователя
4. Доступность сервиса
5. Ограничение ответственности

Coverage includes:
- no illegal content/use
- no abuse and unauthorized scraping/circumvention
- AI may produce incorrect outputs
- service availability disclaimer
- user responsibility for submitted content
- no liability clause

### Privacy (`frontend/privacy.html`)
Added sections:
1. Какие данные хранятся
2. Как используются данные
3. Сторонняя обработка
4. Срок хранения
5. Контакт

Coverage includes:
- stored data: chats, project files, memory entries
- usage for AI processing
- third-party processing by LLM providers
- simple retention note
- contact placeholder

## 3. How acceptance is stored now
- `POST /api/auth/guest-or-login` now requires `accept_terms: true`.
- If missing/false: request is rejected (`422`).
- Server-side acceptance is persisted in:
  - `storage/auth_acceptance.json`
- Stored fields per user:
  - `accepted_terms: true`
  - `accepted_at: <ISO UTC timestamp>`
- Auth response now includes:
  - `accepted_terms`
  - `accepted_at`

## 4. UI improvements
- Last activity in project/chat lists as relative time:
  - e.g. `5 мин назад`, `2 ч назад`.
- Friendly fallback error text:
  - `Ошибка запроса, попробуйте ещё раз`
- AI disclaimer under input:
  - `Ответы ИИ могут быть неточными`
- Frontend auth submit now sends server acceptance flag:
  - `{ email, accept_terms: true }`

## 5. Smoke checks
- Syntax check:
  - `python -m py_compile backend/app/api/auth.py backend/app/api/auth_deps.py backend/app/core/auth_token.py backend/app/services/auth_acceptance_store.py backend/app/api/legal.py`
  - Result: OK
- Code marker checks verified:
  - acceptance + rate-limit logic present
  - legal sections present in terms/privacy
  - relative activity + friendly error + AI disclaimer present

## 6. Remaining legal gaps (honest)
- No legal versioning (`terms_version`, `privacy_version`) in acceptance records.
- No DSAR/export/delete legal workflow.
- No governing law / dispute resolution clauses.
- Contact email is still placeholder.
- Login rate limit is in-memory only (resets on process restart).
