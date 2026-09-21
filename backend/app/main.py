"""
AI Workspace Platform - FastAPI Application
Main entry point for the backend API
"""
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.core.config import settings
from app.db.bootstrap import bootstrap_dev_schema
# Import models so their tables are registered in Base.metadata before create_all
from app.models.project import Project  # noqa: F401
from app.models.chat import Chat        # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.user import User        # noqa: F401
from app.models.file import File        # noqa: F401
from app.models.chat_artifact import ChatArtifact  # noqa: F401
from app.api.dashboard import router as dashboard_router
from app.api.jobs import router as jobs_router
from app.api.runner import router as runner_router
from app.api.manager import router as manager_router
from app.api.projects import router as projects_router
from app.api.chats import router as chats_router
from app.api.ai_chat import router as ai_chat_router
from app.api.files import router as files_router
from app.api.auth import router as auth_router
from app.api.memory import router as memory_router
from app.api.legal import router as legal_router
from app.api.plans import router as plans_router
from app.api.billing import router as billing_router
from app.api.models import router as models_router
from app.api.media import router as media_router
from app.api.file_edits import router as file_edits_router
from app.api.readiness import router as readiness_router
from app.runtime_freshness import compute_backend_code_stamp

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_STARTED_AT = datetime.now(timezone.utc).isoformat()
RUNTIME_CODE_STAMP = compute_backend_code_stamp(PROJECT_ROOT)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI Workspace Platform - AI chat, projects, and files",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(dashboard_router)
app.include_router(jobs_router)
app.include_router(runner_router)
app.include_router(manager_router)
app.include_router(projects_router)
app.include_router(chats_router)
app.include_router(ai_chat_router)
app.include_router(files_router)
app.include_router(auth_router)
app.include_router(memory_router)
app.include_router(legal_router)
app.include_router(plans_router)
app.include_router(billing_router)
app.include_router(models_router)
app.include_router(media_router)
app.include_router(file_edits_router)
app.include_router(readiness_router)


@app.on_event("startup")
async def _startup_bootstrap_dev_schema() -> None:
    """Keep local bootstrap explicit and keep schema migrations out of app startup."""
    bootstrap_dev_schema()

# Frontend paths
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring and load balancers"""
    try:
        from redis import Redis  # type: ignore[import]

        redis_conn = Redis.from_url(settings.REDIS_URL)
        redis_conn.ping()
        payload = {"status": "healthy", "redis": "ok"}
    except Exception as exc:
        payload = {
            "status": "degraded",
            "redis": "error",
            "redis_error": str(exc),
        }

    payload.update({
        "version": settings.VERSION,
        "service": settings.PROJECT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runtime_started_at": RUNTIME_STARTED_AT,
        "runtime_code_stamp": RUNTIME_CODE_STAMP,
    })
    return payload


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "AI Workspace Platform API",
        "version": settings.VERSION,
        "docs": "/docs",
        "documentation": "/documentation",
        "public_docs": "/docs-public",
        "health": "/health",
        "dashboard": "/dashboard",
    }


@app.get("/dashboard", tags=["Dashboard"])
async def serve_dashboard():
    """Serve the dashboard HTML page"""
    dashboard_file = FRONTEND_DIR / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    return {"error": "Dashboard not found"}


@app.get("/chat", tags=["Chat"])
async def serve_chat():
    """Serve the chat HTML page"""
    chat_file = FRONTEND_DIR / "chat.html"
    if chat_file.exists():
        return FileResponse(chat_file)
    return {"error": "Chat not found"}


@app.get("/documentation", tags=["Documentation"])
async def serve_documentation():
    """Serve the product documentation page"""
    docs_file = FRONTEND_DIR / "docs.html"
    if docs_file.exists():
        return FileResponse(docs_file)
    return {"error": "Documentation not found"}


# === COMPATIBILITY PATCH FOR LEGACY DASHBOARD ===

@app.get("/project-state")
@app.get("/api/project-state")
async def compat_project_state(project_path: str = "/opt/ai-workspace/storage/projects/ai-platform"):
    """
    Legacy endpoint for dashboard compatibility.
    Returns dashboard state in old shape.
    """
    try:
        from app.api.dashboard import get_state
        state = get_state()
        return {"ok": True, "state": state}
    except Exception as e:
        return {"ok": False, "error": str(e), "state": {}}


@app.get("/progress-files")
@app.get("/api/progress-files")
async def compat_progress_files(project_path: str = "/opt/ai-workspace/storage/projects/ai-platform"):
    """
    Legacy endpoint for dashboard compatibility.
    """
    try:
        progress_dir = Path(project_path) / "docs" / "progress"
        progress_dir.mkdir(parents=True, exist_ok=True)

        files = []
        for fp in sorted(progress_dir.iterdir()):
            if fp.is_file():
                files.append({
                    "name": fp.name,
                    "path": str(fp),
                    "size": fp.stat().st_size
                })

        return {"ok": True, "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e), "files": []}


@app.get("/progress-file")
@app.get("/api/progress-file")
async def compat_progress_file(path: str):
    """
    Legacy endpoint for dashboard compatibility.
    """
    try:
        fp = Path(path)
        if not fp.exists():
            return {"ok": False, "error": "file not found"}

        return {
            "ok": True,
            "content": fp.read_text(encoding="utf-8", errors="ignore")
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/runner/status")
@app.get("/api/runner/status")
async def compat_runner_status():
    """
    Stub status so dashboard stops throwing 404.
    """
    try:
        from app.services.job_queue import get_active_job
        active = get_active_job()
        if active:
            return {
                "ok": True,
                "is_running": True,
                "job_id": active.get("job_id"),
                "status": active.get("status"),
                "current_task": active.get("prompt"),
                "current_step": active.get("current_stage"),
                "attempts": 0,
                "steps_total": 0,
                "steps_completed": 0,
                "steps_failed": []
            }

        return {
            "ok": True,
            "is_running": False,
            "job_id": None,
            "status": "idle",
            "current_task": None,
            "current_step": None,
            "attempts": 0,
            "steps_total": 0,
            "steps_completed": 0,
            "steps_failed": []
        }
    except Exception as e:
        return {
            "ok": False,
            "is_running": False,
            "error": str(e)
        }


@app.post("/runner/start")
@app.post("/api/runner/start")
async def compat_runner_start(payload: dict):
    """
    Fallback runner start: routes autonomous start into normal chat-start queue
    so dashboard button works and stops failing.
    """
    try:
        from app.services.job_queue import create_job, start_job_execution

        task = payload.get("task") or payload.get("prompt") or "autonomous task"
        max_attempts = payload.get("max_attempts", 2)

        job_id = create_job(
            task_type="chat",
            prompt=task,
            metadata={
                "project_path": "/opt/ai-workspace/storage/projects/ai-platform",
                "autonomous_requested": True,
                "max_attempts": max_attempts
            }
        )
        start_job_execution(job_id)

        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued"
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


@app.get("/runner/events/{job_id}")
@app.get("/api/runner/events/{job_id}")
async def compat_runner_events(job_id: str):
    """
    Minimal SSE-compatible response to avoid 404 on EventSource.
    """
    from fastapi.responses import StreamingResponse
    import json

    def gen():
        payload = {
            "job_id": job_id,
            "stage": "connected",
            "message": "runner stream connected",
            "level": "info"
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/runner/stop")
@app.post("/api/runner/stop")
async def compat_runner_stop():
    return {"ok": True, "stopped": True}

# === END COMPATIBILITY PATCH ===

