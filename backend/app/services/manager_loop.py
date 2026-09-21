"""
Manager Loop — Two-tier autonomous execution engine.

Architecture:
  Manager (this module):
    - Reads roadmap → selects next task via task_intake
    - Builds narrow, verifiable execution step
    - Dispatches to worker (file_executor)
    - Reviews worker result by checking files on disk
    - Decides: accepted | retry_required | blocked
    - Creates targeted fix task if retry needed (NOT the worker)

  Worker (file_executor):
    - Receives only the step prompt
    - Creates/modifies only the specified files
    - Returns files_changed list
    - Makes ZERO management decisions

State: docs/progress/manager_state.json
  Single source of truth for lifecycle.
  Persists across restarts.

Universal design:
  project_root is a parameter. New project = new project_root
  with its own roadmap + docs. No code changes needed.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from app.core.config import settings

_DEFAULT_ROOT = Path(settings.PROJECT_ROOT)
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def _state_file(project_root: Path) -> Path:
    return project_root / "docs" / "progress" / "manager_state.json"


def _load_state(project_root: Path) -> dict:
    f = _state_file(project_root)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _empty_state()


def _save_state(state: dict, project_root: Path) -> None:
    state["updated_at"] = datetime.now().isoformat()
    f = _state_file(project_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _empty_state() -> dict:
    return {
        "status": "idle",           # idle|selecting|planning|executing|reviewing|accepted|retry_required|blocked
        "current_task": None,       # full roadmap task dict
        "current_step": None,       # step prompt sent to worker
        "fix_task": None,           # manager-created fix prompt (retry only)
        "worker_result": None,      # {success, files_changed, output, error}
        "review": None,             # {verdict, checks, issues, notes}
        "retry_count": 0,
        "max_retries": MAX_RETRIES,
        "current_job_id": None,
        "accepted_tasks": [],       # last 20 accepted
        "blocked_tasks": [],        # last 20 blocked
        "history": [],              # last 20 cycle outcomes
        "updated_at": None,
        # SP-5: sprint tracking fields
        "sprint_id": None,
        "sprint_start_ts": None,
        "sprint_accepted": 0,
        "sprint_blocked": 0,
    }


def get_manager_state(project_root: Optional[Path] = None) -> dict:
    return _load_state(project_root or _DEFAULT_ROOT)


def reset_manager_state(project_root: Optional[Path] = None) -> dict:
    """Reset to idle, preserving history."""
    root = project_root or _DEFAULT_ROOT
    state = _load_state(root)
    state.update({
        "status": "idle",
        "current_task": None,
        "current_step": None,
        "fix_task": None,
        "worker_result": None,
        "review": None,
        "retry_count": 0,
        "current_job_id": None,
    })
    _save_state(state, root)
    return state


def sync_completed_recovery_tasks(project_root: Optional[Path] = None) -> dict:
    """
    Synchronize manager state with the canonical MVP recovery completion list.

    Canonical truth: autopilot_config.json → mvp_recovery.completed_tasks
    This function enforces that truth on manager_state.json:

    1. If current_task is a recovery task listed as completed → clear it, set idle
    2. Remove stale blocked_task entries for tasks that are now completed
    3. Remove the ad-hoc accepted_tasks_r4_recovery field if present
    4. Return a summary of what changed

    Safe to call at any time. Read-only on autopilot_config, read-write on manager_state.
    """
    root = project_root or _DEFAULT_ROOT
    cfg_path = root / "docs" / "progress" / "autopilot_config.json"
    if not cfg_path.exists():
        return {"synced": False, "reason": "autopilot_config.json not found"}

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        completed = set(cfg.get("mvp_recovery", {}).get("completed_tasks", []))
    except Exception as e:
        return {"synced": False, "reason": f"Cannot read autopilot_config: {e}"}

    state = _load_state(root)
    changes = []

    # 1. If current_task is a completed recovery task, clear it
    ct = state.get("current_task") or {}
    if ct.get("_is_mvp_recovery") and ct.get("id") in completed:
        state["status"] = "idle"
        state["current_task"] = None
        state["current_step"] = None
        state["fix_task"] = None
        state["worker_result"] = None
        state["review"] = None
        state["retry_count"] = 0
        changes.append(f"cleared current_task {ct['id']} (already completed)")

    # 2. Remove blocked_task entries for tasks that are now completed
    before = len(state.get("blocked_tasks") or [])
    state["blocked_tasks"] = [
        b for b in (state.get("blocked_tasks") or [])
        if b.get("task_id") not in completed
    ]
    removed = before - len(state["blocked_tasks"])
    if removed:
        changes.append(f"removed {removed} stale blocked_task entries for completed tasks")

    # 3. Remove ad-hoc one-off recovery fields
    for stale_key in list(state.keys()):
        if stale_key.startswith("accepted_tasks_") and stale_key != "accepted_tasks":
            del state[stale_key]
            changes.append(f"removed stale field '{stale_key}'")

    if changes:
        _save_state(state, root)

    return {
        "synced": True,
        "completed_tasks": sorted(completed),
        "changes": changes,
        "manager_status": state["status"],
        "current_task": (state.get("current_task") or {}).get("id"),
    }


# ---------------------------------------------------------------------------
# Import path validator — used by review pipeline
# ---------------------------------------------------------------------------

def _check_python_imports(file_path: Path) -> list[str]:
    """
    Scan a Python file for wrong import prefixes that would fail at runtime.

    When uvicorn/FastAPI runs from backend/, the package root is backend/ so
    imports must be "from app.X" not "from backend.app.X".

    Returns a list of bad import lines (empty list = OK).
    """
    bad: list[str] = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # Only flag actual import statements, not comments or strings
            if stripped.startswith(("#", '"""', "'''")):
                continue
            if (
                stripped.startswith("from backend.app.")
                or stripped.startswith("import backend.app.")
            ):
                bad.append(f"line {lineno}: {stripped[:100]}")
    except Exception:
        pass
    return bad


