"""
AI Workspace Platform - Orchestrator Service
Main controller that manages task execution until completion

CHATGPT-FIRST ARCHITECTURE:
The Orchestrator now uses ChatGPT-first approach:
1. Receives tasks from the API
2. Creates Definition of Done for each task
3. Runs ChatGPT executor (primary) with self-review loop
4. Uses Supervisor to verify completion
5. ChatGPT retries with self-fix (up to 2 attempts)
6. Claude executor only as FALLBACK when:
   - Task too complex for self-execution
   - Self-review shows critical issues after max attempts
   - Alternative implementation needed
7. Only marks done when DoD verified
8. Handles blocked tasks appropriately

Execution Modes:
- chatgpt_self: ChatGPT handles entire task lifecycle
- claude_fallback: Claude invoked after ChatGPT failures

FEATURES:
- Self-review loop that checks result against requirements
- Checks if files were created/modified as expected
- Verifies function/class definitions exist
- Progressive retry with self-fix prompts
- Claude fallback for complex cases
- Real-time status synchronization
- Dashboard shows execution mode and why Claude was invoked

This is the main entry point for ChatGPT-first task execution.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from app.core.config import settings

from app.services.supervisor import (
    Supervisor,
    DefinitionOfDone,
    TaskVerdict,
    BlockerType,
    get_supervisor,
    supervise_task
)
from app.services.project_state import (
    get_project_state,
    on_job_start,
    on_job_progress,
    on_job_finish,
    on_job_error
)
from app.services.status_updater import sync_status_file


class OrchestratorStatus(str, Enum):
    """Status of orchestrator execution"""
    IDLE = "idle"
    RUNNING = "running"
    PLANNING = "planning"  # Manager building plan
    STEP_EXECUTING = "step_executing"  # Executing a step
    STEP_REVIEWING = "step_reviewing"  # Manager reviewing step result
    VERIFYING = "verifying"
    RETRYING = "retrying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    REVIEWING = "reviewing"  # Self-review step
    SELF_FIXING = "self_fixing"  # ChatGPT self-fixing issues
    CLAUDE_FALLBACK = "claude_fallback"  # Claude invoked as fallback


class ExecutionMode(str, Enum):
    """Execution mode for ChatGPT-first architecture"""
    CHATGPT_SELF = "chatgpt_self"  # ChatGPT doing everything
    CLAUDE_FALLBACK = "claude_fallback"  # Claude as fallback
    MANAGER = "manager"  # ChatGPT as manager, Claude for steps


class ProgressEventType(str, Enum):
    """Progress event types for manager mode"""
    PLAN_CREATED = "plan_created"
    STEP_STARTED = "step_started"
    STEP_MODE_SELF = "step_mode_self"
    STEP_MODE_CLAUDE = "step_mode_claude"
    STEP_REVIEW = "step_review"
    STEP_RETRY = "step_retry"
    STEP_COMPLETED = "step_completed"
    TASK_COMPLETED = "task_completed"
    TASK_BLOCKED = "task_blocked"


@dataclass
class PlanStep:
    """A single step in the execution plan"""
    step_id: str
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed, skipped
    mode: str = "self"  # self, claude
    output: Optional[str] = None
    review_passed: bool = False
    review_notes: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "status": self.status,
            "mode": self.mode,
            "output": self.output,
            "review_passed": self.review_passed,
            "review_notes": self.review_notes,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts
        }


@dataclass
class ExecutionPlan:
    """Execution plan built by manager"""
    plan_id: str
    task_description: str
    steps: List[PlanStep]
    current_step_index: int = 0
    status: str = "created"  # created, in_progress, completed, blocked
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_description": self.task_description,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "status": self.status,
            "created_at": self.created_at
        }

    def get_current_step(self) -> Optional[PlanStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None


@dataclass
class ReviewResult:
    """Result of self-review step"""
    passed: bool
    checks_performed: List[str] = field(default_factory=list)
    issues_found: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    severity: str = "none"  # none, minor, major, critical
    can_self_fix: bool = True  # Can ChatGPT fix this itself
    needs_claude: bool = False  # Need Claude as fallback

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "checks_performed": self.checks_performed,
            "issues_found": self.issues_found,
            "suggestions": self.suggestions,
            "severity": self.severity,
            "can_self_fix": self.can_self_fix,
            "needs_claude": self.needs_claude
        }


@dataclass
class ExecutionResult:
    """Result of orchestrator execution"""
    success: bool
    task_id: str
    status: OrchestratorStatus
    mode: ExecutionMode = ExecutionMode.CHATGPT_SELF
    output: Optional[str] = None
    files_changed: List[str] = None
    attempts: int = 0
    blocked_reason: Optional[str] = None
    review: Optional[ReviewResult] = None
    claude_invoked: bool = False
    claude_reason: Optional[str] = None
    duration_seconds: float = 0
    plan: Optional[ExecutionPlan] = None  # Execution plan for manager mode

    def __post_init__(self):
        if self.files_changed is None:
            self.files_changed = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "status": self.status.value,
            "mode": self.mode.value,
            "output": self.output,
            "files_changed": self.files_changed,
            "attempts": self.attempts,
            "blocked_reason": self.blocked_reason,
            "review": self.review.to_dict() if self.review else None,
            "claude_invoked": self.claude_invoked,
            "claude_reason": self.claude_reason,
            "duration_seconds": self.duration_seconds,
            "plan": self.plan.to_dict() if self.plan else None
        }


class Orchestrator:
    """
    Manager Mode Orchestrator

    MANAGER MODE (NEW):
    ChatGPT acts as a manager/supervisor, NOT a simple router:
    1. Receives task -> Breaks it into sequential subtasks (steps)
    2. ChatGPT builds an execution PLAN with steps
    3. Each step is executed SEPARATELY
    4. Claude can only be called for a SPECIFIC subtask, not the whole task
    5. After each step, ChatGPT MUST review the result
    6. If result is bad/incomplete, ChatGPT creates a fix-step and runs another step
    7. Only ChatGPT decides when to move to the next step
    8. Claude does NOT determine the overall task flow

    Progress events show step-by-step manager flow:
    - plan_created: Plan built from task
    - step_started: Step execution begins
    - step_mode_self / step_mode_claude: Which executor handles the step
    - step_review: Manager reviewing step result
    - step_retry: Step needs retry
    - step_completed: Step finished
    - task_completed: All steps done

    Dashboard shows:
    - execution_mode: manager (primary), chatgpt_self, claude_fallback
    - current_step: plan, step_N, review, complete
    - plan with steps and their statuses
    - which steps used Claude
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.progress_path = self.project_root / "docs" / "progress"
        self.orchestrator_state_file = self.progress_path / "orchestrator_state.json"
        self._chatgpt_executor = None  # Primary executor
        self._claude_executor = None   # Fallback executor
        self._supervisor = None
        self.max_self_attempts = 2     # Max self-fix attempts before Claude fallback
        self.max_step_attempts = 2     # Max attempts per step
        self.enable_claude_fallback = True
        self.enable_manager_mode = True  # NEW: Manager mode enabled by default
        self._progress_events = []  # Store progress events
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist"""
        self.progress_path.mkdir(parents=True, exist_ok=True)

    @property
    def chatgpt_executor(self):
        """Lazy load ChatGPT executor (primary)"""
        if self._chatgpt_executor is None:
            from app.services.chatgpt_executor import ChatGPTFirstExecutor
            self._chatgpt_executor = ChatGPTFirstExecutor(project_root=self.project_root)
        return self._chatgpt_executor

    @property
    def claude_executor(self):
        """Lazy load Claude executor (fallback only)"""
        if self._claude_executor is None:
            from app.services.claude_executor import ClaudeExecutor
            self._claude_executor = ClaudeExecutor(project_root=self.project_root)
        return self._claude_executor

    @property
    def supervisor(self):
        """Lazy load supervisor"""
        if self._supervisor is None:
            self._supervisor = get_supervisor(self.project_root)
        return self._supervisor

    def _load_state(self) -> Dict[str, Any]:
        """Load orchestrator state"""
        if self.orchestrator_state_file.exists():
            try:
                return json.loads(self.orchestrator_state_file.read_text())
            except Exception:
                pass
        return {
            "status": OrchestratorStatus.IDLE.value,
            "mode": ExecutionMode.MANAGER.value,  # Default to manager mode
            "current_task": None,
            "current_job_id": None,
            "current_step": "idle",
            "current_step_index": 0,
            "current_dod": None,
            "plan": None,  # Execution plan for manager mode
            "attempts": 0,
            "max_attempts": self.max_self_attempts,
            "reviews": [],
            "progress_events": [],  # Manager mode progress events
            "claude_invoked": False,
            "claude_reason": None,
            "history": [],
            "blocked_tasks": [],
            "completed_tasks": [],
            "updated_at": None
        }

    def _save_state(self, state: Dict[str, Any]):
        """Save orchestrator state"""
        state["updated_at"] = datetime.now().isoformat()
        state["blocked_tasks"] = state.get("blocked_tasks", [])[-20:]
        state["completed_tasks"] = state.get("completed_tasks", [])[-20:]
        self.orchestrator_state_file.write_text(
            json.dumps(state, indent=2, ensure_ascii=False)
        )
        # Sync status file
        sync_status_file()

    def _emit_progress_event(
        self,
        event_type: ProgressEventType,
        message: str,
        step_index: Optional[int] = None,
        extra: Optional[Dict] = None
    ):
        """Emit a progress event for manager mode tracking"""
        event = {
            "event_type": event_type.value,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "step_index": step_index,
            "extra": extra or {}
        }
        self._progress_events.append(event)

        # Also update state with progress events
        state = self._load_state()
        if "progress_events" not in state:
            state["progress_events"] = []
        state["progress_events"].append(event)
        # Keep only last 50 events
        state["progress_events"] = state["progress_events"][-50:]
        self._save_state(state)

    def _update_status_md(self, phase: str, message: str, details: Optional[Dict] = None):
        """Update CURRENT_STATUS.md with current orchestration phase"""
        try:
            status_file = self.progress_path / "CURRENT_STATUS.md"
            if not status_file.exists():
                return

            content = status_file.read_text()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Find and update Active Task section
            pattern = r'(## Active Task\n)(.*?)(?=\n---)'
            task_info = f"**Phase:** {phase}\n**Status:** {message}\n**Updated:** {timestamp}"
            if details:
                for key, value in details.items():
                    task_info += f"\n**{key}:** {value}"

            replacement = f"\\g<1>{task_info}\n"
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)

            status_file.write_text(content)
        except Exception:
            pass

    def review_task_result(
        self,
        task_description: str,
        task_output: str,
        dod: DefinitionOfDone
    ) -> ReviewResult:
        """
        GPT-style review of task result.

        Performs comprehensive checks:
        1. Required files exist
        2. Expected patterns found
        3. Functions/classes defined
        4. No obvious errors
        5. Result matches request intent
        """
        checks = []
        issues = []
        suggestions = []

        # Check 1: Required files exist
        for file_path in dod.required_files:
            full_path = self.project_root / file_path
            checks.append(f"File exists: {file_path}")
            if not full_path.exists():
                issues.append(f"Missing file: {file_path}")
                suggestions.append(f"Create file: {file_path}")

        # Check 2: Required patterns in files
        for file_path, pattern in dod.required_patterns.items():
            full_path = self.project_root / file_path
            checks.append(f"Pattern in {file_path}")
            if full_path.exists():
                content = full_path.read_text()
                if not re.search(pattern, content):
                    issues.append(f"Pattern not found: {pattern[:30]}")
                    suggestions.append(f"Add {pattern} to {file_path}")
            else:
                issues.append(f"Cannot check pattern - missing file: {file_path}")

        # Check 3: Output contains error indicators
        error_patterns = [
            (r'traceback', 'Traceback detected in output'),
            (r'error:', 'Error message in output'),
            (r'exception', 'Exception in output'),
            (r'failed:', 'Failure reported'),
            (r'cannot', 'Cannot complete action'),
        ]
        for pattern, description in error_patterns:
            checks.append(f"Check for: {description}")
            if re.search(pattern, task_output.lower()):
                # Verify it's a real error, not just mentioning error handling
                context = re.findall(rf'.{{0,50}}{pattern}.{{0,50}}', task_output.lower())
                if context and not any('handle' in c or 'catch' in c for c in context):
                    issues.append(description)

        # Check 4: Intent matching - basic heuristics
        intent_checks = [
            ('creat', 'create', lambda: any(
                (self.project_root / f).exists()
                for f in dod.required_files
            )),
            ('implement', 'implement', lambda: any(
                'def ' in task_output or 'class ' in task_output
                for _ in [1]
            )),
            ('fix', 'fix', lambda: 'fixed' in task_output.lower() or 'resolved' in task_output.lower()),
            ('add', 'add', lambda: 'added' in task_output.lower() or any(
                (self.project_root / f).exists()
                for f in dod.required_files
            )),
        ]

        for keyword, intent, check_func in intent_checks:
            if keyword in task_description.lower():
                checks.append(f"Intent: {intent}")
                try:
                    if not check_func():
                        issues.append(f"Intent not fulfilled: {intent}")
                        suggestions.append(f"Ensure task actually {intent}s what was requested")
                except Exception:
                    pass

        # Check 5: Output is substantive
        checks.append("Output is substantive")
        if len(task_output.strip()) < 50:
            issues.append("Output too short - may be incomplete")
            suggestions.append("Provide complete implementation")

        # Determine severity
        if not issues:
            severity = "none"
        elif len(issues) == 1 and 'short' not in issues[0].lower():
            severity = "minor"
        elif len(issues) <= 2:
            severity = "major"
        else:
            severity = "critical"

        return ReviewResult(
            passed=len(issues) == 0,
            checks_performed=checks,
            issues_found=issues,
            suggestions=suggestions,
            severity=severity
        )

    def create_enhanced_fix_prompt(
        self,
        original_task: str,
        review: ReviewResult,
        verification: Dict[str, Any],
        attempt: int,
        previous_output: str
    ) -> str:
        """
        Create enhanced fix prompt with progressive escalation.

        Escalation levels:
        - Attempt 1: Gentle nudge
        - Attempt 2: Direct requirements
        - Attempt 3: Very explicit commands
        """
        # Combine review and verification issues
        all_issues = review.issues_found + verification.get('issues', [])
        all_suggestions = review.suggestions + verification.get('suggestions', [])

        # Remove duplicates while preserving order
        seen = set()
        unique_issues = []
        for i in all_issues:
            if i not in seen:
                seen.add(i)
                unique_issues.append(i)

        seen = set()
        unique_suggestions = []
        for s in all_suggestions:
            if s not in seen:
                seen.add(s)
                unique_suggestions.append(s)

        issues_text = "\n".join(f"- {i}" for i in unique_issues)
        suggestions_text = "\n".join(f"- {s}" for s in unique_suggestions)

        if attempt == 1:
            return f"""## Please Fix the Following Issues

