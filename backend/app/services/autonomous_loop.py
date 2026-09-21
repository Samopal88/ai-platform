"""
AI Workspace Platform - Autonomous Loop Foundation
Development cycle: plan → implement → review → verify → update → next

Enhanced with:
- Orchestrator integration for full verification loop
- GPT-style review at each step
- Definition of Done checking
- Retry logic with progressive escalation
- Blocked task handling
- Real status synchronization

Key principles:
- One step per job (no infinite loops)
- State drives next action
- Each cycle updates progress
- Tasks verified before marking complete
- Can be paused/resumed
- Uses orchestrator for execution (not direct Claude calls)
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from app.services.project_state import get_project_state, ProjectState
from app.services.agents.base_agent import AgentResult
from app.core.config import settings


class LoopStep(str, Enum):
    """Steps in the autonomous development loop"""
    PLAN = "plan"
    IMPLEMENT = "implement"
    REVIEW = "review"
    VERIFY = "verify"
    RETRY = "retry"
    UPDATE = "update"
    NEXT = "next"
    IDLE = "idle"
    BLOCKED = "blocked"


@dataclass
class LoopState:
    """State of the autonomous loop"""
    current_step: LoopStep
    current_task: Optional[str]
    last_result: Optional[Dict[str, Any]]
    iteration: int
    is_running: bool
    error: Optional[str]
    retry_count: int = 0
    max_retries: int = 3
    blocked_reason: Optional[str] = None
    use_orchestrator: bool = True  # NEW: Use orchestrator for execution


class AutonomousLoop:
    """
    Manages the autonomous development loop.

    The loop follows this cycle:
    1. PLAN: Analyze task and create plan
    2. IMPLEMENT: Execute the plan (via orchestrator)
    3. REVIEW: Review the implementation
    4. VERIFY: Check Definition of Done
    5. RETRY: If verification fails, retry
    6. UPDATE: Update state and progress
    7. NEXT: Determine next task

    Only ONE step is executed per job to prevent infinite loops.
    Tasks are verified before marking complete.

    NEW: Uses orchestrator for full verification loop.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.loop_state_file = self.project_root / "docs" / "progress" / "loop_state.json"
        self._agents = None
        self._supervisor = None
        self._orchestrator = None

    @property
    def agents(self):
        """Lazy load agents"""
        if self._agents is None:
            from app.services.agents import PlannerAgent, CoderAgent, ReviewAgent
            self._agents = {
                "planner": PlannerAgent(str(self.project_root)),
                "coder": CoderAgent(str(self.project_root)),
                "reviewer": ReviewAgent(str(self.project_root))
            }
        return self._agents

    @property
    def supervisor(self):
        """Lazy load supervisor"""
        if self._supervisor is None:
            from app.services.supervisor import get_supervisor
            self._supervisor = get_supervisor(self.project_root)
        return self._supervisor

    @property
    def orchestrator(self):
        """Lazy load orchestrator"""
        if self._orchestrator is None:
            from app.services.orchestrator import get_orchestrator
            self._orchestrator = get_orchestrator(self.project_root)
        return self._orchestrator

    def _load_loop_state(self) -> LoopState:
        """Load loop state from file"""
        if self.loop_state_file.exists():
            try:
                data = json.loads(self.loop_state_file.read_text())
                return LoopState(
                    current_step=LoopStep(data.get("current_step", "idle")),
                    current_task=data.get("current_task"),
                    last_result=data.get("last_result"),
                    iteration=data.get("iteration", 0),
                    is_running=data.get("is_running", False),
                    error=data.get("error"),
                    retry_count=data.get("retry_count", 0),
                    max_retries=data.get("max_retries", 3),
                    blocked_reason=data.get("blocked_reason"),
                    use_orchestrator=data.get("use_orchestrator", True)
                )
            except Exception:
                pass

        return LoopState(
            current_step=LoopStep.IDLE,
            current_task=None,
            last_result=None,
            iteration=0,
            is_running=False,
            error=None,
            retry_count=0,
            max_retries=3,
            blocked_reason=None,
            use_orchestrator=True
        )

    def _save_loop_state(self, state: LoopState) -> bool:
        """Save loop state to file"""
        try:
            data = {
                "current_step": state.current_step.value,
                "current_task": state.current_task,
                "last_result": state.last_result,
                "iteration": state.iteration,
                "is_running": state.is_running,
                "error": state.error,
                "retry_count": state.retry_count,
                "max_retries": state.max_retries,
                "blocked_reason": state.blocked_reason,
                "use_orchestrator": state.use_orchestrator,
                "updated_at": datetime.now().isoformat()
            }
            self.loop_state_file.parent.mkdir(parents=True, exist_ok=True)
            self.loop_state_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

            # Sync status file
            self._sync_status()

            return True
        except Exception:
            return False

    def _sync_status(self):
        """Synchronize CURRENT_STATUS.md"""
        try:
            from app.services.status_updater import sync_status_file
            sync_status_file()
        except Exception:
            pass

    def start_loop(self, task: str) -> Dict[str, Any]:
        """
        Start a new autonomous loop with a task.

        Args:
            task: Initial task to work on

        Returns:
            Result of the first step
        """
        state = LoopState(
            current_step=LoopStep.PLAN,
            current_task=task,
            last_result=None,
            iteration=1,
            is_running=True,
            error=None
        )
        self._save_loop_state(state)

        # Execute first step (plan)
        return self.execute_step()

    def execute_step(self) -> Dict[str, Any]:
        """
        Execute one step of the loop.

        This method executes ONLY ONE step and returns.
        Call it again for the next step.
        """
        state = self._load_loop_state()

        if not state.is_running:
            return {
                "status": "idle",
                "message": "Loop is not running. Call start_loop() first.",
                "step": state.current_step.value
            }

        # Check if paused
        project_state = get_project_state(self.project_root)
        if project_state.get_state().get("is_paused"):
            return {
                "status": "paused",
                "message": "Loop is paused",
                "step": state.current_step.value
            }

        try:
            result = self._execute_current_step(state)
            return result
        except Exception as e:
            state.error = str(e)
            state.is_running = False
            self._save_loop_state(state)
            return {
                "status": "error",
                "message": str(e),
                "step": state.current_step.value
            }

    def _execute_current_step(self, state: LoopState) -> Dict[str, Any]:
        """Execute the current step based on loop state"""

        if state.current_step == LoopStep.PLAN:
            return self._step_plan(state)
        elif state.current_step == LoopStep.IMPLEMENT:
            return self._step_implement(state)
        elif state.current_step == LoopStep.REVIEW:
            return self._step_review(state)
        elif state.current_step == LoopStep.VERIFY:
            return self._step_verify(state)
        elif state.current_step == LoopStep.RETRY:
            return self._step_retry(state)
        elif state.current_step == LoopStep.UPDATE:
            return self._step_update(state)
        elif state.current_step == LoopStep.NEXT:
            return self._step_next(state)
        elif state.current_step == LoopStep.BLOCKED:
            return {
                "status": "blocked",
                "message": state.blocked_reason or "Task is blocked",
                "step": "blocked"
            }
        else:
            return {
                "status": "idle",
                "message": "Loop is idle",
                "step": "idle"
            }

    def _step_plan(self, state: LoopState) -> Dict[str, Any]:
        """Execute plan step"""
        planner = self.agents["planner"]
        result = planner.process(state.current_task or "No task specified")

        # Update state
        state.last_result = result.to_dict()
        state.current_step = LoopStep.IMPLEMENT
        self._save_loop_state(state)

        return {
            "status": "completed",
            "step": "plan",
            "result": result.output,
            "next_step": "implement",
            "iteration": state.iteration
        }

    def _step_implement(self, state: LoopState) -> Dict[str, Any]:
        """Execute implement step - uses orchestrator for full verification"""

        if state.use_orchestrator:
            # Use orchestrator for full verification loop
            job_id = f"loop-{state.iteration}"
            result = self.orchestrator.execute_task(
                task_description=state.current_task or "",
                job_id=job_id,
                task_type="code",
                max_attempts=state.max_retries
            )

            # Update state based on orchestrator result
            state.last_result = result.to_dict() if hasattr(result, 'to_dict') else {
                "output": result.output,
                "success": result.success,
                "files_changed": result.files_changed,
                "attempts": result.attempts
            }

            if result.success:
                # Task completed via orchestrator - skip directly to UPDATE
                state.current_step = LoopStep.UPDATE
                state.retry_count = 0
                self._save_loop_state(state)

                return {
                    "status": "completed",
                    "step": "implement",
                    "result": result.output,
                    "files_changed": result.files_changed,
                    "attempts": result.attempts,
                    "next_step": "update",
                    "iteration": state.iteration,
                    "orchestrated": True
                }
            else:
                # Task blocked via orchestrator
                state.current_step = LoopStep.BLOCKED
                state.blocked_reason = result.blocked_reason
                state.is_running = False
                self._save_loop_state(state)

                return {
                    "status": "blocked",
                    "step": "implement",
                    "result": result.blocked_reason,
                    "verdict": "blocked",
                    "next_step": None,
                    "iteration": state.iteration,
                    "orchestrated": True
                }

        else:
            # Legacy: Use direct coder agent
            coder = self.agents["coder"]

            # Use plan from previous step as context
            context = {"plan": state.last_result} if state.last_result else None
            result = coder.process(state.current_task or "", context)

            # Update state
            state.last_result = result.to_dict()
            state.current_step = LoopStep.REVIEW
            self._save_loop_state(state)

            return {
                "status": "completed",
                "step": "implement",
                "result": result.output,
                "files_changed": result.files_changed,
                "next_step": "review",
                "iteration": state.iteration,
                "orchestrated": False
            }

    def _step_review(self, state: LoopState) -> Dict[str, Any]:
        """Execute review step"""
        reviewer = self.agents["reviewer"]

        # Use implementation from previous step
        context = {"implementation": state.last_result} if state.last_result else None
        result = reviewer.process(f"Review: {state.current_task}", context)

        # Update state - move to VERIFY instead of UPDATE
        state.last_result = result.to_dict()
        state.current_step = LoopStep.VERIFY
        self._save_loop_state(state)

        return {
            "status": "completed",
            "step": "review",
            "result": result.output,
            "verdict": result.next_action,
            "next_step": "verify",
            "iteration": state.iteration
        }

    def _step_verify(self, state: LoopState) -> Dict[str, Any]:
        """Execute verification step - check Definition of Done"""
        from app.services.supervisor import supervise_task

        # Get task output from last result
        task_output = None
        if state.last_result:
            task_output = state.last_result.get("output", "")

        # Run supervisor verification
        verification = supervise_task(
            task_description=state.current_task or "Unknown task",
            task_output=task_output
        )

        if verification["verdict"] == "complete":
            # Task is verified complete - move to update
            state.current_step = LoopStep.UPDATE
            state.retry_count = 0
            self._save_loop_state(state)

            return {
                "status": "completed",
                "step": "verify",
                "result": "Task verified complete",
                "verdict": "complete",
                "next_step": "update",
                "iteration": state.iteration
            }

        elif verification.get("should_retry", False):
            # Task needs fixes - move to retry
            state.current_step = LoopStep.RETRY
            state.retry_count += 1
            state.last_result = {
                **(state.last_result or {}),
                "fix_prompt": verification.get("fix_prompt"),
                "issues": verification.get("issues", [])
            }
            self._save_loop_state(state)

            return {
                "status": "needs_fix",
                "step": "verify",
                "result": f"Verification failed: {verification.get('issues', [])}",
                "verdict": "incomplete",
                "next_step": "retry",
                "retry_count": state.retry_count,
                "iteration": state.iteration
            }

        else:
            # Task is blocked - stop the loop
            state.current_step = LoopStep.BLOCKED
            state.blocked_reason = verification.get("message", "Task blocked after multiple retries")
            state.is_running = False
            self._save_loop_state(state)

            return {
                "status": "blocked",
                "step": "verify",
                "result": state.blocked_reason,
                "verdict": "blocked",
                "next_step": None,
                "iteration": state.iteration
            }

    def _step_retry(self, state: LoopState) -> Dict[str, Any]:
        """Execute retry step - attempt to fix issues"""

        if state.retry_count > state.max_retries:
            # Too many retries - mark as blocked
            state.current_step = LoopStep.BLOCKED
            state.blocked_reason = f"Failed after {state.retry_count} attempts"
            state.is_running = False
            self._save_loop_state(state)

            return {
                "status": "blocked",
                "step": "retry",
                "result": state.blocked_reason,
                "verdict": "blocked",
                "next_step": None,
                "iteration": state.iteration
            }

        # Get fix prompt from previous verification
        fix_prompt = None
        if state.last_result:
            fix_prompt = state.last_result.get("fix_prompt")

        if not fix_prompt:
            # Create a basic fix prompt
            issues = state.last_result.get("issues", []) if state.last_result else []
            fix_prompt = f"""Fix the following issues in task: {state.current_task}

Issues:
{chr(10).join(f'- {i}' for i in issues)}

Attempt {state.retry_count} of {state.max_retries}.
"""

        # Re-run coder with fix prompt
        coder = self.agents["coder"]
        result = coder.process(fix_prompt, {"retry": True, "attempt": state.retry_count})

        # Update state - go back to review
        state.last_result = result.to_dict()
        state.current_step = LoopStep.REVIEW
        self._save_loop_state(state)

        return {
            "status": "completed",
            "step": "retry",
            "result": f"Retry attempt {state.retry_count} completed",
            "files_changed": result.files_changed,
            "next_step": "review",
            "retry_count": state.retry_count,
            "iteration": state.iteration
        }

    def _step_update(self, state: LoopState) -> Dict[str, Any]:
        """Execute update step - update project state"""
        # Update project state
        project_state = get_project_state(self.project_root)
        project_state.on_job_finish(
            job_id=f"loop-{state.iteration}",
            success=True,
            changed_files=state.last_result.get("files_changed", []) if state.last_result else []
        )

        # Update state
        state.current_step = LoopStep.NEXT
        self._save_loop_state(state)

        return {
            "status": "completed",
            "step": "update",
            "result": "State updated",
            "next_step": "next",
            "iteration": state.iteration
        }

    def _step_next(self, state: LoopState) -> Dict[str, Any]:
        """Determine next task and move to next iteration"""

        # For MVP, complete the loop after one full cycle
        # In production, this would read from IMPLEMENTATION_PLAN.md

        state.iteration += 1
        state.current_step = LoopStep.IDLE
        state.is_running = False
        state.current_task = None
        self._save_loop_state(state)

        return {
            "status": "completed",
            "step": "next",
            "result": "Loop cycle completed",
            "message": "One development cycle completed. Call start_loop() with new task to continue.",
            "iteration": state.iteration
        }

    def stop_loop(self) -> Dict[str, Any]:
        """Stop the loop gracefully"""
        state = self._load_loop_state()
        state.is_running = False
        self._save_loop_state(state)

        return {
            "status": "stopped",
            "message": "Loop stopped",
            "step": state.current_step.value,
            "iteration": state.iteration
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current loop status"""
        state = self._load_loop_state()
        return {
            "is_running": state.is_running,
            "current_step": state.current_step.value,
            "current_task": state.current_task,
            "iteration": state.iteration,
            "has_error": bool(state.error),
            "error": state.error
        }


# Convenience functions
_loop: Optional[AutonomousLoop] = None


def get_autonomous_loop(project_root: Optional[Path] = None) -> AutonomousLoop:
    """Get or create autonomous loop instance"""
    global _loop
    if _loop is None or (project_root and project_root != _loop.project_root):
        _loop = AutonomousLoop(project_root)
    return _loop


def start_development_loop(task: str) -> Dict[str, Any]:
    """Start a new development loop"""
    return get_autonomous_loop().start_loop(task)


def execute_next_step() -> Dict[str, Any]:
    """Execute the next step in the loop"""
    return get_autonomous_loop().execute_step()


def get_loop_status() -> Dict[str, Any]:
    """Get loop status"""
    return get_autonomous_loop().get_status()
