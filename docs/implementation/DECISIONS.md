# Implementation Decisions

## 2026-04-29

Decision:

- Keep `IMPLEMENTATION_EXECUTION_PLAN_2026-04-29.md` as the master execution plan.
- Track actual completed work in `docs/implementation/EXECUTION_LOG.md`.
- Track current active step in `docs/implementation/CURRENT_EXECUTION_STATUS.md`.
- Do not delete or move runtime/user data until the repo hygiene phase explicitly classifies it.

Reason:

- The existing repo has many runtime files, DB files, pycache files, and generated docs mixed into git status.
- A strict execution log prevents losing context when working from another computer.

Decision:

- Add `.gitignore` before any cleanup or feature work.
- Ignore runtime/data/cache files without deleting them.
- Keep `.env.example` files trackable.

Reason:

- The server contains live SQLite DBs and runtime data that should not be removed casually.
- The first safe action is to stop new noise from entering git.

Decision:

- Use `git rm --cached` for tracked runtime/cache/data files.
- Do not physically delete runtime files during Phase 1.2.

Reason:

- The files are not source code, but may still be useful runtime/user state on the server.

Decision:

- Do not install Python packages globally with `--break-system-packages`.

Reason:

- The server Python is externally managed by the OS. A project virtualenv is the safer production path.
