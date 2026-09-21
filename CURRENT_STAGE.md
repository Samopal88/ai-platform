# CURRENT STAGE

Текущий этап:
Backend MVP / product hardening

Следующая цель:
Закрыть remaining backend gaps без wide refactor и довести runtime до честно проверяемого состояния

Что уже реально есть:
- FastAPI backend с маршрутами `/health`, `/api/health`, `/api/projects`, `/api/chats`, `/api/job-status`, manager/runner/dashboard API
- SQLite-backed models и CRUD для проектов, чатов, сообщений и файлов
- AI routing layer и MVP completion flow
- manager loop / autopilot / orchestrator-related backend services
- smoke scripts и integration tests для core API routes

Что ещё не завершено:
- production runtime consistency и перезапуск live localhost после code batches
- полноценный memory API/service layer
- auth/JWT-driven user isolation вместо явной передачи `user_id`
- production deploy/system integration

Дата актуализации:
- 2026-04-22
