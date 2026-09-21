"""
AI Workspace Platform - Supervisor Service
Manages task execution with review loops and completion validation

The Supervisor:
1. Checks if task result matches the request
2. Verifies required files were created
3. Detects incomplete work
4. Creates follow-up tasks for fixes
5. Retries failed tasks with progressive escalation
6. Updates status accurately
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from app.core.config import settings


class TaskVerdict(str, Enum):
    """Result of task verification"""
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NEEDS_FIX = "needs_fix"
    BLOCKED = "blocked"
    FAILED = "failed"


class BlockerType(str, Enum):
    """Types of blockers"""
    MISSING_FILE = "missing_file"
    MISSING_FUNCTION = "missing_function"
    TEST_FAILURE = "test_failure"
    BUILD_ERROR = "build_error"
    VALIDATION_ERROR = "validation_error"
    REPEATED_FAILURE = "repeated_failure"
    UNKNOWN = "unknown"


@dataclass
class DefinitionOfDone:
    """Defines what constitutes a completed task"""
    task_id: str
    description: str
    required_files: List[str] = field(default_factory=list)
    required_patterns: Dict[str, str] = field(default_factory=dict)  # file -> pattern
    expected_outputs: List[str] = field(default_factory=list)
    validation_commands: List[str] = field(default_factory=list)
    max_retries: int = 3


@dataclass
class VerificationResult:
    """Result of task verification"""
    verdict: TaskVerdict
    issues: List[str] = field(default_factory=list)
    missing_files: List[str] = field(default_factory=list)
    missing_patterns: Dict[str, str] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)
    blocker_type: Optional[BlockerType] = None


@dataclass
class TaskAttempt:
    """Record of a task execution attempt"""
    attempt_number: int
    timestamp: str
    prompt: str
    result: Optional[str]
    verdict: TaskVerdict
    issues: List[str] = field(default_factory=list)


class Supervisor:
    """
    Supervises task execution with review loops.

    Key responsibilities:
    - Define completion criteria for tasks
    - Verify task results
    - Create follow-up tasks for incomplete work
    - Track retry attempts
    - Escalate persistent failures
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.progress_path = self.project_root / "docs" / "progress"
        self.supervisor_state_file = self.progress_path / "supervisor_state.json"
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist"""
        self.progress_path.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> Dict[str, Any]:
        """Load supervisor state"""
        if self.supervisor_state_file.exists():
            try:
                return json.loads(self.supervisor_state_file.read_text())
            except Exception:
                pass
        return {
            "active_task": None,
            "attempts": [],
            "total_retries": 0,
            "blocked_tasks": [],
            "completed_tasks": [],
            "updated_at": None
        }

    def _save_state(self, state: Dict[str, Any]):
        """Save supervisor state"""
        state["updated_at"] = datetime.now().isoformat()
        self.supervisor_state_file.write_text(
            json.dumps(state, indent=2, ensure_ascii=False)
        )

    def create_definition_of_done(
        self,
        task_id: str,
        description: str,
        required_files: Optional[List[str]] = None,
        required_patterns: Optional[Dict[str, str]] = None,
        expected_outputs: Optional[List[str]] = None,
        max_retries: int = 3
    ) -> DefinitionOfDone:
        """
        Create a Definition of Done for a task.

        Args:
            task_id: Unique task identifier
            description: What the task should accomplish
            required_files: Files that must exist after completion
            required_patterns: Patterns that must be found in files
            expected_outputs: Expected output strings
            max_retries: Maximum retry attempts

        Returns:
            DefinitionOfDone object
        """
        dod = DefinitionOfDone(
            task_id=task_id,
            description=description,
            required_files=required_files or [],
            required_patterns=required_patterns or {},
            expected_outputs=expected_outputs or [],
            max_retries=max_retries
        )

        # Save DoD to file
        dod_file = self.progress_path / f"dod_{task_id}.json"
        dod_file.write_text(json.dumps({
            "task_id": dod.task_id,
            "description": dod.description,
            "required_files": dod.required_files,
            "required_patterns": dod.required_patterns,
            "expected_outputs": dod.expected_outputs,
            "max_retries": dod.max_retries,
            "created_at": datetime.now().isoformat()
        }, indent=2, ensure_ascii=False))

        return dod

    def verify_task_completion(
        self,
        dod: DefinitionOfDone,
        task_output: Optional[str] = None
    ) -> VerificationResult:
        """
        Verify if a task meets its Definition of Done.

        Args:
            dod: The Definition of Done to check against
            task_output: Output from the task execution

        Returns:
            VerificationResult with verdict and issues
        """
        issues = []
        missing_files = []
        missing_patterns = {}

        # Check required files
        for file_path in dod.required_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                issues.append(f"Missing required file: {file_path}")
                missing_files.append(file_path)

        # Check required patterns in files
        for file_path, pattern in dod.required_patterns.items():
            full_path = self.project_root / file_path
            if full_path.exists():
                content = full_path.read_text()
                if not re.search(pattern, content):
                    issues.append(f"Pattern '{pattern}' not found in {file_path}")
                    missing_patterns[file_path] = pattern
            else:
                issues.append(f"Cannot check pattern - file missing: {file_path}")
                if file_path not in missing_files:
                    missing_files.append(file_path)

        # Check expected outputs
        if task_output:
            for expected in dod.expected_outputs:
                if expected not in task_output:
                    issues.append(f"Expected output not found: {expected}")

        # Determine verdict
        if not issues:
            verdict = TaskVerdict.COMPLETE
            suggestions = ["Task completed successfully"]
        elif missing_files:
            verdict = TaskVerdict.INCOMPLETE
            suggestions = [f"Create missing file: {f}" for f in missing_files]
        elif missing_patterns:
            verdict = TaskVerdict.NEEDS_FIX
            suggestions = [
                f"Add required code to {f}: pattern '{p}'"
                for f, p in missing_patterns.items()
            ]
        else:
            verdict = TaskVerdict.NEEDS_FIX
            suggestions = ["Review and fix the issues listed"]

        return VerificationResult(
            verdict=verdict,
            issues=issues,
            missing_files=missing_files,
            missing_patterns=missing_patterns,
            suggestions=suggestions
        )

    def record_attempt(
        self,
        task_id: str,
        prompt: str,
        result: Optional[str],
        verification: VerificationResult
    ) -> int:
        """
        Record a task execution attempt.

        Args:
            task_id: Task identifier
            prompt: The prompt that was sent
            result: The result received
            verification: Verification result

        Returns:
            Current attempt number
        """
        state = self._load_state()

        if state["active_task"] != task_id:
            state["active_task"] = task_id
            state["attempts"] = []

        attempt_num = len(state["attempts"]) + 1
        attempt = TaskAttempt(
            attempt_number=attempt_num,
            timestamp=datetime.now().isoformat(),
            prompt=prompt,
            result=result[:500] if result else None,  # Truncate
            verdict=verification.verdict,
            issues=verification.issues
        )

        state["attempts"].append({
            "attempt_number": attempt.attempt_number,
            "timestamp": attempt.timestamp,
            "prompt": attempt.prompt[:200],  # Truncate prompt
            "verdict": attempt.verdict.value,
            "issues": attempt.issues[:5]  # Limit issues
        })

        state["total_retries"] = attempt_num - 1
        self._save_state(state)

        return attempt_num

    def should_retry(self, task_id: str, dod: DefinitionOfDone) -> bool:
        """
        Determine if task should be retried.

        Args:
            task_id: Task identifier
            dod: Definition of Done with max_retries

        Returns:
            True if should retry, False if should stop
        """
        state = self._load_state()
        if state["active_task"] != task_id:
            return True

        attempts = len(state.get("attempts", []))
        return attempts < dod.max_retries

    def create_fix_prompt(
        self,
        original_task: str,
        verification: VerificationResult,
        attempt_num: int
    ) -> str:
        """
        Create a prompt for fixing incomplete work.

        Args:
            original_task: Original task description
            verification: What failed verification
            attempt_num: Current attempt number

        Returns:
            Prompt for fix attempt
        """
        issues_text = "\n".join(f"- {issue}" for issue in verification.issues)
        suggestions_text = "\n".join(f"- {s}" for s in verification.suggestions)

        prompt = f"""## Fix Required (Attempt {attempt_num})

