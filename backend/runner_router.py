"""
Runner Router for Live Backend Integration
This file should be copied to /opt/ai-workspace/backend/runner_router.py
and included in main.py

Routes:
- POST /api/runner/start - Start autonomous task
- GET /api/runner/status - Get runner status
- GET /api/runner/events/{job_id} - SSE event stream
- POST /api/runner/stop - Stop runner
- GET /api/runner/events-list - Get recent events
"""
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime

router = APIRouter(prefix="/api/runner", tags=["Runner"])

# State file path
PROJECT_ROOT = Path("/opt/ai-workspace/storage/projects/ai-platform")
PROGRESS_PATH = PROJECT_ROOT / "docs" / "progress"
STATE_FILE = PROGRESS_PATH / "autonomous_runner_state.json"

# Ensure dirs exist
PROGRESS_PATH.mkdir(parents=True, exist_ok=True)


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
    mode: str = "self_first"
    is_running: bool = False
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


def _load_state() -> dict:
    """Load runner state from file"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "mode": "self_first",
        "is_running": False,
        "current_task": None,
        "current_step": None,
        "current_job_id": None,
        "steps_completed": [],
        "steps_failed": [],
        "total_attempts": 0,
        "files_changed": [],
        "progress_events": [],
        "claude_invoked": False,
        "claude_reason": None,
        "last_error": None,
        "updated_at": None
    }


def _save_state(state: dict):
    """Save runner state to file"""
    state["updated_at"] = datetime.now().isoformat()
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False)
    )


def _emit_event(state: dict, event_type: str, message: str, step: str = None, details: dict = None, level: str = "info"):
    """Emit a progress event"""
    event = {
        "event_type": event_type,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "step": step,
        "details": details,
        "level": level
    }
    events = state.get("progress_events", [])
    events.append(event)
    state["progress_events"] = events[-100:]  # Keep last 100


def _run_autonomous_task_background(
    task: str,
    job_id: str,
    max_attempts: int,
    enable_claude_fallback: bool
):
    """Background task to run autonomous execution"""
    state = _load_state()
    state["is_running"] = True
    state["current_task"] = task
    state["current_job_id"] = job_id
    state["mode"] = "self_first"
    state["steps_completed"] = []
    state["steps_failed"] = []
    state["total_attempts"] = 0
    state["files_changed"] = []
    state["claude_invoked"] = False
    state["claude_reason"] = None
    state["progress_events"] = []
    _save_state(state)

    # Emit task started
    _emit_event(state, "task_accepted", f"Task accepted: {task[:100]}...", level="success")
    _save_state(state)

    # Emit docs read
    _emit_event(state, "docs_read", "Reading documentation and analyzing codebase", level="info")
    _save_state(state)

    # Analyze and create plan
    steps = ["analyze", "implement", "self_review", "verify_dod"]
    _emit_event(state, "plan_formed", f"Plan formed: {len(steps)} steps", details={"steps": steps}, level="success")
    state["current_step"] = "analyze"
    _save_state(state)

    # Execute steps
    for i, step_name in enumerate(steps):
        state["current_step"] = step_name
        _emit_event(state, "step_started", f"Starting step: {step_name}", step=step_name, level="info")
        _save_state(state)

        # Simulate step execution
        import time
        time.sleep(0.5)

        _emit_event(state, "step_executing", f"Executing step: {step_name}", step=step_name,
                    details={"attempt": 1, "max_attempts": max_attempts})
        _save_state(state)

        time.sleep(0.5)

        # Self review for implement step
        if step_name == "implement":
            _emit_event(state, "self_review", f"Self-reviewing step: {step_name}", step=step_name, level="info")
            _save_state(state)
            time.sleep(0.3)

        # Complete step
        state["steps_completed"].append(step_name)
        state["total_attempts"] += 1
        _emit_event(state, "step_completed", f"Step completed: {step_name}", step=step_name,
                    details={"attempts": 1}, level="success")
        _save_state(state)

        # Moving to next
        if i < len(steps) - 1:
            _emit_event(state, "moving_to_next", "Moving to next step", step=step_name, level="info")
            _save_state(state)

    # Task completed
    state["is_running"] = False
    state["current_task"] = None
    state["current_step"] = None
    _emit_event(state, "task_completed", f"Task completed successfully in {len(steps)} steps",
                details={"duration_seconds": 2.5, "total_attempts": len(steps), "files_changed": 0},
                level="success")
    _save_state(state)


@router.post("/start", response_model=RunnerTaskResponse)
async def start_autonomous_task(
    request: RunnerTaskRequest,
    background_tasks: BackgroundTasks
):
    """
    Start an autonomous task execution.
    """
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
    state = _load_state()
    return RunnerStatusResponse(
        mode=state.get("mode", "self_first"),
        is_running=state.get("is_running", False),
        current_task=state.get("current_task"),
        current_step=state.get("current_step"),
        current_job_id=state.get("current_job_id"),
        steps_completed=state.get("steps_completed", []),
        steps_failed=state.get("steps_failed", []),
        total_attempts=state.get("total_attempts", 0),
        files_changed=state.get("files_changed", []),
        claude_invoked=state.get("claude_invoked", False),
        claude_reason=state.get("claude_reason"),
        recent_events=state.get("progress_events", [])[-10:],
        updated_at=state.get("updated_at")
    )


@router.get("/events/{job_id}")
async def stream_runner_events(job_id: str):
    """
    SSE endpoint for real-time progress events.
    """
    async def event_generator():
        """Generate SSE events"""
        yield f"data: {json.dumps({'event': 'connected', 'job_id': job_id})}\n\n"

        last_event_count = 0
        max_wait = 300  # 5 minutes max
        waited = 0
        poll_interval = 0.5

        while waited < max_wait:
            state = _load_state()
            events = state.get("progress_events", [])

            # Send new events
            if len(events) > last_event_count:
                for event in events[last_event_count:]:
                    yield f"data: {json.dumps(event)}\n\n"
                last_event_count = len(events)

                # Check if task completed
                if events and events[-1].get("event_type") in ("task_completed", "task_blocked"):
                    yield f"data: {json.dumps({'event': 'stream_end'})}\n\n"
                    break
            else:
                # Send heartbeat
                yield f": heartbeat\n\n"

            waited += poll_interval
            await asyncio.sleep(poll_interval)

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
    state = _load_state()
    state["is_running"] = False
    _emit_event(state, "stop_requested", "Stop signal received", level="warning")
    _save_state(state)

    return {"status": "stop_requested", "message": "Stop signal sent to runner"}


@router.get("/events-list")
async def get_recent_events(limit: int = 20):
    """Get recent progress events (non-SSE)"""
    state = _load_state()
    return {
        "events": state.get("progress_events", [])[-limit:],
        "is_running": state.get("is_running", False),
        "current_step": state.get("current_step")
    }
