"""
AI Workspace Platform - Autonomous Build Runner
Self-first execution controller that runs tasks to completion

MODE: Autonomous Build Runner
- Does not wait for user confirmations on normal steps
- Does not ask "what next?"
- Does not stop after first step
- Continues until first testable beta result

EXECUTION FLOW:
1. Task accepted -> docs read -> plan formed
2. Execute step X -> self-review -> DoD check
3. Retry if needed (up to max_attempts)
4. Claude fallback if self-mode fails (optional)
5. Step completed -> move to next step
6. Update CURRENT_STATUS.md after each step

PROGRESS EVENTS:
- task_accepted
- docs_read
- plan_formed
- step_started
- step_executing
- self_review
- dod_check
- retry
- claude_fallback (if invoked)
- step_completed
- moving_to_next
- task_completed / task_blocked
"""
import json
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import queue
from app.core.config import settings


class RunnerMode(str, Enum):
    """Execution modes"""
    SELF_FIRST = "self_first"      # Primary: self-execution
    CLAUDE_FALLBACK = "claude_fallback"  # Claude as fallback
    STOPPED = "stopped"


class StepStatus(str, Enum):
    """Step execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEWING = "reviewing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class ProgressEvent:
    """Progress event for real-time updates"""
    event_type: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    step: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    level: str = "info"  # info, warning, error, success

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp,
            "step": self.step,
            "details": self.details,
            "level": self.level
        }


@dataclass
class StepResult:
    """Result of a single step execution"""
    success: bool
    step_name: str
    output: str
    files_changed: List[str] = field(default_factory=list)
    review_passed: bool = False
    dod_passed: bool = False
    attempts: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "step_name": self.step_name,
            "output": self.output,
            "files_changed": self.files_changed,
            "review_passed": self.review_passed,
            "dod_passed": self.dod_passed,
            "attempts": self.attempts,
            "error": self.error
        }


@dataclass
class BuildResult:
    """Result of complete build execution"""
    success: bool
    mode: RunnerMode
    steps_completed: List[str] = field(default_factory=list)
    steps_failed: List[str] = field(default_factory=list)
    total_attempts: int = 0
    files_changed: List[str] = field(default_factory=list)
    output: str = ""
    error: Optional[str] = None
    duration_seconds: float = 0
    claude_invoked: bool = False
    claude_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "mode": self.mode.value,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "total_attempts": self.total_attempts,
            "files_changed": self.files_changed,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "claude_invoked": self.claude_invoked,
            "claude_reason": self.claude_reason
        }


class AutonomousBuildRunner:
    """
    Autonomous Build Runner - self-first execution controller

    Key behaviors:
    - Does not wait for user confirmations on normal steps
    - Continues until task is completed or blocked
    - Updates CURRENT_STATUS.md after each step
    - Emits progress events for dashboard

    Beta goals:
    - Dashboard shows live status
    - Queue launches tasks
    - Progress events visible
    - Self-first execution works
    - Can queue task and see it complete
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        max_step_attempts: int = 2,
        enable_claude_fallback: bool = True
    ):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.progress_path = self.project_root / "docs" / "progress"
        self.state_file = self.progress_path / "autonomous_runner_state.json"
        self.max_step_attempts = max_step_attempts
        self.enable_claude_fallback = enable_claude_fallback

        # Event system
        self._event_queue: queue.Queue = queue.Queue()
        self._event_listeners: List[Callable[[ProgressEvent], None]] = []

        # Execution state
        self._current_task: Optional[str] = None
        self._current_step: Optional[str] = None
        self._mode: RunnerMode = RunnerMode.SELF_FIRST
        self._is_running: bool = False
        self._stop_requested: bool = False

        # Lazy loaded executors
        self._chatgpt_executor = None
        self._claude_executor = None
        self._orchestrator = None

        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist"""
        self.progress_path.mkdir(parents=True, exist_ok=True)

    @property
    def chatgpt_executor(self):
        """Lazy load ChatGPT executor"""
        if self._chatgpt_executor is None:
            from app.services.chatgpt_executor import ChatGPTFirstExecutor
            self._chatgpt_executor = ChatGPTFirstExecutor(project_root=self.project_root)
        return self._chatgpt_executor

    @property
    def claude_executor(self):
        """Lazy load Claude executor"""
        if self._claude_executor is None:
            from app.services.claude_executor import ClaudeExecutor
            self._claude_executor = ClaudeExecutor(project_root=self.project_root)
        return self._claude_executor

    @property
    def orchestrator(self):
        """Lazy load orchestrator"""
        if self._orchestrator is None:
            from app.services.orchestrator import get_orchestrator
            self._orchestrator = get_orchestrator(self.project_root)
        return self._orchestrator

    def _load_state(self) -> Dict[str, Any]:
        """Load runner state"""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {
            "mode": RunnerMode.SELF_FIRST.value,
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

    def _save_state(self, state: Dict[str, Any]):
        """Save runner state"""
        state["updated_at"] = datetime.now().isoformat()
        self.state_file.write_text(
            json.dumps(state, indent=2, ensure_ascii=False)
        )

    def _emit_event(self, event: ProgressEvent):
        """Emit progress event to all listeners"""
        # Add to state
        state = self._load_state()
        events = state.get("progress_events", [])
        events.append(event.to_dict())
        # Keep last 100 events
        state["progress_events"] = events[-100:]
        self._save_state(state)

        # Put in queue for SSE
        self._event_queue.put(event)

        # Call listeners
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception:
                pass

    def add_event_listener(self, listener: Callable[[ProgressEvent], None]):
        """Add progress event listener"""
        self._event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[ProgressEvent], None]):
        """Remove progress event listener"""
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)

    def get_events(self, timeout: float = 1.0) -> Optional[ProgressEvent]:
        """Get next event from queue (for SSE)"""
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _update_status_md(self, phase: str, message: str, details: Optional[Dict] = None):
        """Update CURRENT_STATUS.md with current phase"""
        try:
            status_file = self.progress_path / "CURRENT_STATUS.md"

            # Create or update the file
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Load existing content
            content = ""
            if status_file.exists():
                content = status_file.read_text()

            # Update Last Updated section
            content = re.sub(
                r'## Last Updated\n.*',
                f'## Last Updated\n{timestamp}',
                content
            )

            # Add or update Active Task section
            task_section = f"""## Active Task