Your previous attempt was helpful but needs some adjustments.

### Original Task
{original_task}

### Issues Found
{issues_text}

### Suggestions
{suggestions_text}

Please address these issues to complete the task.
"""

        elif attempt == 2:
            return f"""## REQUIRED FIXES - Attempt {attempt}

The task is not complete. These issues MUST be fixed:

### Critical Issues
{issues_text}

### Required Actions
{suggestions_text}

### Original Task (for reference)
{original_task}

Do NOT skip any requirements. Each issue listed must be resolved.
"""

        else:
            return f"""## FINAL ATTEMPT - Attempt {attempt}

This is the FINAL attempt. If these issues are not resolved, the task will be BLOCKED.

### MUST FIX (Critical)
{issues_text}

### EXACT STEPS REQUIRED
{suggestions_text}

### CONTEXT
Original task: {original_task[:200]}

IMPORTANT:
- Each file mentioned MUST exist after completion
- Each function/class mentioned MUST be defined
- No error messages should appear
- This is the FINAL chance to complete this task
"""

    def execute_task(
        self,
        task_description: str,
        job_id: str,
        task_type: str = "general",
        custom_dod: Optional[DefinitionOfDone] = None,
        max_attempts: int = 2,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> ExecutionResult:
        """
        Execute a task using ChatGPT-first approach.

        This is the MAIN entry point for task execution.
        ChatGPT handles the task with self-review loop.
        Claude is only invoked as fallback when needed.

        Flow:
        1. ChatGPT analyzes and plans
        2. ChatGPT implements
        3. Self-review (ChatGPT reviews its own work)
        4. Verify Definition of Done
        5. Self-fix if issues found (up to max_attempts)
        6. Claude fallback if still failing (optional)
        7. Complete when DoD verified

        Args:
            task_description: What to accomplish
            job_id: Job ID for tracking
            task_type: Type of task (general, code, analyze, etc.)
            custom_dod: Optional custom Definition of Done
            max_attempts: Maximum self-fix attempts (default 2)
            on_progress: Optional progress callback

        Returns:
            ExecutionResult with status, mode, and output
        """
        start_time = time.time()

        state = self._load_state()
        state["status"] = OrchestratorStatus.RUNNING.value
        state["mode"] = ExecutionMode.CHATGPT_SELF.value
        state["current_task"] = task_description
        state["current_job_id"] = job_id
        state["current_step"] = "analyze"
        state["attempts"] = 0
        state["max_attempts"] = max_attempts
        state["reviews"] = []
        state["claude_invoked"] = False
        state["claude_reason"] = None
        self._save_state(state)

        # Create or use DoD
        dod = custom_dod or self.supervisor.infer_dod_from_task(task_description)
        state["current_dod"] = {
            "task_id": dod.task_id,
            "description": dod.description,
            "required_files": dod.required_files,
            "required_patterns": dod.required_patterns
        }
        self._save_state(state)

        # Mark job started
        on_job_start(job_id, task_description[:100], f"ChatGPT-first: {task_type}")
        self._update_status_md("Starting", f"Task: {task_description[:100]}", {
            "Job": job_id,
            "Mode": "chatgpt_self"
        })

        if on_progress:
            on_progress(f"Starting ChatGPT-first execution with up to {max_attempts} self-attempts")

        attempt = 0
        # CRITICAL: Store original task separately from current_prompt
        # This prevents review/fix prompts from polluting file execution
        original_task = task_description
        current_prompt = task_description
        last_output = None
        files_changed = []
        last_review = None
        claude_invoked = False
        claude_reason = None

        while attempt < max_attempts:
            attempt += 1
            state["attempts"] = attempt
            state["current_step"] = "implement" if attempt == 1 else "self_fix"
            state["status"] = OrchestratorStatus.RUNNING.value if attempt == 1 else OrchestratorStatus.SELF_FIXING.value
            self._save_state(state)

            on_job_progress(job_id, f"Self-execution attempt {attempt}/{max_attempts}")
            self._update_status_md(
                "Implementing" if attempt == 1 else "Self-fixing",
                f"Attempt {attempt}/{max_attempts}",
                {"Task": original_task[:50], "Mode": "chatgpt_self"}
            )

            if on_progress:
                on_progress(f"Attempt {attempt}/{max_attempts}: ChatGPT self-executing...")

            # Execute the task using ChatGPT executor
            # CRITICAL: ALWAYS pass original_task, not fix_prompt
            # The chatgpt_executor now handles this internally, but we enforce it here too
            try:
                result = self.chatgpt_executor.execute_task(
                    task_description=original_task,  # ALWAYS use original task
                    job_id=f"{job_id}-attempt-{attempt}",
                    task_type=task_type
                )
                last_output = result.output or ""
                if result.files_changed:
                    files_changed.extend(result.files_changed)
            except Exception as e:
                on_job_progress(job_id, f"Execution error: {str(e)}")
                last_output = f"Error: {str(e)}"

            # === SELF-REVIEW STEP ===
            state["current_step"] = "self_review"
            state["status"] = OrchestratorStatus.REVIEWING.value
            self._save_state(state)

            if on_progress:
                on_progress(f"Attempt {attempt}: Performing self-review...")

            review = self.review_task_result(
                task_description=original_task,  # Review against original task
                task_output=last_output,
                dod=dod
            )
            last_review = review

            # Determine if can self-fix or needs Claude
            can_self_fix = review.severity in ("none", "minor", "major") and attempt < max_attempts
            needs_claude = review.severity == "critical" or (not can_self_fix and self.enable_claude_fallback)

            state["reviews"].append({
                "attempt": attempt,
                "timestamp": datetime.now().isoformat(),
                "passed": review.passed,
                "checks": review.checks_performed,
                "issues": review.issues_found,
                "severity": review.severity,
                "can_self_fix": can_self_fix,
                "needs_claude": needs_claude
            })
            self._save_state(state)

            # === VERIFICATION STEP ===
            state["current_step"] = "verify_dod"
            state["status"] = OrchestratorStatus.VERIFYING.value
            self._save_state(state)

            if on_progress:
                on_progress(f"Attempt {attempt}: Verifying Definition of Done...")

            verification = supervise_task(
                task_description=original_task,  # Verify against original task
                task_output=last_output,
                custom_dod=dod
            )

            # Combine review and verification results
            is_complete = review.passed and verification["verdict"] == "complete"
            has_minor_issues = review.severity == "minor" and verification["verdict"] != "blocked"

            if is_complete:
                # Task is done!
                duration = time.time() - start_time

                state["current_step"] = "complete"
                state["status"] = OrchestratorStatus.COMPLETED.value
                state["current_task"] = None
                state["current_job_id"] = None
                state["current_dod"] = None
                state["completed_tasks"].append({
                    "task_id": dod.task_id,
                    "job_id": job_id,
                    "status": "completed",
                    "mode": ExecutionMode.CHATGPT_SELF.value,
                    "attempts": attempt,
                    "duration_seconds": duration,
                    "completed_at": datetime.now().isoformat()
                })
                self._save_state(state)

                on_job_finish(job_id, success=True, files=files_changed)
                self._update_status_md("Completed", f"Task completed after {attempt} self-attempt(s)", {
                    "Duration": f"{duration:.1f}s",
                    "Files": len(files_changed),
                    "Mode": "chatgpt_self"
                })

                if on_progress:
                    on_progress(f"Task completed successfully after {attempt} self-attempt(s)!")

                return ExecutionResult(
                    success=True,
                    task_id=dod.task_id,
                    status=OrchestratorStatus.COMPLETED,
                    mode=ExecutionMode.CHATGPT_SELF,
                    output=last_output,
                    files_changed=list(set(files_changed)),
                    attempts=attempt,
                    review=review,
                    claude_invoked=False,
                    duration_seconds=duration
                )

            # Check if should self-fix or need Claude fallback
            should_retry = verification.get("should_retry", False) or has_minor_issues

            if should_retry and can_self_fix and attempt < max_attempts:
                # Task needs self-fix
                state["current_step"] = "self_fix"
                on_job_progress(
                    job_id,
                    f"Self-review found {len(review.issues_found)} issues, self-fixing..."
                )
                self._update_status_md(
                    "Self-Fixing",
                    f"Issues found: {len(review.issues_found)}",
                    {"Severity": review.severity, "Mode": "chatgpt_self"}
                )

                if on_progress:
                    on_progress(f"Attempt {attempt}: Found issues, creating self-fix prompt...")

                # NOTE: fix_prompt is now internal-only for logging/debugging
                # We NO LONGER pass it to chatgpt_executor - always use original_task
                fix_prompt = self.create_enhanced_fix_prompt(
                    original_task=original_task,
                    review=review,
                    verification=verification,
                    attempt=attempt,
                    previous_output=last_output
                )
                # NOTE: current_prompt is no longer used - we always pass original_task to executor
                # Keeping this assignment for state tracking only, NOT for execution
                current_prompt = fix_prompt

            elif needs_claude and self.enable_claude_fallback:
                # Try Claude as fallback - ALWAYS with original_task
                claude_reason = f"Self-execution failed after {attempt} attempts: {review.issues_found[0] if review.issues_found else 'unknown'}"
                state["mode"] = ExecutionMode.CLAUDE_FALLBACK.value
                state["current_step"] = "claude_fallback"
                state["status"] = OrchestratorStatus.CLAUDE_FALLBACK.value
                state["claude_invoked"] = True
                state["claude_reason"] = claude_reason
                self._save_state(state)

                on_job_progress(job_id, f"Invoking Claude as fallback: {claude_reason}")
                self._update_status_md(
                    "Claude Fallback",
                    f"ChatGPT self-execution failed, trying Claude",
                    {"Reason": claude_reason[:50], "Mode": "claude_fallback"}
                )

                if on_progress:
                    on_progress(f"ChatGPT self-execution failed, invoking Claude as fallback...")

                try:
                    claude_result = self.claude_executor.execute(original_task, task_type)
                    last_output = claude_result.answer or ""
                    if claude_result.changed_files:
                        files_changed.extend(claude_result.changed_files)
                    claude_invoked = True

                    # Re-verify after Claude - use original_task
                    verification = supervise_task(
                        task_description=original_task,
                        task_output=last_output,
                        custom_dod=dod
                    )

                    if verification["verdict"] == "complete":
                        duration = time.time() - start_time

                        state["current_step"] = "complete"
                        state["status"] = OrchestratorStatus.COMPLETED.value
                        state["current_task"] = None
                        state["current_job_id"] = None
                        state["completed_tasks"].append({
                            "task_id": dod.task_id,
                            "job_id": job_id,
                            "status": "completed_with_fallback",
                            "mode": ExecutionMode.CLAUDE_FALLBACK.value,
                            "attempts": attempt,
                            "duration_seconds": duration,
                            "completed_at": datetime.now().isoformat()
                        })
                        self._save_state(state)

                        on_job_finish(job_id, success=True, files=files_changed)
                        self._update_status_md("Completed (Claude)", f"Completed with Claude fallback", {
                            "Duration": f"{duration:.1f}s",
                            "Mode": "claude_fallback"
                        })

                        if on_progress:
                            on_progress(f"Task completed with Claude fallback!")

                        return ExecutionResult(
                            success=True,
                            task_id=dod.task_id,
                            status=OrchestratorStatus.COMPLETED,
                            mode=ExecutionMode.CLAUDE_FALLBACK,
                            output=last_output,
                            files_changed=list(set(files_changed)),
                            attempts=attempt,
                            review=last_review,
                            claude_invoked=True,
                            claude_reason=claude_reason,
                            duration_seconds=duration
                        )

                except Exception as e:
                    last_output = f"Claude fallback also failed: {str(e)}"

                break  # Exit loop after Claude fallback

            elif verification.get("blocked", False):
                # Task is blocked - stop retrying
                break

        # If we get here, task is blocked
        duration = time.time() - start_time
        blocked_reason = f"Failed after {attempt} self-attempts"
        if claude_invoked:
            blocked_reason += " (and Claude fallback)"
        if last_review and last_review.issues_found:
            blocked_reason += f": {last_review.issues_found[0]}"
        elif verification.get("issues"):
            blocked_reason += f": {verification['issues'][0]}"

        state["current_step"] = "blocked"
        state["status"] = OrchestratorStatus.BLOCKED.value
        state["current_task"] = None
        state["current_job_id"] = None
        state["current_dod"] = None
        state["blocked_tasks"].append({
            "task_id": dod.task_id,
            "job_id": job_id,
            "status": "blocked",
            "mode": state.get("mode", ExecutionMode.CHATGPT_SELF.value),
            "attempts": attempt,
            "reason": blocked_reason,
            "claude_invoked": claude_invoked,
            "duration_seconds": duration,
            "blocked_at": datetime.now().isoformat()
        })
        self._save_state(state)

        on_job_error(job_id, blocked_reason)
        self._update_status_md("Blocked", blocked_reason[:100], {
            "Attempts": attempt,
            "Duration": f"{duration:.1f}s",
            "Mode": state.get("mode", "chatgpt_self")
        })

        if on_progress:
            on_progress(f"Task blocked: {blocked_reason}")

        return ExecutionResult(
            success=False,
            task_id=dod.task_id,
            status=OrchestratorStatus.BLOCKED,
            mode=ExecutionMode(state.get("mode", ExecutionMode.CHATGPT_SELF.value)),
            output=last_output,
            files_changed=list(set(files_changed)),
            attempts=attempt,
            blocked_reason=blocked_reason,
            review=last_review,
            claude_invoked=claude_invoked,
            claude_reason=claude_reason,
            duration_seconds=duration
        )

    def build_execution_plan(
        self,
        task_description: str,
        job_id: str
    ) -> ExecutionPlan:
        """
        Build an execution plan from a task description.

        ChatGPT (manager) analyzes the task and breaks it into sequential steps.
        Each step should be small enough to execute and verify independently.

        This is the key difference from simple routing:
        - Manager decides HOW to break down the task
        - Manager decides the ORDER of steps
        - Manager decides which steps need Claude vs self-execution
        """
        plan_id = f"plan-{job_id}-{int(time.time())}"

        # Analyze task to extract subtasks
        task_lower = task_description.lower()

        steps = []

        # Detect multi-part tasks
        # Look for numbered lists, bullet points, or common task separators
        parts = []

        # Check for numbered items: "1. xxx 2. xxx"
        numbered_match = re.findall(r'\d+\.\s+([^\.]+(?:\.[^\d]|$))', task_description)
        if numbered_match:
            parts = numbered_match

        # Check for bullet points or dashes
        if not parts:
            bullet_match = re.findall(r'[-•]\s+([^\n]+)', task_description)
            if bullet_match:
                parts = bullet_match

        # Check for "and", "then", "after that" separators
        if not parts:
            separator_keywords = ['затем', 'потом', 'после этого', 'then', 'after that', 'next']
            for sep in separator_keywords:
                if sep in task_lower:
                    parts = re.split(rf'\s*{sep}\s*', task_description, flags=re.IGNORECASE)
                    break

        # If no explicit parts found, create logical steps based on task type
        if not parts:
            # Create default steps based on task analysis
            if any(word in task_lower for word in ['implement', 'create', 'add', 'build', 'создай', 'добавь', 'реализуй']):
                parts = [
                    f"Analyze requirements: {task_description[:100]}",
                    f"Implement: {task_description[:100]}",
                    f"Verify implementation"
                ]
            elif any(word in task_lower for word in ['fix', 'repair', 'исправ']):
                parts = [
                    f"Analyze the issue: {task_description[:100]}",
                    f"Apply fix",
                    f"Verify fix"
                ]
            elif any(word in task_lower for word in ['refactor', 'рефактор']):
                parts = [
                    f"Analyze code structure",
                    f"Refactor: {task_description[:100]}",
                    f"Verify refactoring"
                ]
            else:
                # Single step for simple tasks
                parts = [task_description]

        # Convert parts to PlanSteps
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            # Determine if this step likely needs Claude (complex) or can be self-executed
            needs_claude = any(word in part.lower() for word in [
                'complex', 'advanced', 'refactor large', 'rewrite', 'claude',
                'сложн', 'переписа'
            ])

            step = PlanStep(
                step_id=f"step-{i+1}",
                description=part,
                status="pending",
                mode="claude" if needs_claude else "self",
                max_attempts=self.max_step_attempts
            )
            steps.append(step)

        return ExecutionPlan(
            plan_id=plan_id,
            task_description=task_description,
            steps=steps,
            current_step_index=0,
            status="created"
        )

    def review_step_result(
        self,
        step: PlanStep,
        step_output: str,
        task_description: str
    ) -> ReviewResult:
        """
        Manager reviews a single step's result.

        This is different from reviewing the whole task:
        - Only checks if THIS step is complete
        - Doesn't verify the whole DoD yet
        - Determines if retry is needed for this step
        """
        checks = []
        issues = []
        suggestions = []

        # Check 1: Output is substantive
        checks.append("Step output is substantive")
        if len(step_output.strip()) < 20:
            issues.append("Step output too short - may be incomplete")
            suggestions.append("Complete the step fully")

        # Check 2: No error indicators
        error_patterns = [
            (r'error:', 'Error message found'),
            (r'exception', 'Exception in output'),
            (r'failed', 'Failure indicated'),
            (r'cannot', 'Cannot complete action'),
            (r'ошибка', 'Error (Russian)'),
            (r'не удалось', 'Failed (Russian)'),
        ]

        output_lower = step_output.lower()
        for pattern, desc in error_patterns:
            checks.append(f"Check: no {desc}")
            if re.search(pattern, output_lower):
                # Verify it's not in error handling context
                context = re.findall(rf'.{{0,30}}{pattern}.{{0,30}}', output_lower)
                if context and not any('handle' in c or 'catch' in c or 'except' in c for c in context):
                    issues.append(desc)
                    suggestions.append(f"Fix: {desc}")

        # Check 3: Step-specific validation based on description
        step_lower = step.description.lower()

        if any(word in step_lower for word in ['create', 'add', 'implement', 'создай']):
            checks.append("Creation confirmed")
            if not any(word in output_lower for word in ['created', 'added', 'implemented', 'создан', 'добавлен']):
                issues.append("Creation not confirmed in output")

        if any(word in step_lower for word in ['fix', 'repair', 'исправ']):
            checks.append("Fix confirmed")
            if not any(word in output_lower for word in ['fixed', 'repaired', 'resolved', 'исправлен', 'решен']):
                issues.append("Fix not confirmed in output")

        # Determine severity
        if not issues:
            severity = "none"
        elif len(issues) == 1:
            severity = "minor"
        elif len(issues) <= 2:
            severity = "major"
        else:
            severity = "critical"

        return ReviewResult(
            passed=len(issues) == 0,
            checks_performed=checks,
            issues_found=issues,
            suggestions=suggestions,
            severity=severity,
            can_self_fix=severity in ("none", "minor", "major") and step.attempts < step.max_attempts,
            needs_claude=severity == "critical" and step.mode != "claude"
        )

    def execute_step(
        self,
        step: PlanStep,
        task_description: str,
        job_id: str,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Execute a single step of the plan.

        Manager delegates execution to either:
        - Self (ChatGPT) for simple steps
        - Claude for complex steps

        Returns the step output.
        """
        step_job_id = f"{job_id}-{step.step_id}"

        if step.mode == "claude" and self.enable_claude_fallback:
            # Execute with Claude
            self._emit_progress_event(
                ProgressEventType.STEP_MODE_CLAUDE,
                f"Step {step.step_id} delegated to Claude",
                extra={"step_id": step.step_id, "description": step.description}
            )

            if on_progress:
                on_progress(f"Step {step.step_id}: Executing with Claude...")

            try:
                result = self.claude_executor.execute(
                    prompt=step.description,
                    task_type="code"
                )
                return result.answer or ""
            except Exception as e:
                return f"Claude execution error: {str(e)}"
        else:
            # Execute with self (ChatGPT)
            self._emit_progress_event(
                ProgressEventType.STEP_MODE_SELF,
                f"Step {step.step_id} executed by ChatGPT",
                extra={"step_id": step.step_id, "description": step.description}
            )

            if on_progress:
                on_progress(f"Step {step.step_id}: Executing with ChatGPT...")

            try:
                result = self.chatgpt_executor.execute_task(
                    task_description=step.description,
                    job_id=step_job_id,
                    task_type="general"
                )
                return result.output or ""
            except Exception as e:
                return f"ChatGPT execution error: {str(e)}"

    def execute_task_manager_mode(
        self,
        task_description: str,
        job_id: str,
        task_type: str = "general",
        custom_dod: Optional[DefinitionOfDone] = None,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> ExecutionResult:
        """
        Execute a task in MANAGER MODE.

        ChatGPT acts as the manager/supervisor:
        1. Breaks task into sequential steps (build plan)
        2. Executes each step separately
        3. Reviews each step's result
        4. Decides whether to retry, fix, or proceed
        5. Only completes when all steps pass review

        Claude is ONLY called for specific subtasks, NOT the whole task.
        ChatGPT (manager) ALWAYS decides the flow.

        Args:
            task_description: Full task description
            job_id: Job ID for tracking
            task_type: Type of task
            custom_dod: Optional Definition of Done
            on_progress: Progress callback

        Returns:
            ExecutionResult with plan and step details
        """
        start_time = time.time()
        self._progress_events = []  # Reset progress events

        # === PHASE 1: PLANNING ===
        state = self._load_state()
        state["status"] = OrchestratorStatus.PLANNING.value
        state["mode"] = ExecutionMode.MANAGER.value
        state["current_task"] = task_description
        state["current_job_id"] = job_id
        state["current_step"] = "planning"
        state["progress_events"] = []
        self._save_state(state)

        on_job_start(job_id, task_description[:100], "Manager mode")

        if on_progress:
            on_progress("Manager mode: Building execution plan...")

        # Build the plan
        plan = self.build_execution_plan(task_description, job_id)

        self._emit_progress_event(
            ProgressEventType.PLAN_CREATED,
            f"Plan created with {len(plan.steps)} steps",
            extra={"plan_id": plan.plan_id, "step_count": len(plan.steps)}
        )

        state["plan"] = plan.to_dict()
        state["current_step_index"] = 0
        self._save_state(state)

        self._update_status_md("Planning", f"Plan created: {len(plan.steps)} steps", {
            "Job": job_id,
            "Mode": "manager"
        })

        if on_progress:
            on_progress(f"Plan created: {len(plan.steps)} steps")

        # Create DoD if needed
        dod = custom_dod or self.supervisor.infer_dod_from_task(task_description)
        state["current_dod"] = {
            "task_id": dod.task_id,
            "description": dod.description,
            "required_files": dod.required_files,
            "required_patterns": dod.required_patterns
        }
        self._save_state(state)

        # === PHASE 2: STEP-BY-STEP EXECUTION ===
        files_changed = []
        all_outputs = []
        claude_invoked = False
        claude_reason = None

        for step_idx, step in enumerate(plan.steps):
            plan.current_step_index = step_idx
            state["current_step_index"] = step_idx
            state["current_step"] = f"step_{step_idx + 1}"
            state["status"] = OrchestratorStatus.STEP_EXECUTING.value
            self._save_state(state)

            self._emit_progress_event(
                ProgressEventType.STEP_STARTED,
                f"Starting step {step_idx + 1}: {step.description[:50]}",
                step_index=step_idx,
                extra={"step_id": step.step_id, "mode": step.mode}
            )

            if on_progress:
                on_progress(f"Step {step_idx + 1}/{len(plan.steps)}: {step.description[:50]}...")

            # Execute step with retry loop
            step.status = "in_progress"
            step_output = ""

            while step.attempts < step.max_attempts:
                step.attempts += 1

                # Execute the step
                step_output = self.execute_step(
                    step=step,
                    task_description=task_description,
                    job_id=job_id,
                    on_progress=on_progress
                )

                # Track if Claude was used
                if step.mode == "claude":
                    claude_invoked = True
                    if not claude_reason:
                        claude_reason = f"Step {step.step_id} required Claude"

                # === MANAGER REVIEW ===
                state["status"] = OrchestratorStatus.STEP_REVIEWING.value
                self._save_state(state)

                self._emit_progress_event(
                    ProgressEventType.STEP_REVIEW,
                    f"Manager reviewing step {step_idx + 1}",
                    step_index=step_idx,
                    extra={"attempt": step.attempts}
                )

                if on_progress:
                    on_progress(f"Manager reviewing step {step_idx + 1}...")

                review = self.review_step_result(
                    step=step,
                    step_output=step_output,
                    task_description=task_description
                )

                step.review_passed = review.passed
                step.review_notes = "; ".join(review.issues_found) if review.issues_found else "OK"
                step.output = step_output

                if review.passed:
                    # Step completed successfully
                    step.status = "completed"

                    self._emit_progress_event(
                        ProgressEventType.STEP_COMPLETED,
                        f"Step {step_idx + 1} completed",
                        step_index=step_idx,
                        extra={"attempts": step.attempts, "mode": step.mode}
                    )

                    if on_progress:
                        on_progress(f"Step {step_idx + 1} completed after {step.attempts} attempt(s)")

                    break  # Move to next step

                elif review.can_self_fix and step.attempts < step.max_attempts:
                    # Retry the step
                    self._emit_progress_event(
                        ProgressEventType.STEP_RETRY,
                        f"Step {step_idx + 1} needs retry: {review.issues_found[0] if review.issues_found else 'issues found'}",
                        step_index=step_idx,
                        extra={"attempt": step.attempts, "issues": review.issues_found}
                    )

                    if on_progress:
                        on_progress(f"Step {step_idx + 1}: Retrying due to {review.severity} issues...")

                    # Manager decides: try Claude if self failed
                    if review.needs_claude and step.mode == "self":
                        step.mode = "claude"
                        if on_progress:
                            on_progress(f"Step {step_idx + 1}: Escalating to Claude...")

                elif review.needs_claude and step.mode != "claude" and self.enable_claude_fallback:
                    # Escalate to Claude
                    step.mode = "claude"
                    step.attempts -= 1  # Don't count this as a full attempt

                    if on_progress:
                        on_progress(f"Step {step_idx + 1}: Escalating to Claude fallback...")

                else:
                    # Step failed after max attempts
                    step.status = "failed"
                    break

            # Update plan in state
            state["plan"] = plan.to_dict()
            self._save_state(state)

            # Check if step failed
            if step.status == "failed":
                # Task is blocked at this step
                duration = time.time() - start_time
                blocked_reason = f"Blocked at step {step_idx + 1}: {step.review_notes or 'failed'}"

                self._emit_progress_event(
                    ProgressEventType.TASK_BLOCKED,
                    blocked_reason,
                    step_index=step_idx,
                    extra={"step_id": step.step_id}
                )

                plan.status = "blocked"
                state["status"] = OrchestratorStatus.BLOCKED.value
                state["current_task"] = None
                state["current_job_id"] = None
                state["plan"] = plan.to_dict()
                state["blocked_tasks"].append({
                    "task_id": dod.task_id,
                    "job_id": job_id,
                    "status": "blocked",
                    "mode": ExecutionMode.MANAGER.value,
                    "blocked_step": step_idx + 1,
                    "reason": blocked_reason,
                    "duration_seconds": duration,
                    "blocked_at": datetime.now().isoformat()
                })
                self._save_state(state)

                on_job_error(job_id, blocked_reason)

                return ExecutionResult(
                    success=False,
                    task_id=dod.task_id,
                    status=OrchestratorStatus.BLOCKED,
                    mode=ExecutionMode.MANAGER,
                    output="\n\n".join(all_outputs + [step_output]),
                    files_changed=files_changed,
                    attempts=sum(s.attempts for s in plan.steps),
                    blocked_reason=blocked_reason,
                    claude_invoked=claude_invoked,
                    claude_reason=claude_reason,
                    duration_seconds=duration,
                    plan=plan
                )

            # Collect output
            all_outputs.append(f"## Step {step_idx + 1}: {step.description[:50]}\n{step_output}")

            on_job_progress(job_id, f"Step {step_idx + 1}/{len(plan.steps)} completed")

        # === PHASE 3: COMPLETION ===
        duration = time.time() - start_time

        self._emit_progress_event(
            ProgressEventType.TASK_COMPLETED,
            f"Task completed: {len(plan.steps)} steps executed",
            extra={"duration": duration, "claude_invoked": claude_invoked}
        )

        plan.status = "completed"
        state["status"] = OrchestratorStatus.COMPLETED.value
        state["current_step"] = "complete"
        state["current_task"] = None
        state["current_job_id"] = None
        state["plan"] = plan.to_dict()
        state["completed_tasks"].append({
            "task_id": dod.task_id,
            "job_id": job_id,
            "status": "completed",
            "mode": ExecutionMode.MANAGER.value,
            "steps_completed": len(plan.steps),
            "claude_invoked": claude_invoked,
            "duration_seconds": duration,
            "completed_at": datetime.now().isoformat()
        })
        self._save_state(state)

        on_job_finish(job_id, success=True, files=files_changed)

        self._update_status_md("Completed", f"Manager mode: {len(plan.steps)} steps completed", {
            "Duration": f"{duration:.1f}s",
            "Steps": len(plan.steps),
            "Claude Used": "Yes" if claude_invoked else "No"
        })

        if on_progress:
            on_progress(f"Task completed! {len(plan.steps)} steps executed in {duration:.1f}s")

        return ExecutionResult(
            success=True,
            task_id=dod.task_id,
            status=OrchestratorStatus.COMPLETED,
            mode=ExecutionMode.MANAGER,
            output="\n\n".join(all_outputs),
            files_changed=files_changed,
            attempts=sum(s.attempts for s in plan.steps),
            claude_invoked=claude_invoked,
            claude_reason=claude_reason,
            duration_seconds=duration,
            plan=plan
        )

    def execute_task_simple(
        self,
        task_description: str,
        job_id: str
    ) -> ExecutionResult:
        """
        Execute a simple task without full verification loop.
        Uses ChatGPT executor in self mode.
        """
        state = self._load_state()
        state["status"] = OrchestratorStatus.RUNNING.value
        state["mode"] = ExecutionMode.CHATGPT_SELF.value
        state["current_task"] = task_description
        state["current_job_id"] = job_id
        self._save_state(state)

        on_job_start(job_id, task_description[:100], "Simple ChatGPT execution")

        try:
            result = self.chatgpt_executor.execute_task(
                task_description=task_description,
                job_id=job_id,
                task_type="general"
            )

            state["status"] = OrchestratorStatus.COMPLETED.value
            state["current_task"] = None
            state["current_job_id"] = None
            self._save_state(state)

            on_job_finish(
                job_id,
                success=result.success,
                files=result.files_changed
            )

            return ExecutionResult(
                success=result.success,
                task_id=job_id,
                status=OrchestratorStatus.COMPLETED if result.success else OrchestratorStatus.FAILED,
                mode=ExecutionMode.CHATGPT_SELF,
                output=result.output,
                files_changed=result.files_changed,
                attempts=1
            )

        except Exception as e:
            state["status"] = OrchestratorStatus.FAILED.value
            state["current_task"] = None
            self._save_state(state)

            on_job_error(job_id, str(e))

            return ExecutionResult(
                success=False,
                task_id=job_id,
                status=OrchestratorStatus.FAILED,
                mode=ExecutionMode.CHATGPT_SELF,
                output=str(e),
                attempts=1,
                blocked_reason=str(e)
            )

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status with manager mode details"""
        state = self._load_state()
        return {
            "status": state.get("status"),
            "mode": state.get("mode", ExecutionMode.MANAGER.value),
            "current_step": state.get("current_step", "idle"),
            "current_step_index": state.get("current_step_index", 0),
            "current_task": state.get("current_task"),
            "current_job_id": state.get("current_job_id"),
            "current_dod": state.get("current_dod"),
            "plan": state.get("plan"),
            "attempts": state.get("attempts", 0),
            "max_attempts": state.get("max_attempts", 2),
            "reviews": state.get("reviews", [])[-5:],
            "progress_events": state.get("progress_events", [])[-20:],
            "claude_invoked": state.get("claude_invoked", False),
            "claude_reason": state.get("claude_reason"),
            "blocked_tasks": state.get("blocked_tasks", []),
            "completed_tasks": state.get("completed_tasks", []),
            "recent_history": state.get("history", [])[-5:],
            "updated_at": state.get("updated_at")
        }


# Convenience functions
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator(project_root: Optional[Path] = None) -> Orchestrator:
    """Get or create orchestrator instance"""
    global _orchestrator
    if _orchestrator is None or (project_root and project_root != _orchestrator.project_root):
        _orchestrator = Orchestrator(project_root)
    return _orchestrator


def execute_with_verification(
    task_description: str,
    job_id: str,
    task_type: str = "general",
    max_attempts: int = 3,
    use_manager_mode: bool = True
) -> ExecutionResult:
    """
    Main entry point: execute a task with full verification loop.

    By default uses manager mode for step-by-step execution.
    Set use_manager_mode=False for legacy ChatGPT-first mode.
    """
    orchestrator = get_orchestrator()

    if use_manager_mode and orchestrator.enable_manager_mode:
        return orchestrator.execute_task_manager_mode(
            task_description=task_description,
            job_id=job_id,
            task_type=task_type
        )
    else:
        return orchestrator.execute_task(
            task_description=task_description,
            job_id=job_id,
            task_type=task_type,
            max_attempts=max_attempts
        )


def execute_manager_mode(
    task_description: str,
    job_id: str,
    task_type: str = "general",
    on_progress: Optional[Callable[[str], None]] = None
) -> ExecutionResult:
    """
    Execute a task in manager mode explicitly.
    """
    return get_orchestrator().execute_task_manager_mode(
        task_description=task_description,
        job_id=job_id,
        task_type=task_type,
        on_progress=on_progress
    )
