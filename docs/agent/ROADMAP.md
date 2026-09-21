# ROADMAP — AI Workspace Platform (Product-Only)

Задачи только для пользовательской платформы: проекты, чаты, файлы, модели, UX.

Исключено из scope:
- autonomous developer loop
- manager loop / repair queue / autopilot sprint
- любые правки `backend/app/services/manager_loop.py`, `backend/app/services/repair_queue.py`, `backend/app/api/manager.py`, `scripts/run_continuous.py`, `docs/progress/autopilot_config.json`

Формат каждой задачи:
- ID
- title
- Files
- Change
- Why

---

## Phase 1 — Core User Flow Reliability

### P1.1 Fix message window semantics for chat context

**Files:** `backend/app/services/chat_service.py`  
**Change:** Обновить `get_messages(...)`, чтобы при `limit` возвращались последние N сообщений в хронологическом порядке (сейчас берутся первые N).  
**Why:** `/api/chats/{id}/complete` и UI получают неактуальный контекст в длинных чатах.

### P1.2 Wire `context_builder` into `/api/chats/{chat_id}/complete`

**Files:** `backend/app/api/ai_chat.py`, `backend/app/services/context_builder.py`  
**Change:** Перед вызовом модели формировать единый system context через `context_builder` (project description + memory + recent convo + instructions) и подключить его в prompt.  
**Why:** Сейчас `context_builder` не используется, память проекта не попадает в prompt централизованно.

### P1.3 Harden complete endpoint against model/provider failures

**Files:** `backend/app/api/ai_chat.py`, `backend/app/services/model_router.py`  
**Change:** Добавить deterministic fallback path при пустом/ошибочном ответе модели, защиту от сохранения пустого assistant message, стабильные error details для frontend.  
**Why:** `complete` должен быть устойчивым и предсказуемым в пользовательском сценарии.

### P1.4 Ensure personal chats are created with `user_id`

**Files:** `frontend/chat.html`, `backend/app/api/chats.py`  
**Change:** Передавать `user_id` при создании личного чата и валидировать это на API-слое для personal flow.  
**Why:** Иначе чат может не попадать в `/api/chats?user_id=...` после перезагрузки интерфейса.

---

## Phase 2 — Project Instructions and Context Quality

### P2.1 Add PATCH endpoint for partial project updates

**Files:** `backend/app/api/projects.py`  
**Change:** Добавить `PATCH /api/projects/{project_id}` с тем же контрактом, что `ProjectUpdate`, без обязательных полей.  
**Why:** Инструкции проекта должны обновляться частично и предсказуемо (API parity для UI).

### P2.2 Make instructions update explicitly idempotent in frontend

**Files:** `frontend/chat.html`  
**Change:** Единый helper для сохранения instructions (обработка race, статусы `saving/saved/error`, отключение кнопки только на активный запрос).  
**Why:** Улучшает UX и снижает риск потери изменений в project instructions.

### P2.3 Add context size budgeting across project files

**Files:** `backend/app/api/ai_chat.py`, `backend/app/services/text_extractor.py`  
**Change:** Ввести общий budget на суммарный объём project file context + явную маркировку, какие файлы были усечены.  
**Why:** Стабильность latency и качества ответа при большом числе вложений.

---

## Phase 3 — Chat/Project Lists for UI

### P3.1 Extend chat read schema with list metadata

**Files:** `backend/app/schemas/chat.py`  
**Change:** Добавить поля в list/read контракт: `message_count`, `last_message_at` (nullable), `last_message_preview` (nullable, short).  
**Why:** UI-списки чатов должны показывать живую активность, а не только title/model.

### P3.2 Implement chat list aggregation in service layer

**Files:** `backend/app/services/chat_service.py`  
**Change:** Для list endpoints считать `message_count` и `last_message_at` через SQL aggregation/subquery без N+1.  
**Why:** Производительность и корректная сортировка чатов по активности.

### P3.3 Sort personal and project chat lists by last activity

**Files:** `backend/app/services/chat_service.py`, `backend/app/api/chats.py`  
**Change:** Отдавать чаты в порядке `last_message_at DESC NULLS LAST, created_at DESC`; сохранить стабильный fallback.  
**Why:** Пользователь ожидает видеть последние активные чаты сверху.

### P3.4 Render chat metadata in `chat.html`

**Files:** `frontend/chat.html`  
**Change:** Показывать в карточке чата: `model`, `message_count`, `last_message_at`; добавить компактный subtitle формат.  
**Why:** Улучшает навигацию и читаемость списков.

### P3.5 Add project list metadata for sidebar

**Files:** `backend/app/schemas/project.py`, `backend/app/services/project_service.py`, `backend/app/api/projects.py`  
**Change:** Добавить в список проектов поля `chat_count`, `last_message_at` (aggregated), вернуть их в list response.  
**Why:** Проекты в sidebar должны показывать реальную активность, не только название/описание.

### P3.6 Render project activity metadata in `chat.html`

**Files:** `frontend/chat.html`  
**Change:** В project cards показать `chat_count` и `last_message_at`; fallback для пустых проектов.  
**Why:** Быстрее выбирать нужный проект в multi-project сценарии.

---

## Phase 4 — Endpoint Robustness (User Product)

### P4.1 Return clean 404/400 for invalid project-scoped operations

**Files:** `backend/app/api/chats.py`, `backend/app/api/files.py`, `backend/app/services/project_service.py`  
**Change:** Перед созданием project chat/upload/delete явно проверять существование project и возвращать typed HTTP errors вместо возможных DB-level 500.  
**Why:** Пользовательский API должен быть предсказуемым при ошибочном вводе/устаревших ID.

### P4.2 Make completion attachment handling fault-tolerant

**Files:** `backend/app/api/ai_chat.py`  
**Change:** Локально перехватывать ошибки чтения отдельных файлов/изображений, пропускать только проблемный файл, не роняя весь completion.  
**Why:** Один повреждённый файл не должен ломать весь ответ ассистента.

### P4.3 Add lightweight product observability for chat completions

**Files:** `backend/app/api/ai_chat.py`, `backend/app/api/chats.py`  
**Change:** Логировать structured события user product уровня (chat_id, model, latency_ms, attachment_count, completion_status).  
**Why:** Нужна диагностика user-facing проблем без привязки к autopilot/manager.

---

## Phase 5 — Chat UX Polish

### P5.1 Support “create chat inside selected project” flow

**Files:** `frontend/chat.html`  
**Change:** В модалке `New Chat` учитывать текущий selected project и создавать чат в проекте (с явным UI переключателем Personal/Project).  
**Why:** Сейчас создание нового чата всегда personal, это ломает ожидаемый project workflow.

### P5.2 Add retry action for failed send/complete

**Files:** `frontend/chat.html`  
**Change:** При ошибке отправки показывать inline action `Повторить` для последнего user message.  
**Why:** Уменьшает friction при временных сетевых/провайдерных сбоях.

### P5.3 Improve loading and empty states for chat/project panes

**Files:** `frontend/chat.html`  
**Change:** Привести loading/empty/error состояния списков к единому паттерну, убрать неоднозначные сообщения, добавить короткие CTA.  
**Why:** Финальный UX-полиш для основной пользовательской платформы.
