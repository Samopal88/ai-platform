"""
AI Workspace Platform - Claude Executor Service
Minimal executor that can work in self mode or claude mode

Modes:
- self: Execute task locally without Claude API
- claude: Execute task via Claude API (when available)

Returns:
- answer: Response text
- mode: Which mode was used (self/claude)
- changed_files: List of files changed
- summary: Brief task summary
"""
import os
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from app.core.config import settings


class ExecutionMode(str, Enum):
    SELF = "self"
    CLAUDE = "claude"


@dataclass
class ExecutionResult:
    """Result of task execution"""
    answer: str
    mode: ExecutionMode
    changed_files: List[str]
    summary: str
    success: bool
    error: Optional[str] = None
    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "mode": self.mode.value,
            "changed_files": self.changed_files,
            "summary": self.summary,
            "success": self.success,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms
        }


class ClaudeExecutor:
    """
    Executor for AI tasks.
    Can operate in self mode (local) or claude mode (API).
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        claude_api_key: Optional[str] = None,
        prefer_mode: ExecutionMode = ExecutionMode.SELF
    ):
        self.project_root = project_root or Path(settings.PROJECT_ROOT)
        self.claude_api_key = claude_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.prefer_mode = prefer_mode
        self._claude_available = self._check_claude_available()

    def _check_claude_available(self) -> bool:
        """Check if Claude API is available"""
        if not self.claude_api_key:
            return False
        # For now, just check if key exists
        # In production, would verify with a test API call
        return len(self.claude_api_key) > 10

    def get_available_mode(self) -> ExecutionMode:
        """Get the mode that will be used for execution"""
        if self.prefer_mode == ExecutionMode.CLAUDE and self._claude_available:
            return ExecutionMode.CLAUDE
        return ExecutionMode.SELF

    def execute(
        self,
        prompt: str,
        task_type: str = "general",
        context: Optional[Dict[str, Any]] = None,
        force_mode: Optional[ExecutionMode] = None
    ) -> ExecutionResult:
        """
        Execute a task.

        Args:
            prompt: Task description/prompt
            task_type: Type of task (general, code, analysis, etc.)
            context: Additional context for the task
            force_mode: Force specific execution mode

        Returns:
            ExecutionResult with answer and metadata
        """
        start_time = datetime.now()
        mode = force_mode or self.get_available_mode()

        try:
            if mode == ExecutionMode.CLAUDE:
                result = self._execute_claude(prompt, task_type, context)
            else:
                result = self._execute_self(prompt, task_type, context)

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            result.execution_time_ms = execution_time
            result.mode = mode
            return result

        except Exception as e:
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            return ExecutionResult(
                answer="",
                mode=mode,
                changed_files=[],
                summary=f"Execution failed: {str(e)}",
                success=False,
                error=f"{str(e)}\n{traceback.format_exc()}",
                execution_time_ms=execution_time
            )

    def _execute_self(
        self,
        prompt: str,
        task_type: str,
        context: Optional[Dict[str, Any]]
    ) -> ExecutionResult:
        """
        Execute task in self mode (local processing).
        This is a minimal implementation that acknowledges the task.
        """
        # Parse task to understand what's being asked
        task_analysis = self._analyze_task(prompt, task_type)

        # Generate response based on task type
        if task_type == "status":
            answer = self._generate_status_response()
        elif task_type == "analyze":
            answer = self._generate_analysis_response(prompt, context)
        elif task_type == "code":
            answer = self._generate_code_response(prompt, context)
        else:
            answer = self._generate_general_response(prompt, task_analysis)

        return ExecutionResult(
            answer=answer,
            mode=ExecutionMode.SELF,
            changed_files=[],
            summary=f"Self-mode execution: {task_analysis.get('summary', 'Task processed')}",
            success=True
        )

    def _execute_claude(
        self,
        prompt: str,
        task_type: str,
        context: Optional[Dict[str, Any]]
    ) -> ExecutionResult:
        """
        Execute task via Claude API.
        Fallback to self mode if API fails.
        """
        try:
            # Import anthropic only when needed
            import anthropic

            client = anthropic.Anthropic(api_key=self.claude_api_key)

            # Build system message based on task type
            system_message = self._build_system_message(task_type)

            # Build user message with context
            user_message = prompt
            if context:
                user_message = f"Context:\n{json.dumps(context, indent=2)}\n\nTask:\n{prompt}"

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=system_message,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )

            answer = response.content[0].text

            # Extract any file changes mentioned in response
            changed_files = self._extract_changed_files(answer)

            return ExecutionResult(
                answer=answer,
                mode=ExecutionMode.CLAUDE,
                changed_files=changed_files,
                summary=f"Claude API execution completed",
                success=True
            )

        except ImportError:
            # anthropic library not installed, fallback to self
            return self._execute_self(prompt, task_type, context)

        except Exception as e:
            # API error, fallback to self with note
            self_result = self._execute_self(prompt, task_type, context)
            self_result.answer = f"[Claude API unavailable, using self mode]\n\n{self_result.answer}"
            self_result.error = f"Claude API error: {str(e)}"
            return self_result

    def _analyze_task(self, prompt: str, task_type: str) -> Dict[str, Any]:
        """Analyze task to understand intent"""
        prompt_lower = prompt.lower()

        analysis = {
            "type": task_type,
            "summary": prompt[:100] + "..." if len(prompt) > 100 else prompt,
            "keywords": []
        }

        # Extract keywords
        keywords = []
        if "create" in prompt_lower or "создай" in prompt_lower:
            keywords.append("create")
        if "fix" in prompt_lower or "исправ" in prompt_lower:
            keywords.append("fix")
        if "update" in prompt_lower or "обнов" in prompt_lower:
            keywords.append("update")
        if "analyze" in prompt_lower or "анализ" in prompt_lower:
            keywords.append("analyze")
        if "status" in prompt_lower or "статус" in prompt_lower:
            keywords.append("status")

        analysis["keywords"] = keywords
        return analysis

    def _generate_status_response(self) -> str:
        """Generate a status response"""
        state_file = self.project_root / "docs" / "progress" / "state.json"
        status_file = self.project_root / "docs" / "progress" / "CURRENT_STATUS.md"

        response_parts = ["## Current Status\n"]

        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                response_parts.append(f"**Stage:** {state.get('current_stage', 'unknown')}")
                response_parts.append(f"**Mode:** {state.get('mode', 'self')}")
                if state.get('active_task'):
                    response_parts.append(f"**Active Task:** {state.get('active_task')}")
                if state.get('last_completed_task'):
                    response_parts.append(f"**Last Completed:** {state.get('last_completed_task')}")
            except Exception:
                response_parts.append("Unable to read state file")

        return "\n".join(response_parts)

    def _generate_analysis_response(self, prompt: str, context: Optional[Dict]) -> str:
        """Generate an analysis response"""
        return f"""## Analysis Result

