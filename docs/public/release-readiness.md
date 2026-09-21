# Статус готовности платформы

Платформа сейчас доводится до production-ready состояния без подключения live-ключей провайдеров.

## Что уже работает

- Чат, проекты и история сообщений.
- Email/password вход и гостевой режим.
- Каталог моделей с описаниями и производителями.
- Загрузка файлов в проекты.
- Предпросмотр AI-редактирования файлов с подтверждением.
- Тарифы, токены и базовая панель использования.
- Документация продукта.

## Что работает в демо-режиме

- Оплата YooKassa: интерфейс и backend готовы, live-ключи не подключены.
- Генерация изображений: кнопка есть, без ключей показывает понятное состояние.
- Распознавание речи: загрузка аудио есть, без ключей показывает понятное состояние.
- Web-поиск: surface есть, provider включается конфигурацией.

## Что нужно перед продажами

- Перевести окружение из development в production.
- Подключить PostgreSQL как основной production DB путь.
- Подключить live-ключи OpenAI, Anthropic, Google/Gemini и YooKassa.
- Прогнать полный smoke и browser QA после подключения ключей.
- Проверить списание токенов на чат, файлы, картинки, речь и web-поиск.

## Внутренние чеклисты

- `docs/implementation/PRODUCTION_HARDENING_NEXT.md` — общий hardening-план.
- `docs/implementation/PRODUCTION_ENV_CHECKLIST.md` — production environment.
- `docs/implementation/TOKEN_ACCOUNTING_AUDIT.md` — аудит списания токенов и хранилища.
- `docs/implementation/DEPLOY_ROLLBACK_CHECKLIST.md` — deploy и rollback.
- `docs/implementation/BROWSER_QA_CHECKLIST.md` — ручная проверка в браузере.
- `docs/implementation/RELEASE_SMOKE.md` — smoke-команды перед релизом.

Текущий приоритет до подключения ключей:

- production DB/deploy mode;
- стабильный restart/rollback;
- account UX;
- token/storage accounting verification;
- browser/mobile QA;
- чистый commit-ready diff без runtime-мусора.
