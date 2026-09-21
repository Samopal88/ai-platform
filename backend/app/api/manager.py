"""
Manager Loop API — Two-tier autonomous execution endpoints.

Endpoints:
  GET  /api/manager/state        — current manager lifecycle state (safe to poll)
  POST /api/manager/run-cycle    — run one full manager cycle (background)
  POST /api/manager/reset        — reset to idle (cancels current cycle state)
  GET  /api/manager/history      — last 20 cycle outcomes
  GET  /api/manager/next-task    — preview next task + context + prompt (no side effects)
  POST /api/manager/retry        — force retry of current task (manager resets retry_count back to 0 -> will pick up retry on next cycle)

Portable: project_root is a query param so this router works for any project.
"""
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pathlib import Path
from typing import Optional
from app.core.config import settings

router = APIRouter(prefix="/api/manager", tags=["Manager Loop"])

_DEFAULT_ROOT = Path(settings.PROJECT_ROOT)
_SPRINT_RUNNING = False


def _root(project_path: Optional[str]) -> Path:
    return Path(project_path) if project_path else _DEFAULT_ROOT


def _last_run_report_path(root: Path) -> Path:
    return root / "reports" / "autopilot_last_run.json"


def _load_last_run_report(root: Path) -> dict:
    path = _last_run_report_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# State — safe to poll from dashboard
# ---------------------------------------------------------------------------

@router.get("/human-status")
async def get_human_status(project_path: Optional[str] = Query(None)):
    """
    Operator-friendly manager status.

    Returns a compact, rule-based, human-readable payload derived from the
    current manager state. No LLM required. Safe to poll from the dashboard.

    Fields:
      status, summary, task_id, task_title, phase, problem,
      changed_files, next_action, check_command, expected_result,
      safe_to_auto_run, reason_not_safe, retry_count, max_retries,
      accepted_count, blocked_count, mode
    """
    from app.services.manager_human_status import build_human_status
    from pathlib import Path
    root = Path(project_path) if project_path else None
    result = build_human_status(root)
    result["sprint_running"] = _SPRINT_RUNNING
    return result




@router.get("/last-run")
async def get_last_run_report(project_path: Optional[str] = Query(None)):
    """Return autopilot last-run report from reports/autopilot_last_run.json."""
    root = _root(project_path)
    path = _last_run_report_path(root)
    report = _load_last_run_report(root)
    if not report:
        return {
            "exists": False,
            "path": str(path),
            "message": "Last-run report not found. Run scripts/run_continuous.py or scripts/run_autopilot.py.",
        }
    return {
        "exists": True,
        "path": str(path),
        "report": report,
    }

