"""
Phase Gate — Checks whether the current phase's preconditions are met
before the manager dispatches a task that requires them.

See docs/agent/PHASE_GATES.md for the full policy specification.

Usage:
  result = check(phase_name, project_root)
  if result.verdict == "blocked":
      # select repair tasks first
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PhaseGateResult:
    phase: str
    verdict: str          # cleared | warning | blocked | escalate
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repair_tasks_needed: list[str] = field(default_factory=list)
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "verdict": self.verdict,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
            "repair_tasks_needed": self.repair_tasks_needed,
            "checked_at": self.checked_at,
        }


# ---------------------------------------------------------------------------
# File validity helpers
# ---------------------------------------------------------------------------

def _file_exists_nonempty(project_root: Path, rel_path: str) -> bool:
    f = project_root / rel_path
    return f.exists() and f.stat().st_size > 50  # >50 bytes = not trivially empty


def _file_has_pattern(project_root: Path, rel_path: str, pattern: str) -> bool:
    f = project_root / rel_path
    if not f.exists():
        return False
    try:
        content = f.read_text(encoding="utf-8", errors="replace")
        return bool(re.search(pattern, content))
    except Exception:
        return False


def _file_is_stub(project_root: Path, rel_path: str) -> bool:
    """
    Return True if file looks like a stub (def main(): pass pattern).
    Uses the same detection as false_accept_auditor.
    """
    f = project_root / rel_path
    if not f.exists():
        return False
    try:
        content = f.read_text(encoding="utf-8", errors="replace")
        # Pattern: only a def main(): pass wrapper
        if re.search(
            r'def main\s*\(\s*\):\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass',
            content, re.DOTALL
        ):
            return True
        # Pattern: all functions are stubs
        all_defs = re.findall(r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:', content)
        pass_bodies = re.findall(
            r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass\b',
            content, re.DOTALL
        )
        if all_defs and len(all_defs) >= 2 and len(pass_bodies) == len(all_defs):
            return True
    except Exception:
        pass
    return False


def _executive_memory_status(project_root: Path, rel_path: str) -> Optional[str]:
    """
    Return the confidence/status of a file from executive memory.
    Returns: 'verified' | 'structural' | 'file_only' | 'false_positive' | None (not in memory)
    """
    try:
        from app.services.executive_memory import load as load_mem
        mem = load_mem(project_root)
        # Check false_positives first
        for fp in mem.get("false_positives", []):
            if fp.get("file") == rel_path and fp.get("status") != "repaired":
                return "false_positive"
        # Check implemented
        for cat in ("pages", "api_routers", "services", "schemas", "migrations"):
            for e in mem.get("implemented", {}).get(cat, []):
                if e.get("path") == rel_path:
                    return e.get("confidence", "file_only")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Per-phase gate conditions
# ---------------------------------------------------------------------------

def _check_phase_4(project_root: Path) -> PhaseGateResult:
    result = PhaseGateResult(phase="Phase 4", verdict="cleared",
                             checked_at=datetime.now().isoformat())

    # session.py must exist with real engine
    if not _file_exists_nonempty(project_root, "backend/app/db/session.py"):
        result.blocking_reasons.append(
            "backend/app/db/session.py missing — DB session not configured"
        )
    elif _file_is_stub(project_root, "backend/app/db/session.py"):
        result.blocking_reasons.append(
            "backend/app/db/session.py is a stub — not a real DB session"
        )
    elif not _file_has_pattern(project_root, "backend/app/db/session.py", r"create_engine|SessionLocal"):
        result.blocking_reasons.append(
            "backend/app/db/session.py lacks create_engine/SessionLocal — not a real session module"
        )

    # requirements.txt must have sqlalchemy active
    if not _file_has_pattern(project_root, "backend/requirements.txt",
                              r"^sqlalchemy|^SQLAlchemy"):
        result.warnings.append(
            "SQLAlchemy may not be in requirements.txt — DB imports may fail"
        )

    if result.blocking_reasons:
        result.verdict = "blocked"
        result.repair_tasks_needed = ["4.2-repair"]
    return result


def _propagate_block(result: PhaseGateResult, prior: PhaseGateResult, label: str) -> None:
    """
    Propagate a blocked prior phase into result.

    Shows: the phase label + the root-cause reason(s) from the deepest blocking phase.
    Does NOT recursively repeat intermediate labels — keeps it readable.
    """
    result.verdict = "blocked"
    # Find root causes: the reasons that are NOT themselves just "Phase N not cleared"
    root_reasons = [
        r for r in prior.blocking_reasons
        if not r.startswith("Phase ")
    ]
    # Fall back to all reasons if all are phase labels (shouldn't happen)
    if not root_reasons:
        root_reasons = prior.blocking_reasons
    result.blocking_reasons = [label] + root_reasons
    result.repair_tasks_needed = list(prior.repair_tasks_needed)


def _check_phase_5(project_root: Path) -> PhaseGateResult:
    result = PhaseGateResult(phase="Phase 5", verdict="cleared",
                             checked_at=datetime.now().isoformat())

    p4 = _check_phase_4(project_root)
    if p4.verdict == "blocked":
        _propagate_block(result, p4, "Phase 4 not cleared")
        return result

    if not _file_has_pattern(project_root, "backend/app/models/project.py",
                              r"class Project"):
        result.blocking_reasons.append(
            "backend/app/models/project.py missing class Project"
        )

    if result.blocking_reasons:
        result.verdict = "blocked"
    return result


def _check_phase_6(project_root: Path) -> PhaseGateResult:
    result = PhaseGateResult(phase="Phase 6", verdict="cleared",
                             checked_at=datetime.now().isoformat())

    p5 = _check_phase_5(project_root)
    if p5.verdict == "blocked":
        _propagate_block(result, p5, "Phase 5 not cleared")
        return result

    projects_api = "backend/app/api/projects.py"
    projects_svc = "backend/app/services/project_service.py"

    if _file_is_stub(project_root, projects_api):
        result.blocking_reasons.append(
            f"{projects_api} is a stub — projects API not real"
        )
        result.repair_tasks_needed.append("5.3-repair")
    elif not _file_has_pattern(project_root, projects_api,
                               r'@router\.(get|post|put|delete)'):
        result.blocking_reasons.append(
            f"{projects_api} has no route decorators — not a real router"
        )

    if _file_is_stub(project_root, projects_svc):
        result.blocking_reasons.append(
            f"{projects_svc} is a stub — project service not real"
        )
        result.repair_tasks_needed.append("5.2-repair")

    # projects router must be registered in main.py
    if not _file_has_pattern(project_root, "backend/app/main.py",
                              r"projects_router|include_router.*project"):
        result.warnings.append(
            "Projects router may not be registered in main.py"
        )

    if result.blocking_reasons:
        result.verdict = "blocked"
    return result


def _check_phase_7(project_root: Path) -> PhaseGateResult:
    result = PhaseGateResult(phase="Phase 7", verdict="cleared",
                             checked_at=datetime.now().isoformat())

    p6 = _check_phase_6(project_root)
    if p6.verdict == "blocked":
        _propagate_block(result, p6, "Phase 6 not cleared")
        return result

    chats_api = "backend/app/api/chats.py"
    chat_svc = "backend/app/services/chat_service.py"

    if _file_is_stub(project_root, chats_api):
        result.blocking_reasons.append(f"{chats_api} is a stub")
        result.repair_tasks_needed.append("6.3-repair")
    if _file_is_stub(project_root, chat_svc):
        result.blocking_reasons.append(f"{chat_svc} is a stub")
        result.repair_tasks_needed.append("6.2-repair")

    if result.blocking_reasons:
        result.verdict = "blocked"
    return result


def _check_phase_8(project_root: Path) -> PhaseGateResult:
    result = PhaseGateResult(phase="Phase 8", verdict="cleared",
                             checked_at=datetime.now().isoformat())

    p7 = _check_phase_7(project_root)
    if p7.verdict == "blocked":
        _propagate_block(result, p7, "Phase 7 not cleared")
        return result

    ai_chat = "backend/app/api/ai_chat.py"
    if _file_is_stub(project_root, ai_chat):
        result.blocking_reasons.append(f"{ai_chat} is a stub — AI chat endpoint not real")
        result.repair_tasks_needed.append("7.2-repair")
    elif not _file_has_pattern(project_root, ai_chat, r'@router\.(get|post|put|delete)'):
        result.blocking_reasons.append(f"{ai_chat} has no routes")

    if result.blocking_reasons:
        result.verdict = "blocked"
    return result


def _check_phase_9(project_root: Path) -> PhaseGateResult:
    result = PhaseGateResult(phase="Phase 9", verdict="cleared",
                             checked_at=datetime.now().isoformat())

    p8 = _check_phase_8(project_root)
    if p8.verdict == "blocked":
        _propagate_block(result, p8, "Phase 8 not cleared")
        return result

    # All core APIs must be real
    for path, label in [
        ("backend/app/api/projects.py", "projects"),
        ("backend/app/api/chats.py", "chats"),
        ("backend/app/api/ai_chat.py", "ai_chat"),
        ("backend/app/api/files.py", "files"),
    ]:
        if _file_is_stub(project_root, path):
            result.blocking_reasons.append(f"{label} API is still a stub")
            result.repair_tasks_needed.append(f"{label}-repair")

    if result.blocking_reasons:
        result.verdict = "blocked"
    return result


def _check_phase_10(project_root: Path) -> PhaseGateResult:
    result = PhaseGateResult(phase="Phase 10", verdict="cleared",
                             checked_at=datetime.now().isoformat())

    p9 = _check_phase_9(project_root)
    if p9.verdict == "blocked":
        _propagate_block(result, p9, "Phase 9 not cleared")
        return result

    # chat.html must not be a static placeholder
    chat_html = "frontend/chat.html"
    if _file_exists_nonempty(project_root, chat_html):
        if not _file_has_pattern(project_root, chat_html, r'function\s+\w+|addEventListener'):
            result.blocking_reasons.append(
                "frontend/chat.html appears to be static HTML with no JavaScript — "
                "chat UI integration not complete"
            )
        mem_status = _executive_memory_status(project_root, chat_html)
        if mem_status == "false_positive":
            result.blocking_reasons.append(
                "frontend/chat.html is recorded as a false positive in executive memory"
            )
            result.repair_tasks_needed.append("chat-html-repair")
    else:
        result.blocking_reasons.append("frontend/chat.html missing")

    if result.blocking_reasons:
        result.verdict = "blocked"
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PHASE_CHECKERS = {
    "Phase 4": _check_phase_4,
    "Phase 5": _check_phase_5,
    "Phase 6": _check_phase_6,
    "Phase 7": _check_phase_7,
    "Phase 8": _check_phase_8,
    "Phase 9": _check_phase_9,
    "Phase 10": _check_phase_10,
}


def check(phase: str, project_root: Path) -> PhaseGateResult:
    """
    Run the phase gate for the given phase name.
    Returns PhaseGateResult with verdict: cleared | warning | blocked | escalate.
    """
    checker = _PHASE_CHECKERS.get(phase)
    if not checker:
        # Unknown phase — no gate defined, allow with warning
        return PhaseGateResult(
            phase=phase,
            verdict="warning",
            warnings=[f"No phase gate defined for '{phase}' — proceeding without check"],
            checked_at=datetime.now().isoformat(),
        )
    return checker(project_root)


def persist_result(result: PhaseGateResult, project_root: Path) -> None:
    """Store gate result in executive memory for future cycles to read."""
    try:
        from app.services.executive_memory import load as load_mem, _save as save_mem
        mem = load_mem(project_root)
        mem.setdefault("phase_readiness", {})[result.phase] = {
            "status": result.verdict,
            "blocking_reasons": result.blocking_reasons,
            "repair_tasks_needed": result.repair_tasks_needed,
            "warnings": result.warnings,
            "last_checked": result.checked_at,
        }
        save_mem(mem, project_root)
    except Exception:
        pass
