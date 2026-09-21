"""
AI Workspace Platform - ChatGPT-First Executor Service
Primary executor that tries ChatGPT first, falls back to Claude only when needed.

Execution Modes:
- chatgpt_self: ChatGPT executes, self-reviews, and completes task
- claude_fallback: Claude invoked after ChatGPT failures

Flow:
1. ChatGPT analyzes task
2. ChatGPT creates plan
3. ChatGPT implements
4. ChatGPT self-reviews
5. ChatGPT verifies Definition of Done
6. If issues found -> ChatGPT retries (up to 2 self-attempts)
7. If still failing -> Claude fallback (optional)
8. Final review and complete

This is the NEW primary executor replacing claude_executor as the default.
"""
import json
import time
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from app.core.config import settings


class ExecutionMode(str, Enum):
    """Execution modes for ChatGPT-first architecture"""
    CHATGPT_SELF = "chatgpt_self"       # ChatGPT doing everything itself
    CLAUDE_FALLBACK = "claude_fallback"  # Claude invoked as fallback
    HYBRID = "hybrid"                    # Both models working together


class ExecutionStep(str, Enum):
    """Steps in the self-execution loop"""
    ANALYZE = "analyze"
    PLAN = "plan"
    IMPLEMENT = "implement"
    SELF_REVIEW = "self_review"
    VERIFY_DOD = "verify_dod"
    RETRY = "retry"
    COMPLETE = "complete"
    FALLBACK = "fallback"


@dataclass
class DefinitionOfDone:
    """Definition of Done for a task"""
    task_id: str
    description: str
    required_files: List[str] = field(default_factory=list)
    required_patterns: Dict[str, str] = field(default_factory=dict)
    success_indicators: List[str] = field(default_factory=list)
    completion_checks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "required_files": self.required_files,
            "required_patterns": self.required_patterns,
            "success_indicators": self.success_indicators,
            "completion_checks": self.completion_checks
        }


@dataclass
class SelfReviewResult:
    """Result of self-review step"""
    passed: bool
    checks_performed: List[str] = field(default_factory=list)
    issues_found: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    severity: str = "none"  # none, minor, major, critical
    can_self_fix: bool = True
    needs_claude: bool = False

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
    """Result of ChatGPT-first execution"""
    success: bool
    task_id: str
    mode: ExecutionMode
    current_step: ExecutionStep
    output: str
    files_changed: List[str] = field(default_factory=list)
    attempts: int = 0
    self_review: Optional[SelfReviewResult] = None
    dod_status: Optional[Dict[str, Any]] = None
    claude_invoked: bool = False
    claude_reason: Optional[str] = None
    duration_seconds: float = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "mode": self.mode.value,
            "current_step": self.current_step.value,
            "output": self.output,
            "files_changed": self.files_changed,
            "attempts": self.attempts,
            "self_review": self.self_review.to_dict() if self.self_review else None,
            "dod_status": self.dod_status,
            "claude_invoked": self.claude_invoked,
            "claude_reason": self.claude_reason,
            "duration_seconds": self.duration_seconds,
            "error": self.error
        }