@router.get("/state")
async def get_manager_state(project_path: Optional[str] = Query(None)):
    """
    Current manager lifecycle state — compact observation view.

    Lifecycle: idle → selecting → planning → executing → reviewing → accepted | retry_required | blocked

    Always safe to call — read-only.
    Persists across restarts (backed by manager_state.json).

    Returns a concise payload with the most useful fields for live observation:
      status, current_task (id + title + files), last_executor, last_files_changed,
      last_verified_unchanged, retry_count, max_retries, next_task (id + title),
      accepted_count, blocked_count, last_verdict, last_review_notes, updated_at.
    Full raw state is also included under the 'raw' key.
    """
    from app.services.manager_loop import get_manager_state as _get
    from app.services.task_intake import choose_next_task

    root = _root(project_path)
    raw = _get(project_root=root)

    task = raw.get("current_task") or {}
    wr   = raw.get("worker_result") or {}
    rev  = raw.get("review") or {}

    # Peek next task without side effects
    try:
        nt = choose_next_task()
    except Exception:
        nt = None

    compact = {
        # ── Loop status ──────────────────────────────────────────────────────
        "status":               raw.get("status"),
        "retry_count":          raw.get("retry_count", 0),
        "max_retries":          raw.get("max_retries", 2),
        "updated_at":           raw.get("updated_at"),

        # ── Current task ─────────────────────────────────────────────────────
        "current_task": {
            "id":    task.get("id"),
            "title": task.get("title"),
            "files": task.get("files", []),
            "phase": task.get("phase"),
        } if task else None,

        # ── Last execution result ────────────────────────────────────────────
        "last_executor":            wr.get("executor"),
        "last_files_changed":       wr.get("files_changed") or [],
        "last_verified_unchanged":  wr.get("verified_unchanged") or [],
        "last_worker_error":        wr.get("error"),

        # ── Last review ──────────────────────────────────────────────────────
        "last_verdict":       rev.get("verdict"),
        "last_review_notes":  rev.get("notes"),
        "last_review_checks": rev.get("checks") or [],

        # ── Progress counters ────────────────────────────────────────────────
        "accepted_count": len(raw.get("accepted_tasks") or []),
        "blocked_count":  len(raw.get("blocked_tasks")  or []),

        # ── Sprint tracking (SP-5) ───────────────────────────────────────────
        "sprint_id":       raw.get("sprint_id"),
        "sprint_start_ts": raw.get("sprint_start_ts"),
        "sprint_accepted": raw.get("sprint_accepted", 0),
        "sprint_blocked":  raw.get("sprint_blocked", 0),
        "sprint_running":  _SPRINT_RUNNING,

        # ── What's next ──────────────────────────────────────────────────────
        "next_task": {
            "id":    nt.get("id"),
            "title": nt.get("title"),
            "files": nt.get("files", []),
        } if nt else None,
    }
    return compact


@router.get("/history")
async def get_manager_history(
    limit: int = 20,
    project_path: Optional[str] = Query(None),
):
    """Last N cycle outcomes (task_id, verdict, files_changed, timestamp)."""
    from app.services.manager_loop import get_manager_state
    state = get_manager_state(project_root=_root(project_path))
    return {
        "history": state.get("history", [])[-limit:],
        "accepted": state.get("accepted_tasks", [])[-limit:],
        "blocked": state.get("blocked_tasks", [])[-limit:],
    }


@router.get("/next-task")
async def preview_next_task(project_path: Optional[str] = Query(None)):
    """Preview the next roadmap task, resolved context, and compact prompt. No side effects."""
    from app.services.task_intake import choose_next_task, resolve_product_context, build_execution_prompt
    task = choose_next_task()
    if not task:
        return {"task": None, "context": None, "execution_prompt": None, "message": "No actionable tasks"}
    context = resolve_product_context(task)
    return {
        "task": task,
        "context": context,
        "execution_prompt": build_execution_prompt(task, context),
    }


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@router.post("/run-cycle")
async def run_manager_cycle(
    background_tasks: BackgroundTasks,
    project_path: Optional[str] = Query(None),
):
    """
    Start one full manager cycle in the background.

    Cycle: selecting → planning → executing → reviewing → accepted|retry_required|blocked

    If current state is retry_required the manager will use the same task
    and build a targeted fix prompt automatically.
    Returns immediately with current state snapshot.
    """
    from app.services.manager_loop import get_manager_state, run_manager_cycle as _run
    root = _root(project_path)
    state = get_manager_state(root)

    # Prevent concurrent cycles
    if state.get("status") in ("selecting", "planning", "executing", "reviewing"):
        return {
            "started": False,
            "message": f"Cycle already in progress (status: {state['status']})",
            "state": state,
        }

    def _bg():
        try:
            _run(project_root=root)
        except Exception as _e:
            import logging as _log
            _log.getLogger(__name__).error("manager _bg cycle crashed: %s", _e)
            try:
                from app.services.manager_loop import _load_state, _save_state as _ss
                _st = _load_state(root)
                if _st.get("status") in ("selecting", "planning", "executing", "reviewing"):
                    _st["status"] = "idle"
                    _st["error"] = str(_e)[:200]
                    _ss(_st, root)
            except Exception:
                pass

    background_tasks.add_task(_bg)
    return {
        "started": True,
        "message": "Manager cycle started",
        "current_status": state.get("status"),
    }


