"""
Manager Human Status — Operator observation layer.

Converts raw manager_state.json into a compact, rule-based, human-readable
status payload.  No LLM required.  Deterministic.  Safe to poll.

Used by GET /api/manager/human-status.

Status classes (rule-based):
  A  retry_required + target file(s) untouched  → doc-only failure
  B  retry_required + worker error               → hard failure
  C  retry_required + other review issue         → generic retry
  D  accepted                                    → task done
  E  blocked                                     → max retries exceeded
  F  executing / planning / selecting / reviewing → in progress
  G  idle + next task exists                     → ready
  H  idle + no task                              → roadmap exhausted

Each class provides: summary, problem, next_action, check_command,
expected_result, safe_to_auto_run, reason_not_safe.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from app.core.config import settings

_DEFAULT_ROOT = Path(settings.PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

def _detect_mode(project_root: Path) -> str:
    """Return 'mvp_recovery' or 'normal'."""
    try:
        from app.services.executive_memory import is_mvp_recovery_mode
        if is_mvp_recovery_mode(project_root):
            return "mvp_recovery"
    except Exception:
        pass
    return "normal"


# ---------------------------------------------------------------------------
# Next-task peek (no side effects)
# ---------------------------------------------------------------------------

def _peek_next_task() -> Optional[dict]:
    try:
        from app.services.task_intake import choose_next_task
        return choose_next_task()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Rule-based classifier
# ---------------------------------------------------------------------------

def _classify(state: dict, next_task: Optional[dict]) -> dict:
    """
    Map raw state to a human-status record.

    Returns a dict with all required fields.
    """
    status      = state.get("status", "idle")
    task        = state.get("current_task") or {}
    review      = state.get("review") or {}
    worker      = state.get("worker_result") or {}
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    task_id    = task.get("id", "—")
    task_title = task.get("title", "—")
    phase      = task.get("phase", "—")
    task_files = task.get("files", [])

    files_changed: list[str] = worker.get("files_changed") or []
    verified_unchanged: list[str] = worker.get("verified_unchanged") or []
    last_executor: str = worker.get("executor") or "—"
    review_notes: str = review.get("notes", "")
    review_verdict: str = review.get("verdict", "")
    worker_error: str = worker.get("error") or ""

    accepted_count = len(state.get("accepted_tasks") or [])
    blocked_count  = len(state.get("blocked_tasks") or [])

    # ── In-progress states ───────────────────────────────────────────────────
    if status in ("selecting", "planning", "executing", "reviewing"):
        verb = {
            "selecting":  "Selecting next task from roadmap…",
            "planning":   f"Building execution prompt for {task_id}…",
            "executing":  f"Worker is executing {task_id} — {task_title}",
            "reviewing":  f"Manager is reviewing worker output for {task_id}",
        }[status]
        return dict(
            status=status,
            summary=verb,
            task_id=task_id,
            task_title=task_title,
            phase=phase,
            problem=None,
            changed_files=files_changed,
            next_action="Wait for cycle to finish, then refresh.",
            check_command="curl -s http://localhost:8000/api/manager/state | python3 -m json.tool | grep status",
            expected_result=f"status changes from '{status}' to accepted/retry_required/blocked/idle",
            safe_to_auto_run=False,
            reason_not_safe="Cycle already in progress.",
            retry_count=retry_count,
            max_retries=max_retries,
            accepted_count=accepted_count,
            blocked_count=blocked_count,
            last_executor=last_executor,
            last_verdict=review_verdict or None,
            last_verified_unchanged=verified_unchanged,
            next_task_id=None,
            next_task_title=None,
            mode=_detect_mode(_DEFAULT_ROOT),
        )
    if status == "retry_required":
        target_files_set = set(task_files)
        changed_set      = set(files_changed)
        doc_files_changed = [f for f in files_changed if f.startswith("docs/")]
        target_untouched  = bool(target_files_set) and not (target_files_set & changed_set)

        if worker_error:
            # Case B: hard worker error
            summary = (
                f"Task {task_id} failed with a worker error. "
                f"No files were written. The error must be resolved before retrying."
            )
            problem = f"Worker error: {worker_error[:200]}"
            next_action = (
                "Read the worker error above. Fix the root cause (missing import, "
                "syntax error, or permission issue). Then run another cycle."
            )
            check_command = (
                f"curl -s http://localhost:8000/api/manager/state "
                f"| python3 -m json.tool | grep -A3 worker_result"
            )
            expected_result = "worker_result.error is null after fix"
            safe_to_auto_run = False
            reason_not_safe = f"Worker error must be fixed first: {worker_error[:100]}"

        elif target_untouched and doc_files_changed:
            # Case A: doc-only change
            summary = (
                f"Task {task_id} failed review. "
                f"The worker modified only docs instead of the required target file(s). "
                f"This is a prompt confusion issue."
            )
            problem = (
                f"Target file(s) not changed: {', '.join(sorted(target_files_set))}. "
                f"Only docs were modified: {', '.join(doc_files_changed[:3])}."
            )
            next_action = (
                "Run another cycle — the task brief now has explicit read-only guards on "
                "reference docs. The worker should modify only the target file on retry."
            )
            check_command = (
                f"curl -s http://localhost:8000/api/manager/run-cycle-sync -X POST "
                f"&& grep -c '' {task_files[0] if task_files else 'backend/requirements.txt'}"
            )
            expected_result = f"Target file {task_files[0] if task_files else '(see task)'} is modified and non-empty."
            safe_to_auto_run = True
            reason_not_safe = None

        elif target_untouched:
            # Case A variant: target untouched, no doc change
            summary = (
                f"Task {task_id} failed review. "
                f"The required target file(s) were not changed by the worker."
            )
            problem = (
                f"Target file(s) untouched: {', '.join(sorted(target_files_set))}. "
                f"Review notes: {review_notes[:200]}"
            )
            next_action = "Run another cycle. The manager will send a targeted fix prompt."
            check_command = (
                f"curl -s http://localhost:8000/api/manager/run-cycle-sync -X POST "
                f"| python3 -m json.tool | grep -A5 review"
            )
            expected_result = "verdict changes to accepted and target file is modified."
            safe_to_auto_run = True
            reason_not_safe = None

        else:
            # Case C: other review failure
            summary = (
                f"Task {task_id} failed review. "
                f"Retry {retry_count}/{max_retries}. Review issue: {review_notes[:150]}"
            )
            problem = review_notes[:300] or "Review failed — see manager state for details."
            next_action = (
                f"Run another cycle ({max_retries - retry_count} retry(ies) remaining). "
                "If retries are exhausted the task will be blocked."
            )
            check_command = (
                "curl -s http://localhost:8000/api/manager/run-cycle-sync -X POST "
                "| python3 -m json.tool | grep verdict"
            )
            expected_result = "verdict: accepted"
            safe_to_auto_run = retry_count < max_retries
            reason_not_safe = None if retry_count < max_retries else "Max retries reached — task will block."

        return dict(
            status=status,
            summary=summary,
            task_id=task_id,
            task_title=task_title,
            phase=phase,
            problem=problem,
            changed_files=files_changed,
            next_action=next_action,
            check_command=check_command,
            expected_result=expected_result,
            safe_to_auto_run=safe_to_auto_run,
            reason_not_safe=reason_not_safe,
            retry_count=retry_count,
            max_retries=max_retries,
            accepted_count=accepted_count,
            blocked_count=blocked_count,
            last_executor=last_executor,
            last_verdict=review_verdict or None,
            last_verified_unchanged=verified_unchanged,
            next_task_id=None,
            next_task_title=None,
            mode=_detect_mode(_DEFAULT_ROOT),
        )

    # ── accepted ─────────────────────────────────────────────────────────────
    if status == "accepted":
        changed_str = ", ".join(files_changed[:5]) or "—"
        return dict(
            status=status,
            summary=(
                f"Task {task_id} accepted. "
                f"The required file(s) were updated and all review checks passed."
            ),
            task_id=task_id,
            task_title=task_title,
            phase=phase,
            problem=None,
            changed_files=files_changed,
            next_action=(
                "Run the next cycle to advance to the next roadmap task, "
                "or use Run Auto to continue automatically."
            ),
            check_command=(
                f"curl -s http://localhost:8000/api/manager/run-cycle-sync -X POST "
                f"| python3 -m json.tool | grep status"
            ),
            expected_result="Next task selected and status transitions through selecting → accepted.",
            safe_to_auto_run=True,
            reason_not_safe=None,
            retry_count=0,
            max_retries=max_retries,
            accepted_count=accepted_count,
            blocked_count=blocked_count,
            last_executor=last_executor,
            last_verdict=review_verdict or None,
            last_verified_unchanged=verified_unchanged,
            next_task_id=None,
            next_task_title=None,
            mode=_detect_mode(_DEFAULT_ROOT),
        )

    # ── blocked ───────────────────────────────────────────────────────────────
    if status == "blocked":
        return dict(
            status=status,
            summary=(
                f"Task {task_id} is blocked after {retry_count} attempt(s). "
                "Manual repair or prompt fix is needed before continuing."
            ),
            task_id=task_id,
            task_title=task_title,
            phase=phase,
            problem=review_notes[:400] or "Max retries exceeded with no accepted result.",
            changed_files=files_changed,
            next_action=(
                "1. Read the problem above.\n"
                "2. Fix the underlying issue (missing file, bad prompt, broken dependency).\n"
                "3. Run POST /api/manager/retry to re-queue this task, or\n"
                "   POST /api/manager/reset then run the next cycle to skip it."
            ),
            check_command=(
                f"cat {_DEFAULT_ROOT / 'docs/progress/manager_state.json'} "
                "| python3 -m json.tool | grep -A10 review"
            ),
            expected_result="After manual fix: retry returns verdict accepted.",
            safe_to_auto_run=False,
            reason_not_safe="Task is blocked — automated retry will immediately re-block without a fix.",
            retry_count=retry_count,
            max_retries=max_retries,
            accepted_count=accepted_count,
            blocked_count=blocked_count,
            last_executor=last_executor,
            last_verdict=review_verdict or None,
            last_verified_unchanged=verified_unchanged,
            next_task_id=None,
            next_task_title=None,
            mode=_detect_mode(_DEFAULT_ROOT),
        )

    # ── idle ──────────────────────────────────────────────────────────────────
    mode = _detect_mode(_DEFAULT_ROOT)
    if next_task:
        nt_id    = next_task.get("id", "?")
        nt_title = next_task.get("title", "")
        nt_files = next_task.get("files", [])
        files_preview = ", ".join(nt_files[:3]) or "(see roadmap)"
        return dict(
            status="idle",
            summary=(
                f"Manager is idle. Next task ready: [{nt_id}] {nt_title}. "
                f"Target: {files_preview}"
            ),
            task_id=nt_id,
            task_title=nt_title,
            phase=next_task.get("phase", "—"),
            problem=None,
            changed_files=[],
            next_action=(
                "Click 'Run Cycle' to execute the next task, "
                "or 'Run Auto' to run all remaining tasks automatically."
            ),
            check_command=(
                "curl -s http://localhost:8000/api/manager/run-cycle-sync -X POST "
                "| python3 -m json.tool | grep -E 'status|verdict'"
            ),
            expected_result=f"status: accepted and {files_preview} modified.",
            safe_to_auto_run=True,
            reason_not_safe=None,
            retry_count=0,
            max_retries=max_retries,
            accepted_count=accepted_count,
            blocked_count=blocked_count,
            last_executor=last_executor,
            last_verdict=review_verdict or None,
            last_verified_unchanged=verified_unchanged,
            next_task_id=nt_id,
            next_task_title=nt_title,
            mode=mode,
        )

    # Case H: truly idle, no tasks
    return dict(
        status="idle",
        summary="No actionable tasks remain. The roadmap is exhausted or all tasks are complete.",
        task_id=None,
        task_title=None,
        phase=None,
        problem=None,
        changed_files=[],
        next_action="Review ROADMAP.md and add new tasks, or check docs/agent/MVP_ACCEPTANCE.md.",
        check_command=(
            f"grep -c 'status: done\\|\\[x\\]\\|\\[done\\]' "
            f"{_DEFAULT_ROOT / 'docs/agent/ROADMAP.md'} || echo '0 done tasks'"
        ),
        expected_result="All tasks marked [x] in ROADMAP.md.",
        safe_to_auto_run=False,
        reason_not_safe="No tasks to run.",
        retry_count=0,
        max_retries=max_retries,
        accepted_count=accepted_count,
        blocked_count=blocked_count,
        last_executor=last_executor,
        last_verdict=review_verdict or None,
        last_verified_unchanged=verified_unchanged,
        next_task_id=None,
        next_task_title=None,
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_human_status(project_root: Optional[Path] = None) -> dict:
    """
    Build the full human-readable operator status payload.

    Reads manager_state.json and peeks at the next roadmap task.
    No LLM required.  Safe to call on every dashboard refresh.
    """
    root = project_root or _DEFAULT_ROOT
    try:
        from app.services.manager_loop import get_manager_state
        state = get_manager_state(project_root=root)
    except Exception as e:
        return {
            "status": "error",
            "summary": f"Could not read manager state: {e}",
            "task_id": None,
            "task_title": None,
            "phase": None,
            "problem": str(e),
            "changed_files": [],
            "next_action": "Check that manager_state.json is readable.",
            "check_command": f"cat {root / 'docs/progress/manager_state.json'}",
            "expected_result": "Valid JSON.",
            "safe_to_auto_run": False,
            "reason_not_safe": "Manager state unreadable.",
            "retry_count": 0,
            "max_retries": 2,
            "accepted_count": 0,
            "blocked_count": 0,
            "mode": "unknown",
        }

    next_task = _peek_next_task()
    result = _classify(state, next_task)

    # Read-only sprint observation fields for dashboard progress UI.
    cfg = {}
    cfg_path = root / "docs/progress/autopilot_config.json"
    try:
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}

    sprint_cfg = cfg.get("sprint") or {}
    sprint_start_ts = state.get("sprint_start_ts")
    sprint_elapsed_sec: Optional[int] = None
    if sprint_start_ts:
        try:
            start = datetime.fromisoformat(str(sprint_start_ts).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            sprint_elapsed_sec = int((datetime.now(timezone.utc) - start).total_seconds())
            if sprint_elapsed_sec < 0:
                sprint_elapsed_sec = 0
        except Exception:
            sprint_elapsed_sec = None

    result["sprint_id"] = state.get("sprint_id") or sprint_cfg.get("id") or cfg.get("mode")
    result["sprint_start_ts"] = sprint_start_ts
    result["sprint_accepted"] = state.get("sprint_accepted", result.get("accepted_count", 0))
    result["sprint_blocked"] = state.get("sprint_blocked", result.get("blocked_count", 0))
    result["sprint_max_accepted"] = sprint_cfg.get("max_accepted")
    result["sprint_elapsed_sec"] = sprint_elapsed_sec

    return result