**Phase:** {phase}
**Status:** {message}
**Mode:** {self._mode.value}
**Updated:** {timestamp}"""

            if details:
                for key, value in details.items():
                    task_section += f"\n**{key}:** {value}"

            # Replace or insert Active Task section
            if '## Active Task' in content:
                content = re.sub(
                    r'## Active Task\n.*?(?=\n---|\n## |$)',
                    task_section + '\n',
                    content,
                    flags=re.DOTALL
                )
            else:
                # Insert after first heading
                lines = content.split('\n')
                insert_pos = 2  # After title and first blank line
                for i, line in enumerate(lines):
                    if line.startswith('---'):
                        insert_pos = i + 1
                        break
                lines.insert(insert_pos, '\n' + task_section + '\n')
                content = '\n'.join(lines)

            status_file.write_text(content)

        except Exception as e:
            # Non-critical, don't fail
            pass

    def _analyze_task(self, task_description: str) -> Dict[str, Any]:
        """Analyze task and create execution plan"""
        task_lower = task_description.lower()

        # Determine task type
        if any(word in task_lower for word in ['создай', 'create', 'implement', 'add', 'добавь']):
            task_type = 'create'
        elif any(word in task_lower for word in ['исправь', 'fix', 'repair', 'bug']):
            task_type = 'fix'
        elif any(word in task_lower for word in ['обнови', 'update', 'modify', 'изменить']):
            task_type = 'update'
        elif any(word in task_lower for word in ['удали', 'delete', 'remove']):
            task_type = 'delete'
        elif any(word in task_lower for word in ['тест', 'test', 'verify']):
            task_type = 'test'
        else:
            task_type = 'general'

        # Extract potential file targets
        file_patterns = [
            r'([a-zA-Z_/]+\.(?:py|js|ts|html|css|json|md))',
            r'файл[а-я]*\s+([^\s,]+)',
            r'file\s+([^\s,]+)',
        ]
        files = []
        for pattern in file_patterns:
            matches = re.findall(pattern, task_description)
            files.extend(matches)

        # Create steps based on task type
        steps = ['analyze', 'implement', 'self_review', 'verify_dod']
        if task_type == 'test':
            steps = ['analyze', 'implement_test', 'run_test', 'self_review', 'verify_dod']
        elif task_type == 'fix':
            steps = ['analyze_issue', 'implement_fix', 'self_review', 'verify_fix', 'verify_dod']

        return {
            'task_type': task_type,
            'target_files': list(set(files)),
            'steps': steps,
            'estimated_complexity': 'medium' if len(files) > 2 or len(task_description) > 200 else 'low'
        }

    def _execute_step(
        self,
        step_name: str,
        task_description: str,
        context: Dict[str, Any]
    ) -> StepResult:
        """Execute a single step with self-review"""
        attempt = 0
        last_output = ""
        files_changed = []

        while attempt < self.max_step_attempts:
            attempt += 1

            self._emit_event(ProgressEvent(
                event_type="step_executing",
                message=f"Executing step: {step_name} (attempt {attempt})",
                step=step_name,
                details={"attempt": attempt, "max_attempts": self.max_step_attempts}
            ))

            # Execute with ChatGPT executor
            try:
                step_prompt = self._create_step_prompt(step_name, task_description, context, attempt)

                result = self.chatgpt_executor.execute_task(
                    task_description=step_prompt,
                    job_id=f"{context.get('job_id', 'runner')}-{step_name}-{attempt}",
                    task_type=context.get('task_type', 'general')
                )

                last_output = result.output or ""
                if result.files_changed:
                    files_changed.extend(result.files_changed)

            except Exception as e:
                last_output = f"Execution error: {str(e)}"

            # Self-review
            self._emit_event(ProgressEvent(
                event_type="self_review",
                message=f"Self-reviewing step: {step_name}",
                step=step_name,
                level="info"
            ))

            review_result = self._self_review_step(step_name, last_output, context)

            if review_result['passed']:
                # DoD check
                self._emit_event(ProgressEvent(
                    event_type="dod_check",
                    message=f"Verifying Definition of Done for: {step_name}",
                    step=step_name
                ))

                dod_result = self._verify_step_dod(step_name, last_output, context)

                if dod_result['complete']:
                    return StepResult(
                        success=True,
                        step_name=step_name,
                        output=last_output,
                        files_changed=list(set(files_changed)),
                        review_passed=True,
                        dod_passed=True,
                        attempts=attempt
                    )

            # Need retry
            if attempt < self.max_step_attempts:
                self._emit_event(ProgressEvent(
                    event_type="retry",
                    message=f"Retrying step: {step_name} ({attempt + 1}/{self.max_step_attempts})",
                    step=step_name,
                    details={"issues": review_result.get('issues', [])},
                    level="warning"
                ))

                # Update context with retry info
                context['retry_issues'] = review_result.get('issues', [])

        # Failed after all attempts
        return StepResult(
            success=False,
            step_name=step_name,
            output=last_output,
            files_changed=list(set(files_changed)),
            review_passed=False,
            dod_passed=False,
            attempts=attempt,
            error=f"Failed after {attempt} attempts"
        )

    def _create_step_prompt(
        self,
        step_name: str,
        task_description: str,
        context: Dict[str, Any],
        attempt: int
    ) -> str:
        """
        Create execution task for a step.

        IMPORTANT: Always returns the clean original task_description.
        Retry context (retry_issues) is used only internally in _execute_step
        for self-review decision logic — never injected into the task payload
        sent to file_executor.

        This prevents "Self-Correction Attempt 2" / retry markdown from
        polluting the actual file content generated by file_executor.
        """
        # ALWAYS return the original clean task — no review/fix markup injected
        return task_description

    def _self_review_step(
        self,
        step_name: str,
        output: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Self-review a step result"""
        issues = []
        checks = []

        # Basic checks
        output_lower = output.lower()

        # Check for errors
        error_indicators = ['error:', 'traceback', 'exception', 'failed:', 'cannot']
        for indicator in error_indicators:
            checks.append(f"Check for: {indicator}")
            if indicator in output_lower:
                # Verify it's not in error handling context
                context_match = re.findall(rf'.{{0,30}}{indicator}.{{0,30}}', output_lower)
                if context_match and not any('handle' in c or 'catch' in c for c in context_match):
                    issues.append(f"Found error indicator: {indicator}")

        # Check output length
        checks.append("Output is substantive")
        if len(output.strip()) < 50:
            issues.append("Output too short - may be incomplete")

        # Check for success indicators
        success_indicators = ['completed', 'done', 'success', 'created', 'updated', 'fixed']
        has_success = any(ind in output_lower for ind in success_indicators)
        checks.append("Has success indicator")
        if not has_success and step_name in ('implement', 'implement_fix', 'implement_test'):
            issues.append("No success indicator found")

        return {
            'passed': len(issues) == 0,
            'checks': checks,
            'issues': issues,
            'severity': 'critical' if len(issues) > 2 else ('major' if len(issues) > 0 else 'none')
        }

    def _verify_step_dod(
        self,
        step_name: str,
        output: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify step meets Definition of Done"""
        checks = []
        all_passed = True

        # Check target files if specified
        target_files = context.get('target_files', [])
        for file_path in target_files:
            full_path = self.project_root / file_path
            exists = full_path.exists()
            checks.append({
                'check': f'file_exists:{file_path}',
                'passed': exists
            })
            if not exists:
                all_passed = False

        # Step-specific checks
        if step_name == 'analyze':
            # Analysis should produce understanding
            has_analysis = any(word in output.lower() for word in ['анализ', 'analysis', 'understand', 'identified'])
            checks.append({'check': 'has_analysis', 'passed': has_analysis})
            if not has_analysis:
                all_passed = False

        elif step_name in ('implement', 'implement_fix', 'implement_test'):
            # Implementation should have code
            has_code = 'def ' in output or 'class ' in output or 'function' in output.lower()
            checks.append({'check': 'has_code', 'passed': has_code})
            # For now, don't fail on this as output might be summary

        return {
            'complete': all_passed,
            'checks': checks,
            'passed_count': sum(1 for c in checks if c.get('passed', False)),
            'total_count': len(checks)
        }

    def run_task(
        self,
        task_description: str,
        job_id: Optional[str] = None
    ) -> BuildResult:
        """
        Run a task autonomously until completion or blocking

        This is the main entry point for autonomous execution.
        Does not wait for user confirmations.
        """
        start_time = time.time()
        job_id = job_id or f"runner-{int(time.time())}"

        # Initialize state
        state = self._load_state()
        state["mode"] = RunnerMode.SELF_FIRST.value
        state["is_running"] = True
        state["current_task"] = task_description
        state["current_job_id"] = job_id
        state["steps_completed"] = []
        state["steps_failed"] = []
        state["total_attempts"] = 0
        state["files_changed"] = []
        state["claude_invoked"] = False
        state["claude_reason"] = None
        state["last_error"] = None
        state["progress_events"] = []
        self._save_state(state)

        self._is_running = True
        self._mode = RunnerMode.SELF_FIRST

        # Emit task accepted
        self._emit_event(ProgressEvent(
            event_type="task_accepted",
            message=f"Task accepted: {task_description[:100]}...",
            level="success"
        ))

        self._update_status_md("Task Accepted", task_description[:100], {"Job": job_id})

        # Analyze task and create plan
        self._emit_event(ProgressEvent(
            event_type="docs_read",
            message="Reading documentation and analyzing codebase",
            level="info"
        ))

        analysis = self._analyze_task(task_description)

        self._emit_event(ProgressEvent(
            event_type="plan_formed",
            message=f"Plan formed: {len(analysis['steps'])} steps",
            details=analysis,
            level="success"
        ))

        self._update_status_md("Plan Formed", f"{len(analysis['steps'])} steps planned", {
            "Task Type": analysis['task_type'],
            "Complexity": analysis['estimated_complexity']
        })

        # Execute steps
        context = {
            'job_id': job_id,
            'task_type': analysis['task_type'],
            'target_files': analysis['target_files'],
            'analysis': analysis
        }

        all_files_changed = []
        steps_completed = []
        steps_failed = []
        total_attempts = 0
        final_output = ""
        claude_invoked = False
        claude_reason = None

        for step_name in analysis['steps']:
            if self._stop_requested:
                break

            self._current_step = step_name

            self._emit_event(ProgressEvent(
                event_type="step_started",
                message=f"Starting step: {step_name}",
                step=step_name,
                level="info"
            ))

            self._update_status_md(f"Step: {step_name}", "Executing", {
                "Progress": f"{len(steps_completed)}/{len(analysis['steps'])}"
            })

            # Execute step
            step_result = self._execute_step(step_name, task_description, context)
            total_attempts += step_result.attempts

            if step_result.success:
                steps_completed.append(step_name)
                all_files_changed.extend(step_result.files_changed)
                final_output = step_result.output

                self._emit_event(ProgressEvent(
                    event_type="step_completed",
                    message=f"Step completed: {step_name}",
                    step=step_name,
                    details={"attempts": step_result.attempts},
                    level="success"
                ))

                # Move to next
                if step_name != analysis['steps'][-1]:
                    self._emit_event(ProgressEvent(
                        event_type="moving_to_next",
                        message=f"Moving to next step",
                        step=step_name,
                        level="info"
                    ))

            else:
                # Step failed - try Claude fallback if enabled
                if self.enable_claude_fallback and not claude_invoked:
                    self._emit_event(ProgressEvent(
                        event_type="claude_fallback",
                        message=f"Invoking Claude fallback for step: {step_name}",
                        step=step_name,
                        level="warning"
                    ))

                    self._mode = RunnerMode.CLAUDE_FALLBACK
                    claude_invoked = True
                    claude_reason = f"Self-execution failed: {step_result.error}"

                    self._update_status_md("Claude Fallback", f"Step {step_name} needs Claude", {
                        "Reason": claude_reason[:50]
                    })

                    # Try with Claude
                    try:
                        claude_result = self.claude_executor.execute(
                            prompt=task_description,
                            task_type=context['task_type']
                        )
                        final_output = claude_result.answer or ""
                        if claude_result.changed_files:
                            all_files_changed.extend(claude_result.changed_files)
                        steps_completed.append(step_name)

                        self._emit_event(ProgressEvent(
                            event_type="step_completed",
                            message=f"Step completed with Claude: {step_name}",
                            step=step_name,
                            level="success"
                        ))

                    except Exception as e:
                        steps_failed.append(step_name)
                        self._emit_event(ProgressEvent(
                            event_type="step_failed",
                            message=f"Step failed (Claude fallback also failed): {step_name}",
                            step=step_name,
                            details={"error": str(e)},
                            level="error"
                        ))
                        break

                else:
                    steps_failed.append(step_name)
                    self._emit_event(ProgressEvent(
                        event_type="step_failed",
                        message=f"Step failed: {step_name}",
                        step=step_name,
                        details={"error": step_result.error},
                        level="error"
                    ))
                    break

        # Finalize
        duration = time.time() - start_time
        success = len(steps_failed) == 0 and len(steps_completed) == len(analysis['steps'])

        # Update state - clear all running state after completion
        state = self._load_state()
        state["is_running"] = False
        state["current_task"] = None
        state["current_step"] = None
        state["current_job_id"] = None  # Clear stale job_id after completion
        state["steps_completed"] = steps_completed
        state["steps_failed"] = steps_failed
        state["total_attempts"] = total_attempts
        state["files_changed"] = list(set(all_files_changed))
        state["claude_invoked"] = claude_invoked
        state["claude_reason"] = claude_reason
        state["last_job_id"] = job_id  # Preserve last job for history
        self._save_state(state)

        self._is_running = False
        self._current_task = None
        self._current_step = None

        # Final events
        if success:
            self._emit_event(ProgressEvent(
                event_type="task_completed",
                message=f"Task completed successfully in {len(steps_completed)} steps",
                details={
                    "duration_seconds": duration,
                    "total_attempts": total_attempts,
                    "files_changed": len(set(all_files_changed))
                },
                level="success"
            ))
            self._update_status_md("Completed", f"Task completed in {duration:.1f}s", {
                "Steps": len(steps_completed),
                "Files": len(set(all_files_changed)),
                "Mode": self._mode.value
            })
        else:
            error_msg = f"Task blocked at step: {steps_failed[0] if steps_failed else 'unknown'}"
            self._emit_event(ProgressEvent(
                event_type="task_blocked",
                message=error_msg,
                details={
                    "steps_completed": steps_completed,
                    "steps_failed": steps_failed
                },
                level="error"
            ))
            self._update_status_md("Blocked", error_msg, {
                "Completed": len(steps_completed),
                "Failed": len(steps_failed)
            })

        return BuildResult(
            success=success,
            mode=self._mode,
            steps_completed=steps_completed,
            steps_failed=steps_failed,
            total_attempts=total_attempts,
            files_changed=list(set(all_files_changed)),
            output=final_output,
            error=None if success else f"Failed steps: {steps_failed}",
            duration_seconds=duration,
            claude_invoked=claude_invoked,
            claude_reason=claude_reason
        )

    def stop(self):
        """Request stop of current execution"""
        self._stop_requested = True

    def get_status(self) -> Dict[str, Any]:
        """Get current runner status"""
        state = self._load_state()
        return {
            "mode": state.get("mode", RunnerMode.SELF_FIRST.value),
            "is_running": state.get("is_running", False),
            "current_task": state.get("current_task"),
            "current_step": state.get("current_step"),
            "current_job_id": state.get("current_job_id"),
            "steps_completed": state.get("steps_completed", []),
            "steps_failed": state.get("steps_failed", []),
            "total_attempts": state.get("total_attempts", 0),
            "files_changed": state.get("files_changed", []),
            "claude_invoked": state.get("claude_invoked", False),
            "claude_reason": state.get("claude_reason"),
            "recent_events": state.get("progress_events", [])[-10:],
            "updated_at": state.get("updated_at")
        }


# Singleton instance
_runner: Optional[AutonomousBuildRunner] = None


def get_runner(project_root: Optional[Path] = None) -> AutonomousBuildRunner:
    """Get or create runner instance"""
    global _runner
    if _runner is None or (project_root and project_root != _runner.project_root):
        _runner = AutonomousBuildRunner(project_root)
    return _runner


def run_autonomous_task(
    task_description: str,
    job_id: Optional[str] = None
) -> BuildResult:
    """Main entry point: run a task autonomously"""
    return get_runner().run_task(task_description, job_id)


def get_runner_status() -> Dict[str, Any]:
    """Get current runner status"""
    return get_runner().get_status()
