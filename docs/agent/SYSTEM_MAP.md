# AI Workspace Platform — System Map

## Directory Layout

```
/opt/ai-workspace/storage/projects/ai-platform/
├── backend/
│   ├── app/
│   │   ├── main.py                  FastAPI app factory
│   │   ├── core/config.py           Settings
│   │   ├── api/
│   │   │   ├── jobs.py              Task/job endpoints
│   │   │   ├── dashboard.py         Dashboard data endpoints
│   │   │   └── runner.py            Runner control endpoints
│   │   ├── models/                  Pydantic models
│   │   ├── db/                      Database layer
│   │   └── services/
│   │       ├── orchestrator.py      Main task controller
│   │       ├── chatgpt_executor.py  Primary executor (self-review loop)
│   │       ├── file_executor.py     Real file operations
│   │       ├── supervisor.py        DoD inference + verification
│   │       ├── job_queue.py         File-based job queue
│   │       ├── project_state.py     state.json management
│   │       ├── status_updater.py    CURRENT_STATUS.md sync
│   │       ├── claude_executor.py   Claude API fallback
│   │       ├── autonomous_runner.py Multi-step autonomous runner
│   │       ├── autonomous_loop.py   Loop-based autonomous execution
│   │       └── agents/
│   │           ├── base.py          BaseAgent + AgentResult
│   │           ├── planner.py       PlannerAgent
│   │           ├── coder.py         CoderAgent
│   │           └── reviewer.py      ReviewAgent
│   ├── runner_router.py
│   └── main_with_runner.py
├── frontend/
│   ├── dashboard.html               Main web dashboard
│   └── chat.html                    Chat interface
├── docs/
│   ├── agent/                       ← Agent reference files (this dir)
│   │   ├── PROJECT_BRIEF.md
│   │   ├── SYSTEM_MAP.md
│   │   └── WORKFLOW.md
│   └── progress/                    Runtime state files
│       ├── CURRENT_STATUS.md        Human-readable live status
│       ├── state.json               Active/recent job info
│       ├── orchestrator_state.json  Orchestrator execution state
│       ├── chatgpt_executor_state.json
│       ├── file_executor_state.json
│       ├── supervisor_state.json
│       ├── autonomous_runner_state.json
│       └── loop_state.json
├── storage/
│   └── jobs/                        One <job_id>.json per job
├── sandbox/                         Safe agent scratch space
└── scripts/                         Utility scripts
```

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/chat-start` | Start task → returns `job_id` immediately |
| GET | `/api/job-status/{job_id}` | Poll job progress |
| POST | `/api/job-cancel/{job_id}` | Cancel a running job |
| GET | `/api/jobs` | List recent jobs (default 20) |
| GET | `/api/queue-status` | Counts: queued/running/finished/failed |
| GET | `/api/active-job` | Current in-flight job or `{active: false}` |
| POST | `/api/orchestrate` | Manager-mode task (step-by-step) |
| GET | `/api/orchestrator-status` | Orchestrator current state |
| GET | `/api/orchestrator-history` | Completed/blocked task history |

---

## Services — Call Graph

```
/api/chat-start
  └─ job_queue.create_job()
  └─ job_queue.start_job_execution()
       └─ _real_executor(job_id)
            └─ orchestrator.execute_task()
                 ├─ supervisor.infer_dod_from_task()
                 ├─ chatgpt_executor.execute_task(original_task)
                 │    └─ file_executor.execute_task(original_task)
                 │         ├─ analyze_task()   → intent + target_files
                 │         ├─ create_plan()    → ExecutionPlan (steps)
                 │         └─ execute_step()   → create_file / modify_file
                 ├─ orchestrator.review_task_result()
                 ├─ supervisor.verify_task_completion()
                 └─ [retry if issues] → original_task again (never fix_prompt)

/api/orchestrate
  └─ orchestrator.execute_task_manager_mode()
       ├─ build_execution_plan()     → PlanStep list
       └─ per-step: execute_step() + review_step_result()
```

---

## State Files — Key Fields

### `docs/progress/orchestrator_state.json`
```json
{
  "status": "completed | running | blocked | planning",
  "mode": "chatgpt_self | manager | claude_fallback",
  "current_task": null,
  "current_job_id": null,
  "current_step": "complete",
  "current_dod": { "required_files": [], "required_patterns": {} },
  "attempts": 1,
  "reviews": [],
  "completed_tasks": [],
  "blocked_tasks": []
}
```

### `docs/progress/state.json`
```json
{
  "active_task": null,
  "active_job_id": null,
  "last_job_id": "...",
  "last_completed_task": "...",
  "last_finished_at": "...",
  "recent_job_id": "...",
  "recent_job_status": "finished"
}
```

### `storage/jobs/<id>.json`
```json
{
  "job_id": "abc12345",
  "task_type": "code | chat | general",
  "prompt": "...",
  "status": "queued | started | in_progress | finished | failed | cancelled",
  "current_stage": "...",
  "progress": [{ "timestamp": "...", "message": "..." }],
  "answer": "...",
  "files_changed": ["sandbox/foo.py"],
  "error": null
}
```

---

## File Executor — Safe Paths

Write allowed (prefix match):
`sandbox/` `tests/` `docs/` `storage/` `scripts/` `frontend/`
`backend/app/services/` `backend/app/api/` `backend/app/models/`
`backend/app/core/` `backend/app/generated/`

Write blocked: `.env` `main.py` `__init__.py` `.git/` `settings.json` `*.pyc`

Path safety: `_normalize_path()` resolves symlinks, rejects `../` traversal,
must stay within `PROJECT_ROOT`.

---

## Product Documentation Layer

```
docs/
 ├── VISION_DOCUMENT.md
 ├── SYSTEM_ARCHITECTURE.md
 ├── DATA_MODEL.md
 ├── AGENT_INTERACTION_SPEC.md
 ├── IMPLEMENTATION_PLAN.md
 └── TASK_PROMPT_TEMPLATES.md
```

**Purpose:** Define platform behaviour and requirements.

**Rule:** When implementing features, read only the specific relevant section of
these files, not the entire documents.

---

## Dashboard

- File: `frontend/dashboard.html`
- Polls: `/api/active-job`, `/api/queue-status`, `/api/orchestrator-status`
- Shows: live job progress, files_changed, orchestrator mode, plan steps (manager mode)
- No build step required — plain HTML/JS served by FastAPI static handler
