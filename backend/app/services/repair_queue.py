"""
Repair Queue — Persistent priority queue for repair tasks.

When false accepts, stubs, doc-only changes, or regressions are detected,
the system creates repair tasks and adds them here.

The manager checks this queue BEFORE selecting from the roadmap.
P0/P1/P2 repairs override roadmap order.
P3/P4 repairs may be deferred until end of current phase.

Storage: docs/progress/repair_queue.json
Policy doc: docs/agent/REPAIR_POLICY.md
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from app.core.config import settings

_QUEUE_FILE = "docs/progress/repair_queue.json"

# Priority order (lower number = higher priority)
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}

PRIORITY_THRESHOLD_OVERRIDE = {"P0", "P1", "P2"}  # these override roadmap
MAX_ATTEMPTS_DEFAULT = 2


def _queue_path(project_root: Path) -> Path:
    return project_root / _QUEUE_FILE


def _load(project_root: Path) -> list[dict]:
    f = _queue_path(project_root)
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


def _save(queue: list[dict], project_root: Path) -> None:
    f = _queue_path(project_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(queue, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Public: add a repair task
# ---------------------------------------------------------------------------

def add_repair(
    original_task_id: str,
    original_task_title: str,
    file: str,
    reason: str,
    detection_source: str,
    repair_brief: str,
    priority: str = "P2",
    blocking_tasks: Optional[list[str]] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """
    Add a repair task to the queue.

    priority: P0 (emergency) | P1 (critical) | P2 (high) | P3 (medium) | P4 (low)
    """
    from pathlib import Path as _Path
    root = project_root or _Path(settings.PROJECT_ROOT)
    queue = _load(root)

    repair_id = f"{original_task_id}-repair-{datetime.now().strftime('%H%M%S')}"

    # SP-1: cascade depth guard — reject repair-of-repair (depth > 1)
    if "-repair-" in str(original_task_id):
        return {"cascade_blocked": True, "reason": "repair-of-repair not allowed — cascade depth > 1"}

    # Don't duplicate: check if repair for same file + reason already pending
    for entry in queue:
        if (entry.get("file") == file
                and entry.get("status") == "pending"
                and entry.get("original_task_id") == original_task_id):
            return entry  # already queued

    entry: dict = {
        "repair_id": repair_id,
        "original_task_id": original_task_id,
        "original_task_title": original_task_title[:80],
        "file": file,
        "priority": priority,
        "reason": reason[:200],
        "detection_source": detection_source,
        "detected_at": datetime.now().isoformat(),
        "repair_brief": repair_brief,
        "attempts": 0,
        "max_attempts": MAX_ATTEMPTS_DEFAULT,
        "status": "pending",
        "blocking_tasks": blocking_tasks or [],
    }
    queue.append(entry)
    _save(queue, root)
    return entry


# ---------------------------------------------------------------------------
# Public: get the next repair to execute (or None)
# ---------------------------------------------------------------------------

def next_repair(
    project_root: Path,
    allow_deferred: bool = False,
) -> Optional[dict]:
    """
    Return the highest-priority pending repair entry.

    If allow_deferred is False (default), only returns P0/P1/P2 repairs.
    P3/P4 are returned only when allow_deferred=True.
    """
    queue = _load(project_root)
    pending = [e for e in queue if e.get("status") == "pending"]
    if not pending:
        return None

    # Sort by priority (P0 first), then by detected_at
    def sort_key(e: dict) -> tuple:
        p = _PRIORITY_ORDER.get(e.get("priority", "P4"), 4)
        return (p, e.get("detected_at", ""))

    pending.sort(key=sort_key)

    for entry in pending:
        if allow_deferred:
            return entry
        if entry.get("priority") in PRIORITY_THRESHOLD_OVERRIDE:
            return entry
    return None


def has_override_repairs(project_root: Path) -> bool:
    """Return True if any P0/P1/P2 repair is pending."""
    return next_repair(project_root) is not None


# ---------------------------------------------------------------------------
# Public: convert repair entry to a task dict (for manager_loop compatibility)
# ---------------------------------------------------------------------------

def repair_to_task(entry: dict) -> dict:
    """
    Convert a repair queue entry into a task dict that manager_loop can use.
    Uses the same structure as roadmap tasks.
    """
    return {
        "id": entry["repair_id"],
        "title": f"REPAIR: {entry['original_task_title']}",
        "phase": "Repair",
        "files": [entry["file"]],
        "change": entry["reason"],
        "why": f"False accept / stub detected in {entry['file']}",
        "status": "todo",
        "_is_repair": True,
        "_repair_brief": entry.get("repair_brief", ""),
        "_repair_entry": entry,
    }


# ---------------------------------------------------------------------------
# Public: update repair status after verdict
# ---------------------------------------------------------------------------

def mark_repair_started(repair_id: str, project_root: Path) -> None:
    queue = _load(project_root)
    for e in queue:
        if e.get("repair_id") == repair_id:
            e["attempts"] = e.get("attempts", 0) + 1
            break
    _save(queue, project_root)


def mark_repair_complete(repair_id: str, project_root: Path) -> None:
    queue = _load(project_root)
    for e in queue:
        if e.get("repair_id") == repair_id:
            e["status"] = "completed"
            e["completed_at"] = datetime.now().isoformat()
            break
    _save(queue, project_root)


def mark_repair_failed(repair_id: str, reason: str, project_root: Path) -> None:
    queue = _load(project_root)
    for e in queue:
        if e.get("repair_id") == repair_id:
            attempts = e.get("attempts", 0)
            if attempts >= e.get("max_attempts", MAX_ATTEMPTS_DEFAULT):
                e["status"] = "blocked"
                e["block_reason"] = reason
                e["blocked_at"] = datetime.now().isoformat()
            else:
                e["status"] = "pending"  # re-queue for another attempt
                e["last_failure"] = reason[:120]
            break
    _save(queue, project_root)


# ---------------------------------------------------------------------------
# Public: create repair from false_accept_auditor finding
# ---------------------------------------------------------------------------

def queue_from_finding(
    finding,  # AuditFinding from false_accept_auditor
    project_root: Path,
    blocking_tasks: Optional[list[str]] = None,
) -> dict:
    """
    Convert a false_accept_auditor.AuditFinding into a queued repair.
    """
    # Map finding severity to priority
    priority_map = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}
    priority = priority_map.get(finding.severity, "P2")

    repair_brief = _build_repair_brief(finding)

    return add_repair(
        original_task_id=finding.task_id,
        original_task_title=finding.task_title,
        file=finding.rel_path,
        reason=finding.detail,
        detection_source="false_accept_auditor",
        repair_brief=repair_brief,
        priority=priority,
        blocking_tasks=blocking_tasks or [],
        project_root=project_root,
    )


def _build_repair_brief(finding) -> str:
    """Build a repair task brief from an AuditFinding."""
    return f"""REPAIR TASK BRIEF
