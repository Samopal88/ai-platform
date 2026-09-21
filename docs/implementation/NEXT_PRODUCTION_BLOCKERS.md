# Next production blockers

Дата: 2026-05-01

## Процент готовности

- Demo/MVP: 77-79%.
- Paid production без реальных ключей: 54-56%.
- Полный Vision: 47-50%.

## Что уже подтверждено

- Health endpoint работает.
- Auth/account smoke проходит.
- Release surface smoke проходит.
- Free plan project/storage/token limits проходят negative smoke.
- Storage accounting после upload/delete проходит smoke.
- Ключевые backend modules и smoke scripts компилируются.

## Блокеры до продаж

1. PostgreSQL rehearsal и переход с SQLite.
2. YooKassa test/live flow и webhook idempotency.
3. SMTP и password reset.
4. Реальные AI provider keys: OpenAI, Anthropic, Gemini, image, speech.
5. Финальный model picker UX и проверка реальных provider routes.
6. Browser QA evidence desktop/mobile.
7. HTTPS/domain.
8. Monitoring и backups.
9. Legal docs финальная вычитка.
10. Token accounting сверка на реальных ответах провайдеров.

## Следующие автономные фазы

- Собрать единый `scripts/full_release_smoke.py`.
- Убрать временные manual-only проверки из release flow.
- Подготовить PostgreSQL rehearsal compose/systemd path.
- Подготовить YooKassa test-mode contract.
- Доделать SMTP/password reset backend flow.
