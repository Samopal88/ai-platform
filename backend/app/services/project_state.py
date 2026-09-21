"""
AI Workspace Platform - Project State Service
Manages project state.json for tracking development progress

State structure:
- current_stage: Current development stage
- active_task: Currently executing task
- last_completed_task: Last successfully completed task
- last_job_id: ID of the last job
- last_changed_files: List of recently changed files
- updated_at: Last update timestamp
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
from app.core.config import settings


class StageType(str, Enum):
    """Development stage types"""
    INIT = "init"
    PROJECT_STATE = "project_state"
    CLAUDE_EXECUTOR = "claude_executor"
    JOB_PIPELINE = "job_pipeline"
    STATUS_AUTO_UPDATE = "status_auto_update"
    DASHBOARD_SYNC = "dashboard_sync"
    DATABASE_LAYER = "database_layer"
    MULTI_PROJECT = "multi_project"
    AGENT_ARCHITECTURE = "agent_architecture"
    AUTONOMOUS_LOOP = "autonomous_loop"
    NIGHT_AUTOPILOT = "night_autopilot"
    COMPLETED = "completed"


class TaskStatus(str, Enum):
    """Task execution statuses"""
    PENDING = "pending"
    QUEUED = "queued"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    FAILED = "failed"
    BLOCKED = "blocked"


# Default project root
DEFAULT_PROJECT_ROOT = Path(settings.PROJECT_ROOT)


class ProjectState:
    """
    Manages project state for AI Workspace development.
    State is persisted to docs/progress/state.json
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or DEFAULT_PROJECT_ROOT
        self.state_file = self.project_root / "docs" / "progress" / "state.json"
        self._ensure_state_file()

    def _ensure_state_file(self):
        """Ensure state file and directory exist"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            self._write_state(self._default_state())

    def _default_state(self) -> Dict[str, Any]:
        """Default state structure"""
        return {
            "current_stage": StageType.INIT.value,
            "active_task": None,
            "last_completed_task": None,
            "last_job_id": None,
            "last_changed_files": [],
            "updated_at": datetime.now().isoformat(),
            "mode": "self",
            "is_paused": False,
            "error": None,
            "history": []
        }

    def _read_state(self) -> Dict[str, Any]:
        """Read current state from file"""
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text())
        except Exception:
            pass  # Non-critical, return default state
        return self._default_state()

    def _write_state(self, state: Dict[str, Any]) -> bool:
        """Write state to file"""
        try:
            state["updated_at"] = datetime.now().isoformat()
            self.state_file.write_text(
                json.dumps(state, indent=2, ensure_ascii=False)
            )
            return True
        except Exception:
            return False

    def get_state(self) -> Dict[str, Any]:
        """Get current state"""
        return self._read_state()

    def get_current_stage(self) -> str:
        """Get current development stage"""
        return self._read_state().get("current_stage", StageType.INIT.value)

    def get_active_task(self) -> Optional[str]:
        """Get currently active task"""
        return self._read_state().get("active_task")

    def get_last_job_id(self) -> Optional[str]:
        """Get last job ID"""
        return self._read_state().get("last_job_id")

    # === Job lifecycle methods ===

    def on_job_start(
        self,
        job_id: str,
        task_description: str,
        stage: Optional[str] = None
    ) -> bool:
        """
        Called when a job starts.
        Updates state with job info.
        """
        state = self._read_state()

        # Add to history if there was a previous task
        if state.get("active_task"):
            history_entry = {
                "task": state["active_task"],
                "job_id": state.get("last_job_id"),
                "status": "interrupted",
                "timestamp": datetime.now().isoformat()
            }
            if "history" not in state:
                state["history"] = []
            state["history"].append(history_entry)
            # Keep only last 50 history entries
            state["history"] = state["history"][-50:]

        state["active_task"] = task_description
        state["last_job_id"] = job_id
        state["mode"] = "self"  # Default to self mode
        state["error"] = None

        if stage:
            state["current_stage"] = stage

        return self._write_state(state)

    def on_job_progress(
        self,
        job_id: str,
        progress_message: str,
        changed_files: Optional[List[str]] = None,
        mode: Optional[str] = None
    ) -> bool:
        """
        Called during job execution to update progress.
        """
        state = self._read_state()

        # Only update if this is the active job
        if state.get("last_job_id") != job_id:
            return False

        if changed_files:
            existing_files = state.get("last_changed_files", [])
            # Add new files, avoid duplicates
            for f in changed_files:
                if f not in existing_files:
                    existing_files.append(f)
            state["last_changed_files"] = existing_files[-20:]  # Keep last 20

        if mode:
            state["mode"] = mode

        return self._write_state(state)

    def on_job_finish(
        self,
        job_id: str,
        success: bool = True,
        changed_files: Optional[List[str]] = None,
        next_stage: Optional[str] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Called when a job finishes.
        Updates state with completion info.
        """
        state = self._read_state()

        # Only update if this is the active job
        if state.get("last_job_id") != job_id:
            return False

        # Add to history
        history_entry = {
            "task": state.get("active_task"),
            "job_id": job_id,
            "status": "finished" if success else "failed",
            "timestamp": datetime.now().isoformat()
        }
        if "history" not in state:
            state["history"] = []
        state["history"].append(history_entry)
        state["history"] = state["history"][-50:]

        if success:
            state["last_completed_task"] = state.get("active_task")
            state["active_task"] = None
            state["error"] = None
            if next_stage:
                state["current_stage"] = next_stage
        else:
            state["error"] = error or "Job failed"

        if changed_files:
            state["last_changed_files"] = changed_files[-20:]

        return self._write_state(state)

    def on_job_error(
        self,
        job_id: str,
        error_message: str
    ) -> bool:
        """
        Called when a job encounters an error.
        """
        state = self._read_state()

        if state.get("last_job_id") != job_id:
            return False

        state["error"] = error_message

        # Add to history
        history_entry = {
            "task": state.get("active_task"),
            "job_id": job_id,
            "status": "failed",
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }
        if "history" not in state:
            state["history"] = []
        state["history"].append(history_entry)
        state["history"] = state["history"][-50:]

        return self._write_state(state)

    # === Stage management ===

    def set_stage(self, stage: str) -> bool:
        """Set current development stage"""
        state = self._read_state()
        state["current_stage"] = stage
        return self._write_state(state)

    def advance_stage(self, next_stage: str, task_summary: str) -> bool:
        """
        Advance to next stage after completing current one.
        Records the transition.
        """
        state = self._read_state()

        old_stage = state.get("current_stage")
        state["current_stage"] = next_stage
        state["last_completed_task"] = f"Completed stage: {old_stage} - {task_summary}"
        state["active_task"] = None
        state["last_changed_files"] = []

        return self._write_state(state)

    # === Mode and pause control ===

    def set_mode(self, mode: str) -> bool:
        """Set execution mode (self/claude)"""
        state = self._read_state()
        state["mode"] = mode
        return self._write_state(state)

    def set_paused(self, paused: bool) -> bool:
        """Set paused state"""
        state = self._read_state()
        state["is_paused"] = paused
        return self._write_state(state)

    # === File tracking ===

    def add_changed_files(self, files: List[str]) -> bool:
        """Add files to the changed files list"""
        state = self._read_state()
        existing = state.get("last_changed_files", [])
        for f in files:
            if f not in existing:
                existing.append(f)
        state["last_changed_files"] = existing[-20:]
        return self._write_state(state)

    def clear_changed_files(self) -> bool:
        """Clear the changed files list"""
        state = self._read_state()
        state["last_changed_files"] = []
        return self._write_state(state)

    # === State summary ===

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of current state for display"""
        state = self._read_state()
        return {
            "current_stage": state.get("current_stage", "unknown"),
            "active_task": state.get("active_task"),
            "last_completed_task": state.get("last_completed_task"),
            "last_job_id": state.get("last_job_id"),
            "files_changed_count": len(state.get("last_changed_files", [])),
            "mode": state.get("mode", "self"),
            "is_paused": state.get("is_paused", False),
            "has_error": bool(state.get("error")),
            "updated_at": state.get("updated_at")
        }


# Global instance for convenience
_project_state: Optional[ProjectState] = None


def get_project_state(project_root: Optional[Path] = None) -> ProjectState:
    """Get or create project state instance"""
    global _project_state
    if _project_state is None or (project_root and project_root != _project_state.project_root):
        _project_state = ProjectState(project_root)
    return _project_state


# Convenience functions
def on_job_start(job_id: str, task: str, stage: Optional[str] = None) -> bool:
    """Convenience function for job start"""
    return get_project_state().on_job_start(job_id, task, stage)


def on_job_progress(job_id: str, message: str, files: Optional[List[str]] = None, mode: Optional[str] = None) -> bool:
    """Convenience function for job progress"""
    return get_project_state().on_job_progress(job_id, message, files, mode)


def on_job_finish(job_id: str, success: bool = True, files: Optional[List[str]] = None, next_stage: Optional[str] = None, error: Optional[str] = None) -> bool:
    """Convenience function for job finish"""
    return get_project_state().on_job_finish(job_id, success, files, next_stage, error)


def on_job_error(job_id: str, error: str) -> bool:
    """Convenience function for job error"""
    return get_project_state().on_job_error(job_id, error)


def get_current_state() -> Dict[str, Any]:
    """Get current state dict"""
    return get_project_state().get_state()


def get_state_summary() -> Dict[str, Any]:
    """Get state summary for display"""
    return get_project_state().get_summary()
