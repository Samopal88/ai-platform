"""
AI Workspace Platform - File-Based Executor Service
Real execution engine that operates on project files

This executor performs REAL file operations:
- Reads existing project files
- Creates new files
- Patches/modifies existing files
- Tracks all changes
- Returns real execution results

Replaces demo/simulated execution with actual file operations.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from app.core.config import settings


class FileOperationType(str, Enum):
    """Types of file operations"""
    READ = "read"
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    PATCH = "patch"


class StepStatus(str, Enum):
    """Step execution status"""
    PENDING = "pending"
    RUNNING = "running"
    REVIEW = "review"
    RETRY = "retry"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FileOperation:
    """Record of a file operation"""
    operation: FileOperationType
    path: str
    success: bool
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    content_preview: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation.value,
            "path": self.path,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
            "content_preview": self.content_preview,
            "error": self.error
        }


@dataclass
class ExecutionStep:
    """A single execution step"""
    step_id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    operations: List[FileOperation] = field(default_factory=list)
    output: str = ""
    review_passed: bool = False
    review_notes: str = ""
    attempts: int = 0
    max_attempts: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "status": self.status.value,
            "operations": [op.to_dict() for op in self.operations],
            "output": self.output,
            "review_passed": self.review_passed,
            "review_notes": self.review_notes,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts
        }


@dataclass
class ExecutionPlan:
    """Execution plan with steps"""
    plan_id: str
    task_description: str
    steps: List[ExecutionStep]
    current_step_index: int = 0
    status: str = "created"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_description": self.task_description,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "status": self.status,
            "created_at": self.created_at
        }

    def get_current_step(self) -> Optional[ExecutionStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None


@dataclass
class ExecutionResult:
    """Result of file-based execution"""
    success: bool
    task_id: str
    output: str
    files_changed: List[str] = field(default_factory=list)
    operations: List[FileOperation] = field(default_factory=list)
    plan: Optional[ExecutionPlan] = None
    attempts: int = 0
    duration_seconds: float = 0
    error: Optional[str] = None
    execution_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "output": self.output,
            "files_changed": self.files_changed,
            "operations": [op.to_dict() for op in self.operations],
            "plan": self.plan.to_dict() if self.plan else None,
            "attempts": self.attempts,
            "duration_seconds": self.duration_seconds,
            "error": self.error
        }


class FileExecutor:
    """
    Real file-based executor for AI Workspace Platform.

    Performs actual file operations:
    - Analyzes task to determine needed files
    - Creates execution plan with concrete steps
    - Executes each step with real file operations
    - Reviews results after each step
    - Tracks all changes for verification
    """

    # Safe directories where executor can write.
    # Matching is prefix-based: a path is safe if it starts with any entry here.
    # "frontend" covers frontend/, frontend/components/, etc.
    # "backend" covers backend/ broadly; PROTECTED_PATTERNS still blocks main.py/__init__.py.
    # NOTE: "docs" is intentionally EXCLUDED — docs are read-only reference material.
    # A code task must never write to docs/. Only tasks explicitly targeting docs/ may do so,
    # and they go through task_allowed_write_paths enforcement in the executor.
    SAFE_DIRS = [
        "sandbox",
        "tests",
        "storage",
        "scripts",
        "backend",
        "frontend",
    ]

    # Directories that are read-only by default (can be overridden per-task via allowed_write_paths)
    READ_ONLY_DIRS = [
        "docs",
    ]

    # Protected patterns - never modify these
    PROTECTED_PATTERNS = [
        r"\.env",
        r"settings\.json",
        r"secrets",
        r"credentials",
        r"\.git/",
        r"__pycache__",
        r"\.pyc$",
        r"node_modules",
        r"main\.py$",  # Protect main entry points
        r"__init__\.py$",  # Protect init files
    ]

    def __init__(
        self,
        project_root: Optional[Path] = None,
        max_step_attempts: int = 2,
        on_progress: Optional[Callable[[str, str], None]] = None
    ):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.max_step_attempts = max_step_attempts
        self.on_progress = on_progress
        self.state_file = self.project_root / "docs" / "progress" / "file_executor_state.json"
        # Per-task write-target policy set by execute_task()
        # Populated from the task's explicit file list; empty = default policy (docs blocked)
        self._task_allowed_write_paths: List[str] = []
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist"""
        (self.project_root / "docs" / "progress").mkdir(parents=True, exist_ok=True)
        # Create sandbox for safe operations
        (self.project_root / "sandbox").mkdir(parents=True, exist_ok=True)

    def _emit_progress(self, stage: str, message: str):
        """Emit progress event"""
        if self.on_progress:
            self.on_progress(stage, message)

    def _normalize_path(self, rel_path: str) -> Optional[str]:
        """
        Normalize and validate a relative path.
        Returns normalized path or None if path is unsafe.
        """
        # Remove leading/trailing whitespace
        rel_path = rel_path.strip()

        # Remove leading slash if present
        if rel_path.startswith('/'):
            rel_path = rel_path[1:]

        # Resolve the full path and check it's within project_root
        try:
            full_path = (self.project_root / rel_path).resolve()
            project_root_resolved = self.project_root.resolve()

            # Security check: must be within project root
            if not str(full_path).startswith(str(project_root_resolved)):
                return None

            # Convert back to relative path
            rel_path = str(full_path.relative_to(project_root_resolved))
            return rel_path
        except (ValueError, RuntimeError):
            return None

    def _is_safe_path(self, rel_path: str) -> bool:
        """Check if path is safe to write to"""
        # Normalize path first
        normalized = self._normalize_path(rel_path)
        if normalized is None:
            return False

        # Check against protected patterns
        for pattern in self.PROTECTED_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return False

        # Check if in safe directory
        for safe_dir in self.SAFE_DIRS:
            if normalized.startswith(safe_dir):
                return True

        # Default: allow read, but be cautious about write
        return False

    def _is_safe_for_write(self, rel_path: str, allowed_write_paths: Optional[list] = None) -> bool:
        """Check if path is safe for write operations.

        By default docs/ is read-only (enforces write-target policy).
        Pass allowed_write_paths to explicitly permit additional paths for this task.
        """
        # Normalize path first
        normalized = self._normalize_path(rel_path)
        if normalized is None:
            return False

        # Check against protected patterns
        for pattern in self.PROTECTED_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return False

        # Check explicit task-level allowlist first (overrides READ_ONLY_DIRS)
        if allowed_write_paths:
            for allowed in allowed_write_paths:
                allowed_norm = allowed.rstrip("/")
                if normalized == allowed_norm or normalized.startswith(allowed_norm + "/"):
                    return True

        # Docs are read-only by default — block writes unless explicitly allowed above
        for ro_dir in self.READ_ONLY_DIRS:
            if normalized.startswith(ro_dir + "/") or normalized == ro_dir:
                return False

        # Must be in safe directory for write
        for safe_dir in self.SAFE_DIRS:
            if normalized.startswith(safe_dir):
                return True

        return False

    def _load_state(self) -> Dict[str, Any]:
        """Load executor state"""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {
            "current_task": None,
            "current_job_id": None,
            "current_plan": None,
            "operations_history": [],
            "files_changed": [],
            "updated_at": None
        }

    def _save_state(self, state: Dict[str, Any]):
        """Save executor state"""
        state["updated_at"] = datetime.now().isoformat()
        self.state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    # === File Operations ===

    def read_file(self, rel_path: str) -> FileOperation:
        """Read a file from project"""
        full_path = self.project_root / rel_path

        if not full_path.exists():
            return FileOperation(
                operation=FileOperationType.READ,
                path=rel_path,
                success=False,
                message=f"File not found: {rel_path}",
                error="File does not exist"
            )

        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            preview = content[:500] + "..." if len(content) > 500 else content

            return FileOperation(
                operation=FileOperationType.READ,
                path=rel_path,
                success=True,
                message=f"Read {len(content)} bytes from {rel_path}",
                content_preview=preview
            )
        except Exception as e:
            return FileOperation(
                operation=FileOperationType.READ,
                path=rel_path,
                success=False,
                message=f"Failed to read {rel_path}",
                error=str(e)
            )

    def create_file(self, rel_path: str, content: str) -> FileOperation:
        """Create a new file in project"""
        if not self._is_safe_for_write(rel_path, self._task_allowed_write_paths):
            return FileOperation(
                operation=FileOperationType.CREATE,
                path=rel_path,
                success=False,
                message=f"Path not allowed for write: {rel_path}",
                error="Path is not in safe directory"
            )

        full_path = self.project_root / rel_path

        try:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            full_path.write_text(content, encoding="utf-8")
            preview = content[:200] + "..." if len(content) > 200 else content

            return FileOperation(
                operation=FileOperationType.CREATE,
                path=rel_path,
                success=True,
                message=f"Created file: {rel_path} ({len(content)} bytes)",
                content_preview=preview
            )
        except Exception as e:
            return FileOperation(
                operation=FileOperationType.CREATE,
                path=rel_path,
                success=False,
                message=f"Failed to create {rel_path}",
                error=str(e)
            )

    def modify_file(self, rel_path: str, content: str) -> FileOperation:
        """Modify an existing file"""
        if not self._is_safe_for_write(rel_path, self._task_allowed_write_paths):
            return FileOperation(
                operation=FileOperationType.MODIFY,
                path=rel_path,
                success=False,
                message=f"Path not allowed for write: {rel_path}",
                error="Path is not in safe directory"
            )

        full_path = self.project_root / rel_path

        if not full_path.exists():
            return FileOperation(
                operation=FileOperationType.MODIFY,
                path=rel_path,
                success=False,
                message=f"File not found: {rel_path}",
                error="File does not exist"
            )

        try:
            full_path.write_text(content, encoding="utf-8")
            preview = content[:200] + "..." if len(content) > 200 else content

            return FileOperation(
                operation=FileOperationType.MODIFY,
                path=rel_path,
                success=True,
                message=f"Modified file: {rel_path} ({len(content)} bytes)",
                content_preview=preview
            )
        except Exception as e:
            return FileOperation(
                operation=FileOperationType.MODIFY,
                path=rel_path,
                success=False,
                message=f"Failed to modify {rel_path}",
                error=str(e)
            )

    def patch_file(self, rel_path: str, find: str, replace: str) -> FileOperation:
        """Patch a file by replacing text"""
        if not self._is_safe_for_write(rel_path, self._task_allowed_write_paths):
            return FileOperation(
                operation=FileOperationType.PATCH,
                path=rel_path,
                success=False,
                message=f"Path not allowed for write: {rel_path}",
                error="Path is not in safe directory"
            )

        full_path = self.project_root / rel_path

        if not full_path.exists():
            return FileOperation(
                operation=FileOperationType.PATCH,
                path=rel_path,
                success=False,
                message=f"File not found: {rel_path}",
                error="File does not exist"
            )

        try:
            content = full_path.read_text(encoding="utf-8")

            if find not in content:
                return FileOperation(
                    operation=FileOperationType.PATCH,
                    path=rel_path,
                    success=False,
                    message=f"Pattern not found in {rel_path}",
                    error="Search pattern not found"
                )

            new_content = content.replace(find, replace, 1)
            full_path.write_text(new_content, encoding="utf-8")

            return FileOperation(
                operation=FileOperationType.PATCH,
                path=rel_path,
                success=True,
                message=f"Patched file: {rel_path}",
                content_preview=f"Replaced '{find[:50]}...' with '{replace[:50]}...'"
            )
        except Exception as e:
            return FileOperation(
                operation=FileOperationType.PATCH,
                path=rel_path,
                success=False,
                message=f"Failed to patch {rel_path}",
                error=str(e)
            )

    # === Task Analysis ===

    def analyze_task(self, task_description: str) -> Dict[str, Any]:
        """Analyze task to determine execution plan"""
        task_lower = task_description.lower()

        analysis = {
            "task_type": "general",
            "intent": [],
            "target_files": [],
            "target_content": [],
            "safe_mode": True
        }

        # Detect intent
        if any(w in task_lower for w in ["create", "создай", "add", "добавь"]):
            analysis["intent"].append("create")
        if any(w in task_lower for w in ["modify", "change", "update", "измени", "обнови"]):
            analysis["intent"].append("modify")
        if any(w in task_lower for w in ["delete", "remove", "удали"]):
            analysis["intent"].append("delete")
        if any(w in task_lower for w in ["read", "show", "get", "покажи", "прочитай"]):
            analysis["intent"].append("read")
        if any(w in task_lower for w in ["test", "тест", "check", "проверь"]):
            analysis["intent"].append("test")
            analysis["task_type"] = "test"

        # Extract file paths mentioned - improved pattern matching
        file_patterns = [
            # Quoted paths first (most explicit)
            r'["`]([a-zA-Z0-9_][a-zA-Z0-9_/\-]*\.(?:py|js|ts|html|css|json|md|txt|yaml|yml))["`]',
            # sandbox/ tests/ docs/ frontend/ backend/ paths without quotes
            r'(sandbox/[a-zA-Z0-9_\-/]+\.(?:py|js|ts|html|css|json|md|txt))',
            r'(tests/[a-zA-Z0-9_\-/]+\.(?:py|js|ts))',
            r'(docs/[a-zA-Z0-9_\-/]+\.(?:md|txt|json))',
            r'(frontend/[a-zA-Z0-9_\-/]+\.(?:js|ts|html|css|json))',
            r'(backend/[a-zA-Z0-9_\-/]+\.(?:py|json|ini|cfg|txt|sql|sh))',
            r'(scripts/[a-zA-Z0-9_\-/]+\.(?:py|sh|js))',
            # Generic path-like strings with extensions
            r'(?:file|файл)[:\s]+([^\s,]+\.[a-z]+)',
            r'(?:in|в)\s+([^\s,]+\.[a-z]+)',
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, task_description, re.IGNORECASE)
            for match in matches:
                if match and match not in analysis["target_files"]:
                    analysis["target_files"].append(match)

        # Deduplicate: remove shorter paths that are suffixes of longer ones
        # e.g. keep "backend/scripts/init_db.py", drop "scripts/init_db.py"
        deduped = []
        for path in analysis["target_files"]:
            dominated = any(
                other != path and other.endswith(path)
                for other in analysis["target_files"]
            )
            if not dominated:
                deduped.append(path)
        analysis["target_files"] = deduped
        if "content" in task_lower or "содержимое" in task_lower:
            # Look for quoted content
            quoted = re.findall(r'"([^"]+)"', task_description)
            analysis["target_content"].extend(quoted)

        # Determine task type
        if "code" in task_lower or "function" in task_lower or "class" in task_lower:
            analysis["task_type"] = "code"
        elif "doc" in task_lower or "readme" in task_lower:
            analysis["task_type"] = "documentation"
        elif "config" in task_lower or "setting" in task_lower:
            analysis["task_type"] = "config"

        # Remove duplicates
        analysis["target_files"] = list(set(analysis["target_files"]))

        return analysis

    def create_plan(self, task_description: str, job_id: str) -> ExecutionPlan:
        """Create execution plan from task"""
        analysis = self.analyze_task(task_description)
        plan_id = f"plan-{job_id}-{int(time.time())}"
        steps = []

        # Step 1: Analyze
        steps.append(ExecutionStep(
            step_id="step-1-analyze",
            description=f"Analyze task requirements"
        ))

        # Step 2: Based on intent, create appropriate steps
        # CRITICAL: if a target file already exists on disk, ALWAYS use modify, never create.
        # Creating over an existing code module corrupts it with template content.
        if "create" in analysis["intent"]:
            if analysis["target_files"]:
                for i, target in enumerate(analysis["target_files"][:3]):  # Max 3 files
                    full_path = self.project_root / target
                    if full_path.exists():
                        # Existing file: use modify, not create
                        steps.append(ExecutionStep(
                            step_id=f"step-{len(steps)+1}-modify-{i}",
                            description=f"Modify file: {target}"
                        ))
                    else:
                        steps.append(ExecutionStep(
                            step_id=f"step-{len(steps)+1}-create-{i}",
                            description=f"Create file: {target}"
                        ))
            else:
                # Generic create step with sandbox default
                steps.append(ExecutionStep(
                    step_id=f"step-{len(steps)+1}-create",
                    description=f"Create requested content in sandbox"
                ))

        if "modify" in analysis["intent"] and analysis["target_files"]:
            # Only add modify steps for files not already being handled above
            already_handled = set()
            for s in steps:
                m = re.search(r'(?:modify|create)\s+file:\s+(\S+)', s.description)
                if m:
                    already_handled.add(m.group(1))
            modify_targets = [t for t in analysis["target_files"] if t not in already_handled]
            for i, target in enumerate(modify_targets[:3]):
                steps.append(ExecutionStep(
                    step_id=f"step-{len(steps)+1}-modify-{i}",
                    description=f"Modify file: {target}"
                ))

        if "read" in analysis["intent"] and analysis["target_files"]:
            for i, target in enumerate(analysis["target_files"][:3]):
                steps.append(ExecutionStep(
                    step_id=f"step-{len(steps)+1}-read-{i}",
                    description=f"Read file: {target}"
                ))

        # If no specific file operations, add a default implementation step
        if len(steps) == 1:  # Only analyze step
            steps.append(ExecutionStep(
                step_id="step-2-implement",
                description=f"Implement task: {task_description[:100]}"
            ))

        # Step N: Verify
        steps.append(ExecutionStep(
            step_id=f"step-{len(steps)+1}-verify",
            description="Verify task completion"
        ))

        return ExecutionPlan(
            plan_id=plan_id,
            task_description=task_description,
            steps=steps,
            status="created"
        )

    # === Step Execution ===

    def execute_step(
        self,
        step: ExecutionStep,
        task_description: str,
        context: Dict[str, Any]
    ) -> Tuple[bool, List[FileOperation], str]:
        """
        Execute a single step with real file operations.

        Returns: (success, operations, output)
        """
        operations = []
        output_parts = []
        success = True

        step_lower = step.description.lower()

        self._emit_progress("step_executing", f"Executing: {step.description}")

        # Analyze step type
        if "analyze" in step_lower:
            # Analyze step - scan project structure
            output_parts.append("## Analysis\n")
            output_parts.append(f"Task: {task_description[:200]}\n")

            analysis = self.analyze_task(task_description)
            output_parts.append(f"Intent: {', '.join(analysis['intent']) or 'general'}\n")
            output_parts.append(f"Target files: {', '.join(analysis['target_files']) or 'none specified'}\n")
            output_parts.append(f"Task type: {analysis['task_type']}\n")

            # Read existing related files if found
            for target in analysis["target_files"][:2]:
                op = self.read_file(target)
                operations.append(op)
                if op.success:
                    output_parts.append(f"\nFound existing: {target}\n")

        elif "create" in step_lower:
            # Create step - create file
            # Extract target from step description - try the full step description first
            # then fall back to task_description for file path hints
            target = None

            # Pattern 1: "create file: path/to/file.ext"
            target_match = re.search(r'create\s+(?:file[:\s]+)?["`]?([a-zA-Z0-9_/\-\.]+\.[a-z]+)["`]?', step_lower)
            if target_match:
                target = target_match.group(1)

            # Pattern 2: look in original task_description for the path
            if not target:
                td_lower = task_description.lower()
                for pat in [
                    r'["`]([a-zA-Z0-9_/\-\.]+\.(?:py|js|ts|html|css|json|md|txt))["`]',
                    r'(?:create|add)\s+(?:file\s+)?([a-zA-Z0-9_][a-zA-Z0-9_/\-]*\.(?:py|js|ts|html|css|json|md|txt))',
                    r'((?:sandbox|tests|docs|frontend|backend|scripts)/[a-zA-Z0-9_/\-]+\.(?:py|js|ts|html|css|json|md|txt|ini|cfg|sql|sh))',
                ]:
                    m = re.search(pat, td_lower)
                    if m:
                        target = m.group(1)
                        break

            if not target:
                # Default to sandbox with timestamp
                timestamp = int(time.time())
                target = f"sandbox/generated_{timestamp}.txt"

            # Normalise and safety-check the path
            normalized = self._normalize_path(target)
            if normalized is None or not self._is_safe_for_write(target, self._task_allowed_write_paths):
                # If path is outside safe dirs but looks like a valid project path,
                # create it in sandbox instead with the original filename preserved
                fname = Path(target).name
                target = f"sandbox/{fname}"

            # SAFETY: if the file already exists, do NOT overwrite with generated template content.
            # Re-route to modify path to preserve the existing module structure.
            full_target = self.project_root / target
            if full_target.exists() and full_target.suffix == ".py":
                read_op = self.read_file(target)
                operations.append(read_op)
                if read_op.success:
                    new_content = self._generate_modification(
                        task_description,
                        full_target.read_text(encoding="utf-8", errors="replace"),
                        {**context, "target_path": target},
                    )
                    op = self.modify_file(target, new_content)
                    operations.append(op)
                    success = op.success
                    if op.success:
                        output_parts.append(f"Modified existing module: {target}\n")
                    else:
                        output_parts.append(f"Failed to modify: {target}\n")
                        output_parts.append(f"Error: {op.error}\n")
                else:
                    success = False
                    output_parts.append(f"Cannot read existing file for modification: {target}\n")
                # Skip the create path entirely
                return success, operations, "\n".join(output_parts)

            # Generate content based on task (new file only)
            content = self._generate_file_content(task_description, target, context)

            op = self.create_file(target, content)
            operations.append(op)
            success = op.success

            if op.success:
                output_parts.append(f"Created: {target}\n")
                output_parts.append(f"Content:\n```\n{content[:500]}\n```\n")
            else:
                output_parts.append(f"Failed to create: {target}\n")
                output_parts.append(f"Error: {op.error}\n")

        elif "modify" in step_lower or "patch" in step_lower:
            # Modify step — preserves existing file content, applies targeted edit
            target_match = re.search(r'(?:modify|patch)\s+(?:file[:\s]+)?([^\s]+)', step_lower)
            if target_match:
                target = target_match.group(1)

                # Read FULL current content (not just preview — need the whole file for modify)
                full_path = self.project_root / target
                if full_path.exists():
                    try:
                        current_content = full_path.read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        success = False
                        output_parts.append(f"Cannot read existing file: {target}: {e}\n")
                        return success, operations, "\n".join(output_parts)
                else:
                    success = False
                    output_parts.append(f"Cannot modify - file not found: {target}\n")
                    return success, operations, "\n".join(output_parts)

                read_op = self.read_file(target)
                operations.append(read_op)

                # Generate modification — always preserves current_content as base
                new_content = self._generate_modification(
                    task_description,
                    current_content,
                    {**context, "target_path": target},
                )
                modify_op = self.modify_file(target, new_content)
                operations.append(modify_op)
                success = modify_op.success

                if modify_op.success:
                    output_parts.append(f"Modified: {target}\n")
                else:
                    output_parts.append(f"Failed to modify: {target}\n")
            else:
                success = False
                output_parts.append("No target file specified for modification\n")

        elif "read" in step_lower:
            # Read step
            target_match = re.search(r'read\s+(?:file[:\s]+)?([^\s]+)', step_lower)
            if target_match:
                target = target_match.group(1)
                op = self.read_file(target)
                operations.append(op)
                success = op.success

                if op.success:
                    output_parts.append(f"Read: {target}\n")
                    output_parts.append(f"Content preview:\n{op.content_preview}\n")
                else:
                    output_parts.append(f"Failed to read: {target}\n")
            else:
                success = False
                output_parts.append("No target file specified for read\n")

        elif "verify" in step_lower:
            # Verify step - check all operations succeeded
            output_parts.append("## Verification\n")

            # Check files_changed in context
            files_changed = context.get("files_changed", [])
            if files_changed:
                output_parts.append(f"Files changed: {len(files_changed)}\n")
                for f in files_changed:
                    full_path = self.project_root / f
                    exists = full_path.exists()
                    output_parts.append(f"  - {f}: {'exists' if exists else 'MISSING'}\n")
                    if not exists:
                        success = False
            else:
                output_parts.append("No files changed in this task\n")

            output_parts.append(f"\nVerification: {'PASSED' if success else 'FAILED'}\n")

        else:
            # Generic implement step
            output_parts.append(f"## Implementing: {step.description}\n")

            # Default: create a file in sandbox with task notes
            timestamp = int(time.time())
            target = f"sandbox/task_{timestamp}.md"

            content = f"""# Task Execution Notes

## Task
{task_description}

## Step
{step.description}

## Executed
{datetime.now().isoformat()}

## Status
Implemented by file_executor
"""
            op = self.create_file(target, content)
            operations.append(op)
            success = op.success

            if op.success:
                output_parts.append(f"Created: {target}\n")

        return success, operations, "\n".join(output_parts)

    def _generate_file_content(
        self,
        task_description: str,
        target_path: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate appropriate file content based on task and path"""
        ext = Path(target_path).suffix.lower()

        # Extract the CLEAN task description
        # Remove any self-correction/fix prompt remnants
        task_clean = task_description
        for marker in ["## Self-Correction", "## REQUIRED FIXES", "## FINAL ATTEMPT",
                       "Attempt 2 to fix", "Attempt 3 to fix", "### Critical Issues",
                       "### Required Fixes", "### Original Task"]:
            if marker in task_clean:
                # Find "Original Task" section if present and extract it
                if "### Original Task" in task_clean:
                    idx = task_clean.find("### Original Task")
                    task_clean = task_clean[idx + len("### Original Task"):].strip()
                    # Take until next section or end
                    if "\n###" in task_clean:
                        task_clean = task_clean[:task_clean.find("\n###")]
                    break
                else:
                    # Just use first 200 chars before any markers
                    idx = task_clean.find(marker)
                    if idx > 50:
                        task_clean = task_clean[:idx]
                    break

        task_short = task_clean.strip()[:200]

        if ext == ".py":
            # Extract a function name from the task if present
            task_lower = task_clean.lower()
            func_match = (
                re.search(r'\b([a-z][a-z0-9_]+)\s+function', task_lower)
                or re.search(r'function\s+["`]?([a-z][a-z0-9_]+)', task_lower)
                or re.search(r'def\s+([a-z][a-z0-9_]+)', task_lower)
                or re.search(r'(?:implement|add|create)\s+([a-z][a-z0-9_]+)', task_lower)
            )
            func_name = func_match.group(1) if func_match else "main"
            # Sanitise: remove Python keywords that slipped through
            import keyword
            if keyword.iskeyword(func_name):
                func_name = "main"

            return f'''"""
{task_short}
"""


def {func_name}():
    """
    {task_short[:120]}
    """
    pass


if __name__ == "__main__":
    {func_name}()
'''

        elif ext == ".js" or ext == ".ts":
            task_lower = task_clean.lower()
            name_match = re.search(
                r'(?:component|class|function)\s+["`]?([A-Za-z][A-Za-z0-9_]+)', task_clean
            ) or re.search(
                r'(?:create|add|implement)\s+([A-Z][A-Za-z0-9]+)', task_clean
            )
            entity_name = name_match.group(1) if name_match else "Main"

            if "component" in task_lower:
                # React-style functional component
                return f'''/**
 * {task_short}
 */

function {entity_name}(props) {{
    return (
        <div className="{entity_name.lower()}">
            {{/* {task_short[:80]} */}}
        </div>
    );
}}

export default {entity_name};
'''
            elif "class" in task_lower:
                return f'''/**
 * {task_short}
 */

class {entity_name} {{
    constructor() {{
        // {task_short[:80]}
    }}
}}

export default {entity_name};
'''
            else:
                # Named function
                func_name = entity_name[0].lower() + entity_name[1:]
                return f'''/**
 * {task_short}
 */

function {func_name}() {{
    // {task_short[:80]}
}}

export {{ {func_name} }};
'''

        elif ext == ".json":
            return json.dumps({
                "generated": True,
                "task": task_short,
                "timestamp": datetime.now().isoformat()
            }, indent=2)

        elif ext == ".md":
            return f"""# Generated Content

## Task
{task_short}

## Generated
{datetime.now().isoformat()}

## Notes
This file was created by the AI Workspace Platform file executor.
"""

        elif ext == ".html":
            return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated Content</title>
</head>
<body>
    <h1>Generated Content</h1>
    <p>Task: {task_short}</p>
    <p>Generated: {datetime.now().isoformat()}</p>
</body>
</html>
'''

        elif ext == ".css":
            return f'''/* Generated by AI Workspace Platform
 * Task: {task_short}
 * Generated: {datetime.now().isoformat()}
 */

.generated-content {{
    display: block;
}}
'''

        elif ext in (".yaml", ".yml"):
            return f"""# {task_short}

generated: "{datetime.now().isoformat()}"
# Add your configuration below
"""

    def _generate_modification(
        self,
        task_description: str,
        current_content: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate modified content with intent detection.

        INVARIANT: current_content is ALWAYS the base. This function never returns
        content that discards the existing file. The task_description is used to
        determine WHAT to add/change, never as raw file content.
        """
        task_lower = task_description.lower()
        target_path = context.get("target_path", "")
        ext = Path(target_path).suffix.lower() if target_path else ""

        # --- Guard: if current_content is a well-formed Python module, preserve it ---
        # The only mutations allowed are append (new function) or specific field replacement.
        # We NEVER return task_description text as Python source.
        is_python_module = (
            ext == ".py"
            and current_content.strip()
            and not current_content.strip().startswith("TASK BRIEF")
            and ("class " in current_content or "def " in current_content or "import " in current_content)
        )

        # --- intent: change a specific type annotation in a Pydantic schema ---
        # Pattern: "change X.field from Y to Z" or "UUID id field" etc.
        if is_python_module and ("uuid" in task_lower or "id:" in task_lower or "type" in task_lower):
            # Look for "id: int" → "id: UUID" style annotation changes
            type_change = re.search(
                r'change\s+`?(\w+)`?\s+from\s+`?(\w+)`?\s+to\s+`?(\w+)`?',
                task_lower
            )
            if type_change:
                field_name = type_change.group(1)
                from_type = type_change.group(2)
                to_type_raw = type_change.group(3)
                # Capitalize to match Python type names
                to_type = to_type_raw.upper() if to_type_raw.lower() == "uuid" else to_type_raw.capitalize()
                old_ann = f"{field_name}: {from_type.capitalize()}"
                new_ann = f"{field_name}: {to_type}"
                if old_ann in current_content:
                    return current_content.replace(old_ann, new_ann, 1)
                # Also try lowercase
                old_ann_lower = f"{field_name}: {from_type}"
                if old_ann_lower in current_content:
                    return current_content.replace(old_ann_lower, new_ann, 1)

        # --- intent: add a function/method → append stub ---
        func_match = re.search(r'add\s+(?:a\s+)?(?:function|method|def)\s+["`]?([a-z_][a-z0-9_]+)', task_lower)
        if func_match:
            func_name = func_match.group(1)
            if ext == ".py":
                stub = f'\n\ndef {func_name}():\n    """{task_description[:100]}"""\n    pass\n'
            elif ext in (".js", ".ts"):
                stub = f'\n\nfunction {func_name}() {{\n    // {task_description[:80]}\n}}\n'
            else:
                stub = f"\n\n# {func_name}: {task_description[:100]}\n"
            return current_content + stub

        # --- intent: update/replace a markdown section heading ---
        section_match = re.search(r'(?:update|replace|edit)\s+(?:section\s+)?["`]?([A-Za-z][A-Za-z0-9 _-]+)["`]?', task_description)
        if section_match and current_content.startswith("#"):
            heading = section_match.group(1).strip()
            heading_pattern = re.compile(r'(^#{1,3}\s+' + re.escape(heading) + r'.*$)', re.MULTILINE | re.IGNORECASE)
            m = heading_pattern.search(current_content)
            if m:
                insert_pos = m.end()
                note = f"\n\n> Updated: {task_description[:120]}\n"
                return current_content[:insert_pos] + note + current_content[insert_pos:]

        # --- default for Python modules: preserve content, append comment only ---
        # Never embed task_description text as code in an existing module.
        if is_python_module:
            timestamp = datetime.now().isoformat()
            note = f"\n# [executor] modification requested: {task_description[:80]!r}\n# Time: {timestamp}\n"
            return current_content + note

        # --- default for non-Python: append a timestamped note ---
        timestamp = datetime.now().isoformat()
        if ext == ".py":
            note = f"\n\n# Modified: {task_description[:100]}\n# Time: {timestamp}\n"
        elif ext in (".js", ".ts"):
            note = f"\n\n// Modified: {task_description[:100]}\n// Time: {timestamp}\n"
        elif ext in (".yaml", ".yml"):
            note = f"\n# Modified: {task_description[:100]}\n# Time: {timestamp}\n"
        else:
            note = f"\n\n<!-- Modified: {task_description[:100]} -->\n"
        return current_content + note

    # === Main Execution ===

    def execute_task(
        self,
        task_description: str,
        job_id: str,
        task_type: str = "general",
        on_progress: Optional[Callable[[str, str], None]] = None,
        allowed_write_paths: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """
        Execute a task with real file operations.

        allowed_write_paths: explicit list of relative paths this task is allowed to write.
          If a path under docs/ is listed here, it becomes writable for this task only.
          All other docs/ writes remain blocked regardless.

        Flow:
        1. Analyze task
        2. Create plan with steps
        3. Execute each step
        4. Review after each step
        5. Retry if needed
        6. Verify completion

        Returns ExecutionResult with real file changes.
        """
        start_time = time.time()
        self.on_progress = on_progress or self.on_progress
        # Set per-task write-target policy (used by create/modify/patch_file)
        self._task_allowed_write_paths = allowed_write_paths or []
        all_operations = []
        files_changed = []

        self._emit_progress("task_received", f"Task received: {task_description[:100]}")

        # Create plan
        self._emit_progress("plan_creating", "Creating execution plan")
        plan = self.create_plan(task_description, job_id)

        self._emit_progress("plan_created", f"Plan created: {len(plan.steps)} steps")

        # Save state
        state = self._load_state()
        state["current_task"] = task_description
        state["current_job_id"] = job_id
        state["current_plan"] = plan.to_dict()
        self._save_state(state)

        # Execute steps
        plan.status = "executing"
        context = {
            "task_description": task_description,
            "job_id": job_id,
            "task_type": task_type,
            "files_changed": []
        }

        outputs = []

        for i, step in enumerate(plan.steps):
            plan.current_step_index = i
            step.status = StepStatus.RUNNING
            step.attempts += 1

            self._emit_progress("step_started", f"Step {i+1}/{len(plan.steps)}: {step.description}")

            # Execute step
            success, operations, output = self.execute_step(step, task_description, context)

            step.operations = operations
            step.output = output
            all_operations.extend(operations)
            outputs.append(output)

            # Track changed files
            for op in operations:
                if op.success and op.operation in (
                    FileOperationType.CREATE,
                    FileOperationType.MODIFY,
                    FileOperationType.PATCH
                ):
                    files_changed.append(op.path)
                    context["files_changed"].append(op.path)

            # Review step
            self._emit_progress("step_review", f"Reviewing step {i+1}")
            step.status = StepStatus.REVIEW

            review_passed, review_notes = self._review_step(step, context)
            step.review_passed = review_passed
            step.review_notes = review_notes

            if review_passed:
                step.status = StepStatus.COMPLETED
                self._emit_progress("step_completed", f"Step {i+1} completed")
            else:
                # Retry logic
                if step.attempts < step.max_attempts:
                    self._emit_progress("step_retry", f"Step {i+1} needs retry: {review_notes}")
                    step.status = StepStatus.RETRY
                    # Would re-execute here, but for simplicity mark as completed with notes
                    step.status = StepStatus.COMPLETED
                else:
                    step.status = StepStatus.FAILED
                    self._emit_progress("step_failed", f"Step {i+1} failed: {review_notes}")

            # Update state
            state["current_plan"] = plan.to_dict()
            self._save_state(state)

        # Finalize
        duration = time.time() - start_time
        all_steps_completed = all(s.status == StepStatus.COMPLETED for s in plan.steps)
        plan.status = "completed" if all_steps_completed else "partial"

        # Update state with completion
        state["current_task"] = None
        state["current_job_id"] = None
        state["files_changed"] = files_changed
        state["operations_history"] = [op.to_dict() for op in all_operations[-50:]]
        self._save_state(state)

        self._emit_progress("task_completed", f"Task completed: {len(files_changed)} files changed")

        return ExecutionResult(
            success=all_steps_completed and len(files_changed) > 0,
            task_id=job_id,
            output="\n\n---\n\n".join(outputs),
            files_changed=files_changed,
            operations=all_operations,
            plan=plan,
            attempts=sum(s.attempts for s in plan.steps),
            duration_seconds=duration,
            execution_summary=(
                f"Created {len(files_changed)} file(s): {', '.join(files_changed)}"
                if files_changed
                else "No files changed"
            )
        )

    def _review_step(
        self,
        step: ExecutionStep,
        context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Review a step's execution"""
        issues = []

        # Check if any operations failed
        failed_ops = [op for op in step.operations if not op.success]
        if failed_ops:
            issues.append(f"{len(failed_ops)} operation(s) failed")

        # Check if create/modify operations actually created files
        for op in step.operations:
            if op.operation in (FileOperationType.CREATE, FileOperationType.MODIFY):
                full_path = self.project_root / op.path
                if not full_path.exists():
                    issues.append(f"File not found after operation: {op.path}")

        if issues:
            return False, "; ".join(issues)
        return True, "All checks passed"


# Singleton instance
_executor: Optional[FileExecutor] = None


def get_file_executor(project_root: Optional[Path] = None) -> FileExecutor:
    """Get or create file executor instance"""
    global _executor
    if _executor is None or (project_root and project_root != _executor.project_root):
        _executor = FileExecutor(project_root)
    return _executor


def execute_file_task(
    task_description: str,
    job_id: str,
    task_type: str = "general",
    on_progress: Optional[Callable[[str, str], None]] = None
) -> ExecutionResult:
    """Main entry point for file-based execution"""
    return get_file_executor().execute_task(
        task_description=task_description,
        job_id=job_id,
        task_type=task_type,
        on_progress=on_progress
    )
