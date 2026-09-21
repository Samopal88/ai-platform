"""
Recovery Gate — Preflight readiness checks for MVP recovery tasks.

Purpose:
  Before auto-run dispatches a recovery task to the worker, this module checks
  whether the task's prerequisites are truly satisfied on disk.

  This is different from completion tracking (autopilot_config completed_tasks):
  it checks the *content quality* of dependency files, not just whether they ran.

Design rules:
  - All checks are based on files on disk — no network calls, no DB connections
  - A check that fails must return a clear human-readable reason
  - The gate is conservative: unknown tasks are NOT blocked (gate only fires
    for tasks with explicit dependency rules)
  - No hardcoded task IDs except in the dependency map — adding a new task
    means adding an entry to TASK_DEPENDENCIES, not changing gate logic
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Dependency map — keyed by recovery task ID
# Values: list of (file_to_check, check_type, human_label) tuples
#
# Check types:
#   "exists"        — file must exist and be non-empty
#   "has_import"    — file must contain a real import statement (not just a stub)
#   "has_apirouter" — file must define an APIRouter instance
#   "has_class"     — file must contain at least one class definition
#   "no_stub"       — file must not be a pass-only stub
#   "importable"    — file must be syntactically valid Python
# ---------------------------------------------------------------------------

TASK_DEPENDENCIES: dict[str, list[tuple[str, str, str]]] = {
    # R3 requires real DB session module
    "R3": [
        ("backend/app/db/session.py", "no_stub", "DB session must be real (not a stub)"),
        ("backend/app/db/session.py", "has_import", "DB session must import SQLAlchemy"),
    ],
    # R4 requires real SQLAlchemy available (requirements.txt)
    "R4": [
        ("backend/requirements.txt", "exists", "requirements.txt must exist"),
        ("backend/requirements.txt", "has_import", "requirements.txt must contain sqlalchemy"),
    ],
    # R5 requires real session and real schema
    "R5": [
        ("backend/app/db/session.py", "no_stub", "DB session must be real"),
        ("backend/app/schemas/project.py", "has_class", "ProjectRead schema must exist"),
        ("backend/app/schemas/project.py", "no_stub", "schemas/project.py must not be a stub"),
    ],
    # R6 requires real service
    "R6": [
        ("backend/app/services/project_service.py", "no_stub", "project_service must be real"),
        ("backend/app/services/project_service.py", "has_import", "project_service must import SQLAlchemy"),
        ("backend/app/schemas/project.py", "has_class", "project schemas must have real classes"),
    ],
    # R7 requires real session
    "R7": [
        ("backend/app/db/session.py", "no_stub", "DB session must be real"),
    ],
    # R8 requires real chat schema and session
    "R8": [
        ("backend/app/schemas/chat.py", "has_class", "Chat schemas must exist"),
        ("backend/app/schemas/chat.py", "no_stub", "chat schema must not be a stub"),
        ("backend/app/db/session.py", "no_stub", "DB session must be real"),
    ],
    # R9 requires real chat service
    "R9": [
        ("backend/app/services/chat_service.py", "no_stub", "chat_service must be real"),
        ("backend/app/services/chat_service.py", "has_import", "chat_service must import SQLAlchemy"),
        ("backend/app/schemas/chat.py", "has_class", "chat schemas must exist"),
    ],
    # R10 requires real session
    "R10": [
        ("backend/app/db/session.py", "no_stub", "DB session must be real"),
    ],
    # R11 requires real model_router and chat service
    "R11": [
        ("backend/app/services/model_router.py", "no_stub", "model_router must be real"),
        ("backend/app/services/chat_service.py", "no_stub", "chat_service must be real"),
    ],
    # R12 (router registration) requires all three API modules to have real routers
    "R12": [
        ("backend/app/api/projects.py", "has_apiRouter", "projects router must exist"),
        ("backend/app/api/chats.py", "has_apiRouter", "chats router must exist"),
        ("backend/app/api/ai_chat.py", "has_apiRouter", "ai_chat router must exist"),
    ],
    # R13 (smoke test) requires R12 to be done — checked via DB session availability
    "R13": [
        ("backend/app/main.py", "has_import", "main.py must have startup DB init"),
        ("backend/app/api/projects.py", "has_apiRouter", "projects router must be real"),
    ],
}

# Pattern used to detect "has_import" in requirements.txt (package name, not import)
_REQUIREMENTS_PACKAGES = {
    "backend/requirements.txt": re.compile(r'^sqlalchemy', re.IGNORECASE | re.MULTILINE),
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    task_id: str
    ready: bool
    blocking_checks: list[str] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.ready:
            return "All prerequisites satisfied"
        return "; ".join(self.blocking_checks)


# ---------------------------------------------------------------------------
# Individual check implementations
# ---------------------------------------------------------------------------

def _check_exists(full_path: Path) -> bool:
    return full_path.exists() and full_path.stat().st_size > 0


def _check_no_stub(full_path: Path) -> bool:
    """Return True if file is NOT a pass-only stub."""
    if not full_path.exists():
        return False
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    if not content.strip():
        return False

    # Detect the known stub patterns
    stub_patterns = [
        r'def \w+\s*\([^)]*\)\s*:\s*\n\s+pass\b',   # def foo(): pass
        r'def main\s*\(\s*\)\s*:\s*\n\s+pass\b',
        r'def crud\s*\(\s*\)\s*:\s*\n',
        r'def fastapi\s*\(\s*\)\s*:\s*\n',
        r'def chat\s*\(\s*\)\s*:\s*\n',
    ]
    for pat in stub_patterns:
        if re.search(pat, content):
            return False

    # If all function bodies are pass
    all_defs = re.findall(r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:', content)
    pass_bodies = re.findall(
        r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass\b',
        content, re.DOTALL
    )
    if all_defs and len(pass_bodies) == len(all_defs):
        return False

    return True


def _check_has_import(full_path: Path) -> bool:
    """Return True if the file contains real import statements or package lines."""
    if not full_path.exists():
        return False
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False

    # Special case: requirements.txt
    special = _REQUIREMENTS_PACKAGES.get(str(full_path.name))
    if special or str(full_path).endswith("requirements.txt"):
        return bool(re.search(r'^sqlalchemy', content, re.IGNORECASE | re.MULTILINE))

    # Python files: look for real import lines
    return bool(re.search(r'^(?:import|from)\s+\w', content, re.MULTILINE))


def _check_has_class(full_path: Path) -> bool:
    """Return True if file defines at least one class."""
    if not full_path.exists():
        return False
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return bool(re.search(r'^class\s+\w+', content, re.MULTILINE))


def _check_has_apiRouter(full_path: Path) -> bool:
    """Return True if file contains a real APIRouter definition."""
    if not full_path.exists():
        return False
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return bool(re.search(r'APIRouter\s*\(', content))


def _check_importable(full_path: Path) -> bool:
    """Return True if the Python file is syntactically valid."""
    if not full_path.exists():
        return False
    try:
        import ast
        ast.parse(full_path.read_text(encoding="utf-8", errors="replace"))
        return True
    except SyntaxError:
        return False


_CHECKERS = {
    "exists": _check_exists,
    "no_stub": _check_no_stub,
    "has_import": _check_has_import,
    "has_class": _check_has_class,
    "has_apiRouter": _check_has_apiRouter,
    "importable": _check_importable,
}


# ---------------------------------------------------------------------------
# Main gate function
# ---------------------------------------------------------------------------

def check_task_ready(task: dict, project_root: Path) -> GateResult:
    """
    Check whether a recovery task's prerequisites are satisfied on disk.

    Returns a GateResult with ready=True if all checks pass, or ready=False
    with a human-readable reason if any check fails.

    Tasks not in TASK_DEPENDENCIES are considered unconditionally ready
    (the gate only fires where dependency rules are explicitly defined).
    """
    task_id = task.get("id", "")

    # Only applies to MVP recovery tasks
    if not task.get("_is_mvp_recovery"):
        return GateResult(task_id=task_id, ready=True, passed_checks=["not a recovery task"])

    deps = TASK_DEPENDENCIES.get(task_id)
    if not deps:
        return GateResult(task_id=task_id, ready=True, passed_checks=["no dependency rules defined"])

    blocking = []
    passed = []

    for rel_path, check_type, label in deps:
        full_path = project_root / rel_path
        checker = _CHECKERS.get(check_type)
        if checker is None:
            passed.append(f"{label} [unknown check type '{check_type}' — skipped]")
            continue

        ok = checker(full_path)
        if ok:
            passed.append(f"{label}: OK")
        else:
            blocking.append(f"PREREQ FAIL — {label} ({rel_path})")

    return GateResult(
        task_id=task_id,
        ready=len(blocking) == 0,
        blocking_checks=blocking,
        passed_checks=passed,
    )
