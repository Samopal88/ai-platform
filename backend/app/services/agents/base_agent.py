"""
AI Workspace Platform - Base Agent
Abstract base class for all agents

All agents:
- Accept a task
- Return a result
- Can use claude_executor
- Have minimal logic in MVP
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.core.config import settings


@dataclass
class AgentResult:
    """Result returned by an agent"""
    success: bool
    output: str
    files_changed: List[str]
    next_action: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "files_changed": self.files_changed,
            "next_action": self.next_action,
            "metadata": self.metadata or {},
            "execution_time_ms": self.execution_time_ms
        }


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Each agent:
    - Has a name and description
    - Can process a task
    - Returns an AgentResult
    - May use ClaudeExecutor for AI tasks
    """

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or settings.PROJECT_ROOT
        self._executor = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Agent description"""
        pass

    @property
    def executor(self):
        """Get or create executor instance"""
        if self._executor is None:
            from app.services.claude_executor import ClaudeExecutor
            from pathlib import Path
            self._executor = ClaudeExecutor(project_root=Path(self.project_root))
        return self._executor

    @abstractmethod
    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Process a task and return result.

        Args:
            task: Task description/prompt
            context: Additional context for the task

        Returns:
            AgentResult with output and metadata
        """
        pass

    def _measure_time(self, start: datetime) -> int:
        """Calculate elapsed time in milliseconds"""
        return int((datetime.now() - start).total_seconds() * 1000)

    def _success_result(
        self,
        output: str,
        files: List[str] = None,
        next_action: str = None,
        time_ms: int = 0
    ) -> AgentResult:
        """Create a success result"""
        return AgentResult(
            success=True,
            output=output,
            files_changed=files or [],
            next_action=next_action,
            execution_time_ms=time_ms
        )

    def _error_result(
        self,
        error: str,
        time_ms: int = 0
    ) -> AgentResult:
        """Create an error result"""
        return AgentResult(
            success=False,
            output=f"Error: {error}",
            files_changed=[],
            execution_time_ms=time_ms
        )
