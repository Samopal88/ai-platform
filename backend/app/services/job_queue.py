"""
AI Workspace Platform - Job Queue Service
File-based job queue for long-running tasks

Integrated with:
- ProjectState: Updates state.json on job lifecycle
- ClaudeExecutor: Executes tasks in self/claude mode
- CURRENT_STATUS.md: Auto-updates on job completion
"""
import os
import json
import uuid
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from enum import Enum
from app.core.config import settings


class JobStatus(str, Enum):
    QUEUED = "queued"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Storage paths
PROJECT_ROOT = Path(settings.PROJECT_ROOT)
JOBS_PATH = PROJECT_ROOT / "storage" / "jobs"
PROGRESS_PATH = PROJECT_ROOT / "docs" / "progress"


def _ensure_paths():
    """Ensure required directories exist"""
    JOBS_PATH.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.mkdir(parents=True, exist_ok=True)


def _get_job_file(job_id: str) -> Path:
    """Get path to job state file"""
    return JOBS_PATH / f"{job_id}.json"


def create_job(
    task_type: str,
    prompt: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a new job and add it to the queue.
    Returns job_id.
    """
    _ensure_paths()

    job_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()

    job_data = {
        "job_id": job_id,
        "task_type": task_type,
        "prompt": prompt,
        "status": JobStatus.QUEUED.value,
        "created_at": timestamp,
        "started_at": None,
        "finished_at": None,
        "current_stage": "Queued",
        "progress": [],
        "answer": None,
        "error": None,
        "files_changed": [],
        "metadata": metadata or {}
    }

    job_file = _get_job_file(job_id)
    job_file.write_text(json.dumps(job_data, indent=2, ensure_ascii=False))

    # Update state.json with new job info
    _update_project_state(job_id, "queued", f"New job: {task_type}")

    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job data by ID"""
    job_file = _get_job_file(job_id)
    if not job_file.exists():
        return None
    try:
        return json.loads(job_file.read_text())
    except Exception:
        return None


def update_job(
    job_id: str,
    status: Optional[JobStatus] = None,
    current_stage: Optional[str] = None,
    progress_entry: Optional[str] = None,
    answer: Optional[str] = None,
    error: Optional[str] = None,
    files_changed: Optional[list] = None
) -> bool:
    """Update job state"""
    job = get_job(job_id)
    if not job:
        return False

    timestamp = datetime.now().isoformat()

    if status:
        job["status"] = status.value
        if status == JobStatus.STARTED:
            job["started_at"] = timestamp
        elif status in (JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELLED):
            job["finished_at"] = timestamp

    if current_stage:
        job["current_stage"] = current_stage

    if progress_entry:
        job["progress"].append({
            "timestamp": timestamp,
            "message": progress_entry,
            "stage": current_stage or job.get("current_stage", "info")
        })

    if answer is not None:
        job["answer"] = answer

    if error is not None:
        job["error"] = error

    if files_changed:
        job["files_changed"].extend(files_changed)

    job_file = _get_job_file(job_id)
    job_file.write_text(json.dumps(job, indent=2, ensure_ascii=False))

    # Update project state
    _update_project_state(
        job_id,
        job["status"],
        current_stage or job.get("current_stage", "")
    )

    return True


def list_jobs(limit: int = 20) -> list:
    """List recent jobs"""
    _ensure_paths()
    jobs = []

    for job_file in sorted(JOBS_PATH.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]:
        try:
            jobs.append(json.loads(job_file.read_text()))
        except Exception:
            pass

    return jobs


def get_active_job() -> Optional[Dict[str, Any]]:
    """Get currently active job (queued/started/in_progress only)."""
    active_statuses = {
        JobStatus.QUEUED.value,
        JobStatus.STARTED.value,
        JobStatus.IN_PROGRESS.value,
    }

    for job in list_jobs(50):
        if job.get("status") in active_statuses:
            return job

    return None


def cancel_job(job_id: str) -> bool:
    """Cancel a job"""
    return update_job(job_id, status=JobStatus.CANCELLED, current_stage="Cancelled by user")


def _update_project_state(job_id: str, status: str, stage: str):
    """Update project state.json with job info"""
    state_file = PROGRESS_PATH / "state.json"
    state = {}

    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except Exception:
            pass

    current_job = get_job(job_id)

    state["current_job_id"] = job_id
    state["last_job_id"] = job_id
    state["last_task_status"] = status
    state["stage"] = stage
    state["current_stage"] = stage
    state["last_updated"] = datetime.now().isoformat()

    if current_job:
        job_status = current_job.get("status")
        is_active = job_status in (
            JobStatus.QUEUED.value,
            JobStatus.STARTED.value,
            JobStatus.IN_PROGRESS.value
        )
        is_finished = job_status in (
            JobStatus.FINISHED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value
        )

        if is_active:
            # Job is still running - set active_job_* fields
            state["active_task"] = current_job.get("prompt")
            state["active_job_id"] = current_job.get("job_id")
            state["active_job_status"] = job_status
            state["active_job_task"] = current_job.get("prompt")
        elif is_finished:
            # Job finished - clear active_job_* fields, set recent_job_*
            state["active_task"] = None
            state["active_job_id"] = None
            state["active_job_status"] = None
            state["active_job_task"] = None
            state["last_completed_task"] = current_job.get("prompt")
            state["last_finished_job_id"] = current_job.get("job_id")
            state["last_finished_at"] = current_job.get("finished_at")
            # Keep recently finished job visible for dashboard restore
            state["recent_job_id"] = current_job.get("job_id")
            state["recent_job_status"] = job_status
            state["recent_job_task"] = current_job.get("prompt")

    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _update_current_status_md(job_id: str, job_data: Dict[str, Any]):
    """Update CURRENT_STATUS.md with job completion info"""
    # Import here to avoid circular imports
    try:
        from app.services.status_updater import update_status_on_job_complete
        update_status_on_job_complete(job_id, job_data)
    except ImportError:
        # status_updater not yet created, skip
        pass


# Job execution (simulated for now, will be replaced with actual executor)
_job_thread: Optional[threading.Thread] = None


def _real_executor(job_id: str):
    """
    Real executor that uses Orchestrator with verification loop.
    Integrates with ProjectState and Supervisor for full task management.

    Supports autonomous runner mode when metadata.autonomous=True.
    """
    from app.services.orchestrator import get_orchestrator, OrchestratorStatus
    from app.services.project_state import (
        on_job_start, on_job_progress, on_job_finish, on_job_error
    )

    job = get_job(job_id)
    if not job:
        return

    prompt = job.get("prompt", "")
    task_type = job.get("task_type", "general")
    metadata = job.get("metadata", {})
    use_verification = metadata.get("use_verification", True)
    use_autonomous = metadata.get("autonomous", False)

    update_job(
        job_id,
        status=JobStatus.STARTED,
        current_stage="Starting execution",
        progress_entry="Task accepted"
    )

    update_job(
        job_id,
        status=JobStatus.IN_PROGRESS,
        current_stage="Analyzing task",
        progress_entry="Analyzing task"
    )

    try:
        if use_autonomous:
            # Use autonomous runner for fully autonomous execution
            from app.services.autonomous_runner import AutonomousBuildRunner

            runner = AutonomousBuildRunner(
                max_step_attempts=metadata.get("max_attempts", 2),
                enable_claude_fallback=metadata.get("enable_claude_fallback", True)
            )

            result = runner.run_task(prompt, job_id)

            if result.success:
                update_job(
                    job_id,
                    status=JobStatus.FINISHED,
                    current_stage="Completed",
                    answer=result.output,
                    files_changed=result.files_changed,
                    progress_entry=f"Autonomous task completed: {len(result.steps_completed)} steps, {result.total_attempts} attempts"
                )
                _update_current_status_md(job_id, get_job(job_id))
            else:
                update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    current_stage="Blocked",
                    error=result.error,
                    answer=result.output,
                    progress_entry=f"Autonomous task blocked: {result.error}"
                )

        else:
            # Use orchestrator for standard execution
            orchestrator = get_orchestrator()

            if use_verification:
                # Execute with full verification loop
                def progress_callback(message: str):
                    stage = str(message).strip()[:80] if message else "Working"
                    update_job(
                        job_id,
                        status=JobStatus.IN_PROGRESS,
                        current_stage=stage,
                        progress_entry=stage
                    )

                update_job(
                    job_id,
                    status=JobStatus.IN_PROGRESS,
                    current_stage="Running orchestrator",
                    progress_entry="Running orchestrator"
                )

                result = orchestrator.execute_task(
                    task_description=prompt,
                    job_id=job_id,
                    task_type=task_type,
                    max_attempts=3,
                    on_progress=progress_callback
                )
            else:
                # Simple execution without verification
                result = orchestrator.execute_task_simple(
                    task_description=prompt,
                    job_id=job_id
                )

            if result.success:
                update_job(
                    job_id,
                    status=JobStatus.FINISHED,
                    current_stage="Completed",
                    answer=result.output,
                    files_changed=result.files_changed,
                    progress_entry=f"Task completed after {result.attempts} attempt(s)"
                )
                update_job(
                    job_id,
                    current_stage="Result verified",
                    progress_entry="Result verified"
                )
                _update_current_status_md(job_id, get_job(job_id))

            elif result.status == OrchestratorStatus.BLOCKED:
                update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    current_stage="Blocked",
                    error=result.blocked_reason,
                    answer=result.output,
                    progress_entry=f"Task blocked after {result.attempts} attempts: {result.blocked_reason}"
                )

            else:
                update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    current_stage="Failed",
                    error=result.blocked_reason or "Unknown error",
                    progress_entry=f"Task failed: {result.blocked_reason}"
                )

    except Exception as e:
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        on_job_error(job_id, error_msg)
        update_job(
            job_id,
            status=JobStatus.FAILED,
            current_stage="Failed",
            error=error_msg,
            progress_entry=f"Execution error: {str(e)}"
        )