@router.post("/run-cycle-sync")
async def run_manager_cycle_sync(project_path: Optional[str] = Query(None)):
    """
    Run one full manager cycle synchronously (blocks until done).
    Use for testing. For production prefer /run-cycle (background).
    """
    from app.services.manager_loop import run_manager_cycle as _run
    root = _root(project_path)
    final_state = _run(project_root=root)
    return {
        "status": final_state.get("status"),
        "task": final_state.get("current_task"),
        "review": final_state.get("review"),
        "worker_result": {
            "success": (final_state.get("worker_result") or {}).get("success"),
            "files_changed": (final_state.get("worker_result") or {}).get("files_changed"),
            "error": (final_state.get("worker_result") or {}).get("error"),
        },
        "retry_count": final_state.get("retry_count", 0),
    }


@router.post("/retry")
async def force_retry(project_path: Optional[str] = Query(None)):
    """Force retry of current blocked/accepted task by resetting retry_count."""
    from app.services.manager_loop import _load_state, _save_state
    root = _root(project_path)
    state = _load_state(root)
    state["retry_count"] = 0
    state["status"] = "retry_required"
    state["review"] = None
    _save_state(state, root)
    return {"status": "retry_queued", "message": "Task will retry on next cycle"}


@router.get("/preflight/{task_id}")
async def preflight_task(task_id: str, project_path: Optional[str] = Query(None)):
    """
    Check whether a recovery task's prerequisites are satisfied on disk.

    Returns ready=True if the task can be safely dispatched to the worker,
    or ready=False with a human-readable reason if prerequisites are missing or stub.
    """
    from app.services.recovery_gate import check_task_ready, GateResult
    from app.services.task_intake import _load_mvp_recovery_tasks
    root = _root(project_path)

    tasks = _load_mvp_recovery_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"task_id": task_id, "found": False, "ready": None, "reason": "task not found in recovery roadmap"}

    gate = check_task_ready(task, root)
    return {
        "task_id": task_id,
        "found": True,
        "ready": gate.ready,
        "reason": gate.reason,
        "blocking_checks": gate.blocking_checks,
        "passed_checks": gate.passed_checks,
    }


@router.post("/sync-state")
async def sync_manager_state(project_path: Optional[str] = Query(None)):
    """
    Synchronize manager_state.json against the canonical recovery completion list
    (autopilot_config.json → mvp_recovery.completed_tasks).

    Clears any current_task that is already completed.
    Removes stale blocked_task entries for completed tasks.
    Removes ad-hoc one-off recovery fields.

    Safe to call at any time. Idempotent.
    """
    from app.services.manager_loop import sync_completed_recovery_tasks
    return sync_completed_recovery_tasks(_root(project_path))


