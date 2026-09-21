# AI Workspace Platform — Project Brief

## Purpose

File-based AI task execution platform. Accepts tasks via HTTP API, executes them
as real file operations inside the project, tracks progress in JSON state files,
and exposes results to a web dashboard.

---

## What the Platform Does

1. User submits a task prompt → `/api/chat-start` or `/api/orchestrate`
2. A job is created in `storage/jobs/<id>.json`
3. The orchestrator breaks the task into steps and executes them
4. The file executor performs **real** file create/modify operations
5. Results (files_changed, output) are written back to the job record
6. Dashboard polls `/api/job-status/<id>` and shows live progress
7. `docs/progress/CURRENT_STATUS.md` is updated after each step

---

## Components

| Layer | Component | Role |
|---|---|---|
| API | `backend/app/api/jobs.py` | chat-start, orchestrate, job-status, active-job, queue-status |
| API | `backend/app/api/dashboard.py` | dashboard data, project state, history |
| Orchestrator | `services/orchestrator.py` | breaks task into steps, manages retry loop |
| Executor | `services/chatgpt_executor.py` | runs steps, calls file_executor |
| Executor | `services/file_executor.py` | **real** file create/modify/patch |
| Supervisor | `services/supervisor.py` | infers DoD, verifies completion |
| Job Queue | `services/job_queue.py` | file-based queue, background thread per job |
| State | `services/project_state.py` | updates state.json on job lifecycle |
| Status | `services/status_updater.py` | keeps CURRENT_STATUS.md in sync |
| Fallback | `services/claude_executor.py` | Claude API fallback (optional) |
| Agents | `services/agents/` | PlannerAgent, CoderAgent, ReviewAgent (BaseAgent) |

---

## Execution Modes

| Mode | Trigger | Description |
|---|---|---|
| `chatgpt_self` | default (chat-start) | Orchestrator → chatgpt_executor → file_executor |
| `manager` | /api/orchestrate | Plan built → steps executed separately → per-step review |
| `claude_fallback` | auto after max_self_attempts | Claude API called for whole task |
| `autonomous` | metadata.autonomous=True | AutonomousBuildRunner (multi-step, self-review loop) |

---

## Safe Write Directories

File executor only writes to these paths (prefix match):

```
sandbox/
tests/
docs/
storage/
scripts/
backend/app/generated/
backend/app/services/
backend/app/api/
backend/app/models/
backend/app/core/
frontend/
```

Protected (never written): `.env`, `main.py`, `__init__.py`, `.git/`, `settings.json`

---

## Definition of Done

A task is **complete** when ALL of:

1. All `required_files` listed in the DoD actually exist on disk
2. All `required_patterns` (regex) match inside those files
3. `review.passed == True` (no error indicators in output)
4. `orchestrator_state.json` → `status: completed`

A task is **blocked** when any of:
- Required files missing after max_attempts
- Claude fallback also fails
- `supervisor.should_retry()` returns False

---

## What Counts as Successful Execution

- `files_changed` in the job record lists **real** paths that exist on disk
- File content does NOT contain self-correction/review markdown
- `orchestrator_state.json` shows `status: completed`, `current_task: null`
- `CURRENT_STATUS.md` shows the completed task with accurate file count
- Dashboard `/api/active-job` returns `active: false` after completion

---

## Current System Status (as of last stabilisation pass)

- Pipeline: `chatgpt_self` mode is primary; `manager` mode available via `/api/orchestrate`
- Prompt pollution fix applied: `_create_step_prompt` always returns clean `task_description`
- `expected_outputs` in DoD intentionally empty (file existence is the DoD signal)
- Fake "simulated" executor removed from `job_queue.py`
- `chatgpt_executor_state.json` clears `current_task` on completion

---

## Product Source of Truth

Primary product requirements are defined in:

- `docs/VISION_DOCUMENT.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/AGENT_INTERACTION_SPEC.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/TASK_PROMPT_TEMPLATES.md`

Agents MUST treat these files as authoritative.

Execution-layer files (SYSTEM_MAP, WORKFLOW, ROADMAP) must NOT contradict them.

---

## Key Paths

```
PROJECT_ROOT = /opt/ai-workspace/storage/projects/ai-platform

backend/app/main.py          — FastAPI entry point
backend/app/api/jobs.py      — primary task API
backend/app/api/dashboard.py — dashboard API
backend/app/services/        — all execution logic
docs/progress/               — state JSON files + CURRENT_STATUS.md
storage/jobs/                — one JSON file per job
sandbox/                     — safe scratch space for agent-created files
frontend/dashboard.html      — web dashboard
```
