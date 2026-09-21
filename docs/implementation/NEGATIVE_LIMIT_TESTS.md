# Negative limit tests

Дата: 2026-05-01

## Что проверяется

- Free plan не дает создать второй проект.
- Free plan не дает превысить лимит хранилища.
- Free plan не дает отправить запрос, если лимит токенов уже исчерпан.
- Удаление файла возвращает занятое место в `billing/me`.

## Команды

```bash
cd /opt/ai-workspace/storage/projects/ai-platform
python3 scripts/negative_limit_smoke.py
python3 scripts/storage_accounting_smoke.py
```

## Последний результат

`negative_limit_smoke.py`:

```json
{
  "ok": true,
  "project_limit": "Project limit reached for current plan (1).",
  "storage_limit": "Storage limit reached for current plan.",
  "token_limit": "Token limit reached for current plan."
}
```

`storage_accounting_smoke.py`:

```json
{
  "ok": true,
  "before": 0,
  "after_upload": 24,
  "after_delete": 0
}
```

## Вывод

Базовые тарифные ограничения работают на backend-уровне. Перед продажами нужно повторить эти проверки после перехода на PostgreSQL и после подключения YooKassa.
