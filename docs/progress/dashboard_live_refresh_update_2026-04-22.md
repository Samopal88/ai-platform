# Dashboard Live Refresh + Progress UI (2026-04-22)

## 1) Изменённые файлы
- `frontend/dashboard.html`
- `backend/app/services/manager_human_status.py`

## 2) Добавленные UI-блоки
- Автообновление dashboard каждые 2 секунды с безопасным start/stop (без дублирующихся interval).
- В `Manager Status`:
  - индикатор `Live / Offline / Updating...`
  - `Last updated` с предупреждением при >10s без успешного refresh
  - компактная ошибка `Не удалось обновить статус`
  - live status badge по lifecycle
  - human-readable action при executing:
    - `Сейчас выполняется: <task_id> — <task_title>`
  - Sprint progress block:
    - Sprint ID, Elapsed, Accepted, Blocked, Retry count
    - progress bar по `accepted / max_accepted` (если доступно)
  - Compact recent-result panel:
    - executor
    - last verdict
    - files changed count
    - verified_unchanged count

## 3) Используемые поля human-status/state
- Базовые: `status`, `summary`, `task_id`, `task_title`, `phase`,
  `retry_count`, `max_retries`, `accepted_count`, `blocked_count`,
  `changed_files`, `last_executor`, `last_verdict`,
  `last_verified_unchanged`, `next_action`, `check_command`,
  `expected_result`, `safe_to_auto_run`, `reason_not_safe`, `mode`.
- Добавлены в observer-слой (`human-status`):
  - `sprint_id`
  - `sprint_accepted`
  - `sprint_blocked`
  - `sprint_max_accepted` (из `docs/progress/autopilot_config.json`)
  - `sprint_elapsed_sec` (если есть `sprint_start_ts`)

## 4) Какие проверки пройдены
- `python -m py_compile backend/app/services/manager_human_status.py` — OK.
- Поиск ключевых интеграций (`rg`) — поля/ID/функции присутствуют.
- Проверка interval:
  - старый глобальный 5s refresh удалён;
  - добавлен singleton 2s refresh;
  - job-polling interval и локальный auto-run polling сохранены.

## 5) Ограничения
- `sprint_elapsed_sec` отображается как `—`, если `sprint_start_ts` отсутствует в state.
- При недоступности backend отображается `Offline` и `Не удалось обновить статус`.
- Полноценный браузерный e2e в этой среде не запускался; выполнены статические и синтаксические проверки.
