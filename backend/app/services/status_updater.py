"""
AI Workspace Platform - Status Updater Service
Auto-updates docs/progress/CURRENT_STATUS.md based on job completion
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from app.core.config import settings

PROJECT_ROOT = Path(settings.PROJECT_ROOT)
PROGRESS_PATH = PROJECT_ROOT / "docs" / "progress"

STATUS_FILE = PROGRESS_PATH / "CURRENT_STATUS.md"
STATE_FILE = PROGRESS_PATH / "state.json"
SUPERVISOR_STATE_FILE = PROGRESS_PATH / "supervisor_state.json"
LOOP_STATE_FILE = PROGRESS_PATH / "loop_state.json"
ORCHESTRATOR_STATE_FILE = PROGRESS_PATH / "orchestrator_state.json"


def _read_json(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_state() -> Dict[str, Any]:
    return _read_json(STATE_FILE)


def get_supervisor_state() -> Dict[str, Any]:
    return _read_json(SUPERVISOR_STATE_FILE)


def get_loop_state() -> Dict[str, Any]:
    return _read_json(LOOP_STATE_FILE)


def get_orchestrator_state() -> Dict[str, Any]:
    return _read_json(ORCHESTRATOR_STATE_FILE)


def get_jobs_status() -> Dict[str, Any]:
    """Get real job queue status from actual job files."""
    jobs_path = PROJECT_ROOT / "storage" / "jobs"
    jobs = []

    if jobs_path.exists():
        for job_file in sorted(jobs_path.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                jobs.append(json.loads(job_file.read_text(encoding="utf-8")))
            except Exception:
                pass

    queued = [j for j in jobs if j.get("status") == "queued"]
    running = [j for j in jobs if j.get("status") in ("started", "in_progress")]
    finished = [j for j in jobs if j.get("status") == "finished"]
    failed = [j for j in jobs if j.get("status") in ("failed", "cancelled")]

    recent_jobs = []
    for job in jobs[:5]:
        recent_jobs.append({
            "job_id": job.get("job_id"),
            "status": job.get("status", "unknown"),
            "task_type": job.get("task_type"),
            "created_at": job.get("created_at"),
            "current_stage": job.get("current_stage", "")
        })

    active_job = next(
        (j for j in jobs if j.get("status") in ("queued", "started", "in_progress")),
        None
    )

    return {
        "total": len(jobs),
        "queued": len(queued),
        "running": len(running),
        "finished": len(finished),
        "failed": len(failed),
        "recent": recent_jobs,
        "active_job": active_job,
        "has_running_jobs": (len(queued) + len(running)) > 0,
    }


def generate_status_report() -> str:
    state = get_state()
    return f"""## Quick Status Report

**Stage:** {state.get('current_stage', 'unknown')}
**Mode:** {state.get('mode', 'self')}
**Last Job:** {state.get('last_job_id', 'none')}
**Active Task:** {state.get('active_task', 'none')}
**Last Completed:** {state.get('last_completed_task', 'none')}
**Files Changed:** {len(state.get('last_changed_files', []))}
**Paused:** {'Yes' if state.get('is_paused') else 'No'}
**Error:** {state.get('error', 'none')}
**Updated:** {state.get('updated_at', 'unknown')}
"""


def generate_full_status() -> str:
    state = get_state()
    supervisor = get_supervisor_state()
    loop_state = get_loop_state()
    orchestrator = get_orchestrator_state()
    jobs = get_jobs_status()

    doc = """# CURRENT_STATUS
## AI Workspace Platform — Real-time Development Status

