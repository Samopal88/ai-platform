"""
AI Workspace Platform - Planner Agent
Agent responsible for planning tasks and breaking them into steps

The Planner:
- Analyzes task requirements
- Creates step-by-step plans
- Identifies dependencies
- Estimates complexity
"""
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.services.agents.base_agent import BaseAgent, AgentResult


class PlannerAgent(BaseAgent):
    """
    Planner agent that creates execution plans for tasks.

    In MVP mode, provides basic planning without AI.
    Can use ClaudeExecutor for more detailed planning.
    """

    @property
    def name(self) -> str:
        return "planner"

    @property
    def description(self) -> str:
        return "Creates step-by-step plans for development tasks"

    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Create a plan for the given task.

        Args:
            task: Task description
            context: Additional context (files, requirements, etc.)

        Returns:
            AgentResult with the plan
        """
        start = datetime.now()

        try:
            # Check if we should use AI for planning
            use_ai = context.get("use_ai", False) if context else False

            if use_ai:
                return self._plan_with_ai(task, context, start)
            else:
                return self._plan_basic(task, context, start)

        except Exception as e:
            return self._error_result(str(e), self._measure_time(start))

    def _plan_basic(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        start: datetime
    ) -> AgentResult:
        """Create a basic plan without AI"""

        # Analyze task keywords
        task_lower = task.lower()
        steps = []

        # Determine task type and create appropriate steps
        if "create" in task_lower or "add" in task_lower or "implement" in task_lower:
            steps = [
                "1. Analyze requirements and existing code",
                "2. Design solution structure",
                "3. Implement core functionality",
                "4. Add error handling",
                "5. Test implementation",
                "6. Update documentation if needed"
            ]
        elif "fix" in task_lower or "bug" in task_lower or "исправ" in task_lower:
            steps = [
                "1. Reproduce the issue",
                "2. Identify root cause",
                "3. Design fix approach",
                "4. Implement fix",
                "5. Verify fix works",
                "6. Check for regressions"
            ]
        elif "refactor" in task_lower or "improve" in task_lower:
            steps = [
                "1. Review current implementation",
                "2. Identify improvement areas",
                "3. Plan changes",
                "4. Implement refactoring",
                "5. Run tests",
                "6. Update affected code"
            ]
        elif "test" in task_lower:
            steps = [
                "1. Identify test scenarios",
                "2. Write test cases",
                "3. Implement tests",
                "4. Run tests",
                "5. Fix failing tests"
            ]
        else:
            steps = [
                "1. Understand task requirements",
                "2. Research and analyze",
                "3. Plan approach",
                "4. Implement solution",
                "5. Verify results"
            ]

        plan = f"""## Plan for: {task[:100]}

### Steps
{chr(10).join(steps)}

### Estimated Complexity
- Type: {'Simple' if len(task) < 100 else 'Medium'}
- Files: ~1-3

### Dependencies
- None identified

### Notes
- Plan generated in basic mode
- For detailed planning, use AI mode
"""

        return self._success_result(
            output=plan,
            next_action="execute_plan",
            time_ms=self._measure_time(start)
        )

    def _plan_with_ai(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        start: datetime
    ) -> AgentResult:
        """Create a plan using AI"""

        prompt = f"""Create a detailed development plan for this task:

Task: {task}

Context: {context or 'None provided'}

Please provide:
1. Step-by-step execution plan
2. Files that need to be created or modified
3. Dependencies and prerequisites
4. Potential risks or blockers
5. Estimated complexity

Format the response as a clear, actionable plan.
"""

        result = self.executor.execute(prompt, task_type="plan")

        if result.success:
            return self._success_result(
                output=result.answer,
                next_action="execute_plan",
                time_ms=self._measure_time(start)
            )
        else:
            # Fallback to basic planning
            return self._plan_basic(task, context, start)
