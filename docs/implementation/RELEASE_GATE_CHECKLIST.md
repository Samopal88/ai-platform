# Release gate checklist

Дата: 2026-05-01

## Gate A: Demo-ready

- Health endpoint возвращает ok.
- Public chat открывается.
- Email/password auth работает.
- Docs открываются отдельным docs UI, а не тем же чатом.
- Model picker работает и показывает описания.
- Тариф free показывает корректные токены и storage.
- Free plan лимиты подтверждены smoke-тестами.

## Gate B: Paid beta

- PostgreSQL rehearsal пройден.
- YooKassa test payments пройдены.
- Webhook YooKassa идемпотентный.
- SMTP production работает.
- Password reset работает.
- Провайдеры моделей подключены реальными ключами.
- Readiness endpoint показывает все обязательные integrations ready.

## Gate C: Public sales

- Домен и HTTPS включены.
- Backups включены и восстановление проверено.
- Monitoring включен.
- Legal docs финализированы.
- Token accounting сверено по нескольким провайдерам.
- Browser QA evidence сохранен.
- Rollback rehearsed.

## Текущий вывод

Сейчас проект близок к demo-ready, но еще не paid public sales. Главные блокеры: production integrations, PostgreSQL, YooKassa, SMTP, финальная UX QA.
