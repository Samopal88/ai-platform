"""
AI Workspace Platform - Autonomous Runner API
Endpoints for autonomous build runner with progress events

Features:
- Start autonomous task execution
- Get runner status
- SSE endpoint for real-time progress events
- Dashboard shows live status
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import asyncio
from app.core.config import settings

router = APIRouter(prefix="/api/runner", tags=["Runner"])


class RunnerTaskRequest(BaseModel):
    """Request to start an autonomous task"""
    task: str
    job_id: Optional[str] = None
    max_attempts: int = 2
    enable_claude_fallback: bool = True


class RunnerTaskResponse(BaseModel):
    """Response after starting a task"""
    job_id: str
    status: str
    message: str
    mode: str


class RunnerStatusResponse(BaseModel):
    """Runner status response"""
    mode: str
    is_running: bool
    current_task: Optional[str] = None
    current_step: Optional[str] = None
    current_job_id: Optional[str] = None
    steps_completed: List[str] = []
    steps_failed: List[str] = []
    total_attempts: int = 0
    files_changed: List[str] = []
    claude_invoked: bool = False
    claude_reason: Optional[str] = None
    recent_events: List[dict] = []
    updated_at: Optional[str] = None


def _run_autonomous_task_background(
    task: str,
    job_id: str,
    max_attempts: int,
    enable_claude_fallback: bool
):
    """Background task to run autonomous execution"""
    from app.services.autonomous_runner import AutonomousBuildRunner
    from pathlib import Path

    project_root = Path(settings.PROJECT_ROOT)
    runner = AutonomousBuildRunner(
        project_root=project_root,
        max_step_attempts=max_attempts,
        enable_claude_fallback=enable_claude_fallback
    )

    # Run the task
    result = runner.run_task(task, job_id)

    # Result is saved in state file
    return result


@router.post("/start", response_model=RunnerTaskResponse)
async def start_autonomous_task(
    request: RunnerTaskRequest,
    background_tasks: BackgroundTasks
):
    """
    Start an autonomous task execution.

    The runner will:
    1. Accept the task
    2. Read docs and analyze
    3. Form a plan
    4. Execute steps with self-review
    5. Retry if needed
    6. Use Claude fallback if self-mode fails
    7. Continue until completion or blocking

    No user confirmations needed for normal steps.
    """
    import time

    job_id = request.job_id or f"auto-{int(time.time())}"

    # Start in background
    background_tasks.add_task(
        _run_autonomous_task_background,
        task=request.task,
        job_id=job_id,
        max_attempts=request.max_attempts,
        enable_claude_fallback=request.enable_claude_fallback
    )

    return RunnerTaskResponse(
        job_id=job_id,
        status="started",
        message=f"Autonomous task started. Poll /api/runner/status or use /api/runner/events/{job_id} for SSE updates.",
        mode="self_first"
    )


@router.get("/status", response_model=RunnerStatusResponse)
async def get_runner_status():
    """Get current autonomous runner status"""
    from app.services.autonomous_runner import get_runner_status

    status = get_runner_status()
    return RunnerStatusResponse(**status)


@router.get("/events/{job_id}")
async def stream_runner_events(job_id: str):
    """
    SSE endpoint for real-time progress events.

    Connect with EventSource:
    ```javascript
    const events = new EventSource('/api/runner/events/' + jobId);
    events.onmessage = (e) => console.log(JSON.parse(e.data));
    ```
    """
    from app.services.autonomous_runner import get_runner
    from pathlib import Path

    project_root = Path(settings.PROJECT_ROOT)
    runner = get_runner(project_root)

    async def event_generator():
        """Generate SSE events"""
        yield f"data: {json.dumps({'event': 'connected', 'job_id': job_id})}\n\n"

        # Poll for events
        max_wait = 300  # 5 minutes max
        waited = 0
        poll_interval = 0.5

        while waited < max_wait:
            event = runner.get_events(timeout=poll_interval)
            if event:
                yield f"data: {json.dumps(event.to_dict())}\n\n"

                # Check if task completed
                if event.event_type in ('task_completed', 'task_blocked'):
                    yield f"data: {json.dumps({'event': 'stream_end'})}\n\n"
                    break
            else:
                # Send heartbeat
                yield f": heartbeat\n\n"

            waited += poll_interval
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/stop")
async def stop_runner():
    """Stop current autonomous execution"""
    from app.services.autonomous_runner import get_runner
    from pathlib import Path

    project_root = Path(settings.PROJECT_ROOT)
    runner = get_runner(project_root)
    runner.stop()

    return {"status": "stop_requested", "message": "Stop signal sent to runner"}


@router.get("/events-list")
async def get_recent_events(limit: int = 20):
    """Get recent progress events (non-SSE)"""
    from app.services.autonomous_runner import get_runner_status

    status = get_runner_status()
    return {
        "events": status.get("recent_events", [])[-limit:],
        "is_running": status.get("is_running", False),
        "current_step": status.get("current_step")
    }