class ChatGPTFirstExecutor:
    """
    ChatGPT-First Executor

    Primary execution flow where ChatGPT handles the entire task lifecycle:
    1. analyze -> plan -> implement -> self_review -> verify_dod -> complete

    Claude is only invoked as fallback when:
    - Task is too complex for self-execution
    - Self-review shows critical issues after 2 attempts
    - Alternative implementation needed
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        max_self_attempts: int = 2,
        enable_claude_fallback: bool = True
    ):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.progress_path = self.project_root / "docs" / "progress"
        self.state_file = self.progress_path / "chatgpt_executor_state.json"
        self.max_self_attempts = max_self_attempts
        self.enable_claude_fallback = enable_claude_fallback
        self._claude_executor = None
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist"""
        self.progress_path.mkdir(parents=True, exist_ok=True)

    @property
    def claude_executor(self):
        """Lazy load Claude executor for fallback"""
        if self._claude_executor is None:
            from app.services.claude_executor import ClaudeExecutor
            self._claude_executor = ClaudeExecutor(project_root=self.project_root)
        return self._claude_executor

    def _load_state(self) -> Dict[str, Any]:
        """Load executor state"""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {
            "mode": ExecutionMode.CHATGPT_SELF.value,
            "current_step": ExecutionStep.ANALYZE.value,
            "current_task": None,
            "job_id": None,
            "attempts": 0,
            "max_attempts": self.max_self_attempts,
            "dod": None,
            "reviews": [],
            "claude_invoked": False,
            "claude_reason": None,
            "history": [],
            "updated_at": None
        }

    def _save_state(self, state: Dict[str, Any]):
        """Save executor state"""
        state["updated_at"] = datetime.now().isoformat()
        self.state_file.write_text(
            json.dumps(state, indent=2, ensure_ascii=False)
        )

    def infer_dod_from_task(self, task_description: str) -> DefinitionOfDone:
        """
        Infer Definition of Done from task description.
        Analyzes the task to determine what success looks like.
        """
        task_lower = task_description.lower()
        task_id = f"task-{int(time.time())}"

        required_files = []
        required_patterns = {}
        success_indicators = []
        completion_checks = []

        # Detect file creation tasks
        file_patterns = [
            (r'creat[e|ing]\s+(?:file\s+)?([^\s,]+\.[a-z]+)', 'create'),
            (r'add\s+(?:file\s+)?([^\s,]+\.[a-z]+)', 'create'),
            (r'implement\s+(?:in\s+)?([^\s,]+\.[a-z]+)', 'modify'),
            (r'(?:modify|update|edit)\s+([^\s,]+\.[a-z]+)', 'modify'),
        ]

        for pattern, action in file_patterns:
            matches = re.findall(pattern, task_lower)
            for match in matches:
                if '/' in match or match.endswith(('.py', '.js', '.ts', '.md', '.json', '.html')):
                    required_files.append(match)
                    success_indicators.append(f"File {action}d: {match}")

        # Detect function/class creation
        if 'function' in task_lower or 'def ' in task_lower:
            success_indicators.append("Function defined")
            completion_checks.append("contains function definition")

        if 'class' in task_lower:
            success_indicators.append("Class defined")
            completion_checks.append("contains class definition")

        # Detect common task types
        if any(word in task_lower for word in ['fix', 'bug', 'error', 'исправ']):
            success_indicators.append("Bug fixed")
            completion_checks.append("no error messages in output")

        if any(word in task_lower for word in ['test', 'тест']):
            success_indicators.append("Tests pass")
            completion_checks.append("test execution successful")

        if any(word in task_lower for word in ['refactor', 'рефактор']):
            success_indicators.append("Code refactored")
            completion_checks.append("code structure improved")

        # Default indicators
        if not success_indicators:
            success_indicators = ["Task completed", "No errors"]
            completion_checks = ["output contains completion indication"]

        return DefinitionOfDone(
            task_id=task_id,
            description=task_description[:200],
            required_files=list(set(required_files)),
            required_patterns=required_patterns,
            success_indicators=success_indicators,
            completion_checks=completion_checks
        )

    def self_review(
        self,
        task_description: str,
        task_output: str,
        dod: DefinitionOfDone,
        attempt: int
    ) -> SelfReviewResult:
        """
        Self-review the task result.
        ChatGPT reviews its own work to find issues before completion.
        """
        checks = []
        issues = []
        suggestions = []

        # Check 1: Required files exist
        for file_path in dod.required_files:
            full_path = self.project_root / file_path
            checks.append(f"File exists: {file_path}")
            if not full_path.exists():
                issues.append(f"Missing required file: {file_path}")
                suggestions.append(f"Create file: {file_path}")

        # Check 2: Required patterns in files
        for file_path, pattern in dod.required_patterns.items():
            full_path = self.project_root / file_path
            checks.append(f"Pattern in {file_path}")
            if full_path.exists():
                content = full_path.read_text()
                if not re.search(pattern, content):
                    issues.append(f"Required pattern not found in {file_path}")
                    suggestions.append(f"Add {pattern} to {file_path}")

        # Check 3: Error indicators in output
        error_patterns = [
            (r'traceback', 'Traceback in output'),
            (r'error:', 'Error message found'),
            (r'exception', 'Exception occurred'),
            (r'failed', 'Failure indicated'),
        ]

        output_lower = task_output.lower()
        for pattern, desc in error_patterns:
            checks.append(f"Check for: {desc}")
            if re.search(pattern, output_lower):
                # Check if it's in error handling context
                context = re.findall(rf'.{{0,30}}{pattern}.{{0,30}}', output_lower)
                if context and not any('handle' in c or 'catch' in c or 'except' in c for c in context):
                    issues.append(desc)

        # Check 4: Output completeness
        checks.append("Output is substantive")
        if len(task_output.strip()) < 30:
            issues.append("Output too short - may be incomplete")
            suggestions.append("Provide complete implementation")

        # Check 5: Success indicators present
        for indicator in dod.success_indicators:
            checks.append(f"Success indicator: {indicator}")
            # Simple heuristic check
            indicator_words = indicator.lower().split()
            if not any(word in output_lower for word in indicator_words if len(word) > 3):
                issues.append(f"Success indicator not confirmed: {indicator}")

        # Determine severity and whether Claude is needed
        if not issues:
            severity = "none"
            can_self_fix = True
            needs_claude = False
        elif len(issues) == 1:
            severity = "minor"
            can_self_fix = True
            needs_claude = False
        elif len(issues) <= 3 and attempt < self.max_self_attempts:
            severity = "major"
            can_self_fix = True
            needs_claude = False
        else:
            severity = "critical"
            can_self_fix = attempt < self.max_self_attempts
            needs_claude = not can_self_fix and self.enable_claude_fallback

        return SelfReviewResult(
            passed=len(issues) == 0,
            checks_performed=checks,
            issues_found=issues,
            suggestions=suggestions,
            severity=severity,
            can_self_fix=can_self_fix,
            needs_claude=needs_claude
        )

    def verify_dod(self, dod: DefinitionOfDone) -> Dict[str, Any]:
        """
        Verify Definition of Done is met.
        Returns detailed status of each check.
        """
        checks = []
        all_passed = True

        # Check required files
        for file_path in dod.required_files:
            full_path = self.project_root / file_path
            exists = full_path.exists()
            checks.append({
                "check": f"file_exists:{file_path}",
                "passed": exists,
                "message": f"File {'exists' if exists else 'missing'}: {file_path}"
            })
            if not exists:
                all_passed = False

        # Check required patterns
        for file_path, pattern in dod.required_patterns.items():
            full_path = self.project_root / file_path
            if full_path.exists():
                content = full_path.read_text()
                found = bool(re.search(pattern, content))
                checks.append({
                    "check": f"pattern:{file_path}",
                    "passed": found,
                    "message": f"Pattern {'found' if found else 'not found'} in {file_path}"
                })
                if not found:
                    all_passed = False
            else:
                checks.append({
                    "check": f"pattern:{file_path}",
                    "passed": False,
                    "message": f"Cannot check pattern - file missing: {file_path}"
                })
                all_passed = False

        return {
            "complete": all_passed,
            "checks": checks,
            "passed_count": sum(1 for c in checks if c["passed"]),
            "total_count": len(checks)
        }

    def create_self_fix_prompt(
        self,
        original_task: str,
        review: SelfReviewResult,
        attempt: int
    ) -> str:
        """Create a prompt for self-fixing issues found in review"""
        issues_text = "\n".join(f"- {i}" for i in review.issues_found)
        suggestions_text = "\n".join(f"- {s}" for s in review.suggestions)

        if attempt == 1:
            return f"""## Self-Correction Required

I found issues in my previous implementation that need fixing.

### Original Task
{original_task}

### Issues Found (Self-Review)
{issues_text}

### Suggested Fixes
{suggestions_text}
"""
        else:
            return f"""## Self-Correction Attempt {attempt}

Attempt {attempt} to fix remaining issues:

### Critical Issues
{issues_text}

### Required Fixes
{suggestions_text}

### Original Task
{original_task[:300]}
"""

    def execute_task(
        self,
        task_description: str,
        job_id: str,
        task_type: str = "general",
        custom_dod: Optional[DefinitionOfDone] = None,
        on_progress: Optional[Callable[[str, str], None]] = None
    ) -> ExecutionResult:
        """
        Execute a task using ChatGPT-first approach.

        Flow:
        1. Analyze task
        2. Create plan
        3. Implement
        4. Self-review
        5. Verify DoD
        6. Retry if needed (up to max_self_attempts)
        7. Claude fallback if still failing (optional)
        8. Complete

        Args:
            task_description: What to accomplish
            job_id: Job ID for tracking
            task_type: Type of task
            custom_dod: Optional custom Definition of Done
            on_progress: Callback for progress updates (step, message)

        Returns:
            ExecutionResult with full details
        """
        start_time = time.time()

        # Initialize state
        state = self._load_state()
        state["mode"] = ExecutionMode.CHATGPT_SELF.value
        state["current_step"] = ExecutionStep.ANALYZE.value
        state["current_task"] = task_description
        state["job_id"] = job_id
        state["attempts"] = 0
        state["claude_invoked"] = False
        state["claude_reason"] = None
        state["reviews"] = []
        self._save_state(state)

        # Create DoD
        dod = custom_dod or self.infer_dod_from_task(task_description)
        state["dod"] = dod.to_dict()
        self._save_state(state)

        if on_progress:
            on_progress(ExecutionStep.ANALYZE.value, f"Analyzing task: {task_description[:50]}...")

        attempt = 0
        last_output = ""
        files_changed = []
        last_review = None

        # IMPORTANT: Store original task separately from execution prompt
        # This prevents review/fix markdown from polluting the actual execution
        original_task = task_description

        # Main execution loop
        while attempt < self.max_self_attempts:
            attempt += 1
            state["attempts"] = attempt

            # Step 1-3: Analyze, Plan, Implement (combined in self-mode)
            state["current_step"] = ExecutionStep.IMPLEMENT.value
            self._save_state(state)

            if on_progress:
                on_progress(ExecutionStep.IMPLEMENT.value, f"Self-executing (attempt {attempt})...")

            # Execute task with real file operations
            # CRITICAL: Always use original_task for file execution, NOT self-fix prompt
            # Self-fix logic is internal to review loop, not for file content generation
            try:
                # For file execution, ALWAYS use the clean original task
                # The self-fix prompt is only for internal retry logic, not for file content
                execution_task = original_task

                # Self execution with real file operations using CLEAN task
                last_output = self._execute_self(execution_task, task_type)

                # Collect files changed from file executor
                if hasattr(self, '_last_files_changed') and self._last_files_changed:
                    files_changed.extend(self._last_files_changed)
                    self._last_files_changed = []

            except Exception as e:
                last_output = f"Execution error: {str(e)}\n{traceback.format_exc()}"

            # Step 4: Self-Review
            state["current_step"] = ExecutionStep.SELF_REVIEW.value
            self._save_state(state)

            if on_progress:
                on_progress(ExecutionStep.SELF_REVIEW.value, "Performing self-review...")

            review = self.self_review(
                task_description=original_task,  # Review against original task
                task_output=last_output,
                dod=dod,
                attempt=attempt
            )
            last_review = review

            state["reviews"].append({
                "attempt": attempt,
                "timestamp": datetime.now().isoformat(),
                "passed": review.passed,
                "issues": review.issues_found,
                "severity": review.severity,
                "can_self_fix": review.can_self_fix,
                "needs_claude": review.needs_claude
            })
            self._save_state(state)

            # Step 5: Verify DoD
            state["current_step"] = ExecutionStep.VERIFY_DOD.value
            self._save_state(state)

            if on_progress:
                on_progress(ExecutionStep.VERIFY_DOD.value, "Verifying Definition of Done...")

            dod_status = self.verify_dod(dod)

            # Check if complete
            if review.passed and dod_status["complete"]:
                # Success!
                duration = time.time() - start_time

                state["current_step"] = ExecutionStep.COMPLETE.value
                state["current_task"] = None   # Clear stale task on completion
                state["job_id"] = None
                state["history"].append({
                    "job_id": job_id,
                    "task": task_description[:100],
                    "status": "completed",
                    "mode": ExecutionMode.CHATGPT_SELF.value,
                    "attempts": attempt,
                    "duration": duration,
                    "completed_at": datetime.now().isoformat()
                })
                self._save_state(state)

                if on_progress:
                    on_progress(ExecutionStep.COMPLETE.value, f"Task completed in {attempt} attempt(s)")

                return ExecutionResult(
                    success=True,
                    task_id=dod.task_id,
                    mode=ExecutionMode.CHATGPT_SELF,
                    current_step=ExecutionStep.COMPLETE,
                    output=last_output,
                    files_changed=list(set(files_changed)),
                    attempts=attempt,
                    self_review=review,
                    dod_status=dod_status,
                    claude_invoked=False,
                    duration_seconds=duration
                )

            # Check if should retry or need Claude
            if review.can_self_fix and attempt < self.max_self_attempts:
                state["current_step"] = ExecutionStep.RETRY.value
                self._save_state(state)

                if on_progress:
                    on_progress(ExecutionStep.RETRY.value, f"Self-fixing {len(review.issues_found)} issues...")

                # Will retry in next iteration
                continue

            # Check if Claude fallback needed
            if review.needs_claude and self.enable_claude_fallback:
                state["current_step"] = ExecutionStep.FALLBACK.value
                state["claude_invoked"] = True
                state["claude_reason"] = f"Self-execution failed after {attempt} attempts: {review.issues_found[0] if review.issues_found else 'unknown'}"
                self._save_state(state)

                if on_progress:
                    on_progress(ExecutionStep.FALLBACK.value, "Invoking Claude as fallback...")

                # Execute with Claude
                try:
                    claude_result = self.claude_executor.execute(
                        prompt=task_description,
                        task_type=task_type,
                        force_mode=None  # Let Claude executor decide
                    )

                    last_output = claude_result.answer
                    if claude_result.changed_files:
                        files_changed.extend(claude_result.changed_files)

                    # Re-verify DoD after Claude
                    dod_status = self.verify_dod(dod)

                    if dod_status["complete"]:
                        duration = time.time() - start_time

                        state["current_step"] = ExecutionStep.COMPLETE.value
                        state["history"].append({
                            "job_id": job_id,
                            "task": task_description[:100],
                            "status": "completed_with_fallback",
                            "mode": ExecutionMode.CLAUDE_FALLBACK.value,
                            "attempts": attempt,
                            "duration": duration,
                            "completed_at": datetime.now().isoformat()
                        })
                        self._save_state(state)

                        if on_progress:
                            on_progress(ExecutionStep.COMPLETE.value, "Completed with Claude fallback")

                        return ExecutionResult(
                            success=True,
                            task_id=dod.task_id,
                            mode=ExecutionMode.CLAUDE_FALLBACK,
                            current_step=ExecutionStep.COMPLETE,
                            output=last_output,
                            files_changed=list(set(files_changed)),
                            attempts=attempt,
                            self_review=review,
                            dod_status=dod_status,
                            claude_invoked=True,
                            claude_reason=state["claude_reason"],
                            duration_seconds=duration
                        )

                except Exception as e:
                    last_output = f"Claude fallback failed: {str(e)}"

        # Task failed after all attempts
        duration = time.time() - start_time

        state["current_task"] = None   # Clear stale task on failure
        state["job_id"] = None
        state["current_step"] = None
        state["history"].append({
            "job_id": job_id,
            "task": task_description[:100],
            "status": "failed",
            "mode": state["mode"],
            "attempts": attempt,
            "issues": last_review.issues_found if last_review else [],
            "duration": duration,
            "failed_at": datetime.now().isoformat()
        })
        self._save_state(state)

        if on_progress:
            on_progress(ExecutionStep.COMPLETE.value, f"Task failed after {attempt} attempts")

        return ExecutionResult(
            success=False,
            task_id=dod.task_id,
            mode=ExecutionMode(state["mode"]),
            current_step=ExecutionStep.COMPLETE,
            output=last_output,
            files_changed=list(set(files_changed)),
            attempts=attempt,
            self_review=last_review,
            dod_status=dod_status if 'dod_status' in dir() else None,
            claude_invoked=state["claude_invoked"],
            claude_reason=state.get("claude_reason"),
            duration_seconds=duration,
            error=f"Failed after {attempt} self-attempts"
        )

    def _execute_self(self, prompt: str, task_type: str) -> str:
        """
        Execute task in self mode using real file operations.
        Uses FileExecutor for actual file creation/modification.
        """
        from app.services.file_executor import get_file_executor

        # Get file executor instance
        file_executor = get_file_executor(self.project_root)

        # Generate a job ID for this execution step
        step_job_id = f"step-{int(time.time())}"

        # Progress collector for this execution
        progress_events = []

        def collect_progress(stage: str, message: str):
            progress_events.append(f"[{stage}] {message}")

        # Execute with real file operations
        result = file_executor.execute_task(
            task_description=prompt,
            job_id=step_job_id,
            task_type=task_type,
            on_progress=collect_progress
        )

        # Store files changed for parent executor to use
        if not hasattr(self, '_last_files_changed'):
            self._last_files_changed = []
        self._last_files_changed = result.files_changed

        # Build output from real execution result
        output_parts = [
            "## Execution Result",
            "",
            f"**Task:** {prompt[:200]}{'...' if len(prompt) > 200 else ''}",
            f"**Type:** {task_type}",
            f"**Status:** {'Success' if result.success else 'Failed'}",
            f"**Duration:** {result.duration_seconds:.2f}s",
            "",
        ]

        # Add files changed
        if result.files_changed:
            output_parts.append("### Files Changed")
            for f in result.files_changed:
                output_parts.append(f"- `{f}`")
            output_parts.append("")

        # Add operations summary
        if result.operations:
            output_parts.append("### Operations Performed")
            for op in result.operations:
                status = "✓" if op.success else "✗"
                output_parts.append(f"- {status} {op.operation.value}: {op.path}")
                if op.content_preview and len(op.content_preview) < 200:
                    output_parts.append(f"  Preview: {op.content_preview[:100]}...")
            output_parts.append("")

        # Add plan info
        if result.plan:
            output_parts.append(f"### Execution Plan ({len(result.plan.steps)} steps)")
            for step in result.plan.steps:
                status_icon = "✓" if step.status.value == "completed" else "○"
                output_parts.append(f"- {status_icon} {step.description}")
            output_parts.append("")

        # Add progress events
        if progress_events:
            output_parts.append("### Progress Log")
            for event in progress_events[-10:]:  # Last 10 events
                output_parts.append(f"- {event}")
            output_parts.append("")

        # Add main output
        if result.output:
            output_parts.append("### Output")
            output_parts.append(result.output)

        # Add error if present
        if result.error:
            output_parts.append("")
            output_parts.append(f"### Error")
            output_parts.append(result.error)

        return "\n".join(output_parts)

    def get_status(self) -> Dict[str, Any]:
        """Get current executor status"""
        state = self._load_state()
        return {
            "mode": state.get("mode"),
            "current_step": state.get("current_step"),
            "current_task": state.get("current_task"),
            "job_id": state.get("job_id"),
            "attempts": state.get("attempts", 0),
            "max_attempts": state.get("max_attempts", self.max_self_attempts),
            "dod": state.get("dod"),
            "reviews": state.get("reviews", [])[-3:],
            "claude_invoked": state.get("claude_invoked", False),
            "claude_reason": state.get("claude_reason"),
            "history": state.get("history", [])[-5:],
            "updated_at": state.get("updated_at")
        }


# Convenience functions
_executor: Optional[ChatGPTFirstExecutor] = None


def get_chatgpt_executor(project_root: Optional[Path] = None) -> ChatGPTFirstExecutor:
    """Get or create ChatGPT-first executor instance"""
    global _executor
    if _executor is None or (project_root and project_root != _executor.project_root):
        _executor = ChatGPTFirstExecutor(project_root)
    return _executor


def execute_chatgpt_first(
    task_description: str,
    job_id: str,
    task_type: str = "general",
    on_progress: Optional[Callable[[str, str], None]] = None
) -> ExecutionResult:
    """
    Main entry point: execute a task using ChatGPT-first approach.
    """
    return get_chatgpt_executor().execute_task(
        task_description=task_description,
        job_id=job_id,
        task_type=task_type,
        on_progress=on_progress
    )


def get_execution_status() -> Dict[str, Any]:
    """Get current execution status"""
    return get_chatgpt_executor().get_status()
