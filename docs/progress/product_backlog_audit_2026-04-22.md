# Product Backlog Audit — AI Workspace Platform (2026-04-22)

## 1) Product gap analysis

### backend/app/api/
- `backend/app/api/ai_chat.py`
  - `context_builder` не подключён, контекст собирается вручную.
  - Устойчивость `complete` ограничена: нет строгого guard на пустой ответ/частичные ошибки вложений.
- `backend/app/api/projects.py`
  - Есть `PUT`, но нет `PATCH` для частичного обновления project instructions.
- `backend/app/api/chats.py`
  - Personal chat может создаваться без `user_id`.
  - List-контракт чатов без activity-полей для UI.
- `backend/app/api/files.py`
  - Project-scoped операции не валидируют существование проекта явно до DB-операций.

### backend/app/services/
- `backend/app/services/chat_service.py`
  - `get_messages(limit)` возвращает первые N (старые), а не последние N.
  - Нет агрегаций `message_count/last_message_at` для list UX.
- `backend/app/services/context_builder.py`
  - Реализован, но не используется в runtime пути `/api/chats/{chat_id}/complete`.
- `backend/app/services/project_service.py`
  - Нет activity-метаданных проектов для sidebar.
- `backend/app/services/model_router.py`
  - Базовый fallback есть, но нет достаточной product-level observability по completion.

### backend/app/schemas/
- `backend/app/schemas/chat.py`
  - Нет `message_count`, `last_message_at`, `last_message_preview`.
- `backend/app/schemas/project.py`
  - Нет `chat_count`, `last_message_at`.
- `backend/app/schemas/file.py`
  - Критичных gap для текущего UI не найдено.

### frontend/chat.html
- Personal chat создаётся без явной передачи `user_id`.
- В списках чатов/проектов нет activity-метрик.
- Нет retry-action для failed send/complete.
- `New Chat` flow всегда personal, без явного сценария создания чата в выбранном проекте.

## 2) Что реально влияет на пользовательский сценарий
- Неправильное окно сообщений (старые вместо последних) ухудшает качество ответов.
- Неиспользуемый `context_builder` снижает качество project-aware ответов.
- Отсутствие `PATCH` для instructions ограничивает аккуратный UX обновления.
- Нет `message_count/last_message_at` в API+UI списках.
- Personal chat без `user_id` может “пропадать” после reload в user-scoped списке.
- `complete` не должен падать целиком из-за проблемного файла/вложения.

## 3) Новый roadmap по фазам
- Полностью перезаписан файл `docs/agent/ROADMAP.md` в product-only формате.
- Исключены manager/repair/autopilot задачи.
- Добавлено 17 маленьких задач по фазам:
  - Phase 1: `P1.1`–`P1.4`
  - Phase 2: `P2.1`–`P2.3`
  - Phase 3: `P3.1`–`P3.6`
  - Phase 4: `P4.1`–`P4.3`
  - Phase 5: `P5.1`–`P5.3`

## 4) Safe for autopilot
- `P1.1`, `P1.2`, `P1.3`, `P1.4`
- `P2.1`, `P2.3`
- `P3.1`, `P3.2`, `P3.3`, `P3.5`
- `P4.1`, `P4.2`, `P4.3`

## 5) Review-only
- `P2.2`
- `P3.4`
- `P3.6`
- `P5.1`
- `P5.2`
- `P5.3`

## 6) Exact first 5 task IDs для запуска
1. `P1.1`
2. `P1.2`
3. `P1.3`
4. `P1.4`
5. `P2.1`