=================

## Repair Reason
{finding.detail}
Detection source: {finding.finding} via false_accept_auditor
Original task: {finding.task_id} — {finding.task_title}

## Target Files (ONLY modify this)
  {finding.rel_path}

## Known Bad Pattern to Avoid
{finding.repair_action}

## Must Not Touch
  backend/app/main.py, backend/app/db/session.py, docs/VISION_DOCUMENT.md,
  docs/SYSTEM_ARCHITECTURE.md, docs/DATA_MODEL.md

## Critical Implementation Requirements
  - No def main(): pass
  - No pass-only function bodies
  - No placeholder text ("Generated Content", "TODO", etc.)
  - Must implement real product logic, not a wrapper script
  - Function names must match what callers in backend/app/ expect

## Acceptance Criteria
  - File exists and is non-empty
  - No function body is only 'pass'
  - No text: 'Generated Content', 'TODO Placeholder'
  - File is a real module, not a script wrapper"""


# ---------------------------------------------------------------------------
# Public: get all pending items for dashboard/status
# ---------------------------------------------------------------------------

def get_pending(project_root: Path) -> list[dict]:
    queue = _load(project_root)
    return [e for e in queue if e.get("status") == "pending"]


def get_all(project_root: Path) -> list[dict]:
    return _load(project_root)
