from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import json
import uuid
from pathlib import Path
from redis import Redis
from rq import Queue
from rq.job import Job

from orchestrator_lib import (
    DEFAULT_MODEL,
    BASE_URL,
    PROJECT_ROOT,
    load_project_state,
    save_project_state,
    call_llm,
    execute_orchestrated_task,
    get_job_events,
    emit_job_event,
)

# Import runner router
from runner_router import router as runner_router

load_dotenv("/opt/ai-workspace/backend/.env")

app = FastAPI(title="AI Workspace Orchestrator")

# Include runner router
app.include_router(runner_router)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(REDIS_URL)
queue = Queue("aiworkspace", connection=redis_conn)


class ChatRequest(BaseModel):
    message: str
    model: str | None = None


class OrchestrateRequest(BaseModel):
    message: str
    project_path: str
    model: str | None = None


class ApproveRequest(BaseModel):
    project_path: str
    decision: str
    comment: str | None = None


class PauseRequest(BaseModel):
    project_path: str
    paused: bool


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "ai-workspace-orchestrator",
        "default_model": DEFAULT_MODEL,
        "base_url": BASE_URL
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    answer = call_llm(req.message, req.model)
    return {
        "ok": True,
        "model": req.model or DEFAULT_MODEL,
        "answer": answer
    }


@app.get("/project-state")
def project_state(project_path: str):
    state = load_project_state(project_path)
    return {"ok": True, "state": state}


@app.post("/approve")
def approve(req: ApproveRequest):
    state = load_project_state(req.project_path)
    state["history"].append({
        "role": "user",
        "type": "approval",
        "decision": req.decision,
        "comment": req.comment
    })
    state["pending_approval"] = None
    save_project_state(req.project_path, state)

    return {"ok": True, "message": f"Решение сохранено: {req.decision}"}


@app.post("/pause")
def pause(req: PauseRequest):
    state = load_project_state(req.project_path)
    state["paused"] = req.paused
    save_project_state(req.project_path, state)
    return {"ok": True, "paused": req.paused}


@app.post("/chat-orchestrate")
def chat_orchestrate(req: OrchestrateRequest):
    result = execute_orchestrated_task(req.project_path, req.message, req.model)
    return result


@app.post("/chat-start")
def chat_start(req: OrchestrateRequest):
    """Start a task with proper job_id tracking for progress events"""
    job_id = str(uuid.uuid4())

    # Emit initial event before queuing
    emit_job_event(job_id, "queued", "Задача поставлена в очередь", extra={"message_preview": req.message[:100]})

    job = queue.enqueue(
        execute_task_with_job_id,
        req.project_path,
        req.message,
        req.model,
        job_id,  # Pass our generated job_id
        job_id=job_id,  # Use the same ID for RQ
        job_timeout=3600,
        result_ttl=86400
    )
    return {
        "ok": True,
        "job_id": job.id,
        "status": "queued"
    }


def execute_task_with_job_id(project_path: str, message: str, model: str | None, rq_job_id: str):
    """Wrapper to pass RQ job_id to execute_orchestrated_task"""
    emit_job_event(rq_job_id, "started", "Задача запущена")
    return execute_orchestrated_task(project_path, message, model, rq_job_id=rq_job_id)


@app.post("/chat-start-tracked")
def chat_start_tracked(req: OrchestrateRequest):
    """Deprecated: use /chat-start instead"""
    return chat_start(req)


@app.get("/job-status/{job_id}")
def job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        return {"ok": False, "error": "job not found"}

    # Get progress events for this job
    events = get_job_events(job_id)

    payload = {
        "ok": True,
        "job_id": job.id,
        "status": job.get_status(),
        "progress": events,
    }

    if job.is_finished:
        payload["result"] = job.result
        # Also include answer/error from result if available
        if isinstance(job.result, dict):
            payload["answer"] = job.result.get("answer")
            payload["error"] = job.result.get("error")
            payload["mode"] = job.result.get("mode")
            payload["files_changed"] = job.result.get("files_changed", [])
    elif job.is_failed:
        payload["error"] = str(job.exc_info)
    else:
        payload["result"] = None

    return payload


@app.get("/job-events/{job_id}")
def job_events(job_id: str):
    """Get all progress events for a job"""
    events = get_job_events(job_id)
    return {
        "ok": True,
        "job_id": job_id,
        "events": events,
        "count": len(events)
    }


@app.get("/progress-files")
def progress_files(project_path: str):
    progress_dir = Path(project_path) / "docs" / "progress"
    progress_dir.mkdir(parents=True, exist_ok=True)

    files = []
    for p in sorted(progress_dir.glob("*.md")):
        files.append({
            "name": p.name,
            "path": str(p),
            "size": p.stat().st_size
        })

    return {"ok": True, "files": files}


@app.get("/progress-file")
def progress_file(path: str):
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "file not found"}
    return {"ok": True, "content": p.read_text(encoding="utf-8")}
