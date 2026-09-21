"""Plan catalog for the Russian paid MVP."""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class PlanDefinition:
    code: str
    name: str
    price_amount: int
    price_currency: str
    project_limit: int
    storage_limit_total: int
    storage_limit_per_project: int
    token_limit_month: int
    is_free: bool = False


MB = 1024 * 1024
GB = 1024 * MB


DEFAULT_PLANS: tuple[PlanDefinition, ...] = (
    PlanDefinition(
        code="free",
        name="Бесплатный",
        price_amount=0,
        price_currency="RUB",
        project_limit=1,
        storage_limit_total=50 * MB,
        storage_limit_per_project=25 * MB,
        token_limit_month=50_000,
        is_free=True,
    ),
    PlanDefinition(
        code="starter_490",
        name="Старт",
        price_amount=490,
        price_currency="RUB",
        project_limit=10,
        storage_limit_total=500 * MB,
        storage_limit_per_project=100 * MB,
        token_limit_month=500_000,
    ),
    PlanDefinition(
        code="medium",
        name="Средний",
        price_amount=1490,
        price_currency="RUB",
        project_limit=30,
        storage_limit_total=1 * GB,
        storage_limit_per_project=100 * MB,
        token_limit_month=1_000_000,
    ),
    PlanDefinition(
        code="pro",
        name="Максимальный",
        price_amount=2990,
        price_currency="RUB",
        project_limit=50,
        storage_limit_total=3 * GB,
        storage_limit_per_project=250 * MB,
        token_limit_month=2_000_000,
    ),
)


def list_plan_definitions() -> list[dict]:
    return [asdict(plan) for plan in DEFAULT_PLANS]


def get_plan_definition(code: str) -> PlanDefinition | None:
    normalized = (code or "").strip().lower()
    for plan in DEFAULT_PLANS:
        if plan.code == normalized:
            return plan
    return None
