"""
Task Level Classifier — assigns a level 0-5 to every task before dispatch.

Levels control:
  - context budget (docs + code files allowed)
  - review strictness
  - retry policy
  - phase gate requirement
  - regression scan scope

See docs/agent/TASK_LEVELS.md for the full specification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Level specification table
# ---------------------------------------------------------------------------

@dataclass
class LevelSpec:
    level: int
    name: str
    description: str
    max_target_files: int
    max_doc_chars: int          # total chars from docs allowed in reference pack
    max_code_chars: int         # total chars from code refs allowed
    max_retries: int
    phase_gate_required: bool
    semantic_validation: str    # "none" | "partial" | "full"
    regression_scope: str       # "target" | "target_deps" | "extended" | "full"
    false_accept_audit: bool
    escalate_on_block: bool
    auto_accept: bool


_LEVEL_SPECS: dict[int, LevelSpec] = {
    0: LevelSpec(
        level=0, name="Trivial Patch",
        description="Single-file, single-change, no logic. One-line fix, constant update.",
        max_target_files=1, max_doc_chars=0, max_code_chars=0,
        max_retries=1, phase_gate_required=False,
        semantic_validation="none", regression_scope="target",
        false_accept_audit=False, escalate_on_block=False, auto_accept=True,
    ),
    1: LevelSpec(
        level=1, name="Local Structural",
        description="Single-file, well-defined structure, no cross-file deps. Schema, config, simple util.",
        max_target_files=2, max_doc_chars=500, max_code_chars=300,
        max_retries=2, phase_gate_required=False,
        semantic_validation="partial", regression_scope="target",
        false_accept_audit=False, escalate_on_block=False, auto_accept=False,
    ),
    2: LevelSpec(
        level=2, name="Semantic Implementation",
        description="Creating a real service, router, or page implementing declared product behavior.",
        max_target_files=3, max_doc_chars=1500, max_code_chars=600,
        max_retries=2, phase_gate_required=False,  # conditional — set by classifier
        semantic_validation="full", regression_scope="target",
        false_accept_audit=True, escalate_on_block=False, auto_accept=False,
    ),
    3: LevelSpec(
        level=3, name="Multi-File Integration",
        description="2+ files that must work together. Router+service, page+API, migration+model.",
        max_target_files=5, max_doc_chars=3000, max_code_chars=1200,
        max_retries=2, phase_gate_required=True,
        semantic_validation="full", regression_scope="target_deps",
        false_accept_audit=True, escalate_on_block=True, auto_accept=False,
    ),
    4: LevelSpec(
        level=4, name="Phase-Critical",
        description="Unlocks a phase or provides a foundation many tasks depend on.",
        max_target_files=3, max_doc_chars=6000, max_code_chars=2000,
        max_retries=3, phase_gate_required=True,
        semantic_validation="full", regression_scope="extended",
        false_accept_audit=True, escalate_on_block=True, auto_accept=False,
    ),
    5: LevelSpec(
        level=5, name="Architecture/Migration",
        description="DB schema, auth, core middleware, multi-file restructuring. High blast radius.",
        max_target_files=8, max_doc_chars=999999, max_code_chars=999999,
        max_retries=1, phase_gate_required=True,
        semantic_validation="full", regression_scope="full",
        false_accept_audit=True, escalate_on_block=True, auto_accept=False,
    ),
}


def get_spec(level: int) -> LevelSpec:
    return _LEVEL_SPECS.get(level, _LEVEL_SPECS[2])


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    level: int
    spec: LevelSpec
    reasons: list[str] = field(default_factory=list)
    phase_gate_applies: bool = False  # refined from spec for this specific task


# ---------------------------------------------------------------------------
# Keyword patterns that bump the level
# ---------------------------------------------------------------------------

# (min_level_triggered, keywords)
_KEYWORD_RULES: list[tuple[int, list[str]]] = [
    # Level 5 triggers
    (5, ["alembic", "migrate", "migration", "auth", "authentication", "refactor all",
         "restructure", "core middleware"]),
    # Level 4 triggers
    (4, ["main.py", "app.include_router", "register.*router", "session.py", "get_db",
         "requirements.txt", "env.py", "alembic.ini", "phase-critical", "foundation"]),
    # Level 3 triggers
    (3, ["register", "wire", "integrate", "connect", "both.*file", "multi-file",
         "router.*service", "service.*router", "and register"]),
    # Level 2 triggers (if file count and change size are modest)
    (2, ["create.*service", "create.*router", "create.*endpoint", "implement",
         "production", "real implementation"]),
]

_RISKY_STEMS = {"main", "session", "base", "config", "env", "alembic", "__init__"}
_INTEGRATION_STEMS = {"router", "main", "app"}


def classify(task: dict) -> ClassificationResult:
    """
    Assign a task level based on file count, file types, keywords, and change description.

    task keys used: id, title, files, change, why, phase
    """
    files: list[str] = task.get("files", [])
    title: str = task.get("title", "").lower()
    change: str = task.get("change", "").lower()
    combined = f"{title} {change}"

    level = 0
    reasons: list[str] = []

    # ── File count baseline ────────────────────────────────────────────────
    n = len(files)
    if n == 0:
        level = max(level, 1)
        reasons.append("no explicit target files — at least level 1")
    elif n == 1:
        level = max(level, 1)
    elif n == 2:
        level = max(level, 1)
        reasons.append("2 target files → level 1 baseline")
    elif n >= 3:
        level = max(level, 2)
        reasons.append(f"{n} target files → level 2 baseline")
    if n > 3:
        level = max(level, 3)
        reasons.append(f"{n} target files → level 3 baseline (multi-file)")

    # ── File type analysis ─────────────────────────────────────────────────
    has_api = any("app/api/" in f for f in files)
    has_service = any("app/services/" in f for f in files)
    has_frontend = any(f.startswith("frontend/") for f in files)
    has_main = any("main.py" in f for f in files)
    has_migration = any("alembic" in f or "migration" in f for f in files)
    has_risky = any(
        any(f.endswith(f"{s}.py") or f"/{s}.py" in f for s in _RISKY_STEMS)
        for f in files
    )

    if has_api and has_service:
        level = max(level, 3)
        reasons.append("API + service in same task → level 3")
    elif has_api or has_service:
        level = max(level, 2)
        reasons.append("API or service file → level 2")
    if has_frontend:
        level = max(level, 2)
        reasons.append("frontend file → level 2")
    if has_main:
        level = max(level, 4)
        reasons.append("main.py in target → level 4")
    if has_migration:
        level = max(level, 5)
        reasons.append("migration file → level 5")
    if has_risky:
        level = max(level, 4)
        reasons.append(f"risky foundation file in targets → level 4")

    # ── Change description length ──────────────────────────────────────────
    if len(task.get("change", "")) > 200:
        level = max(level, 2)
        reasons.append("detailed change description → at least level 2")

    # ── Keyword rules ──────────────────────────────────────────────────────
    for min_level, keywords in _KEYWORD_RULES:
        for kw in keywords:
            import re as _re
            if _re.search(kw, combined):
                if level < min_level:
                    level = min_level
                    reasons.append(f"keyword '{kw}' → level {min_level}")
                break  # only add one reason per rule group

    # ── Cap at 5 ──────────────────────────────────────────────────────────
    level = min(level, 5)

    spec = get_spec(level)

    # Determine if phase gate applies specifically
    # (Level 2 tasks involving APIs or integration check gate)
    phase_gate_applies = spec.phase_gate_required or (
        level == 2 and (has_api or has_service or has_frontend)
    )

    return ClassificationResult(
        level=level,
        spec=spec,
        reasons=reasons,
        phase_gate_applies=phase_gate_applies,
    )


# ---------------------------------------------------------------------------
# Retry policy helper
# ---------------------------------------------------------------------------

def max_retries_for(level: int) -> int:
    return get_spec(level).max_retries


def should_escalate_on_block(level: int) -> bool:
    return get_spec(level).escalate_on_block


def requires_semantic_validation(level: int) -> bool:
    return get_spec(level).semantic_validation != "none"


def requires_false_accept_audit(level: int) -> bool:
    return get_spec(level).false_accept_audit