**Task:** {prompt[:200]}

### Summary
Task received and analyzed in self mode.

### Observations
- Prompt length: {len(prompt)} characters
- Context provided: {'Yes' if context else 'No'}
- Analysis mode: Local processing

### Recommendation
For deeper analysis, Claude API mode is recommended.
"""

    def _generate_code_response(self, prompt: str, context: Optional[Dict]) -> str:
        """Generate a code-related response"""
        return f"""## Code Task Result

**Task:** {prompt[:200]}

### Status
Task acknowledged. In self mode, code generation is limited.

### Available Actions
- Read existing files
- Analyze structure
- Provide guidance

### Recommendation
For code generation/modification, Claude API mode is recommended.
"""

    def _generate_general_response(self, prompt: str, analysis: Dict) -> str:
        """Generate a general response"""
        keywords_str = ", ".join(analysis.get("keywords", [])) or "none detected"

        return f"""## Task Received

**Task:** {prompt[:300]}{"..." if len(prompt) > 300 else ""}

### Analysis
- Keywords detected: {keywords_str}
- Task type: {analysis.get('type', 'general')}

### Execution Mode
Running in **self mode** (local processing).

### Status
Task acknowledged and logged. Ready for next instruction.
"""

    def _build_system_message(self, task_type: str) -> str:
        """Build system message for Claude API based on task type"""
        base_message = """You are an AI assistant helping to build the AI Workspace Platform.
You are operating within a development environment.

Current project: AI Workspace Platform
Location: /opt/ai-workspace/storage/projects/ai-platform

Guidelines:
- Be concise and practical
- Focus on actionable outputs
- If modifying files, list them clearly
- Use markdown formatting
"""

        type_specific = {
            "code": "\nFocus on code quality, maintainability, and best practices.",
            "analyze": "\nProvide thorough analysis with clear structure.",
            "status": "\nProvide clear, concise status updates.",
            "plan": "\nCreate detailed, step-by-step plans."
        }

        return base_message + type_specific.get(task_type, "")

    def _extract_changed_files(self, response: str) -> List[str]:
        """Extract file paths mentioned in response"""
        import re
        files = []

        # Look for file paths in common patterns
        patterns = [
            r'`([^\`]+\.[a-zA-Z]{2,4})`',  # backtick wrapped files
            r'(?:created|modified|updated|changed):\s*([^\s\n]+\.[a-zA-Z]{2,4})',  # action: file
            r'(?:backend|frontend|docs)/[^\s\n\`]+\.[a-zA-Z]{2,4}',  # path patterns
        ]

        for pattern in patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            files.extend(matches)

        # Remove duplicates and clean
        seen = set()
        clean_files = []
        for f in files:
            f = f.strip()
            if f and f not in seen and "." in f:
                seen.add(f)
                clean_files.append(f)

        return clean_files[:20]  # Limit to 20 files


# Convenience function
def execute_task(
    prompt: str,
    task_type: str = "general",
    context: Optional[Dict[str, Any]] = None,
    project_root: Optional[Path] = None
) -> ExecutionResult:
    """
    Convenience function to execute a task.

    Args:
        prompt: Task description
        task_type: Type of task
        context: Additional context
        project_root: Project root path

    Returns:
        ExecutionResult
    """
    executor = ClaudeExecutor(project_root=project_root)
    return executor.execute(prompt, task_type, context)


def get_execution_mode() -> str:
    """Get the current execution mode that will be used"""
    executor = ClaudeExecutor()
    return executor.get_available_mode().value
