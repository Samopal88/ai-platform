"""
AI Workspace Platform - Coder Agent
Agent responsible for implementing code changes

The Coder:
- Writes code based on plans or direct tasks
- Modifies existing files
- Creates new files
- Follows project conventions
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

from app.services.agents.base_agent import BaseAgent, AgentResult


class CoderAgent(BaseAgent):
    """
    Coder agent that implements code changes.

    In MVP mode, provides task acknowledgment.
    Can use ClaudeExecutor for actual code generation.
    """

    @property
    def name(self) -> str:
        return "coder"

    @property
    def description(self) -> str:
        return "Implements code changes based on plans or direct tasks"

    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Implement code for the given task.

        Args:
            task: Task/plan to implement
            context: Additional context (files, plan, etc.)

        Returns:
            AgentResult with implementation details
        """
        start = datetime.now()

        try:
            # Check if we should use AI for coding
            use_ai = context.get("use_ai", False) if context else False

            if use_ai:
                return self._code_with_ai(task, context, start)
            else:
                return self._code_basic(task, context, start)

        except Exception as e:
            return self._error_result(str(e), self._measure_time(start))

    def _code_basic(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        start: datetime
    ) -> AgentResult:
        """Basic code response without AI"""

        # Analyze what files might be involved
        files_mentioned = self._extract_file_hints(task, context)

        output = f"""## Coding Task: {task[:100]}

### Analysis
Task received and analyzed.

### Files to Modify
{chr(10).join(['- ' + f for f in files_mentioned]) if files_mentioned else '- No specific files identified'}

### Implementation Approach
1. Review existing code structure
2. Identify modification points
3. Implement changes
4. Test modifications

### Status
**Mode:** Self (basic)
**Action Required:** For actual code changes, use AI mode or manual implementation.

### Recommendation
To implement this task:
1. Use AI mode for code generation
2. Or manually edit the identified files
"""

        return self._success_result(
            output=output,
            files=files_mentioned,
            next_action="review" if files_mentioned else "plan",
            time_ms=self._measure_time(start)
        )

    def _code_with_ai(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        start: datetime
    ) -> AgentResult:
        """Generate code using AI"""

        # Build context from files if provided
        file_context = ""
        if context and "files" in context:
            for file_path in context["files"][:5]:  # Limit to 5 files
                try:
                    path = Path(self.project_root) / file_path
                    if path.exists():
                        content = path.read_text()[:2000]  # First 2000 chars
                        file_context += f"\n\n### {file_path}\n```\n{content}\n```"
                except Exception:
                    pass

        prompt = f"""Implement this coding task:

Task: {task}

Project: {self.project_root}

{f'Relevant Files:{file_context}' if file_context else ''}

Please provide:
1. Code implementation
2. Files to create or modify
3. Any dependencies needed
4. Brief explanation of changes

Focus on minimal, clean implementation that follows existing patterns.
"""

        result = self.executor.execute(prompt, task_type="code")

        if result.success:
            return self._success_result(
                output=result.answer,
                files=result.changed_files,
                next_action="review",
                time_ms=self._measure_time(start)
            )
        else:
            # Fallback to basic
            return self._code_basic(task, context, start)

    def _extract_file_hints(
        self,
        task: str,
        context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Extract file hints from task and context"""
        files = []

        # Check context for explicit files
        if context and "files" in context:
            files.extend(context["files"])

        # Look for file patterns in task
        import re

        # Match common file patterns
        patterns = [
            r'`([^`]+\.[a-zA-Z]{2,4})`',
            r'(\w+/[\w/]+\.[a-zA-Z]{2,4})',
            r'(backend/\S+)',
            r'(frontend/\S+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, task)
            files.extend(matches)

        # Remove duplicates and clean
        seen = set()
        clean_files = []
        for f in files:
            f = f.strip()
            if f and f not in seen:
                seen.add(f)
                clean_files.append(f)

        return clean_files[:10]  # Limit to 10 files
