# AI Platform — руководство на русском

AI Platform — самостоятельная веб-платформа для работы с AI-моделями внутри
проектов: с чатами, файлами, памятью, историей, лимитами и инструментами
оператора. Интерфейс и API запускаются одним FastAPI-приложением.

## Быстрый запуск

Нужны Git и Python 3.11 или новее.

Linux/macOS:

```bash
git clone https://github.com/Samopal88/ai-platform.git
cd ai-platform
bash scripts/install.sh
.venv/bin/python scripts/ai_platform.py run
```

Windows PowerShell:

```powershell
git clone https://github.com/Samopal88/ai-platform.git
cd ai-platform
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
.venv\Scripts\python.exe scripts\ai_platform.py run
```

Мастер установки:

1. создаёт отдельное Python-окружение `.venv`;
2. устанавливает зависимости backend;
3. генерирует два независимых секретных ключа;
4. спрашивает адрес, порт и AI-провайдера;
5. сохраняет закрытые настройки в `backend/.env`.

После запуска откройте <http://127.0.0.1:8000/chat>. Панель управления доступна
по адресу <http://127.0.0.1:8000/dashboard>, документация API — по адресу
<http://127.0.0.1:8000/docs>.

## Настройка AI-провайдера

При первой установке можно выбрать `none` и добавить ключ позже. Откройте
`backend/.env` и заполните одну подходящую группу:

```dotenv
# OpenAI или совместимый API
OPENAI_API_KEY="ваш-ключ"
OPENAI_BASE_URL="https://api.openai.com/v1"

# Anthropic
ANTHROPIC_API_KEY="ваш-ключ"

# Альтернативные маршруты
ROUTERAI_API_KEY=""
ROUTERAI_BASE_URL=""
RUAPI_API_KEY=""
RUAPI_BASE_URL=""
CLAUDEHUB_API_KEY=""
CLAUDEHUB_BASE_URL=""
```

Перезапустите приложение после изменения `.env`. ID Telegram-канала этому
проекту не нужен: здесь настраиваются AI-провайдеры и, при необходимости,
база, почта, платежи и внешние сервисы.

## Полезные команды

```bash
# Проверить установку
.venv/bin/python scripts/ai_platform.py check

# Запустить в режиме разработки
.venv/bin/python scripts/ai_platform.py run --reload

# Проверить уже запущенный сервер
.venv/bin/python scripts/ai_platform.py status

# Linux: добавить автозапуск для текущего пользователя
.venv/bin/python scripts/ai_platform.py service-install
```

Подробности, включая PostgreSQL, SMTP, YooKassa и безопасный production-запуск,
описаны в [полном руководстве](INSTALLATION.md).

## Что важно знать

- По умолчанию используется SQLite: этого достаточно для локальной разработки.
- Redis может отсутствовать; health-check сообщит о его состоянии отдельно.
- Без API-ключа интерфейс и локальные функции запускаются, но реальные ответы
  внешней модели работать не будут.
- YooKassa, email, web search, генерация изображений и распознавание речи требуют
  отдельных рабочих ключей или сервисов.
- Проект пока находится на стадии MVP/product hardening, а не готового SaaS.