---
"""

    doc += "\n## Current Stage\n"
    doc += f"**Stage:** {state.get('current_stage', 'unknown')}\n"
    doc += f"**Last Job:** {state.get('last_job_id', 'none')} ({state.get('last_task_status', 'unknown')})\n"
    doc += f"**Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

    doc += "\n---\n\n## Orchestrator Status\n"
    orch_status = orchestrator.get("status", "idle")
    doc += f"**Status:** {orch_status}\n"

    reviews = orchestrator.get("reviews", [])
    if reviews:
        last_review = reviews[-1]
        doc += "\n**Last Review:**\n"
        doc += f"- Passed: {'Yes' if last_review.get('passed') else 'No'}\n"
        doc += f"- Severity: {last_review.get('severity', 'unknown')}\n"

    doc += "\n---\n\n## Active Task\n"

    active_task = state.get("active_task")
    orchestrator_task = orchestrator.get("current_task")
    supervisor_task = supervisor.get("active_task")
    loop_task = loop_state.get("current_task")
    has_running_jobs = jobs.get("has_running_jobs", False)

    if orchestrator_task and has_running_jobs:
        doc += f"**Task (Orchestrator):** {orchestrator_task}\n"
        doc += f"- Status: {orch_status}\n"
        doc += f"- Attempts: {orchestrator.get('attempts', 0)}\n"
    elif active_task and has_running_jobs:
        doc += f"**Task:** {active_task}\n"
    elif supervisor_task and has_running_jobs:
        doc += f"**Task (Supervisor):** {supervisor_task}\n"
    elif loop_task and loop_state.get("is_running"):
        doc += f"**Task (Loop):** {loop_task}\n"
    else:
        doc += "**Status:** No jobs currently active\n"
        doc += "**Phase:** Idle\n"
        doc += f"**Last Completed:** {state.get('last_completed_task', 'none')}\n"

    if loop_state.get("is_running"):
        doc += "\n**Autonomous Loop:**\n"
        doc += f"- Step: {loop_state.get('current_step', 'unknown')}\n"
        doc += f"- Iteration: {loop_state.get('iteration', 0)}\n"

    if supervisor.get("active_task") and not orchestrator_task and has_running_jobs:
        doc += "\n**Supervisor:**\n"
        doc += f"- Attempts: {len(supervisor.get('attempts', []))}\n"

    doc += "\n---\n\n## Job Queue Status\n"
    doc += f"- **Queued:** {jobs['queued']}\n"
    doc += f"- **Running:** {jobs['running']}\n"
    doc += f"- **Finished:** {jobs['finished']}\n"
    doc += f"- **Failed:** {jobs['failed']}\n"
    doc += f"- **Total:** {jobs['total']}\n"

    if not jobs["has_running_jobs"]:
        doc += "\n*No jobs currently active*\n"

    if jobs.get("recent"):
        doc += "\n**Recent Jobs:**\n"
        for job in jobs["recent"][:3]:
            doc += f"- `{job['job_id']}` ({job['status']}) - {job['task_type']}\n"

    doc += "\n---\n\n## Completed\n"

    orch_completed = orchestrator.get("completed_tasks", [])[-3:]
    if orch_completed:
        doc += "**Recently Completed (Orchestrator):**\n"
        for item in orch_completed:
            doc += f"- [x] {item.get('task_id', 'Unknown')} ({item.get('attempts', '?')} attempts, {item.get('duration_seconds', 0):.1f}s)\n"

    history = state.get("history", [])
    completed = [h for h in history if h.get("status") == "finished"][-5:]
    if completed:
        doc += "\n**From History:**\n"
        for item in completed:
            doc += f"- [x] {item.get('task', 'Unknown')}\n"

    supervisor_completed = supervisor.get("completed_tasks", [])[-3:]
    if supervisor_completed:
        doc += "\n**Verified Complete:**\n"
        for item in supervisor_completed:
            doc += f"- [x] {item.get('task_id', 'Unknown')}\n"

    if not orch_completed and not completed and not supervisor_completed:
        doc += "No completed tasks in current session\n"

    doc += "\n---\n\n## In Review / Retry\n"
    blocked = supervisor.get("blocked_tasks", [])
    if reviews and orch_status in ("reviewing", "retrying", "step_reviewing"):
        doc += f"Orchestrator is in review state: {orch_status}\n"
    else:
        doc += "Nothing in review\n"

    doc += "\n---\n\n## Blocked\n"
    if blocked:
        for item in blocked[-5:]:
            doc += f"- {item.get('task_id', 'unknown')}: {item.get('reason', 'unknown')}\n"
    else:
        doc += "Nothing blocked\n"

    doc += "\n---\n\n## Files Changed (This Session)\n"

    # Populate from the most recently finished job's files_changed list
    jobs_path = PROJECT_ROOT / "storage" / "jobs"
    session_files: list = state.get("last_changed_files", [])
    if not session_files and jobs_path.exists():
        finished_jobs = sorted(
            [j for j in jobs_path.glob("*.json")],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for jf in finished_jobs[:5]:
            try:
                jdata = json.loads(jf.read_text(encoding="utf-8"))
                if jdata.get("status") == "finished" and jdata.get("files_changed"):
                    session_files = jdata["files_changed"]
                    break
            except Exception:
                pass

    if session_files:
        for f in session_files:
            doc += f"- `{f}`\n"
    else:
        doc += "_No file changes recorded yet_\n"

    doc += "\n---\n\n## Next Steps\n"
    if jobs["has_running_jobs"]:
        doc += "1. Wait for current task to complete\n"
    else:
        doc += "1. Start new task with `/api/orchestrate` (recommended)\n"
        doc += "2. Or use `/api/chat-start` for simple execution\n"

    # Recent jobs table
    jobs_path = PROJECT_ROOT / "storage" / "jobs"
    if jobs_path.exists():
        recent = sorted(
            jobs_path.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True
        )[:5]
        if recent:
            doc += "\n---\n\n## Recent Jobs\n"
            doc += "| job_id | status | task | files |\n"
            doc += "|--------|--------|------|-------|\n"
            for jf in recent:
                try:
                    jdata = json.loads(jf.read_text(encoding="utf-8"))
                    jid = jdata.get("job_id", "?")[:12]
                    jstatus = jdata.get("status", "?")
                    jtask = (jdata.get("prompt") or "")[:40].replace("|", "/")
                    jfiles = len(jdata.get("files_changed") or [])
                    doc += f"| `{jid}` | {jstatus} | {jtask} | {jfiles} |\n"
                except Exception:
                    pass

    doc += f"\n---\n\n## Last Updated\n{datetime.now().isoformat()}\n"

    # Manager loop state
    try:
        from app.services.manager_loop import get_manager_state
        ms = get_manager_state()
        ms_status = ms.get("status", "idle")
        doc += "\n---\n\n## Manager Loop\n"
        doc += f"**Status:** {ms_status}\n"
        current_task = ms.get("current_task") or {}
        if current_task:
            doc += f"**Task:** {current_task.get('id')} — {current_task.get('title', '')}\n"
        review = ms.get("review")
        if review:
            doc += f"**Review verdict:** {review.get('verdict', '?')}\n"
            if review.get("issues"):
                doc += f"**Issues:** {'; '.join(review['issues'][:2])}\n"
        if ms.get("retry_count", 0) > 0:
            doc += f"**Retries:** {ms['retry_count']}/{ms.get('max_retries', 2)}\n"
        wr = ms.get("worker_result") or {}
        if wr.get("files_changed"):
            doc += f"**Files changed:** {', '.join(wr['files_changed'])}\n"
        if ms_status == "blocked":
            bt = (ms.get("blocked_tasks") or [{}])[-1]
            doc += f"**Blocked reason:** {bt.get('reason', '?')}\n"
    except Exception:
        pass

    # Next suggested task from roadmap
    try:
        from app.services.task_intake import choose_next_task, resolve_product_context
        next_task = choose_next_task()
        if next_task:
            ctx = resolve_product_context(next_task)
            doc += "\n---\n\n## Next Suggested Task\n"
            doc += f"- **ID:** {next_task['id']}\n"
            doc += f"- **Title:** {next_task['title']}\n"
            doc += f"- **Phase:** {next_task['phase']}\n"
            if next_task.get("files"):
                doc += f"- **Files:** {', '.join(next_task['files'])}\n"
            if ctx.get("product_docs"):
                doc += f"- **Product docs:** {', '.join(ctx['product_docs'])}\n"
    except Exception:
        pass
    return doc


def write_current_status(content: str) -> bool:
    PROGRESS_PATH.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(content, encoding="utf-8")
    return True


def sync_status_file() -> bool:
    content = generate_full_status()
    return write_current_status(content)


def update_status_on_job_complete(job_id: str, job_data: Dict[str, Any]) -> bool:
    return sync_status_file()