def start_job_execution(job_id: str, executor_func: Optional[Callable] = None):
    """Start executing a job in background thread"""
    global _job_thread

    def run_executor():
        try:
            # Use custom executor if provided, otherwise use real executor
            if executor_func:
                executor_func(job_id)
            else:
                _real_executor(job_id)
        except Exception as e:
            update_job(
                job_id,
                status=JobStatus.FAILED,
                current_stage="Failed",
                error=f"{str(e)}\n{traceback.format_exc()}"
            )

    _job_thread = threading.Thread(target=run_executor, daemon=True)
    _job_thread.start()


def get_queue_status() -> Dict[str, Any]:
    """Get overall queue status"""
    jobs = list_jobs(100)

    queued = len([j for j in jobs if j.get("status") == JobStatus.QUEUED.value])
    running = len([j for j in jobs if j.get("status") in (JobStatus.STARTED.value, JobStatus.IN_PROGRESS.value)])
    finished = len([j for j in jobs if j.get("status") == JobStatus.FINISHED.value])
    failed = len([j for j in jobs if j.get("status") == JobStatus.FAILED.value])

    active_job = get_active_job()

    return {
        "queued_count": queued,
        "running_count": running,
        "finished_count": finished,
        "failed_count": failed,
        "total_count": len(jobs),
        "active_job": active_job
    }
