"""
Jobs API — task submission and status endpoints.

Endpoints:
  GET  /api/health                  — liveness check
  POST /api/chat-start              — enqueue a new chat/task job
  GET  /api/job-status/{job_id}     — status for a specific job
  GET  /api/active-job              — currently active job (if any)
  GET  /api/queue-status            — overall queue statistics
  GET  /api/files-changed           — files changed by the most recent finished job
  GET  /api/blocked-tasks           — jobs that ended in FAILED/blocked state
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

from app.services.job_queue import (
    create_job,
    get_job,
    get_active_job,
    get_queue_status,
    list_jobs,
    start_job_execution,
    JobStatus,
)
from app.runtime_freshness import compute_backend_code_stamp

router = APIRouter(prefix="/api", tags=["Jobs"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_STARTED_AT = datetime.now(timezone.utc).isoformat()
RUNTIME_CODE_STAMP = compute_backend_code_stamp(PROJECT_ROOT)


def _redis_health_payload() -> dict[str, str]:
    try:
        from redis import Redis  # type: ignore[import]
        from app.core.config import settings

        redis_conn = Redis.from_url(settings.REDIS_URL)
        redis_conn.ping()
        return {"status": "healthy", "redis": "ok"}
    except Exception as exc:
        return {
            "status": "degraded",
            "redis": "error",
            "redis_error": str(exc),
        }


def _normalize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(job)
    status_value = normalized.get("status")
    if hasattr(status_value, "value"):
        normalized["status"] = status_value.value
    elif status_value is not None:
        normalized["status"] = str(status_value)
    return normalized


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", tags=["Health"])
async def api_health():
    """API-prefixed liveness check."""
    from app.core.config import settings
    payload = _redis_health_payload()
    payload.update({
        "version": settings.VERSION,
        "service": settings.PROJECT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runtime_started_at": RUNTIME_STARTED_AT,
        "runtime_code_stamp": RUNTIME_CODE_STAMP,
    })
    return payload


# ---------------------------------------------------------------------------
# Job submission
# ---------------------------------------------------------------------------

@router.post("/chat-start")
async def chat_start(payload: Dict[str, Any]):
    """
    Enqueue a new job.

    Body fields:
      prompt        (str, required) — task description
      task_type     (str)           — "chat" | "file" | "general" (default: "chat")
      metadata      (dict)          — passed through to executor
    """
    prompt = payload.get("prompt") or payload.get("message") or payload.get("task")
    if not prompt:
        raise HTTPException(status_code=422, detail="'prompt' field is required")

    task_type = payload.get("task_type", "chat")
    metadata = payload.get("metadata") or {}

    job_id = create_job(task_type=task_type, prompt=prompt, metadata=metadata)
    start_job_execution(job_id)

    return {
        "ok": True,
        "job_id": job_id,
        "status": "queued",
    }


# ---------------------------------------------------------------------------
# Job status / queries
# ---------------------------------------------------------------------------

@router.get("/job-status/{job_id}")
async def job_status(job_id: str):
    """Return full state for a single job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return {"ok": True, "job": _normalize_job(job)}


@router.get("/active-job")
async def active_job():
    """Return the currently running/queued job, or null."""
    job = get_active_job()
    return {"ok": True, "job": job, "has_active": job is not None}


@router.get("/queue-status")
async def queue_status():
    """Return queue statistics (counts + active job snapshot)."""
    status = get_queue_status()
    return {"ok": True, **status}


@router.get("/files-changed")
async def files_changed(limit: int = 20):
    """Return files changed by the most recently finished job."""
    jobs = list_jobs(limit)
    finished = [j for j in jobs if j.get("status") == JobStatus.FINISHED.value]
    if not finished:
        return {"ok": True, "files_changed": [], "job_id": None}

    latest = finished[0]
    return {
        "ok": True,
        "job_id": latest.get("job_id"),
        "files_changed": latest.get("files_changed", []),
    }


@router.get("/blocked-tasks")
async def blocked_tasks(limit: int = 50):
    """Return jobs that ended in a failed/blocked state."""
    jobs = list_jobs(limit)
    blocked = [j for j in jobs if j.get("status") == JobStatus.FAILED.value]
    return {
        "ok": True,
        "blocked_tasks": blocked,
        "count": len(blocked),
    }
