# Operator Status Spec
## AI Workspace Platform — Manager Observer Layer

**Created:** 2026-04-19
**Status:** IMPLEMENTED

---

## Purpose

This document specifies the human-readable manager status system — an operator
observation layer that sits on top of the raw `manager_state.json` data and
converts it into compact, actionable operator guidance.

It is NOT a product feature.  It is a debug and operations tool for the person
running the autonomous development platform.

---

## Endpoint

```
GET /api/manager/human-status
```

- Read-only.  Safe to poll from the dashboard.
- No LLM required.  Rule-based and deterministic.
- Response latency < 100 ms (reads one JSON file + one roadmap file).

### Response Fields

| Field | Type | Description |
|---|---|---|
| `status` | string | Raw manager lifecycle status |
| `summary` | string | Plain-language description of what happened |
| `task_id` | string\|null | Current or next task ID |
| `task_title` | string\|null | Human-readable task title |
| `phase` | string\|null | Roadmap phase |
| `problem` | string\|null | Root cause of failure (if any) |
| `changed_files` | list[str] | Files changed by the last worker run |
| `next_action` | string | What the operator should do next |
| `check_command` | string | Exact terminal command to verify the state |
| `expected_result` | string | What a correct outcome looks like |
| `safe_to_auto_run` | bool | Whether clicking Run Auto is safe right now |
| `reason_not_safe` | string\|null | Why it is not safe (if false) |
| `retry_count` | int | Current retry count |
| `max_retries` | int | Max allowed retries for this task |
| `accepted_count` | int | Total accepted tasks this session |
| `blocked_count` | int | Total blocked tasks this session |
| `mode` | string | `normal` or `mvp_recovery` |

---

## Status Classes (Rule-Based)

### Case A — `retry_required` + target file untouched + only docs changed

> "Task R1 failed review. The worker modified only docs instead of the required
> target file(s). This is a prompt confusion issue."

- **Problem:** target file not changed; doc files changed instead
- **Next action:** run another cycle — prompt guards are now enforced
- **Safe to auto-run:** YES

### Case B — `retry_required` + worker error

> "Task R1 failed with a worker error. No files were written."

- **Problem:** worker hard error (import, syntax, permission)
- **Next action:** fix the error then retry
- **Safe to auto-run:** NO

### Case C — `retry_required` + other review failure

> "Task R1 failed review. Retry 1/3. Review issue: …"

- **Next action:** run another cycle (N retries remaining)
- **Safe to auto-run:** YES (while retries remain)

### Case D — `accepted`

> "Task R1 accepted. The required file(s) were updated and all review checks passed."

- **Next action:** run next cycle or Run Auto
- **Safe to auto-run:** YES

### Case E — `blocked`

> "Task R1 is blocked after 3 attempt(s). Manual repair or prompt fix is needed."

- **Next action:** fix root cause, then POST /api/manager/retry or reset
- **Safe to auto-run:** NO

### Case F — In-progress (`selecting` / `planning` / `executing` / `reviewing`)

> "Worker is executing R1 — Fix requirements.txt: uncomment SQLAlchemy"

- **Next action:** wait for cycle to finish, then refresh
- **Safe to auto-run:** NO (cycle already in progress)

### Case G — `idle` + next task exists

> "Manager is idle. Next task ready: [R2] Fix db/session.py. Target: backend/app/db/session.py"

- **Next action:** Run Cycle or Run Auto
- **Safe to auto-run:** YES

### Case H — `idle` + no tasks

> "No actionable tasks remain. The roadmap is exhausted."

- **Safe to auto-run:** NO

---

## Dashboard Panel

The Manager Status card in `frontend/dashboard.html` reads exclusively from
`/api/manager/human-status`.  If that endpoint fails it falls back to rendering
the raw `/api/manager/state` JSON with a warning banner.

Panel sections:

1. **Status badge** — colour-coded lifecycle label
2. **Retry counter** — current/max retries
3. **Accepted / Blocked counts**
4. **Safe to Auto-Run badge** — green check or orange warning
5. **Current Task** — ID, title, phase
6. **Summary** — plain-language description
7. **Problem** (red callout, if any)
8. **Files Changed** — inline code chips
9. **Next Action** — what to do
10. **Verify With** — exact terminal command + expected result

---

## Haiku Explainer (Specified, Not Yet Implemented)

An optional lightweight explainer can be added later using `claude-haiku-4-5`.

**Proposed endpoint:** `GET /api/manager/explain`

**Input:** the structured `human-status` payload (already assembled)

**Prompt template:**
```
You are an observer of an autonomous software development pipeline.
Given the following structured status payload, write 2-3 clear sentences for a
human operator explaining what is happening, whether the system is stuck,
retrying, blocked, or progressing, and what (if anything) they need to do.
Do not invent facts.  Do not repeat field names.  Be direct.

Status payload:
{json.dumps(payload, indent=2)}
```

**Rules:**
- Use `claude-haiku-4-5-20251001` only, never the manager model.
- Stream the response if latency matters.
- If the call fails, return the `summary` field from human-status as fallback.
- The structured endpoint remains the single source of truth.
- Cache the explainer response for 30 s (keyed on `status + task_id + retry_count`).

**Integration point:** `manager_human_status.py` → add `explain(payload)` function,
call it from a separate `/explain` route, never inline into `/human-status`.

---

## Implementation Notes

- `backend/app/services/manager_human_status.py` — all classification logic
- `backend/app/api/manager.py` — `/human-status` endpoint at line ~18
- `frontend/dashboard.html` — Manager Status card, reads `/api/manager/human-status`
  with raw-state fallback

Source of truth for status rules: this file.
