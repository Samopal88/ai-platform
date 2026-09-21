"""
AI Workspace Platform - Night Autopilot
Preparation for autonomous overnight development

Key principles:
- autonomous_run flag controls behavior
- Reads tasks from IMPLEMENTATION_PLAN.md
- Does NOT run infinitely
- Can be paused/stopped at any time
- All actions are logged
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from app.services.autonomous_loop import AutonomousLoop, get_autonomous_loop
from app.core.config import settings


@dataclass
class AutopilotConfig:
    """Configuration for night autopilot"""
    autonomous_run: bool = False  # Master switch - DEFAULTS TO OFF
    max_iterations: int = 10  # Maximum iterations before stop
    pause_on_error: bool = True  # Stop on first error
    pause_on_review_fail: bool = True  # Stop if review fails
    require_approval: bool = True  # Require approval between major steps
    notify_on_complete: bool = True
    allowed_hours: List[int] = None  # Hours when autopilot can run (e.g., [0,1,2,3,4,5])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "autonomous_run": self.autonomous_run,
            "max_iterations": self.max_iterations,
            "pause_on_error": self.pause_on_error,
            "pause_on_review_fail": self.pause_on_review_fail,
            "require_approval": self.require_approval,
            "notify_on_complete": self.notify_on_complete,
            "allowed_hours": self.allowed_hours or list(range(0, 6))  # Default: midnight to 6am
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AutopilotConfig':
        return cls(
            autonomous_run=data.get("autonomous_run", False),
            max_iterations=data.get("max_iterations", 10),
            pause_on_error=data.get("pause_on_error", True),
            pause_on_review_fail=data.get("pause_on_review_fail", True),
            require_approval=data.get("require_approval", True),
            notify_on_complete=data.get("notify_on_complete", True),
            allowed_hours=data.get("allowed_hours")
        )


class NightAutopilot:
    """
    Night autopilot manager for autonomous overnight development.

    IMPORTANT: autonomous_run is FALSE by default.
    It must be explicitly enabled and the system will NOT run infinitely.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.config_file = self.project_root / "docs" / "progress" / "autopilot_config.json"
        self.plan_file = self.project_root / "docs" / "IMPLEMENTATION_PLAN.md"
        self.log_file = self.project_root / "docs" / "progress" / "autopilot_log.json"

    def _load_config(self) -> AutopilotConfig:
        """Load autopilot configuration"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text())
                return AutopilotConfig.from_dict(data)
            except Exception:
                pass
        return AutopilotConfig()  # Default: autonomous_run = False

    def _save_config(self, config: AutopilotConfig) -> bool:
        """Save autopilot configuration"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(
                json.dumps(config.to_dict(), indent=2, ensure_ascii=False)
            )
            return True
        except Exception:
            return False

    def _log_action(self, action: str, details: Dict[str, Any]) -> None:
        """Log autopilot action"""
        logs = []
        if self.log_file.exists():
            try:
                logs = json.loads(self.log_file.read_text())
            except Exception:
                pass

        logs.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        })

        # Keep last 1000 entries
        logs = logs[-1000:]

        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.write_text(json.dumps(logs, indent=2, ensure_ascii=False))
        except Exception:
            pass

    def is_enabled(self) -> bool:
        """Check if autopilot is enabled"""
        return self._load_config().autonomous_run

    def can_run_now(self) -> tuple[bool, str]:
        """
        Check if autopilot can run right now.

        Returns:
            (can_run, reason)
        """
        config = self._load_config()

        if not config.autonomous_run:
            return False, "Autopilot is disabled (autonomous_run = false)"

        # Check allowed hours
        current_hour = datetime.now().hour
        if config.allowed_hours and current_hour not in config.allowed_hours:
            return False, f"Current hour ({current_hour}) not in allowed hours"

        return True, "Autopilot can run"

    def enable(self, max_iterations: int = 10) -> Dict[str, Any]:
        """
        Enable autopilot.

        Args:
            max_iterations: Maximum iterations to run

        Returns:
            Status dict
        """
        config = self._load_config()
        config.autonomous_run = True
        config.max_iterations = max_iterations
        self._save_config(config)

        self._log_action("enabled", {"max_iterations": max_iterations})

        return {
            "status": "enabled",
            "message": f"Autopilot enabled with max {max_iterations} iterations",
            "config": config.to_dict()
        }

    def disable(self) -> Dict[str, Any]:
        """Disable autopilot"""
        config = self._load_config()
        config.autonomous_run = False
        self._save_config(config)

        self._log_action("disabled", {})

        return {
            "status": "disabled",
            "message": "Autopilot disabled"
        }

    def get_next_task_from_plan(self) -> Optional[str]:
        """
        Read IMPLEMENTATION_PLAN.md and find the next incomplete task.

        Returns:
            Next task description or None
        """
        if not self.plan_file.exists():
            return None

        try:
            content = self.plan_file.read_text()

            # Look for unchecked items: - [ ] task
            pattern = r'-\s*\[\s*\]\s*(.+)'
            matches = re.findall(pattern, content)

            if matches:
                return matches[0].strip()

            return None

        except Exception:
            return None

    def run_one_iteration(self) -> Dict[str, Any]:
        """
        Run ONE autopilot iteration.

        This does NOT run infinitely - it executes one development cycle
        and returns.
        """
        can_run, reason = self.can_run_now()
        if not can_run:
            return {
                "status": "skipped",
                "reason": reason
            }

        config = self._load_config()

        # Get next task
        task = self.get_next_task_from_plan()
        if not task:
            self._log_action("no_task", {})
            return {
                "status": "no_task",
                "message": "No pending tasks found in IMPLEMENTATION_PLAN.md"
            }

        self._log_action("iteration_start", {"task": task})

        try:
            # Run one development cycle
            loop = get_autonomous_loop(self.project_root)
            result = loop.start_loop(task)

            self._log_action("iteration_complete", {
                "task": task,
                "result": result
            })

            return {
                "status": "completed",
                "task": task,
                "result": result
            }

        except Exception as e:
            self._log_action("iteration_error", {
                "task": task,
                "error": str(e)
            })

            if config.pause_on_error:
                config.autonomous_run = False
                self._save_config(config)

            return {
                "status": "error",
                "task": task,
                "error": str(e),
                "autopilot_paused": config.pause_on_error
            }

    def get_status(self) -> Dict[str, Any]:
        """Get autopilot status"""
        config = self._load_config()
        can_run, reason = self.can_run_now()
        next_task = self.get_next_task_from_plan()

        # Get recent log entries
        recent_logs = []
        if self.log_file.exists():
            try:
                logs = json.loads(self.log_file.read_text())
                recent_logs = logs[-5:]  # Last 5 entries
            except Exception:
                pass

        return {
            "enabled": config.autonomous_run,
            "can_run_now": can_run,
            "run_reason": reason,
            "config": config.to_dict(),
            "next_task": next_task,
            "recent_logs": recent_logs
        }


# Convenience functions
_autopilot: Optional[NightAutopilot] = None


def get_autopilot(project_root: Optional[Path] = None) -> NightAutopilot:
    """Get or create autopilot instance"""
    global _autopilot
    if _autopilot is None or (project_root and project_root != _autopilot.project_root):
        _autopilot = NightAutopilot(project_root)
    return _autopilot


def is_autopilot_enabled() -> bool:
    """Check if autopilot is enabled"""
    return get_autopilot().is_enabled()


def enable_autopilot(max_iterations: int = 10) -> Dict[str, Any]:
    """Enable autopilot"""
    return get_autopilot().enable(max_iterations)


def disable_autopilot() -> Dict[str, Any]:
    """Disable autopilot"""
    return get_autopilot().disable()


def run_autopilot_iteration() -> Dict[str, Any]:
    """Run one autopilot iteration"""
    return get_autopilot().run_one_iteration()


def get_autopilot_status() -> Dict[str, Any]:
    """Get autopilot status"""
    return get_autopilot().get_status()
