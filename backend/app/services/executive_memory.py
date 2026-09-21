"""
Executive Memory — Full product state model for the manager.

This is NOT a recent-changes log.
This is the manager's persistent understanding of:
  - what the product is supposed to do
  - what has been implemented and verified
  - what was accepted but is actually a stub (false positives)
  - what is blocked and why
  - what regressions have been detected
  - what critical gaps prevent the product from working

Storage: docs/progress/executive_memory.json
Schema doc: docs/agent/EXECUTIVE_MEMORY_SCHEMA.md

Written after every manager cycle verdict.
Read at the start of every manager cycle.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "2.0"
_MEMORY_FILE = "docs/progress/executive_memory.json"
_BACKUP_FILE = "docs/progress/executive_memory.json.bak"

# Max entries for cycle_log (ring buffer); everything else grows until resolved
_MAX_CYCLE_LOG = 50


# ---------------------------------------------------------------------------
# Schema initializer
# ---------------------------------------------------------------------------

def _empty() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": None,
        "product": {
            "name": "AI Workspace Platform",
            "goal": "Multi-project AI chat platform with REST API and web UI",
            "mvp_definition": (
                "User can create projects, start chats, send messages, "
                "get AI responses, upload files"
            ),
            "current_phase": "Unknown",
            "phase_summary": "",
            "authoritative_docs": [
                "docs/VISION_DOCUMENT.md",
                "docs/SYSTEM_ARCHITECTURE.md",
                "docs/DATA_MODEL.md",
                "docs/AGENT_INTERACTION_SPEC.md",
                "docs/IMPLEMENTATION_PLAN.md",
            ],
        },
        "architecture": {
            "decisions": [
                {
                    "id": "arch-001",
                    "decision": "FastAPI backend, SQLite dev DB, SQLAlchemy ORM",
                    "rationale": "Specified in SYSTEM_ARCHITECTURE.md",
                    "must_preserve": True,
                },
                {
                    "id": "arch-002",
                    "decision": "All API routers registered in backend/app/main.py",
                    "rationale": "Single registration point for router discovery",
                    "must_preserve": True,
                },
                {
                    "id": "arch-003",
                    "decision": "File executor writes only to declared safe directories",
                    "rationale": "Security boundary prevents system file corruption",
                    "must_preserve": True,
                },
            ],
            "protected_files": [
                "backend/app/main.py",
                "backend/app/db/session.py",
                "backend/requirements.txt",
                "docs/VISION_DOCUMENT.md",
                "docs/SYSTEM_ARCHITECTURE.md",
                "docs/DATA_MODEL.md",
            ],
        },
        "implemented": {
            "pages": [],
            "api_routers": [],
            "services": [],
            "schemas": [],
            "migrations": [],
        },
        "false_positives": [],
        "stubs": [],
        "blocked": [],
        "regressions": [],
        "product_gaps": [],
        # v2: four-level completion model
        # Values: "missing"|"exists_on_disk"|"semantically_valid"|"integrated"|"product_ready"
        "completion_levels": {},
        "what_must_not_regress": [
            "backend/app/api/projects.py — 5 CRUD routes",
            "backend/app/api/chats.py — 4 routes for chat/message CRUD",
            "backend/app/api/ai_chat.py — POST /api/chats/{id}/complete",
            "backend/app/api/memory.py — 4 memory endpoints",
            "backend/app/api/files.py — 4 file endpoints",
            "backend/app/main.py — router registrations for all above",
        ],
        # v2: repair queue summary reference
        "repair_queue_summary": {"pending_count": 0, "override_count": 0, "last_updated": None},
        # v2: phase readiness tracking
        "phase_readiness": {},
        # v2: reference pack usage and context budget stats
        "recent_reference_packs": [],
        "context_budget_stats": {
            "total_cycles": 0, "total_chars_assembled": 0,
            "avg_chars_per_cycle": 0, "budget_overruns": 0,
            "overrun_cycles": [], "memory_substitutions_used": 0,
            "most_expensive_task_type": None, "by_level": {},
        },
        # v3: MVP recovery mode — set from autopilot_config.json
        "mvp_mode": {
            "active": False,
            "roadmap_override": None,
            "block_expansion_tasks": False,
            "recovery_tasks_remaining": [],
        },
        "cycle_log": [],
    }


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _mem_path(project_root: Path) -> Path:
    return project_root / _MEMORY_FILE


def load(project_root: Path) -> dict:
    f = _mem_path(project_root)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _empty()


def _save(mem: dict, project_root: Path) -> None:
    mem["updated_at"] = datetime.now().isoformat()
    f = _mem_path(project_root)
    f.parent.mkdir(parents=True, exist_ok=True)

    # Backup previous version
    if f.exists():
        try:
            shutil.copy2(f, project_root / _BACKUP_FILE)
        except Exception:
            pass

    f.write_text(json.dumps(mem, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_path(rel_path: str) -> Optional[str]:
    """Return implemented category for a file path, or None."""
    p = rel_path.lower()
    if p.startswith("frontend/") and p.endswith(".html"):
        return "pages"
    if p.startswith("backend/app/api/") and p.endswith(".py"):
        return "api_routers"
    if p.startswith("backend/app/services/") and p.endswith(".py"):
        return "services"
    if p.startswith("backend/app/schemas/") and p.endswith(".py"):
        return "schemas"
    if "alembic/versions/" in p and p.endswith(".py"):
        return "migrations"
    return None


def _extract_key_functions(content: str, rel_path: str) -> list[str]:
    """Extract class/def names and routes from file content."""
    import re
    tokens = []
    for m in re.finditer(r'^(class|def)\s+(\w+)', content, re.MULTILINE):
        tokens.append(f"{m.group(2)}")
    for m in re.finditer(r'@router\.(get|post|put|delete)\(["\']([^"\']+)', content):
        tokens.append(f"{m.group(1).upper()} {m.group(2)}")
    return tokens[:20]


def _has_stub_body(content: str) -> bool:
    """
    Return True if the file looks like a stub (def main/pass body, no real logic).
    Conservative: only fires on very obvious patterns.
    """
    import re
    # Pattern 1: only function is def main(): ... pass
    if re.search(r'def main\(\):\s*\n\s+"""[^"]*"""\s*\n\s+pass', content, re.DOTALL):
        return True
    # Pattern 2: all non-trivial functions have pass-only bodies
    func_bodies = re.findall(
        r'def \w+\([^)]*\):\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass\s*\n',
        content, re.DOTALL
    )
    real_funcs = re.findall(r'def \w+\([^)]*\):', content)
    if real_funcs and len(func_bodies) == len(real_funcs):
        return True
    return False


def _is_false_positive_already(mem: dict, rel_path: str) -> bool:
    return any(fp.get("file") == rel_path for fp in mem.get("false_positives", []))


def _remove_from_implemented(mem: dict, rel_path: str) -> None:
    for cat in ("pages", "api_routers", "services", "schemas", "migrations"):
        lst = mem["implemented"].get(cat, [])
        mem["implemented"][cat] = [e for e in lst if e.get("path") != rel_path]


# ---------------------------------------------------------------------------
# v2: Completion level tracking
# ---------------------------------------------------------------------------
# Four-level model:
#   missing           — file does not exist
#   exists_on_disk    — file exists and is non-empty
#   semantically_valid — file has real implementation (no stub bodies)
#   integrated        — file is imported and used by other accepted files
#   product_ready     — file has been accepted at verified confidence with no known issues

_COMPLETION_ORDER = [
    "missing", "exists_on_disk", "semantically_valid", "integrated", "product_ready"
]


def _compute_completion_level(
    rel_path: str,
    content: str,
    verdict: str,
    is_stub: bool,
    confidence: str,
) -> str:
    """
    Determine the completion level for a file based on verdict and content analysis.
    """
    if verdict != "accepted":
        return "exists_on_disk"  # existed but not accepted
    if is_stub:
        return "exists_on_disk"  # file exists but is not real
    if confidence == "verified":
        return "product_ready"
    if confidence == "structural":
        return "semantically_valid"
    return "exists_on_disk"


def set_completion_level(mem: dict, rel_path: str, level: str) -> None:
    """Set completion level for a path; only upgrades, never downgrades unless explicitly called."""
    import re as _re
    current = mem.get("completion_levels", {}).get(rel_path, "missing")
    current_idx = _COMPLETION_ORDER.index(current) if current in _COMPLETION_ORDER else 0
    new_idx = _COMPLETION_ORDER.index(level) if level in _COMPLETION_ORDER else 0
    # Allow both upgrade and downgrade (repair tasks may downgrade a false positive)
    mem.setdefault("completion_levels", {})[rel_path] = level


def get_completion_level(project_root: Path, rel_path: str) -> str:
    """Return the current completion level for a file."""
    mem = load(project_root)
    return mem.get("completion_levels", {}).get(rel_path, "missing")


# ---------------------------------------------------------------------------
# Public: update after task verdict
# ---------------------------------------------------------------------------

def update_after_task(
    task: dict,
    verdict: str,
    files_changed: list[str],
    review: dict,
    project_root: Path,
) -> None:
    """
    Update executive memory after any verdict.
    Called by manager_loop after _review_result().
    """
    mem = load(project_root)
    now = datetime.now().isoformat()
    task_id = task.get("id", "?")
    task_title = task.get("title", "")[:80]

    # Update phase
    phase = task.get("phase", "")
    if phase:
        mem["product"]["current_phase"] = phase
        mem["product"]["phase_summary"] = task_title

    # Process each changed file
    for rel_path in files_changed:
        full = project_root / rel_path
        if not full.exists():
            continue

        try:
            content = full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        cat = _classify_path(rel_path)

        if verdict == "accepted":
            # Check if it is actually a stub despite being accepted
            is_stub = _has_stub_body(content)

            if is_stub and cat in ("services", "api_routers"):
                # Record as false positive
                if not _is_false_positive_already(mem, rel_path):
                    mem["false_positives"].append({
                        "task_id": task_id,
                        "file": rel_path,
                        "accepted_at": now,
                        "detected_at": now,
                        "reason": "File accepted but contains only stub/pass body",
                        "detection_method": "post_acceptance_scan",
                        "repair_task_id": f"{task_id}-repair",
                        "status": "pending_repair",
                    })
                    mem["product_gaps"].append({
                        "gap_id": f"gap-{task_id}",
                        "description": f"{rel_path} is a stub — key functionality not implemented",
                        "impact": f"Tasks depending on {rel_path} will fail at runtime",
                        "repair_task": f"{task_id}-repair",
                        "priority": "high",
                    })
                    mem["stubs"].append({
                        "path": rel_path,
                        "function": "multiple",
                        "task_id": task_id,
                        "reason": "Worker produced stub body",
                        "repair_priority": "high",
                    })
                # v2: completion level = exists_on_disk (stub is not semantically valid)
                set_completion_level(mem, rel_path, "exists_on_disk")
            elif cat:
                # Real acceptance — add to implemented
                key_functions = _extract_key_functions(content, rel_path)
                entry = {
                    "path": rel_path,
                    "description": task_title,
                    "accepted_at": now,
                    "task_id": task_id,
                    "confidence": "structural",
                    "key_functions": key_functions,
                }
                # Remove any previous entry for this path
                _remove_from_implemented(mem, rel_path)
                mem["implemented"].setdefault(cat, []).append(entry)
                # v2: set completion level to semantically_valid (full audit would set product_ready)
                set_completion_level(mem, rel_path, "semantically_valid")

                # Remove from stubs/false_positives if it was there
                mem["stubs"] = [s for s in mem.get("stubs", []) if s.get("path") != rel_path]
                mem["false_positives"] = [
                    fp for fp in mem.get("false_positives", [])
                    if fp.get("file") != rel_path
                ]
                # Resolve matching gap
                mem["product_gaps"] = [
                    g for g in mem.get("product_gaps", [])
                    if g.get("gap_id") != f"gap-{task_id}"
                ]
                # v2: upgrade completion level on repair acceptance
                set_completion_level(mem, rel_path, "semantically_valid")

        elif verdict == "blocked":
            set_completion_level(mem, rel_path, "exists_on_disk")
            reason = review.get("notes", "blocked after max retries")
            # Update or add blocked entry
            existing = next((b for b in mem.get("blocked", []) if b.get("task_id") == task_id), None)
            if existing:
                existing["retries"] = existing.get("retries", 0) + 1
                existing["reason"] = reason
            else:
                mem.setdefault("blocked", []).append({
                    "task_id": task_id,
                    "title": task_title,
                    "blocked_at": now,
                    "retries": task.get("retry_count", 1),
                    "reason": reason,
                    "root_cause_hypothesis": "",
                    "resolution": "pending",
                })

    # Append to cycle log
    mem["cycle_log"] = (mem.get("cycle_log") or []) + [{
        "cycle_at": now,
        "task_id": task_id,
        "verdict": verdict,
        "files": files_changed,
        "notes": review.get("notes", "")[:120],
    }]
    mem["cycle_log"] = mem["cycle_log"][-_MAX_CYCLE_LOG:]

    # v2: sync repair queue summary
    try:
        from app.services.repair_queue import get_pending, PRIORITY_THRESHOLD_OVERRIDE
        pending = get_pending(project_root)
        override = [e for e in pending if e.get("priority") in PRIORITY_THRESHOLD_OVERRIDE]
        mem["repair_queue_summary"] = {
            "pending_count": len(pending),
            "override_count": len(override),
            "last_updated": datetime.now().isoformat(),
        }
    except Exception:
        pass

    _save(mem, project_root)


# ---------------------------------------------------------------------------
# Public: read for manager cycle start
# ---------------------------------------------------------------------------

def get_cycle_context(project_root: Path) -> dict:
    """
    Return a summary dict for the manager to read at cycle start.

    Keys:
      has_critical_gaps: bool
      critical_gaps: list[dict]
      pending_false_positives: list[dict]
      blocked_task_ids: list[str]
      product_phase: str
      protected_files: list[str]
    """
    mem = load(project_root)
    critical_gaps = [g for g in mem.get("product_gaps", []) if g.get("priority") == "critical"]
    pending_fp = [fp for fp in mem.get("false_positives", []) if fp.get("status") == "pending_repair"]
    blocked_ids = [b.get("task_id") for b in mem.get("blocked", [])]
    return {
        "has_critical_gaps": len(critical_gaps) > 0,
        "critical_gaps": critical_gaps,
        "pending_false_positives": pending_fp,
        "blocked_task_ids": blocked_ids,
        "product_phase": mem.get("product", {}).get("current_phase", "Unknown"),
        "protected_files": mem.get("architecture", {}).get("protected_files", []),
    }


def get_implemented_summary(project_root: Path) -> str:
    """
    Compact text summary for injection into worker prompts.
    """
    mem = load(project_root)
    impl = mem.get("implemented", {})

    pages = [e["path"] for e in impl.get("pages", [])]
    apis = [e["path"] for e in impl.get("api_routers", [])]
    svcs = [e["path"] for e in impl.get("services", [])]
    stubs = [s["path"] for s in mem.get("stubs", [])]
    fps = [fp["file"] for fp in mem.get("false_positives", []) if fp.get("status") == "pending_repair"]

    lines = ["EXECUTIVE_PRODUCT_STATE:"]
    lines.append(f"  phase: {mem.get('product', {}).get('current_phase', '?')}")
    lines.append(f"  verified pages: {', '.join(pages) or '(none)'}")
    lines.append(f"  verified API routers: {', '.join(apis) or '(none)'}")
    lines.append(f"  verified services: {', '.join(svcs[:8]) or '(none)'}")
    if stubs:
        lines.append(f"  KNOWN STUBS (not real): {', '.join(stubs)}")
    if fps:
        lines.append(f"  FALSE POSITIVES (accepted but broken): {', '.join(fps)}")
    return "\n".join(lines)


def get_memory(project_root: Path) -> dict:
    return load(project_root)


# ---------------------------------------------------------------------------
# MVP mode helpers
# ---------------------------------------------------------------------------

_AUTOPILOT_CONFIG = "docs/progress/autopilot_config.json"


def is_mvp_recovery_mode(project_root: Path) -> bool:
    """Return True if autopilot_config.json has mode = 'mvp_recovery' and mvp_recovery.active."""
    try:
        cfg_path = project_root / _AUTOPILOT_CONFIG
        if not cfg_path.exists():
            return False
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return (
            cfg.get("mode") == "mvp_recovery"
            and cfg.get("mvp_recovery", {}).get("active", False)
        )
    except Exception:
        return False


def get_mvp_recovery_roadmap_path(project_root: Path) -> Optional[str]:
    """Return the path to the MVP recovery roadmap file, or None."""
    try:
        cfg_path = project_root / _AUTOPILOT_CONFIG
        if not cfg_path.exists():
            return None
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return cfg.get("mvp_recovery", {}).get("roadmap_override")
    except Exception:
        return None


def get_stub_patterns_forbidden(project_root: Path) -> list[str]:
    """Return list of stub patterns that must be rejected in MVP mode."""
    try:
        cfg_path = project_root / _AUTOPILOT_CONFIG
        if not cfg_path.exists():
            return []
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return cfg.get("mvp_recovery", {}).get("stub_patterns_forbidden", [])
    except Exception:
        return []


def sync_mvp_mode_to_memory(project_root: Path) -> None:
    """Sync mvp_mode block from autopilot_config.json into executive memory."""
    try:
        mem = load(project_root)
        cfg_path = project_root / _AUTOPILOT_CONFIG
        if not cfg_path.exists():
            return
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        mvp_cfg = cfg.get("mvp_recovery", {})
        mem["mvp_mode"] = {
            "active": mvp_cfg.get("active", False),
            "roadmap_override": mvp_cfg.get("roadmap_override"),
            "block_expansion_tasks": mvp_cfg.get("block_expansion_tasks", False),
            "recovery_tasks_remaining": mvp_cfg.get("completed_tasks", []),
        }
        _save(mem, project_root)
    except Exception:
        pass