@router.post("/run-auto")
async def run_auto_cycles(
    background_tasks: BackgroundTasks,
    max_cycles: int = 50,
    project_path: Optional[str] = Query(None),
):
    """
    Run manager cycles continuously until roadmap is exhausted or max_cycles reached.

    Each cycle: selecting → planning → executing → reviewing → accepted|retry_required|blocked
    On accepted: marks task done in ROADMAP.md, moves to next task automatically.
    On retry_required: retries same task (up to max_retries).
    On blocked: skips to next task.
    Stops when no actionable tasks remain.
    """
    from app.services.manager_loop import (
        get_manager_state,
        run_manager_cycle as _run,
        reset_manager_state,
        sync_completed_recovery_tasks,
    )
    from app.services.task_intake import choose_next_task

    root = _root(project_path)
    state = get_manager_state(root)
    if state.get("status") in ("selecting", "planning", "executing", "reviewing"):
        return {
            "started": False,
            "message": f"Cycle already in progress: {state['status']}",
        }

    # Pre-flight: sync state against canonical completion list before starting
    sync_result = sync_completed_recovery_tasks(root)

    def _auto():
        import logging as _log
        import time as _t

        _logger = _log.getLogger(__name__)
        for i in range(max_cycles):
            # Sync before each cycle — ensures operator-repaired tasks don't re-run
            sync_completed_recovery_tasks(root)

            # Check if any tasks remain
            task = choose_next_task()
            if not task:
                break

            # Preflight gate for recovery tasks — check prerequisites before dispatching
            if task.get("_is_mvp_recovery"):
                from app.services.recovery_gate import check_task_ready
                try:
                    gate = check_task_ready(task, root)
                    if not gate.ready:
                        # Prerequisites not satisfied — record and skip this task.
                        from app.services.manager_loop import _load_state, _save_state as _ss
                        s2 = _load_state(root)
                        s2["status"] = "blocked"
                        s2["preflight_block"] = {
                            "task_id": task["id"],
                            "reason": gate.reason,
                            "blocking_checks": gate.blocking_checks,
                        }
                        _ss(s2, root)
                        _logger.warning(
                            "run-auto: task %s preflight-blocked, skipping to next: %s",
                            task["id"],
                            gate.reason,
                        )
                        reset_manager_state(root)
                        _t.sleep(0.3)
                        continue
                except Exception:
                    pass  # Gate errors must not break the loop

            s = get_manager_state(root)
            # Skip if already in-progress from a previous call
            if s.get("status") in ("selecting", "planning", "executing", "reviewing"):
                _t.sleep(0.5)
                continue

            try:
                s = _run(project_root=root)
            except Exception as _run_e:
                _logger.error("run-auto: cycle exception for task, recovering state: %s", _run_e)
                try:
                    from app.services.manager_loop import _load_state, _save_state as _ss
                    _st = _load_state(root)
                    if _st.get("status") in ("selecting", "planning", "executing", "reviewing"):
                        _st["status"] = "idle"
                        _st["error"] = str(_run_e)[:200]
                        _ss(_st, root)
                except Exception:
                    pass
                reset_manager_state(root)
                _t.sleep(0.5)
                continue
            verdict = s.get("status")

            if verdict == "blocked":
                blocked_task = (s.get("current_task") or {})
                task_id = blocked_task.get("id", "?")
                _logger.warning("run-auto: task %s blocked, skipping to next", task_id)
                reset_manager_state(root)
                _t.sleep(0.3)
                continue

            # Small delay between cycles to allow state writes to flush
            _t.sleep(0.3)

    background_tasks.add_task(_auto)
    return {
        "started": True,
        "message": f"Auto-run started: up to {max_cycles} cycles",
        "pre_flight_sync": sync_result,
    }


@router.post("/run-sprint")
async def run_sprint(
    background_tasks: BackgroundTasks,
    project_path: Optional[str] = Query(None),
):
    """
    Launch bounded autonomous sprint in background.
    """
    from app.services.manager_loop import get_manager_state
    from app.services import sprint_runner

    global _SPRINT_RUNNING

    root = _root(project_path)
    state = get_manager_state(root)
    if _SPRINT_RUNNING or state.get("status") in ("executing", "planning", "reviewing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sprint already running or manager busy",
        )

    def _bg() -> None:
        global _SPRINT_RUNNING
        _SPRINT_RUNNING = True
        try:
            sprint_runner.run_sprint(project_root=root)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("run-sprint crashed: %s", exc)
        finally:
            _SPRINT_RUNNING = False

    background_tasks.add_task(_bg)
    return {
        "status": "started",
        "mode": "sprint",
    }


@router.post("/reset")
async def reset_manager(project_path: Optional[str] = Query(None)):
    """Reset manager to idle, preserving history."""
    from app.services.manager_loop import reset_manager_state
    state = reset_manager_state(project_root=_root(project_path))
    return {"status": state["status"], "message": "Manager reset to idle"}


@router.get("/memory")
async def get_product_memory(project_path: Optional[str] = Query(None)):
    """
    Current product memory: what pages, APIs, services have been implemented,
    what is incomplete, and the last 10 task outcomes.
    """
    from app.services.product_memory import get_memory, get_summary
    root = _root(project_path)
    return {
        "memory": get_memory(root),
        "summary": get_summary(root),
    }
