# Hotfix product sprint: chat flow, web mode, file creation, local UI cleanup

Дата: 2026-04-22

## 1. Exact files changed
- frontend/chat.html
- backend/app/api/ai_chat.py
- backend/app/api/chats.py
- backend/app/services/chat_service.py

## 2. Before/after by F1–F5

### F1 — remove manual chat title entry completely
Before:
- Во фронтенде оставался поток с modal/field для ручного ввода названия чата.

After:
- Модал и input для названия чата удалены.
- `+ Новый чат` создаёт чат сразу (`createChatImmediate`).
- Дефолт backend title остаётся `Новый чат`.
- Добавлен backend auto-title на первом user message, если title всё ещё `Новый чат`.
- Обновление title отражается в sidebar автоматически.

Ключевые точки:
- frontend/chat.html:2821
- backend/app/services/chat_service.py:114
- backend/app/api/chats.py:213

### F2 — hide project header in personal chats
Before:
- В personal режиме мог оставаться пустой project-разделитель/контекст.

After:
- Разделитель заголовка (`/`) показывается только при наличии и проекта, и заголовка чата.
- Статус `Проект: ...` не показывается в personal mode.

Ключевые точки:
- frontend/chat.html:2219
- frontend/chat.html:2646

### F3 — add explicit web-search mode
Before:
- `Веб` в UI не проходил как явный backend-флаг completion.

After:
- Frontend отправляет `web_mode` в `/api/chats/{chat_id}/complete`.
- Backend принимает `CompletionRequest.web_mode`.
- Если web provider не сконфигурирован, backend честно отвечает: `Веб-поиск сейчас недоступен`.
- При включённом web_mode добавлен guard-инструктаж, чтобы не отвечать “у меня нет интернета”.

Ключевые точки:
- frontend/chat.html:2055
- frontend/chat.html:2059
- backend/app/api/ai_chat.py:48
- backend/app/api/ai_chat.py:171
- backend/app/api/ai_chat.py:300

### F4 — file creation from chat requests
Before:
- Создание файлов было нестабильно представлено в UI (в т.ч. для относительных `/api/...` ссылок).

After:
- Поддержка реального создания CSV/TXT/JSON сохранена и доведена.
- Для project chat — файл создаётся в project storage.
- Для personal chat — создаётся temp artifact с download endpoint.
- В ответ assistant добавляется `extra_data.artifact`.
- В UI добавлена явная кнопка скачивания в bubble ассистента.
- Markdown parser теперь обрабатывает и относительные ссылки `/api/...`.

Ключевые точки:
- backend/app/api/ai_chat.py:128
- backend/app/api/ai_chat.py:389
- backend/app/api/ai_chat.py:412
- frontend/chat.html:2450

### F5 — move generation/loading indicator under last user message
Before:
- Индикатор генерации показывался как assistant bubble не привязанно к последнему user bubble.

After:
- Thinking placeholder рендерится как `message-row user thinking-row` сразу под последним user bubble.
- Для стадии генерации не используется top-of-dialog loading banner.

Ключевые точки:
- frontend/chat.html:2420
- frontend/chat.html:786

## 3. Web mode: truly live or UI-gated
Текущее состояние: backend-gated.

- Это не просто UI-тумблер: флаг реально передаётся в backend и обрабатывается.
- Если не заданы `WEB_SEARCH_ENABLED` и `WEB_SEARCH_PROVIDER`, backend возвращает честный ответ `Веб-поиск сейчас недоступен`.
- Полноценный live web-search требует включённого/настроенного провайдера.

## 4. File creation: real or limited
Реальное создание файлов: да, для:
- CSV
- TXT
- JSON

Ограничения:
- XLSX не добавлен (optional scope).

Скоуп сохранения:
- Project chat: в project files.
- Personal chat: temp artifact (downloadable).

## 5. Smoke checks with concrete scenarios
Выполнено:
- `python -m py_compile backend/app/api/ai_chat.py backend/app/api/chats.py backend/app/services/chat_service.py` — OK.

Попытка теста:
- `python -m pytest tests/test_mvp_api.py -k "personal_chat or chats" -q`
- Результат: ошибка окружения БД при collection (`sqlite3.OperationalError: unable to open database file`).

Ручные smoke-сценарии:
1. Нажать `+ Новый чат` в personal и project контексте: чат создаётся сразу, без запроса названия.
2. В новом чате отправить первое сообщение: title меняется с `Новый чат` на авто-сгенерированный.
3. Открыть personal chat: нет пустого `Проект:` блока/разделителя в хедере.
4. Включить `Веб` и отправить запрос без настроенного web provider: получить `Веб-поиск сейчас недоступен`.
5. Запросить `создай таблицу csv ...`: получить сообщение с кнопкой скачивания, скачать реальный файл.
6. После отправки сообщения: `ИИ думает...` отображается под последним user bubble.
