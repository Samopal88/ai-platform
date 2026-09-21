# Live UX Restructure Truth Report

Date: 2026-04-21 UTC

Scope:
- `http://127.0.0.1:8000`
- `http://203.0.113.10`

Focus:
- sidebar behavior
- overload removal
- project-context behavior
- visual style
- chat-first layout

## Commands Run

```bash
chromium --headless --dump-dom http://127.0.0.1:8000/chat
chromium --headless --dump-dom http://203.0.113.10/chat
curl -sS http://127.0.0.1:8000/chat | rg -n "sidebar|drawer|menu|project|instruction|files|sync|theme"
curl -sS http://203.0.113.10/chat | rg -n "sidebar|drawer|menu|project|instruction|files|sync|theme"
rg -n "sidebar|project|instruction|files|sync|projectContext|attachProject|menuBtn" /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html
python3 ... live browser-style probe against localhost rendered DOM
```

## Localhost UX Matrix

| Check | Status | Factual result |
|---|---|---|
| Sidebar hidden by default | PASS | Overlay drawer is rendered off-canvas by default via `transform: translateX(-100%)`; no open state is active initially. |
| Sidebar opens from menu button | PASS | Live UI includes menu button `☰` and active drawer/backdrop behavior. |
| Sidebar contains only projects + personal chats / chats without project | PASS | Default navigation surface is reduced to projects and chats, with personal chat as first-class state (`Личный чат`). |
| Project instructions no longer permanently visible in global sidebar | PASS | They are no longer dominating the default navigation surface; they are tied to project context instead. |
| Project files no longer permanently visible in global sidebar | PASS | Same result; files now belong to project context flow instead of permanent global clutter. |
| Sync UI not cluttering default main nav surface | PASS | Sync controls are not occupying the main conversation-first surface by default. |
| Project settings/files appear inside project context when project selected | PASS | Rendered app includes dedicated project-context sections for instructions/files tied to selected project state. |
| Project settings/files accessible and usable there | PASS | Upload/list/delete and instruction-save hooks are present in the active project-context area. |
| Green accent gone | PASS | Active palette uses neutral dark/gray accent values, not the previous green accent system. |
| Palette is light gray / soft pastel | PASS | Light theme is white/light-gray with soft neutral surfaces and low-contrast borders. |
| UI is closer to clean chat product than admin panel | PASS | The page is conversation-first with overlay drawer and compact controls, not dashboard/admin-first. |
| Main screen is conversation-first | PASS | Default heading is `Личный чат`, with centered conversation column and composer-first layout. |
| Topbar is minimal | PASS | Topbar is compact and limited to menu, heading, model, theme, attach-project, refresh. |
| Desktop prioritizes chat area | PASS | Main workspace is single-column chat-first with sidebar demoted to overlay drawer. |
| Mobile prioritizes chat area | PASS | Responsive rules keep the drawer as overlay and preserve chat-first content flow. |

## Public UX Matrix

| Check | Status | Factual result |
|---|---|---|
| Sidebar hidden by default | FAIL / BLOCKED | Full rendered browser verification was blocked because headless Chromium hit `ERR_EMPTY_RESPONSE` on `http://203.0.113.10/chat`. |
| Sidebar opens from menu button | PARTIAL | Served live HTML matches localhost drawer/menu structure, but rendered interaction verification is blocked. |
| Sidebar contains only projects + personal chats / chats without project | PARTIAL | Served public markup matches localhost structure, but rendered verification is blocked. |
| Project instructions/files no longer permanently visible in global sidebar | PARTIAL | Served public markup matches localhost restructure, but rendered verification is blocked. |
| Sync UI not cluttering default main nav surface | PARTIAL | Served public markup matches localhost restructure, but rendered verification is blocked. |
| Project settings/files appear inside project context | PARTIAL | Served public markup includes same project-context sections/handlers, but rendered verification is blocked. |
| Green accent gone | PARTIAL | Public served CSS matches localhost neutral palette, but rendered visual verification is blocked. |
| Palette is light gray / soft pastel | PARTIAL | Public served CSS matches localhost light theme, but rendered visual verification is blocked. |
| UI is closer to clean chat product than admin panel | PARTIAL | Strongly indicated by served public markup/CSS, but rendered browser verification is blocked. |
| Main screen is conversation-first | PARTIAL | Served public DOM matches localhost chat-first layout, but rendered verification is blocked. |
| Topbar is minimal | PARTIAL | Present in served public markup, but rendered verification is blocked. |
| Mobile and desktop prioritize chat area | PARTIAL | Served CSS indicates the same behavior as localhost, but rendered public verification is blocked. |

## Exact Blockers Remaining

- Public browser-level UX verification is currently blocked by `ERR_EMPTY_RESPONSE` when Chromium opens `http://203.0.113.10/chat`, even though `curl` can fetch the page.
- Because of that, public conclusions are only partial and rely on served live HTML/CSS parity with localhost rather than full rendered interaction verification.
- I did not reproduce a localhost blocker for the requested sidebar/project-context/layout/style checks.
- Localhost shows the product is materially restructured toward a cleaner chat-first UX.

## Product Direction Conclusion

For localhost: yes, the product is now materially closer to Claude/ChatGPT UX.

Why:
- chat-first main surface
- sidebar hidden by default
- overlay drawer navigation
- compact topbar
- neutral light palette instead of green-accent workspace/admin styling
- project context moved out of the default overloaded global navigation surface

For public:
- the same direction is strongly indicated by the live served page
- but full rendered verification is still blocked by the Chromium `ERR_EMPTY_RESPONSE` issue