# ---------------------------------------------------------------------------
# Manager: review logic
# ---------------------------------------------------------------------------

def _review_result(task: dict, worker_result: dict, project_root: Path) -> dict:
    """
    Manager reviews worker output.

    Checks (in order):
    1. Worker reported success (no error)
    2. Every required file exists on disk and is non-empty
    3. Required target files (not just any file) were actually changed
    4. SEMANTIC: content matches product intent (via semantic_validator)
       — includes stub detection, doc-only guard, page identity, regression
    5. False-accept audit: doc-only change detection

    Returns:
      verdict: accepted | retry_required | blocked
    """
    checks = []
    issues = []

    files_required = task.get("files", [])
    files_changed = worker_result.get("files_changed", [])
    verified_unchanged = worker_result.get("verified_unchanged", [])
    worker_success = worker_result.get("success", False)
    worker_error = worker_result.get("error")

    # Check 1: worker did not hard-fail
    if worker_error:
        issues.append(f"Worker error: {worker_error[:150]}")
        checks.append(f"worker_error: {worker_error[:60]}")
    elif not worker_success:
        issues.append("Worker reported failure without error message")
        checks.append("worker_success: FAIL")
    else:
        checks.append("worker_success: OK")

    # Check 2: required files exist on disk
    for rel_path in files_required:
        full = project_root / rel_path
        if full.exists() and full.stat().st_size > 0:
            checks.append(f"file_exists({rel_path}): OK")
        else:
            issues.append(f"Required file missing or empty: {rel_path}")
            checks.append(f"file_exists({rel_path}): FAIL")

    # Check 2b: Python import path sanity for backend/app/ files
    # Catches "from backend.app.X" instead of "from app.X" which compiles fine
    # but fails at runtime when uvicorn runs from the backend/ directory.
    for rel_path in files_changed:
        if rel_path.startswith("backend/app/") and rel_path.endswith(".py"):
            full_py = project_root / rel_path
            if full_py.exists():
                bad = _check_python_imports(full_py)
                if bad:
                    detail = f"Wrong import prefix in {rel_path}: {bad[0]}"
                    issues.append(detail)
                    checks.append(f"import_path({rel_path}): FAIL — {bad[0][:60]}")
                else:
                    checks.append(f"import_path({rel_path}): OK")

    # Check 3: something was changed OR already verified correct on disk.
    # verified_unchanged: executor confirmed files exist, are non-empty, have stable
    # content hash, and contain no placeholder patterns — requirement already satisfied.
    effectively_touched = set(files_changed) | set(verified_unchanged)
    if files_required and not effectively_touched:
        issues.append("Worker made no file changes")
        checks.append("files_changed: NONE")
    elif files_changed:
        checks.append(f"files_changed: {len(files_changed)}")
    elif verified_unchanged:
        checks.append(f"files_changed: 0 (already correct: {len(verified_unchanged)} file(s))")

    # Check 3b: target files (not just docs) were changed — doc-only guard
    # Run even if there are issues, so we capture this distinct failure reason.
    # This check is a hard gate: if worker only touched docs on a code task, fail immediately
    # without even running semantic validation (saves tokens, avoids false-accept).
    # EXCEPTION: if verified_unchanged contains the required code files, the executor
    # confirmed they are already correct — skip the doc-only hard-fail in that case.
    try:
        from app.services.false_accept_auditor import check_doc_only_acceptance
        # Pass the union so that verified_unchanged files don't trigger doc-only guard
        doc_finding = check_doc_only_acceptance(task, list(effectively_touched))
        if doc_finding:
            issues.append(doc_finding.detail)
            checks.append(f"doc_only_guard: FAIL — {doc_finding.detail[:80]}")
            # Hard-fail immediately — semantic validator would be meaningless here
            return {
                "verdict": "retry_required",
                "checks": checks,
                "issues": issues,
                "notes": "; ".join(issues),
                "reviewed_at": datetime.now().isoformat(),
            }
        else:
            code_targets = [f for f in files_required if not f.startswith("docs/")]
            if code_targets:
                checks.append("doc_only_guard: OK")
    except Exception as e:
        checks.append(f"doc_only_guard: ERROR — {str(e)[:60]}")

    # Check 4: semantic / product-intent validation
    # Only run if structural checks passed (files exist); saves time on obvious failures.
    structural_ok = not any("FAIL" in c for c in checks)
    if structural_ok:
        try:
            from app.services.semantic_validator import validate_task_result
            sem = validate_task_result(task, project_root, verified_unchanged=verified_unchanged)
            checks.extend(sem.checks)
            issues.extend(sem.issues)
        except Exception as e:
            # Semantic validator failure must not silently pass — treat as warning
            checks.append(f"semantic_validator: ERROR — {str(e)[:80]}")
            issues.append(f"Semantic validation could not run: {e}")
    else:
        checks.append("semantic_validator: SKIPPED (structural checks failed)")

    # Verdict
    if not issues:
        verdict = "accepted"
        fc_count = len(files_changed)
        vu_count = len(verified_unchanged)
        if fc_count and vu_count:
            notes = f"All checks passed. {fc_count} file(s) changed, {vu_count} already correct."
        elif vu_count:
            notes = f"All checks passed. {vu_count} file(s) already correct (no write needed)."
        else:
            notes = f"All checks passed. {fc_count} file(s) changed."
    elif not worker_success and worker_error:
        verdict = "blocked"
        notes = "; ".join(issues)
    else:
        verdict = "retry_required"
        notes = "; ".join(issues)

    return {
        "verdict": verdict,
        "checks": checks,
        "issues": issues,
        "notes": notes,
        "reviewed_at": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Manager: fix task builder
# ---------------------------------------------------------------------------

def _build_fix_task(task: dict, review: dict, retry_count: int) -> str:
    """
    Manager (not worker) creates a targeted fix prompt.
    Uses executive-standard format: explicitly names the failure, forbids known bad patterns.
    """
    files_str = "\n".join(f"  {f}" for f in task["files"]) if task["files"] else "  see change description"
    issues_str = review.get("notes", "unknown")

    return f"""TASK BRIEF — RETRY ATTEMPT {retry_count}
==========

## Objective
Fix and complete: {task['title']}

## What Failed Previously
{issues_str}

## Target Files (ONLY modify these)
{files_str}

## CRITICAL — Write-Target Policy
Changing docs/ files counts as FAILURE for this task, even if the content looks relevant.
The only acceptable result is modifying the target files listed above.
  - Do NOT write to docs/
  - Do NOT write to docs/agent/
  - Do NOT write to docs/data_model.md or any docs/ path
  - Docs are READ-ONLY context for this task
  - If you only changed docs/, the task will fail again immediately

## Critical Requirements for This Retry
  - Read the failure reason above carefully
  - If the failure is 'def main(): pass stub' — rewrite as a real module, not a script
  - If the failure is 'doc-only change' — modify ONLY the target files, not docs/
  - If the failure is 'missing APIRouter' — add router = APIRouter() and route decorators
  - No placeholder text. No pass-only function bodies. No TODO comments.

## Original Task Requirement
{task.get('change', '')[:400]}

## Acceptance Criteria
  - All target files exist and are non-empty
  - No function body is only 'pass'
  - No file contains 'Generated Content' or placeholder text
  - Target code files (not docs) are the ones that changed"""


# ---------------------------------------------------------------------------
# Worker dispatch
# ---------------------------------------------------------------------------

def _execute_worker(
    step_prompt: str,
    project_root: Path,
    job_id: str,
    task: Optional[dict] = None,
    executor_timeout: int = 300,
) -> dict:
    """
    Dispatch narrow step to the worker.

    Priority:
      1. claude_cli_executor  — real Claude Code CLI, guaranteed file writes
      2. ClaudeExecutor (SDK) — fallback when CLI absent but API key present
      3. FileExecutor         — template-based fallback, always available

    Passes allowed_write_paths derived from the task's declared target files,
    so the executor write-target policy enforces docs-read-only automatically.
    """
    import logging

    log = logging.getLogger(__name__)
    # Derive write allowlist from task files — only those are writable
    allowed_write_paths = list(task.get("files", [])) if task else []

    # ── Priority 1: claude CLI (real file-writing path) ────────────────────
    try:
        from app.services.claude_cli_executor import run_claude_cli, is_available as cli_available
        if cli_available():
            cli_result = run_claude_cli(
                prompt=step_prompt,
                project_root=project_root,
                allowed_write_paths=allowed_write_paths,
                job_id=job_id,
                timeout=executor_timeout,  # SP-8
            )
            if cli_result["success"]:
                return cli_result
            log.warning(
                "claude_cli_executor non-success for job %s (%s); trying SDK executor",
                job_id,
                cli_result.get("error", "no files changed"),
            )
    except Exception as _cli_err:
        log.warning("claude_cli_executor failed for job %s: %s", job_id, _cli_err)

    # ── Priority 2: ClaudeExecutor (SDK) ──────────────────────────────────
    import os as _os
    if _os.environ.get("ANTHROPIC_API_KEY", "").strip():
        try:
            from app.services.claude_executor import ClaudeExecutor, ExecutionMode
            executor = ClaudeExecutor(
                project_root=project_root,
                prefer_mode=ExecutionMode.CLAUDE,
            )
            if executor._claude_available:
                claude_result = executor.execute(
                    prompt=step_prompt,
                    task_type="code",
                    context={"allowed_write_paths": allowed_write_paths, "job_id": job_id},
                )
                if claude_result.success:
                    return {
                        "success": True,
                        "files_changed": claude_result.changed_files,
                        "output": (claude_result.answer or "")[:600],
                        "execution_summary": claude_result.summary,
                        "error": claude_result.error,
                        "executor": "claude",
                    }
                log.warning(
                    "ClaudeExecutor returned unsuccessful result for job %s; falling back to FileExecutor: %s",
                    job_id,
                    claude_result.error or "unknown error",
                )
        except Exception as _ce:
            # Claude unavailable or failed — fall through to FileExecutor
            log.warning("ClaudeExecutor failed for job %s; falling back to FileExecutor: %s", job_id, _ce)

    # ── Fallback: FileExecutor ─────────────────────────────────────────────
    try:
        from app.services.file_executor import FileExecutor
        executor = FileExecutor(project_root=project_root)
        result = executor.execute_task(
            task_description=step_prompt,
            job_id=job_id,
            task_type="code",
            allowed_write_paths=allowed_write_paths,
        )
        return {
            "success": result.success,
            "files_changed": result.files_changed,
            "output": (result.output or "")[:600],
            "execution_summary": result.execution_summary,
            "error": result.error,
            "executor": "file_executor",
        }
    except Exception as e:
        return {
            "success": False,
            "files_changed": [],
            "output": "",
            "execution_summary": "",
            "error": str(e)[:300],
            "executor": "none",
        }


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_manager_cycle(
    project_root: Optional[Path] = None,
    job_id: Optional[str] = None,
    executor_timeout: int = 300,
) -> dict:
    """
    Execute one full manager cycle:

      SELECTING  → choose next task from roadmap
      PLANNING   → build narrow execution step (or fix task on retry)
      EXECUTING  → dispatch to worker (file_executor)
      REVIEWING  → manager checks files on disk
      DECIDED    → accepted | retry_required | blocked

    Safety: before selecting, sync manager state against canonical completion list
    so stale blocked/manual-recovered state never silently pollutes execution.

    Returns the updated manager state dict.
    """
    root = project_root or _DEFAULT_ROOT

    # ── STATE SYNC — canonical recovery truth enforcement ───────────────────
    # If the current_task is already completed per autopilot_config, clear it
    # before continuing. This prevents stale blocked tasks from re-executing.
    sync_completed_recovery_tasks(root)

    state = _load_state(root)

    effective_job_id = job_id or f"mgr-{int(time.time())}"
    state["current_job_id"] = effective_job_id

    # SP-5: initialise sprint tracking fields if not set
    if not state.get("sprint_id"):
        state["sprint_id"] = f"sprint-{int(time.time())}"
        state["sprint_start_ts"] = datetime.now().isoformat()
        state["sprint_accepted"] = 0
        state["sprint_blocked"] = 0

    # ── SELECTING ──────────────────────────────────────────────────────────
    state["status"] = "selecting"
    _save_state(state, root)

    from app.services.task_intake import (
        choose_next_task,
        resolve_product_context,
        build_execution_prompt,
        classify_task,
    )

    # On retry, reuse current task; otherwise pick next (repair queue or roadmap)
    in_retry = state.get("status") in ("retry_required",) or state.get("retry_count", 0) > 0
    if in_retry and state.get("current_task"):
        task = state["current_task"]
        retry_count = state.get("retry_count", 0)
    else:
        task = choose_next_task()
        retry_count = 0
        state["retry_count"] = 0

    if not task:
        state["status"] = "idle"
        state["current_task"] = None
        _save_state(state, root)
        return state

    # ── PREFLIGHT GATE — recovery readiness check ──────────────────────────
    # For MVP recovery tasks, verify that prerequisite files are real and non-stub
    # before dispatching to the worker. A task whose prereqs are not ready will
    # never succeed regardless of how many times it retries.
    if task.get("_is_mvp_recovery") and retry_count == 0:
        try:
            from app.services.recovery_gate import check_task_ready
            gate = check_task_ready(task, root)
            if not gate.ready:
                state["status"] = "blocked"
                state["current_task"] = task
                reason = f"PREFLIGHT FAILED: {gate.reason}"
                _record_blocked(state, task, {"notes": reason}, 0, reason)
                _append_history(state, task, "blocked", {"notes": reason}, {"files_changed": [], "success": False})
                state["retry_count"] = 0
                _save_state(state, root)
                return state
        except Exception:
            pass  # Gate errors must not block execution — gate is conservative

    # Classify the task to set level-aware retry/escalation policy
    task_level = 2  # default
    try:
        clf = classify_task(task)
        if clf:
            task_level = clf.level
            state["current_task_level"] = task_level
            # Override max_retries based on level
            state["max_retries"] = clf.spec.max_retries
    except Exception:
        pass

    state["current_task"] = task
    state["retry_count"] = retry_count

    # ── PLANNING ───────────────────────────────────────────────────────────
    state["status"] = "planning"
    _save_state(state, root)

    context = resolve_product_context(task)

    if retry_count > 0 and state.get("review"):
        step_prompt = _build_fix_task(task, state["review"], retry_count)
        state["fix_task"] = step_prompt
    else:
        step_prompt = build_execution_prompt(task, context)
        state["fix_task"] = None

    state["current_step"] = step_prompt

    # ── EXECUTING ──────────────────────────────────────────────────────────
    state["status"] = "executing"
    _save_state(state, root)

    worker_result = _execute_worker(step_prompt, root, effective_job_id, task=task, executor_timeout=executor_timeout)
    state["worker_result"] = worker_result

    # ── REVIEWING ──────────────────────────────────────────────────────────
    state["status"] = "reviewing"
    _save_state(state, root)

    review = _review_result(task, worker_result, root)
    state["review"] = review
    verdict = review["verdict"]

    # ── DECIDING ───────────────────────────────────────────────────────────
    if verdict == "accepted":
        state["status"] = "accepted"
        state["sprint_accepted"] = (state.get("sprint_accepted") or 0) + 1  # SP-5
        state["accepted_tasks"] = (state.get("accepted_tasks") or []) + [{
            "task_id": task["id"],
            "task_title": task["title"],
            "files_changed": worker_result.get("files_changed", []),
            "accepted_at": datetime.now().isoformat(),
            "retries": retry_count,
        }]
        state["accepted_tasks"] = state["accepted_tasks"][-20:]
        state["retry_count"] = 0
        _append_history(state, task, "accepted", review, worker_result)
        # Mark task done in ROADMAP.md so choose_next_task skips it next cycle
        _mark_roadmap_task_done(task["id"], root)
        # For MVP recovery tasks, also persist to autopilot_config completed_tasks
        if task.get("_is_mvp_recovery"):
            _mark_mvp_recovery_task_done(task["id"], root)
        # Save file snapshots for regression detection on future tasks
        _record_accepted_snapshots(task, worker_result, root)
        # Update product memory (legacy)
        _update_product_memory(task, "accepted", worker_result, review, root)
        # Update executive memory (richer product model)
        _update_executive_memory(task, "accepted", worker_result, review, root)
        # Run false-accept audit on newly accepted files
        _run_false_accept_audit(task, worker_result, root)
        # If task is a repair, mark it complete in repair queue
        if task.get("_is_repair") and task.get("_repair_entry"):
            _complete_repair(task["_repair_entry"].get("repair_id"), root)

    elif verdict == "retry_required":
        next_retry = retry_count + 1
        if next_retry > state.get("max_retries", MAX_RETRIES):
            state["status"] = "blocked"
            state["sprint_blocked"] = (state.get("sprint_blocked") or 0) + 1  # SP-5
            _record_blocked(state, task, review, retry_count, "max retries exceeded")
            _append_history(state, task, "blocked", review, worker_result)
            state["retry_count"] = 0
            _update_product_memory(task, "blocked", worker_result, review, root)
            _update_executive_memory(task, "blocked", worker_result, review, root)
            # Queue repair if applicable
            _queue_repair_on_block(task, review, root)
        else:
            state["status"] = "retry_required"
            state["retry_count"] = next_retry
            _append_history(state, task, "retry_required", review, worker_result)
            _update_product_memory(task, "retry_required", worker_result, review, root)
            _update_executive_memory(task, "retry_required", worker_result, review, root)
        # If was a repair, log the failure
        if task.get("_is_repair") and task.get("_repair_entry"):
            _fail_repair(task["_repair_entry"].get("repair_id"), review.get("notes", ""), root)

    else:  # "blocked"
        state["status"] = "blocked"
        state["sprint_blocked"] = (state.get("sprint_blocked") or 0) + 1  # SP-5
        _record_blocked(state, task, review, retry_count, review.get("notes", "blocked"))
        _append_history(state, task, "blocked", review, worker_result)
        state["retry_count"] = 0
        _update_product_memory(task, "blocked", worker_result, review, root)
        _update_executive_memory(task, "blocked", worker_result, review, root)
        _queue_repair_on_block(task, review, root)
        if task.get("_is_repair") and task.get("_repair_entry"):
            _fail_repair(task["_repair_entry"].get("repair_id"), review.get("notes", ""), root)

    _save_state(state, root)
    return state


def _mark_mvp_recovery_task_done(task_id: str, project_root: Path) -> None:
    """
    Append task_id to autopilot_config.mvp_recovery.completed_tasks.
    This is the persistence mechanism that _load_mvp_recovery_tasks() reads
    to determine which recovery tasks are done.
    _mark_roadmap_task_done writes to ROADMAP.md, which only covers the normal
    roadmap. Recovery roadmap tasks live in MVP_RECOVERY_ROADMAP.md and are
    tracked exclusively via autopilot_config.
    """
    cfg_path = project_root / "docs" / "progress" / "autopilot_config.json"
    if not cfg_path.exists():
        return
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        completed = cfg.setdefault("mvp_recovery", {}).setdefault("completed_tasks", [])
        if task_id not in completed:
            completed.append(task_id)
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    except Exception:
        pass


def _mark_roadmap_task_done(task_id: str, project_root: Path) -> None:
    """
    Append [x] marker to the task heading in ROADMAP.md so that
    choose_next_task() skips it on the next cycle.
    """
    roadmap = project_root / "docs" / "agent" / "ROADMAP.md"
    if not roadmap.exists():
        return
    try:
        text = roadmap.read_text(encoding="utf-8")
        # Match the task heading: ### <task_id> <title>
        pattern = rf'(###\s+{re.escape(task_id)}\b[^\n]*)'
        replacement = r'\1 [x]'
        new_text = re.sub(pattern, replacement, text, count=1)
        if new_text != text:
            roadmap.write_text(new_text, encoding="utf-8")
    except Exception:
        pass


def _record_blocked(state: dict, task: dict, review: dict, retries: int, reason: str) -> None:
    state["blocked_tasks"] = (state.get("blocked_tasks") or []) + [{
        "task_id": task["id"],
        "task_title": task["title"],
        "reason": reason,
        "review_notes": review.get("notes", ""),
        "blocked_at": datetime.now().isoformat(),
        "retries": retries,
    }]
    state["blocked_tasks"] = state["blocked_tasks"][-20:]


def _append_history(
    state: dict,
    task: dict,
    verdict: str,
    review: dict,
    worker_result: dict,
) -> None:
    state["history"] = (state.get("history") or []) + [{
        "task_id": task["id"],
        "task_title": task["title"],
        "verdict": verdict,
        "notes": review.get("notes", ""),
        "files_changed": worker_result.get("files_changed", []),
        "timestamp": datetime.now().isoformat(),
    }]
    state["history"] = state["history"][-20:]


def _record_accepted_snapshots(task: dict, worker_result: dict, project_root: Path) -> None:
    """Save content snapshots of every accepted file for future regression detection."""
    try:
        from app.services.semantic_validator import record_file_snapshot
        for rel_path in (worker_result.get("files_changed") or []):
            full = project_root / rel_path
            if full.exists():
                content = full.read_text(encoding="utf-8", errors="replace")
                record_file_snapshot(project_root, rel_path, content)
    except Exception:
        pass  # never block acceptance on snapshot write failure


def _update_product_memory(
    task: dict,
    verdict: str,
    worker_result: dict,
    review: dict,
    project_root: Path,
) -> None:
    """Update product memory after any task verdict."""
    try:
        from app.services.product_memory import update_after_task
        update_after_task(
            task=task,
            verdict=verdict,
            files_changed=worker_result.get("files_changed") or [],
            semantic_issues=review.get("issues") or [],
            project_root=project_root,
        )
    except Exception:
        pass  # never block verdict on memory write failure


def _update_executive_memory(
    task: dict,
    verdict: str,
    worker_result: dict,
    review: dict,
    project_root: Path,
) -> None:
    """Update executive memory (richer product model) after any task verdict."""
    try:
        from app.services.executive_memory import update_after_task
        update_after_task(
            task=task,
            verdict=verdict,
            files_changed=worker_result.get("files_changed") or [],
            review=review,
            project_root=project_root,
        )
    except Exception:
        pass  # never block verdict on memory write failure


def _run_false_accept_audit(
    task: dict,
    worker_result: dict,
    project_root: Path,
) -> None:
    """
    Run false-accept audit on newly accepted files.
    Records findings in executive memory so future cycles can prioritize repairs.
    Does not change the verdict — runs after acceptance is recorded.
    """
    try:
        from app.services.false_accept_auditor import audit_all_accepted, record_findings_in_memory
        accepted_entry = [{
            "task_id": task.get("id", "?"),
            "task_title": task.get("title", ""),
            "files_changed": worker_result.get("files_changed") or [],
            "accepted_at": datetime.now().isoformat(),
        }]
        report = audit_all_accepted(accepted_entry, project_root)
        if report.has_issues:
            record_findings_in_memory(report.findings, project_root)
            # Also queue repairs for critical findings
            try:
                from app.services.repair_queue import queue_from_finding
                for finding in report.findings:
                    if finding.severity in ("critical", "high"):
                        queue_from_finding(finding, project_root)
            except Exception:
                pass
    except Exception:
        pass  # never block on audit failure


def _queue_repair_on_block(task: dict, review: dict, project_root: Path) -> None:
    """Create a repair queue entry when a task is blocked."""
    # SP-3: never create repair-of-repair — depth capped at 1
    if task.get("_is_repair"):
        import logging as _rl
        _rl.getLogger(__name__).warning(
            "_queue_repair_on_block: skipping repair-of-repair for task %s", task.get("id")
        )
        return
    # Only queue repairs for non-trivial failures (not simple missing file blocks)
    notes = review.get("notes", "")
    if not notes or "missing" in notes.lower():
        return  # structural failure — not a false-accept issue
    try:
        from app.services.repair_queue import add_repair
        files = task.get("files", [])
        for f in files:
            add_repair(
                original_task_id=task.get("id", "?"),
                original_task_title=task.get("title", "")[:80],
                file=f,
                reason=notes[:200],
                detection_source="manager_loop_block",
                repair_brief=(
                    f"Re-implement {f}.\n"
                    f"Original task: {task.get('id')} — {task.get('title', '')[:60]}\n"
                    f"Failure reason: {notes[:200]}\n"
                    f"Requirements: {task.get('change', '')[:300]}"
                ),
                priority="P2",
                project_root=project_root,
            )
    except Exception:
        pass


def _complete_repair(repair_id: Optional[str], project_root: Path) -> None:
    if not repair_id:
        return
    try:
        from app.services.repair_queue import mark_repair_complete
        mark_repair_complete(repair_id, project_root)
    except Exception:
        pass


def _fail_repair(repair_id: Optional[str], reason: str, project_root: Path) -> None:
    if not repair_id:
        return
    try:
        from app.services.repair_queue import mark_repair_failed
        mark_repair_failed(repair_id, reason, project_root)
    except Exception:
        pass