### Original Task
{original_task}

### Issues Found
{issues_text}

### Required Fixes
{suggestions_text}

### Instructions
1. Fix ALL issues listed above
2. Verify that required files exist
3. Ensure all patterns/functions are present
4. Do not introduce new issues

This is attempt {attempt_num}. Focus on fixing the specific issues listed.
"""
        return prompt

    def mark_blocked(
        self,
        task_id: str,
        blocker_type: BlockerType,
        reason: str
    ):
        """
        Mark a task as blocked.

        Args:
            task_id: Task identifier
            blocker_type: Type of blocker
            reason: Why task is blocked
        """
        state = self._load_state()

        state["blocked_tasks"].append({
            "task_id": task_id,
            "blocker_type": blocker_type.value,
            "reason": reason,
            "blocked_at": datetime.now().isoformat(),
            "attempts": len(state.get("attempts", []))
        })

        if state["active_task"] == task_id:
            state["active_task"] = None
            state["attempts"] = []

        self._save_state(state)

        # Update CURRENT_STATUS.md with blocker
        self._update_status_blocked(task_id, blocker_type, reason)

    def mark_complete(self, task_id: str):
        """Mark a task as complete"""
        state = self._load_state()

        state["completed_tasks"].append({
            "task_id": task_id,
            "completed_at": datetime.now().isoformat(),
            "attempts": len(state.get("attempts", []))
        })

        if state["active_task"] == task_id:
            state["active_task"] = None
            state["attempts"] = []

        self._save_state(state)

    def _update_status_blocked(
        self,
        task_id: str,
        blocker_type: BlockerType,
        reason: str
    ):
        """Update CURRENT_STATUS.md with blocked status"""
        status_file = self.progress_path / "CURRENT_STATUS.md"
        if not status_file.exists():
            return

        content = status_file.read_text()

        # Find and update Blocked section
        blocked_marker = "## Blocked"
        if blocked_marker in content:
            # Find the section
            parts = content.split(blocked_marker)
            before = parts[0]
            after_parts = parts[1].split("\n---", 1)

            blocked_section = f"""{blocked_marker}
