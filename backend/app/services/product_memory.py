"""
Product Memory — Persistent structured summary of what has been built.

Tracks implemented pages, APIs, services, and incomplete features.
Written after each accepted task. Injected into future execution prompts.

Storage: docs/progress/product_memory.json
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

_MEMORY_FILE = "docs/progress/product_memory.json"

# ---------------------------------------------------------------------------
# Categories we track
# ---------------------------------------------------------------------------

CATEGORIES = (
    "implemented_pages",    # frontend/*.html that passed acceptance
    "implemented_apis",     # backend/app/api/*.py with real routers
    "implemented_services", # backend/app/services/*.py with real logic
    "incomplete_features",  # stubs / partial implementations
    "recent_changes",       # last 10 accepted task summaries
)


def _memory_file(project_root: Path) -> Path:
    return project_root / _MEMORY_FILE


def _load(project_root: Path) -> dict:
    f = _memory_file(project_root)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _empty()


def _save(mem: dict, project_root: Path) -> None:
    mem["updated_at"] = datetime.now().isoformat()
    f = _memory_file(project_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(mem, indent=2, ensure_ascii=False))


def _empty() -> dict:
    return {
        "implemented_pages": [],        # list of str: rel paths
        "implemented_apis": [],         # list of str: rel paths
        "implemented_services": [],     # list of str: rel paths
        "incomplete_features": [],      # list of {path, reason}
        "recent_changes": [],           # list of {task_id, title, files, verdict, timestamp}
        "updated_at": None,
    }


# ---------------------------------------------------------------------------
# Public: update after a task verdict
# ---------------------------------------------------------------------------

def update_after_task(
    task: dict,
    verdict: str,
    files_changed: list[str],
    semantic_issues: list[str],
    project_root: Path,
) -> None:
    """
    Called by manager_loop after each accepted / blocked / retry verdict.
    Updates the product memory accordingly.
    """
    mem = _load(project_root)

    for rel_path in files_changed:
        _classify_file(rel_path, verdict, semantic_issues, mem)

    # Record recent change entry
    mem["recent_changes"] = (mem.get("recent_changes") or []) + [{
        "task_id": task.get("id", "?"),
        "title": task.get("title", "")[:80],
        "files": files_changed,
        "verdict": verdict,
        "issues": semantic_issues[:3] if semantic_issues else [],
        "timestamp": datetime.now().isoformat(),
    }]
    mem["recent_changes"] = mem["recent_changes"][-10:]

    _save(mem, project_root)


def _classify_file(
    rel_path: str,
    verdict: str,
    semantic_issues: list[str],
    mem: dict,
) -> None:
    path = rel_path.lower()

    if verdict == "accepted":
        # Remove from incomplete if it was there
        mem["incomplete_features"] = [
            f for f in mem.get("incomplete_features", [])
            if f.get("path") != rel_path
        ]
        # Categorise
        if path.startswith("frontend/") and path.endswith(".html"):
            lst = mem.setdefault("implemented_pages", [])
            if rel_path not in lst:
                lst.append(rel_path)
        elif path.startswith("backend/app/api/") and path.endswith(".py"):
            lst = mem.setdefault("implemented_apis", [])
            if rel_path not in lst:
                lst.append(rel_path)
        elif path.startswith("backend/app/services/") and path.endswith(".py"):
            lst = mem.setdefault("implemented_services", [])
            if rel_path not in lst:
                lst.append(rel_path)

    else:
        # Record as incomplete
        reason = "; ".join(semantic_issues[:2]) if semantic_issues else verdict
        incomplete = mem.setdefault("incomplete_features", [])
        # Update existing or append
        existing = next((f for f in incomplete if f.get("path") == rel_path), None)
        if existing:
            existing["reason"] = reason
        else:
            incomplete.append({"path": rel_path, "reason": reason})
        mem["incomplete_features"] = incomplete[-20:]


# ---------------------------------------------------------------------------
# Public: compact summary for prompt injection
# ---------------------------------------------------------------------------

def get_summary(project_root: Path) -> str:
    """
    Returns a compact multi-line PROJECT_STATE block suitable for injection
    into execution prompts.

    Example output:
      PROJECT_STATE:
      - pages: frontend/chat.html, frontend/dashboard.html
      - apis: (none implemented)
      - services: backend/app/services/manager_loop.py, ...
      - incomplete: backend/app/api/chats.py (stub — no APIRouter)
    """
    mem = _load(project_root)

    pages = mem.get("implemented_pages") or []
    apis = mem.get("implemented_apis") or []
    services = mem.get("implemented_services") or []
    incomplete = mem.get("incomplete_features") or []

    def fmt(lst: list) -> str:
        return ", ".join(lst) if lst else "(none)"

    lines = ["PROJECT_STATE:"]
    lines.append(f"  implemented pages: {fmt(pages)}")
    lines.append(f"  implemented APIs: {fmt(apis)}")
    lines.append(f"  implemented services: {fmt(services[:6])}")

    if incomplete:
        inc_strs = [f"{f['path']} ({f.get('reason','?')[:60]})" for f in incomplete[:5]]
        lines.append(f"  incomplete: {'; '.join(inc_strs)}")
    else:
        lines.append("  incomplete: (none known)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public: read raw memory (for API endpoint)
# ---------------------------------------------------------------------------

def get_memory(project_root: Path) -> dict:
    return _load(project_root)
