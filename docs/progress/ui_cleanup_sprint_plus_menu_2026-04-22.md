# UI cleanup sprint: move capabilities into composer plus-menu

Date: 2026-04-22
Project: /opt/ai-workspace/storage/projects/ai-platform

## 1) Files changed
- frontend/chat.html
- backend/app/api/ai_chat.py

## 2) Before/after behavior (U1–U6)

### U1 — remove top-right action buttons
Before:
- Header had standalone capability buttons: `Веб`, `📁 Проект`, `↑ Файл`.

After:
- These three buttons are removed from topbar.
- Header keeps compact controls: user badge, theme toggle, model selector, logout.

### U2 — add composer plus-menu
Before:
- Composer had only plain `+` attachment control, no action menu.

After:
- `+` opens a compact dropdown/popover in composer.
- Menu items:
  - `Загрузить файл`
  - `Поиск в сети`
  - `Создать файл`
  - `Создать таблицу`

### U3 — wire menu actions to real behavior
After mapping:
- `Загрузить файл`
  - In project chat: launches existing project upload flow (`fileInput` -> `uploadProjectFiles`).
  - In personal chat: opens message attachment picker (`msgFileInput`).
- `Поиск в сети`
  - Toggles `state.webMode` used in `/complete` request body (`web_mode`).
  - Shows active composer chip when enabled.
- `Создать файл`
  - Toggles composer intent chip.
  - Sends `extra_data.artifact_intent.type = "txt"` with user message.
- `Создать таблицу`
  - Toggles composer intent chip.
  - Sends `extra_data.artifact_intent.type = "csv"` with user message.

Backend support added:
- Completion endpoint now reads latest user `extra_data.artifact_intent` and forces file artifact mode (`txt/csv/json`), so menu flags affect actual artifact generation path.

### U4 — web mode state in composer
Before:
- Web mode controlled by topbar button.

After:
- Web mode controlled only from composer `+` menu.
- Active state displayed as removable chip `Веб` near composer.
- No dedicated header web button remains.

### U5 — hide project context when irrelevant
Before:
- Personal mode could still feel cluttered with project-related remnants.

After:
- Personal chats keep project heading hidden (`projectHeading.hidden = true` when no project).
- Project context panel remains hidden outside project scope.
- No empty project capability buttons in header.

### U6 — move disclaimer out of input interior
Before:
- `Ответы ИИ могут быть неточными` lived inside composer block under input.

After:
- Disclaimer moved below composer as a subtle separate line (`composer-disclaimer`).
- Input area is cleaner and less visually crowded.

## 3) Where each capability moved
- `Веб` (topbar) -> composer `+` menu item `Поиск в сети` + composer chip `Веб`.
- `↑ Файл` (topbar) -> composer `+` menu item `Загрузить файл`.
- `📁 Проект` (topbar) -> removed from topbar in this cleanup pass (no standalone header control).
- New composer capabilities:
  - `Создать файл` -> intent flag to backend (`artifact_intent: txt`)
  - `Создать таблицу` -> intent flag to backend (`artifact_intent: csv`)

## 4) Screenshot-relevant notes
- Top-right header is visibly cleaner: capability buttons removed.
- Composer now has ChatGPT-like action entrypoint via `+` popover.
- Active capability state is local to composer via compact chips (including removable web mode).
- Disclaimer is visually separated below composer, not competing with text input.

## 5) Smoke checks

Automated:
- `python -m py_compile backend/app/api/ai_chat.py` — OK.

Code-level sanity checks:
- Verified header button IDs/text removed: `webModeBtn`, `attachProjectBtn`, `uploadBtn` absent.
- Verified `+` menu actions exist and are wired (`data-plus-action=*`).
- Verified `sendMessage` passes `artifact_intent` in user message `extra_data` when file/table modes are active.
- Verified `/complete` still receives `web_mode` and backend handles both `web_mode` and `artifact_intent`.

Manual scenarios to run:
1. Open chat: confirm no `Веб/Проект/↑ Файл` buttons in topbar.
2. Click `+`: menu appears with 4 required actions.
3. Enable `Поиск в сети`: chip `Веб` appears; remove chip; state clears.
4. Select `Создать файл`, send prompt: file intent should route to artifact creation flow.
5. Select `Создать таблицу`, send prompt: CSV artifact flow should trigger.
6. In project chat, `Загрузить файл` should upload into project files list.
7. In personal chat, `Загрузить файл` should attach files to the message flow.
8. Disclaimer appears below composer, not inside the input area.
