"""
AI Workspace Platform - Dashboard API
Endpoints for autonomous development panel

Enhanced with:
- Full state synchronization from all sources
- Real-time job queue status
- Supervisor state integration
- Loop state integration
- Orchestrator state integration (NEW)
- Accurate mode display (self/claude)
- Files changed tracking
- Review loop status
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Project root path
PROJECT_ROOT = Path(settings.PROJECT_ROOT)
DOCS_PATH = PROJECT_ROOT / "docs"
PROGRESS_PATH = DOCS_PATH / "progress"
STATE_FILE = PROGRESS_PATH / "state.json"
SUPERVISOR_STATE_FILE = PROGRESS_PATH / "supervisor_state.json"
LOOP_STATE_FILE = PROGRESS_PATH / "loop_state.json"
ORCHESTRATOR_STATE_FILE = PROGRESS_PATH / "orchestrator_state.json"
JOBS_PATH = PROJECT_ROOT / "storage" / "jobs"


class ProjectState(BaseModel):
    """Current project execution state - comprehensive"""
    stage: str = "idle"
    mode: str = "self"  # self or claude
    is_paused: bool = False
    last_task: Optional[str] = None
    last_task_status: str = "none"
    last_updated: str = ""
    # Core state
    current_stage: Optional[str] = None
    active_task: Optional[str] = None
    last_completed_task: Optional[str] = None
    last_job_id: Optional[str] = None
    files_changed_count: int = 0
    has_error: bool = False
    error_message: Optional[str] = None
    # Loop state
    loop_running: bool = False
    loop_step: Optional[str] = None
    loop_iteration: int = 0
    # Supervisor state
    supervisor_task: Optional[str] = None
    retry_count: int = 0
    blocked_count: int = 0
    # Orchestrator state (NEW)
    orchestrator_status: str = "idle"
    orchestrator_attempts: int = 0
    orchestrator_max_attempts: int = 3
    review_in_progress: bool = False
    # Active job persistence (NEW)
    active_job_id: Optional[str] = None
    active_job_status: Optional[str] = None
    active_job_task: Optional[str] = None
    current_step_index: int = 0
    plan_step_count: int = 0


class TaskInfo(BaseModel):
    """Last Claude task information"""
    task_id: Optional[str] = None
    description: str = ""
    status: str = "none"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None


class FileChange(BaseModel):
    """File change record"""
    path: str
    action: str  # created, modified, deleted
    timestamp: str


class ControlAction(BaseModel):
    """Control action request"""
    reason: Optional[str] = None


class JobInfo(BaseModel):
    """Job information for display"""
    job_id: str
    status: str
    task_type: str
    current_stage: str
    created_at: str
    progress_count: int = 0
    has_error: bool = False


def _load_json_file(path: Path) -> Dict[str, Any]:
    """Safely load a JSON file"""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def get_state() -> dict:
    """Load comprehensive state from all sources"""
    # Load main state
    state = _load_json_file(STATE_FILE)

    # Load supervisor state
    supervisor = _load_json_file(SUPERVISOR_STATE_FILE)

    # Load loop state
    loop = _load_json_file(LOOP_STATE_FILE)

    # Load orchestrator state (NEW)
    orchestrator = _load_json_file(ORCHESTRATOR_STATE_FILE)

    # Get accurate active job info from state.json (single source of truth)
    # state.json is updated by job_queue.py on every job lifecycle change
    active_job_id = state.get("active_job_id")
    active_job_status = state.get("active_job_status")
    active_job_task = state.get("active_job_task")

    # Check if active_job_* fields are set and job is actually running
    is_job_active = active_job_id and active_job_status in ("queued", "started", "in_progress")

    # Get plan info from orchestrator for step tracking
    plan = orchestrator.get("plan", {})
    current_step_index = orchestrator.get("current_step_index", 0)
    plan_steps = plan.get("steps", []) if plan else []

    # Build comprehensive state
    result = {
        # From main state
        "stage": state.get("current_stage", state.get("stage", "idle")),
        "mode": orchestrator.get("mode", state.get("mode", "self")),
        "is_paused": state.get("is_paused", False),
        "last_task": state.get("active_task", state.get("last_task", "")),
        "last_task_status": state.get("last_task_status", "none"),
        "last_updated": state.get("updated_at", state.get("last_updated", datetime.now().isoformat())),
        "current_stage": state.get("current_stage", ""),
        "active_task": active_job_task if is_job_active else "",
        "last_completed_task": state.get("last_completed_task", ""),
        "last_job_id": active_job_id if is_job_active else state.get("last_job_id", ""),
        "files_changed_count": len(state.get("last_changed_files", [])),
        "has_error": bool(state.get("error")),
        "error_message": state.get("error"),

        # From loop state
        "loop_running": loop.get("is_running", False),
        "loop_step": loop.get("current_step"),
        "loop_iteration": loop.get("iteration", 0),

        # From supervisor state
        "supervisor_task": supervisor.get("active_task"),
        "retry_count": len(supervisor.get("attempts", [])),
        "blocked_count": len(supervisor.get("blocked_tasks", [])),

        # From orchestrator state (ENHANCED)
        "orchestrator_status": orchestrator.get("status", "idle"),
        "orchestrator_attempts": orchestrator.get("attempts", 0),
        "orchestrator_max_attempts": orchestrator.get("max_attempts", 3),
        "review_in_progress": orchestrator.get("status") in ("reviewing", "verifying", "step_reviewing"),

        # Active job persistence - use state.json as single source of truth
        "active_job_id": active_job_id if is_job_active else None,
        "active_job_status": active_job_status if is_job_active else None,
        "active_job_task": active_job_task if is_job_active else None,
        "current_step_index": current_step_index,
        "plan_step_count": len(plan_steps)
    }

    # Determine best active task from all sources
    if not result["active_task"]:
        if orchestrator.get("current_task"):
            result["active_task"] = orchestrator["current_task"]
        elif loop.get("current_task"):
            result["active_task"] = loop["current_task"]
        elif supervisor.get("active_task"):
            result["active_task"] = supervisor["active_task"]

    # Determine accurate status based on all states
    if result["has_error"]:
        result["last_task_status"] = "error"
    elif orchestrator.get("status") == "blocked":
        result["last_task_status"] = "blocked"
    elif orchestrator.get("status") == "step_reviewing":
        result["last_task_status"] = "step_reviewing"
    elif orchestrator.get("status") == "step_executing":
        result["last_task_status"] = f"step_{current_step_index + 1}"
    elif orchestrator.get("status") == "planning":
        result["last_task_status"] = "planning"
    elif orchestrator.get("status") == "reviewing":
        result["last_task_status"] = "reviewing"
    elif orchestrator.get("status") == "verifying":
        result["last_task_status"] = "verifying"
    elif orchestrator.get("status") == "retrying":
        result["last_task_status"] = f"retry:{orchestrator.get('attempts', 0)}"
    elif orchestrator.get("status") == "running":
        result["last_task_status"] = "running"
    elif loop.get("current_step") == "blocked":
        result["last_task_status"] = "blocked"
    elif result["is_paused"]:
        result["last_task_status"] = "paused"
    elif result["loop_running"]:
        result["last_task_status"] = f"loop:{loop.get('current_step', 'unknown')}"
    elif supervisor.get("active_task"):
        attempts = len(supervisor.get("attempts", []))
        if attempts > 0:
            result["last_task_status"] = f"retry:{attempts}"

    return result


def get_jobs_summary() -> List[JobInfo]:
    """Get recent jobs with summary info"""
    jobs = []
    if JOBS_PATH.exists():
        for job_file in sorted(
            JOBS_PATH.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )[:10]:
            try:
                job = json.loads(job_file.read_text())
                jobs.append(JobInfo(
                    job_id=job.get("job_id", "unknown"),
                    status=job.get("status", "unknown"),
                    task_type=job.get("task_type", "unknown"),
                    current_stage=job.get("current_stage", "unknown"),
                    created_at=job.get("created_at", ""),
                    progress_count=len(job.get("progress", [])),
                    has_error=bool(job.get("error"))
                ))
            except Exception:
                pass
    return jobs


def save_state(state: dict) -> None:
    """Save state to file"""
    PROGRESS_PATH.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now().isoformat()

    # Load existing state and merge
    existing = _load_json_file(STATE_FILE)
    existing.update({
        k: v for k, v in state.items()
        if k in ["is_paused", "last_task_status", "mode", "error"]
    })
    existing["updated_at"] = state["last_updated"]

    STATE_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


@router.get("/status")
async def get_project_status():
    """Get current project state - comprehensive view"""
    state = get_state()
    return ProjectState(**state)


@router.get("/full-state")
async def get_full_state():
    """Get complete state from all sources for debugging"""
    main_state = _load_json_file(STATE_FILE)
    supervisor_state = _load_json_file(SUPERVISOR_STATE_FILE)
    loop_state = _load_json_file(LOOP_STATE_FILE)

    return {
        "main": main_state,
        "supervisor": supervisor_state,
        "loop": loop_state,
        "jobs": [j.dict() for j in get_jobs_summary()]
    }


@router.get("/current-status")
async def get_current_status_md():
    """Get CURRENT_STATUS.md content - syncs first"""
    # Sync status before returning
    try:
        from app.services.status_updater import sync_status_file
        sync_status_file()
    except Exception:
        pass

    status_file = PROGRESS_PATH / "CURRENT_STATUS.md"
    if not status_file.exists():
        return {"content": "# Status\n\nNo status file found."}
    return {"content": status_file.read_text()}


@router.get("/changes")
async def get_recent_changes():
    """Get list of recently changed files"""
    changes_file = PROGRESS_PATH / "changes.json"
    if changes_file.exists():
        try:
            changes = json.loads(changes_file.read_text())
            return {"changes": changes[-20:]}  # Last 20 changes
        except:
            pass

    # Also get from state.json last_changed_files
    state = _load_json_file(STATE_FILE)
    state_files = state.get("last_changed_files", [])
    if state_files:
        changes = [
            {
                "path": f,
                "action": "modified",
                "timestamp": state.get("updated_at", datetime.now().isoformat())
            }
            for f in state_files
        ]
        return {"changes": changes}

    # Fallback: scan for recently modified files
    changes = []
    try:
        for path in PROJECT_ROOT.rglob("*"):
            if path.is_file() and ".git" not in str(path) and "__pycache__" not in str(path):
                rel_path = path.relative_to(PROJECT_ROOT)
                stat = path.stat()
                changes.append({
                    "path": str(rel_path),
                    "action": "modified",
                    "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        # Sort by timestamp descending and take last 20
        changes.sort(key=lambda x: x["timestamp"], reverse=True)
        changes = changes[:20]
    except Exception as e:
        changes = [{"path": "error", "action": "error", "timestamp": str(e)}]

    return {"changes": changes}


@router.get("/progress-files")
async def list_progress_files():
    """List all progress files in docs/progress"""
    files = []
    if PROGRESS_PATH.exists():
        for f in PROGRESS_PATH.glob("*.md"):
            files.append({
                "name": f.name,
                "path": str(f.relative_to(PROJECT_ROOT)),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
    return {"files": files}


@router.get("/progress-file/{filename}")
async def get_progress_file(filename: str):
    """Get content of a specific progress file"""
    # Security: only allow .md files from progress directory
    if not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files allowed")

    filepath = PROGRESS_PATH / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Ensure path doesn't escape progress directory
    if not filepath.resolve().is_relative_to(PROGRESS_PATH.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")

    return {"content": filepath.read_text(), "filename": filename}


@router.get("/last-task")
async def get_last_task():
    """Get information about the last Claude task"""
    task_file = PROGRESS_PATH / "last_task.json"
    if task_file.exists():
        try:
            return TaskInfo(**json.loads(task_file.read_text()))
        except:
            pass

    # Get from supervisor state
    supervisor = _load_json_file(SUPERVISOR_STATE_FILE)
    if supervisor.get("active_task"):
        attempts = supervisor.get("attempts", [])
        last_attempt = attempts[-1] if attempts else {}
        return TaskInfo(
            task_id=supervisor.get("active_task"),
            description=supervisor.get("active_task"),
            status=last_attempt.get("verdict", "in_progress"),
            result=f"Attempt {len(attempts)}"
        )

    # Get from loop state
    loop = _load_json_file(LOOP_STATE_FILE)
    if loop.get("current_task"):
        return TaskInfo(
            task_id=f"loop-{loop.get('iteration', 0)}",
            description=loop.get("current_task"),
            status=loop.get("current_step", "unknown")
        )

    # Default task info from state
    state = get_state()
    return TaskInfo(
        description=state.get("last_task") or state.get("last_completed_task") or "No task recorded",
        status=state.get("last_task_status", "unknown")
    )


@router.get("/supervisor-status")
async def get_supervisor_status():
    """Get supervisor state for review loop monitoring"""
    supervisor = _load_json_file(SUPERVISOR_STATE_FILE)
    return {
        "active_task": supervisor.get("active_task"),
        "attempts": len(supervisor.get("attempts", [])),
        "blocked_tasks": supervisor.get("blocked_tasks", [])[-5:],
        "completed_tasks": supervisor.get("completed_tasks", [])[-5:],
        "updated_at": supervisor.get("updated_at")
    }


@router.get("/loop-status")
async def get_loop_status():
    """Get autonomous loop state"""
    loop = _load_json_file(LOOP_STATE_FILE)
    return {
        "is_running": loop.get("is_running", False),
        "current_step": loop.get("current_step"),
        "current_task": loop.get("current_task"),
        "iteration": loop.get("iteration", 0),
        "retry_count": loop.get("retry_count", 0),
        "blocked_reason": loop.get("blocked_reason"),
        "updated_at": loop.get("updated_at")
    }


@router.get("/orchestrator-state")
async def get_orchestrator_state():
    """Get orchestrator state including review loop status and active job"""
    orchestrator = _load_json_file(ORCHESTRATOR_STATE_FILE)

    # Get recent reviews
    reviews = orchestrator.get("reviews", [])[-5:]

    # Get progress events for manager mode
    progress_events = orchestrator.get("progress_events", [])[-20:]

    # Get plan info for manager mode
    plan = orchestrator.get("plan", {})

    return {
        "status": orchestrator.get("status", "idle"),
        "mode": orchestrator.get("mode", "manager"),
        "current_task": orchestrator.get("current_task"),
        "current_job_id": orchestrator.get("current_job_id"),
        "current_step": orchestrator.get("current_step"),
        "current_step_index": orchestrator.get("current_step_index", 0),
        "current_dod": orchestrator.get("current_dod"),
        "plan": plan,
        "attempts": orchestrator.get("attempts", 0),
        "max_attempts": orchestrator.get("max_attempts", 3),
        "reviews": reviews,
        "progress_events": progress_events,
        "blocked_tasks": orchestrator.get("blocked_tasks", [])[-3:],
        "completed_tasks": orchestrator.get("completed_tasks", [])[-3:],
        "claude_invoked": orchestrator.get("claude_invoked", False),
        "claude_reason": orchestrator.get("claude_reason"),
        "updated_at": orchestrator.get("updated_at")
    }


@router.get("/active-job")
async def get_active_job():
    """
    Get the currently active job from backend state.

    This endpoint allows dashboard to restore active job after page reload.
    Uses state.json as single source of truth for active job info.
    Returns job_id, task, status, and plan progress.
    """
    # Use state.json as single source of truth (updated by job_queue.py)
    state = _load_json_file(STATE_FILE)
    orchestrator = _load_json_file(ORCHESTRATOR_STATE_FILE)

    active_job_id = state.get("active_job_id")
    active_job_status = state.get("active_job_status")
    active_job_task = state.get("active_job_task")

    # Only return as active if job is actually running
    is_active = active_job_id and active_job_status in ("queued", "started", "in_progress")

    if not is_active:
        return {
            "active": False,
            "job_id": None,
            "task": None,
            "status": "idle",
            "plan": None
        }

    plan = orchestrator.get("plan", {})
    progress_events = orchestrator.get("progress_events", [])[-20:]

    return {
        "active": True,
        "job_id": active_job_id,
        "task": active_job_task,
        "status": active_job_status,
        "mode": orchestrator.get("mode", "manager"),
        "current_step": state.get("current_stage"),
        "current_step_index": orchestrator.get("current_step_index", 0),
        "plan": plan,
        "progress_events": progress_events,
        "updated_at": state.get("updated_at")
    }


@router.get("/manager-state")
async def get_manager_state_endpoint():
    """
    Manager loop lifecycle state.
    Lifecycle: idle → selecting → planning → executing → reviewing → accepted|retry_required|blocked
    Persists across reloads (file-backed).
    """
    try:
        from app.services.manager_loop import get_manager_state
        state = get_manager_state()
        # Trim worker output for dashboard display
        wr = state.get("worker_result") or {}
        return {
            "status": state.get("status"),
            "current_task_id": (state.get("current_task") or {}).get("id"),
            "current_task_title": (state.get("current_task") or {}).get("title"),
            "current_step_preview": (state.get("current_step") or "")[:120],
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", 2),
            "review": state.get("review"),
            "worker_success": wr.get("success"),
            "worker_files_changed": wr.get("files_changed", []),
            "worker_error": wr.get("error"),
            "accepted_count": len(state.get("accepted_tasks", [])),
            "blocked_count": len(state.get("blocked_tasks", [])),
            "last_accepted": (state.get("accepted_tasks") or [{}])[-1],
            "last_blocked": (state.get("blocked_tasks") or [{}])[-1],
            "history": state.get("history", [])[-5:],
            "updated_at": state.get("updated_at"),
        }
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


async def get_full_orchestrator_state():
    """Get complete orchestrator state for debugging"""
    return _load_json_file(ORCHESTRATOR_STATE_FILE)


@router.post("/control/pause")
async def pause_execution(action: ControlAction):
    """Pause current execution"""
    state = get_state()
    state["is_paused"] = True
    state["last_task_status"] = "paused"
    save_state(state)

    # Log action
    _log_action("pause", action.reason)

    return {"status": "paused", "message": "Execution paused"}


@router.post("/control/resume")
async def resume_execution(action: ControlAction):
    """Resume paused execution"""
    state = get_state()
    state["is_paused"] = False
    state["last_task_status"] = "in_progress"
    save_state(state)

    _log_action("resume", action.reason)

    return {"status": "resumed", "message": "Execution resumed"}


@router.post("/control/approve")
async def approve_task(action: ControlAction):
    """Approve current task/stage"""
    state = get_state()
    state["last_task_status"] = "approved"
    save_state(state)

    _log_action("approve", action.reason)

    return {"status": "approved", "message": "Task approved"}


@router.post("/control/reject")
async def reject_task(action: ControlAction):
    """Reject current task/stage"""
    state = get_state()
    state["last_task_status"] = "rejected"
    save_state(state)

    _log_action("reject", action.reason)

    return {"status": "rejected", "message": "Task rejected"}


def _log_action(action_type: str, reason: Optional[str]) -> None:
    """Log control action to file"""
    log_file = PROGRESS_PATH / "actions.log"
    log_entry = f"{datetime.now().isoformat()} | {action_type.upper()}"
    if reason:
        log_entry += f" | {reason}"
    log_entry += "\n"

    with open(log_file, "a") as f:
        f.write(log_entry)


def record_file_change(path: str, action: str) -> None:
    """Record a file change (called by other parts of the system)"""
    changes_file = PROGRESS_PATH / "changes.json"
    changes = []
    if changes_file.exists():
        try:
            changes = json.loads(changes_file.read_text())
        except:
            pass

    changes.append({
        "path": path,
        "action": action,
        "timestamp": datetime.now().isoformat()
    })

    # Keep only last 100 changes
    changes = changes[-100:]

    PROGRESS_PATH.mkdir(parents=True, exist_ok=True)
    changes_file.write_text(json.dumps(changes, indent=2, ensure_ascii=False))


def update_task_status(task_id: str, description: str, status: str, result: Optional[str] = None) -> None:
    """Update last task information (called by orchestrator)"""
    task_file = PROGRESS_PATH / "last_task.json"
    task_info = {
        "task_id": task_id,
        "description": description,
        "status": status,
        "started_at": datetime.now().isoformat() if status == "started" else None,
        "completed_at": datetime.now().isoformat() if status in ["completed", "failed"] else None,
        "result": result
    }

    # Preserve started_at if updating existing task
    if task_file.exists():
        try:
            existing = json.loads(task_file.read_text())
            if existing.get("task_id") == task_id and existing.get("started_at"):
                task_info["started_at"] = existing["started_at"]
        except:
            pass

    PROGRESS_PATH.mkdir(parents=True, exist_ok=True)
    task_file.write_text(json.dumps(task_info, indent=2, ensure_ascii=False))
