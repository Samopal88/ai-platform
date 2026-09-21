# Итог UX Sprint (2026-04-23)

Выполнено:
- Исправлено удержание контекста для follow-up реплик (UX-1).
- Добавлен автоматический web-routing для актуальных запросов без обязательного ручного переключателя (UX-2).
- Убрана «сырая» выдача источников из текста ответа; источники передаются структурировано и показываются в компактном collapsible-блоке (UX-3).
- Обновлена политика ответов для web-режима и graceful fallback при сбое поиска без поломки чата (UX-4).
- Добавлен query rewriting на основе последних turn’ов для эллиптических запросов (UX-5).

Live verification (UX-6):
1. «Какая погода на завтра?» -> auto-web: да
2. «в Соболево» -> auto-web: да, контекст сохранён
3. «а так?» -> auto-web: да, контекст сохранён
4. «Новости за сегодня» -> auto-web: да
5. «Что такое FastAPI?» -> auto-web: нет (offline/timeless)

Изменённые файлы:
- /opt/ai-workspace/storage/projects/ai-platform/backend/app/api/ai_chat.py
- /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html
- /opt/ai-workspace/storage/projects/ai-platform/backend/docs/UX_SPRINT_REPORT_2026-04-23.md

Дополнительно сохранён этот итог:
- /opt/ai-workspace/storage/projects/ai-platform/backend/docs/FINAL_SUMMARY_2026-04-23.md