- **{task_id}**: {reason}
  - Type: {blocker_type.value}
  - Blocked at: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{after_parts[0] if len(after_parts) > 1 else ''}
---"""

            content = before + blocked_section + (
                after_parts[1] if len(after_parts) > 1 else ""
            )
            status_file.write_text(content)

    def get_status(self) -> Dict[str, Any]:
        """Get current supervisor status"""
        state = self._load_state()
        return {
            "active_task": state.get("active_task"),
            "current_attempts": len(state.get("attempts", [])),
            "total_blocked": len(state.get("blocked_tasks", [])),
            "total_completed": len(state.get("completed_tasks", [])),
            "recent_blocked": state.get("blocked_tasks", [])[-3:],
            "recent_completed": state.get("completed_tasks", [])[-3:]
        }

    def infer_dod_from_task(self, task_description: str) -> DefinitionOfDone:
        """
        Automatically infer a Definition of Done from task description.

        Supports common task types:
        - create file
        - modify existing file
        - add function/class
        - update route/endpoint
        - update frontend component
        - add test file
        - update docs

        Args:
            task_description: Natural language task description

        Returns:
            DefinitionOfDone with inferred requirements
        """
        task_id = f"task-{datetime.now().strftime('%H%M%S')}"
        required_files = []
        required_patterns = {}
        expected_outputs = []

        # Clean the task description - remove any self-fix remnants
        task_clean = task_description
        for marker in ["## Self-Correction", "## REQUIRED FIXES", "## FINAL ATTEMPT",
                       "Attempt 2 to fix", "### Critical Issues", "### Required Fixes"]:
            if marker in task_clean:
                if "### Original Task" in task_clean:
                    idx = task_clean.find("### Original Task")
                    task_clean = task_clean[idx + len("### Original Task"):].strip()
                    if "\n###" in task_clean:
                        task_clean = task_clean[:task_clean.find("\n###")]
                    break

        # Extract file paths from task - comprehensive patterns ordered from most to least explicit
        file_patterns = [
            # Quoted paths (highest signal)
            r'["`]([a-zA-Z0-9_][a-zA-Z0-9_/\-]*\.(?:py|js|ts|json|yaml|yml|md|txt|html|css))["`]',
            # Explicit directory prefixes
            r'(sandbox/[a-zA-Z0-9_\-/]+\.(?:py|js|ts|json|md|txt|html|css))',
            r'(tests/[a-zA-Z0-9_\-/]+\.(?:py|js|ts))',
            r'(docs/[a-zA-Z0-9_\-/]+\.(?:md|txt|json))',
            r'(frontend/[a-zA-Z0-9_\-/]+\.(?:js|ts|html|css|json))',
            r'(backend/[a-zA-Z0-9_\-/]+\.(?:py|json))',
            r'(scripts/[a-zA-Z0-9_\-/]+\.(?:py|sh|js))',
            # Verb + path
            r'create\s+(?:file\s+)?["`]?([a-zA-Z0-9_/\-\.]+\.[a-z]+)["`]?',
            r'(?:add|write)\s+(?:to\s+)?["`]?([a-zA-Z0-9_/\-\.]+\.[a-z]+)["`]?',
            r'(?:modify|update|edit)\s+(?:file\s+)?["`]?([a-zA-Z0-9_/\-\.]+\.[a-z]+)["`]?',
        ]

        for pattern in file_patterns:
            matches = re.findall(pattern, task_clean, re.IGNORECASE)
            for match in matches:
                if match and match not in required_files:
                    # Basic validation
                    if '/' in match or match.endswith(('.py', '.js', '.ts', '.md', '.json', '.html', '.css', '.txt')):
                        required_files.append(match)

        # Extract function/class names
        func_patterns = [
            (r'function\s+["`]?(\w+)["`]?', 'function'),
            (r'method\s+["`]?(\w+)["`]?', 'method'),
            (r'class\s+["`]?(\w+)["`]?', 'class'),
            (r'implement\s+["`]?(\w+)["`]?', 'implement'),
            (r'add\s+(?:a\s+)?(\w+)\s+(?:function|method|class)', 'add'),
        ]

        for pattern, ptype in func_patterns:
            matches = re.findall(pattern, task_clean, re.IGNORECASE)
            for match in matches:
                # Will check this pattern in Python/JS files
                if required_files:
                    for f in required_files:
                        if f.endswith('.py'):
                            required_patterns[f] = f"def {match}|class {match}"
                        elif f.endswith(('.js', '.ts')):
                            required_patterns[f] = f"function {match}|const {match}|class {match}"

        # expected_outputs are checked with exact substring match against task output.
        # We do NOT populate them here because the actual executor output format is
        # a structured markdown report — not a human-readable summary that would
        # contain strings like "test file created" or "route defined".
        # File existence (required_files) is the definitive verification signal.
        # Subclasses or callers may populate expected_outputs for custom checks.

        return DefinitionOfDone(
            task_id=task_id,
            description=task_clean[:500],
            required_files=list(set(required_files)),
            required_patterns=required_patterns,
            expected_outputs=[],   # Intentionally empty — file checks are sufficient
            max_retries=3
        )


# Convenience functions
_supervisor: Optional[Supervisor] = None


def get_supervisor(project_root: Optional[Path] = None) -> Supervisor:
    """Get or create supervisor instance"""
    global _supervisor
    if _supervisor is None or (project_root and project_root != _supervisor.project_root):
        _supervisor = Supervisor(project_root)
    return _supervisor


def supervise_task(
    task_description: str,
    task_output: Optional[str] = None,
    custom_dod: Optional[DefinitionOfDone] = None
) -> Dict[str, Any]:
    """
    Main entry point for supervising a task.

    Args:
        task_description: What the task should do
        task_output: Output from task execution
        custom_dod: Optional custom Definition of Done

    Returns:
        Dict with verdict, should_retry, and fix_prompt if needed
    """
    supervisor = get_supervisor()

    # Get or create DoD
    dod = custom_dod or supervisor.infer_dod_from_task(task_description)

    # Verify completion
    verification = supervisor.verify_task_completion(dod, task_output)

    # Record attempt
    attempt_num = supervisor.record_attempt(
        task_id=dod.task_id,
        prompt=task_description,
        result=task_output,
        verification=verification
    )

    result = {
        "task_id": dod.task_id,
        "verdict": verification.verdict.value,
        "issues": verification.issues,
        "suggestions": verification.suggestions,
        "attempt": attempt_num
    }

    if verification.verdict == TaskVerdict.COMPLETE:
        supervisor.mark_complete(dod.task_id)
        result["should_retry"] = False
        result["message"] = "Task completed successfully"

    elif supervisor.should_retry(dod.task_id, dod):
        result["should_retry"] = True
        result["fix_prompt"] = supervisor.create_fix_prompt(
            task_description,
            verification,
            attempt_num + 1
        )
        result["message"] = f"Task needs fixes. Retry {attempt_num + 1}/{dod.max_retries}"

    else:
        supervisor.mark_blocked(
            dod.task_id,
            BlockerType.REPEATED_FAILURE,
            f"Failed after {attempt_num} attempts: {verification.issues[0] if verification.issues else 'Unknown'}"
        )
        result["should_retry"] = False
        result["blocked"] = True
        result["message"] = f"Task blocked after {attempt_num} failed attempts"

    return result
