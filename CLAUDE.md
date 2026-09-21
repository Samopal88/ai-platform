# Claude Code — AI Workspace Platform

## Quick Start

Before doing anything else, read:
- `docs/agent/SYSTEM_MAP.md` — architecture and file locations
- `docs/agent/PROJECT_BRIEF.md` — what the platform does and DoD rules
- `docs/progress/CURRENT_STATUS.md` — current runtime state

Do **not** scan all files. Use the map.

---

## Project Root

```
/opt/ai-workspace/storage/projects/ai-platform
```

Live server: `http://localhost:8000` (uvicorn, systemd service `ai-workspace`)

---

## Two-Tier Manager Architecture

The system runs as a two-tier autonomous loop:

- **Manager** (`manager_loop.py`) — reads ROADMAP, selects task, builds step prompt, reviews result, decides verdict
- **Worker** (`file_executor.py`) — receives only the step prompt, creates/modifies files, returns `files_changed`

Manager verdicts: `accepted` | `retry_required` | `blocked`

On `accepted` → task is marked `[x]` in ROADMAP.md automatically → next cycle picks next task.

**Key endpoints:**
```
POST /api/manager/run-cycle       — one cycle (background)
POST /api/manager/run-cycle-sync  — one cycle (blocks, for testing)
POST /api/manager/run-auto        — continuous loop until tasks exhausted
POST /api/manager/reset           — reset to idle
GET  /api/manager/state           — current lifecycle state
GET  /api/manager/next-task       — preview next task (no side effects)
GET  /api/dashboard/manager-state — dashboard-formatted state
GET  /api/health                  — liveness check
GET  /api/blocked-tasks           — tasks that failed max retries
```

---

## ROADMAP

`docs/agent/ROADMAP.md` — the task queue.

- Tasks marked `[x]` are **done** and skipped by `choose_next_task()`
- Phases 1–3 (tasks 1.1–3.5) are all `[x]` — fully implemented
- Add new tasks above the `## Deferred` section
- Format required: `### N.N Title`, `**Files:** path`, `**Change:** ...`

---

## Key Rules

### Reading
- Use `docs/agent/SYSTEM_MAP.md` to find any file before opening it
- Read only the specific file relevant to the current task
- Current job state: `storage/jobs/<id>.json`
- Runtime status: `docs/progress/CURRENT_STATUS.md`

### Writing
- Only write inside SAFE_DIRS (listed in `docs/agent/PROJECT_BRIEF.md`)
- Sandbox for scratch/test files: `sandbox/`
- No `../` path traversal — stay inside PROJECT_ROOT
- After any write, verify the file exists on disk

### Execution
- Work step-by-step: one file change → verify → next step
- Never inject review/fix markdown into file content
- `original_task` is always the execution payload — not the review summary
- A task is done when required files exist, not when output says "completed"

### State
- Do not manually edit `docs/progress/CURRENT_STATUS.md`
- `status_updater.sync_status_file()` handles it automatically
- Manager state: `docs/progress/manager_state.json`
- Orchestrator state: `docs/progress/orchestrator_state.json`

---

## Do Not Touch

- `nginx`, `firewall`, `systemd` units
- `.env`, `secrets`, `credentials` files
- `backend/app/main.py`, `backend/app/__init__.py`
- Anything outside PROJECT_ROOT

---

## Product Requirements

Before implementing features, check `docs/agent/PRODUCT_MAP.md`
to identify relevant product requirements.

---

## Workflow Reference

See `docs/agent/WORKFLOW.md` for the full task pipeline.

---

## File Structure Summary

```
backend/app/
  api/jobs.py          — task endpoints + /api/health
  api/dashboard.py     — dashboard data endpoints
  api/manager.py       — manager loop endpoints (run-cycle, run-auto, reset, state)
  services/
    manager_loop.py    — TWO-TIER ENGINE: selecting→planning→executing→reviewing→verdict
    orchestrator.py    — legacy orchestrator (chatgpt_self / manager mode)
    chatgpt_executor.py— primary executor (ChatGPT-first)
    file_executor.py   — real file ops (worker)
    task_intake.py     — ROADMAP parser + choose_next_task()
    supervisor.py      — DoD inference
    job_queue.py       — queue + background thread
docs/agent/            — agent reference files + ROADMAP.md
docs/progress/         — runtime state JSON + CURRENT_STATUS.md
  manager_state.json   — two-tier loop state (source of truth)
storage/jobs/          — per-job JSON records
sandbox/               — safe scratch space
frontend/dashboard.html— dashboard UI with Manager Loop panel + Run Auto button
scripts/check_state.py — state consistency checker
tests/                 — test_file_executor.py, test_supervisor.py
```
