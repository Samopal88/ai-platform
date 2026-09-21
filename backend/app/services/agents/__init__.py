"""
AI Workspace Platform - Agents Package
Minimal agent architecture for autonomous development
"""
from app.services.agents.base_agent import BaseAgent, AgentResult
from app.services.agents.planner_agent import PlannerAgent
from app.services.agents.coder_agent import CoderAgent
from app.services.agents.review_agent import ReviewAgent

__all__ = [
    "BaseAgent",
    "AgentResult",
    "PlannerAgent",
    "CoderAgent",
    "ReviewAgent",
]
