# PostgreSQL migration rehearsal

Дата: 2026-05-01

## Цель

Перед продажами SQLite нужно заменить на PostgreSQL. Релиз нельзя считать production-ready, пока миграции и smoke-тесты не пройдены на PostgreSQL.

## Минимальный rehearsal

1. Поднять отдельную PostgreSQL базу для rehearsal, не production.
2. Задать `DATABASE_URL` для backend.
3. Прогнать миграции Alembic.
4. Запустить backend.
5. Прогнать smoke-набор:

```bash
cd /opt/ai-workspace/storage/projects/ai-platform
python3 scripts/auth_account_smoke.py
python3 scripts/release_surface_smoke.py
python3 scripts/negative_limit_smoke.py
python3 scripts/storage_accounting_smoke.py
```

## Gate

Переход на PostgreSQL разрешен только если:

- миграции проходят с нуля;
- регистрация, вход, billing и logout работают;
- лимиты free plan отказывают корректно;
- учет storage после upload/delete корректный;
- rollback-план проверен на тестовой базе.

## Статус

Rehearsal еще не выполнен, потому что production PostgreSQL не поднимался в этой фазе. Документ и preflight-скрипт добавлены как обязательный gate перед продажами.
