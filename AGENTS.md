# AGENTS.md — AI Workspace Platform

Instructions for OpenAI Codex, ChatGPT coding agent, and any autonomous agent
working on this project.

---

## Project Root

```
/opt/ai-workspace/storage/projects/ai-platform
```

---

## Start Here

Read these files first, in order, before touching any code:

1. `docs/agent/SYSTEM_MAP.md` — full directory layout, API routes, call graph
2. `docs/agent/PROJECT_BRIEF.md` — purpose, components, DoD, safe paths
3. `docs/progress/CURRENT_STATUS.md` — current runtime state

**Token budget rule**: these three files together are your full project context.
Do not read other files unless SYSTEM_MAP points you to a specific one.

---

## Token Economy Rules

| Do | Don't |
|---|---|
| Read SYSTEM_MAP to locate a file | Scan `backend/app/services/*.py` wholesale |
| Read one target file per step | Read all services to understand one function |
| Use `storage/jobs/<id>.json` for job state | Read all jobs to find the active one |
| Read `docs/progress/CURRENT_STATUS.md` for status | Re-read orchestrator_state + 4 other state files |
| Cache PROJECT_BRIEF for the session | Re-read it on every step |

---

## Execution Rules

### File operations
- Write only inside SAFE_DIRS:
  `sandbox/` `tests/` `docs/` `storage/` `scripts/` `frontend/`
  `backend/app/services/` `backend/app/api/` `backend/app/models/`
  `backend/app/core/` `backend/app/generated/`
- Fallback for unknown paths: write to `sandbox/<filename>`
- Verify file exists after every write before marking step done
- No `../` traversal — stay inside PROJECT_ROOT

### Content
- File content must reflect the actual task description
- Never include review markdown in file content:
  `## Self-Correction`, `## REQUIRED FIXES`, `Attempt N to fix`, etc.
- No placeholder content like `print("done")` unless the task literally asks for it

### Pipeline
- Pass `original_task` to file executor — not the review/fix summary
- Complete one step fully before starting the next
- After each step: record `files_changed`, update job progress
- Mark complete only when required files exist on disk

---

## API Reference (quick)

| Endpoint | Use |
|---|---|
| `POST /api/chat-start` | Submit task, get `job_id` |
| `GET /api/job-status/<id>` | Poll for result |
| `GET /api/active-job` | Check if anything is running |
| `GET /api/queue-status` | Queue counts |
| `POST /api/orchestrate` | Manager-mode (step-by-step) |

---

## Definition of Done

Task is complete when:
1. All target files exist on disk
2. `orchestrator_state.json` → `status: completed`, `current_task: null`
3. Job record → `status: finished`, `files_changed` non-empty (if files expected)
4. No `error` in job record

---

## Do Not Touch

- `nginx`, `systemd`, firewall, `.env`, secrets
- `backend/app/main.py`, any `__init__.py`
- Files outside PROJECT_ROOT

---

## Full Workflow

See `docs/agent/WORKFLOW.md` for the complete step-by-step pipeline with
anti-patterns and common task examples.
