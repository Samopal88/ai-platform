# Provider route audit

Дата: 2026-05-01

## Решение

Платформа должна поддерживать два OpenAI-compatible провайдера:

- `RouterAI` - целевой провайдер для платной версии (`ROUTERAI_API_KEY`, `ROUTERAI_BASE_URL`);
- `RuAPI` - временный провайдер через текущий `OPENAI_API_KEY`, `OPENAI_BASE_URL`.

Router уже подготовлен под цепочку:

1. RouterAI.
2. RuAPI / OpenAI-compatible.
3. Native Anthropic fallback для `claude-*`.

## Модели из текущего RuAPI списка

- `claude-opus-4.7`
- `claude-opus-4.6`
- `claude-opus-4.5`
- `claude-sonnet-4.6`
- `claude-sonnet-4.5`
- `claude-haiku-4.5`
- `gpt-5.4`
- `gpt-5.2`
- `gpt-4.1`
- `gemini-3.1-pro-preview`
- `gemini-2.5-pro`

## Дефолт и экономика

Opus не должен быть моделью по умолчанию. Каталог теперь отсортирован так, чтобы первыми шли экономичные модели:

1. `claude-haiku-4.5`
2. `gpt-4.1`
3. `gpt-5.2`

UI default: `gpt-4.1`.

## Текущая проблема временного ключа

На текущем runtime ключе RuAPI часть моделей периодически возвращает:

- `403 unauthorized: not licensed to use Copilot`;
- `400 model_not_supported`;
- `502 provider2_not_configured`.

Это не ошибка UI-каталога. Это блокер стабильного платного запуска на временном ключе. Для продаж нужен стабильный RouterAI или другой production ключ RuAPI.

## Проверки

- `scripts/provider_proxy_matrix.py` показывает матрицу доступности моделей без раскрытия ключей.
- `scripts/provider_route_smoke.py` проверяет route через публичный backend API.
- `scripts/router_direct_smoke.py` проверяет backend router напрямую.
- `scripts/runtime_env_shape.py` показывает только форму env, без секретов.
