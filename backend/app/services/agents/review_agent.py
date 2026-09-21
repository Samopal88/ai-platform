"""
AI Workspace Platform - Review Agent
Agent responsible for reviewing code changes

The Reviewer:
- Reviews code for quality
- Checks for issues and bugs
- Suggests improvements
- Validates against requirements
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

from app.services.agents.base_agent import BaseAgent, AgentResult


class ReviewAgent(BaseAgent):
    """
    Review agent that analyzes code changes.

    In MVP mode, provides basic review checklist.
    Can use ClaudeExecutor for detailed analysis.
    """

    @property
    def name(self) -> str:
        return "reviewer"

    @property
    def description(self) -> str:
        return "Reviews code changes for quality, issues, and improvements"

    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Review code for the given task.

        Args:
            task: What to review (description or file list)
            context: Additional context (diff, files, requirements)

        Returns:
            AgentResult with review findings
        """
        start = datetime.now()

        try:
            # Check if we should use AI for review
            use_ai = context.get("use_ai", False) if context else False

            if use_ai:
                return self._review_with_ai(task, context, start)
            else:
                return self._review_basic(task, context, start)

        except Exception as e:
            return self._error_result(str(e), self._measure_time(start))

    def _review_basic(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        start: datetime
    ) -> AgentResult:
        """Basic review checklist without AI"""

        # Get files from context
        files = context.get("files", []) if context else []

        checklist = """
### Review Checklist

#### Code Quality
- [ ] Code follows project conventions
- [ ] No obvious bugs or errors
- [ ] Proper error handling
- [ ] No hardcoded values

#### Security
- [ ] No sensitive data exposed
- [ ] Input validation present
- [ ] No injection vulnerabilities

#### Performance
- [ ] No obvious performance issues
- [ ] Efficient algorithms used
- [ ] No unnecessary operations

#### Maintainability
- [ ] Code is readable
- [ ] Functions are focused
- [ ] Good naming conventions

#### Testing
- [ ] Tests updated if needed
- [ ] Edge cases considered
"""

        files_section = ""
        if files:
            files_section = f"""
### Files to Review
{chr(10).join(['- ' + f for f in files])}
"""

        output = f"""## Review: {task[:100]}

{files_section}
{checklist}

### Status
**Mode:** Self (basic checklist)
**Action Required:** Manual review or use AI mode for detailed analysis.

### Verdict
- Pending manual review
"""

        return self._success_result(
            output=output,
            next_action="approve_or_revise",
            time_ms=self._measure_time(start)
        )

    def _review_with_ai(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        start: datetime
    ) -> AgentResult:
        """Review using AI"""

        # Build context from files
        file_context = ""
        files = context.get("files", []) if context else []

        for file_path in files[:3]:  # Limit to 3 files
            try:
                path = Path(self.project_root) / file_path
                if path.exists():
                    content = path.read_text()[:3000]  # First 3000 chars
                    file_context += f"\n\n### {file_path}\n```\n{content}\n```"
            except Exception:
                pass

        # Include diff if provided
        diff = context.get("diff", "") if context else ""
        if diff:
            file_context += f"\n\n### Changes (diff)\n```diff\n{diff[:2000]}\n```"

        prompt = f"""Review this code change:

Task: {task}

{f'Code to Review:{file_context}' if file_context else 'No code provided for review.'}

Please analyze:
1. Code quality and correctness
2. Potential bugs or issues
3. Security concerns
4. Performance considerations
5. Suggestions for improvement

Provide a clear verdict: APPROVE, REQUEST_CHANGES, or NEEDS_DISCUSSION
"""

        result = self.executor.execute(prompt, task_type="analyze")

        if result.success:
            # Determine next action based on review
            next_action = "approved"
            output = result.answer.lower()
            if "request_changes" in output or "changes requested" in output:
                next_action = "revise"
            elif "needs_discussion" in output or "discuss" in output:
                next_action = "discuss"

            return self._success_result(
                output=result.answer,
                files=files,
                next_action=next_action,
                time_ms=self._measure_time(start)
            )
        else:
            # Fallback to basic
            return self._review_basic(task, context, start)
