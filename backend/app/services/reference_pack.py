"""
Reference Pack — Assembles minimal, task-specific context for worker briefs.

Replaces the old approach of either:
  (a) sending vague prompts with no context
  (b) dumping entire docs

A reference pack is assembled deterministically from:
  - executive memory (cheap: summaries and key_functions)
  - doc section excerpts (selected by keyword match)
  - code interface signatures (def lines + first docstring line only)
  - prior false-accept notes for this file

Pack size is bounded by the task level (see docs/agent/REFERENCE_PACK_STANDARD.md).

Usage:
  pack = assemble(task, level_result, project_root)
  brief = build_brief_with_pack(task, pack)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Pack data structure
# ---------------------------------------------------------------------------

@dataclass
class ReferencePack:
    task_id: str
    level: int
    product_goal_summary: str = ""
    phase_context: str = ""
    doc_excerpts: list[str] = field(default_factory=list)    # list of excerpt strings
    interface_refs: list[str] = field(default_factory=list)  # list of signature strings
    prior_notes: list[str] = field(default_factory=list)     # false-accept / repair history
    protected_paths: list[str] = field(default_factory=list)
    architecture_decisions: list[str] = field(default_factory=list)
    total_chars: int = 0
    assembled_at: str = ""

    def render(self) -> str:
        """Render the pack as an injected context block for the worker brief."""
        lines = ["--- REFERENCE PACK ---"]
        if self.product_goal_summary:
            lines.append(self.product_goal_summary)
        if self.phase_context:
            lines.append(f"Phase: {self.phase_context}")
        if self.prior_notes:
            lines.append("PRIOR NOTES (read carefully):")
            lines.extend(f"  {n}" for n in self.prior_notes)
        if self.architecture_decisions:
            lines.append("Architecture decisions:")
            lines.extend(f"  {d}" for d in self.architecture_decisions)
        if self.doc_excerpts:
            lines.append("Relevant spec excerpts:")
            lines.extend(self.doc_excerpts)
        if self.interface_refs:
            lines.append("Interfaces you must match:")
            lines.extend(self.interface_refs)
        if self.protected_paths:
            lines.append(f"Must NOT touch: {', '.join(self.protected_paths)}")
        lines.append("--- END REFERENCE PACK ---")
        return "\n".join(lines)

    def to_summary_dict(self) -> dict:
        """Compact record for executive_memory.recent_reference_packs."""
        return {
            "task_id": self.task_id,
            "level": self.level,
            "doc_excerpts_count": len(self.doc_excerpts),
            "interface_refs_count": len(self.interface_refs),
            "total_chars": self.total_chars,
            "assembled_at": self.assembled_at,
        }


# ---------------------------------------------------------------------------
# Doc section extraction
# ---------------------------------------------------------------------------

def _extract_section(doc_path: Path, keywords: list[str], max_chars: int) -> Optional[str]:
    """
    Extract the most relevant section from a markdown doc.
    Matches the first heading whose text contains any keyword.
    Returns up to max_chars of that section, or None if no match.
    """
    if not doc_path.exists():
        return None
    try:
        text = doc_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = text.splitlines()
    lower_kws = [kw.lower() for kw in keywords]

    # Find the first heading that matches
    start = None
    heading_level = 0
    for i, line in enumerate(lines):
        m = re.match(r'^(#{1,4})\s+(.+)', line)
        if m:
            heading_text = m.group(2).lower()
            if any(kw in heading_text for kw in lower_kws):
                start = i
                heading_level = len(m.group(1))
                break

    if start is None:
        return None

    # Collect until the next heading of same or higher level
    section_lines = [lines[start]]
    for line in lines[start + 1:]:
        m = re.match(r'^(#{1,4})\s+', line)
        if m and len(m.group(1)) <= heading_level:
            break
        section_lines.append(line)

    excerpt = "\n".join(section_lines)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars] + "\n... [truncated]"
    return f"[From {doc_path.name}]\n{excerpt}"


def _get_doc_keywords(task: dict) -> list[str]:
    """Extract search keywords from task title, change, and file types."""
    combined = (task.get("title", "") + " " + task.get("change", "")).lower()
    files = task.get("files", [])

    keywords = []
    # File-type keywords
    if any("api/" in f for f in files):
        keywords.extend(["api", "endpoint", "route", "router"])
    if any("services/" in f for f in files):
        keywords.extend(["service", "function"])
    if any("models/" in f for f in files):
        keywords.extend(["model", "schema", "entity"])
    if any("frontend/" in f for f in files):
        keywords.extend(["chat", "dashboard", "ui", "page"])
    if any("schemas/" in f for f in files):
        keywords.extend(["schema", "pydantic"])

    # Title/change keywords (pick nouns)
    for word in re.findall(r'\b(project|chat|message|file|memory|model|auth|router|session)\b', combined):
        if word not in keywords:
            keywords.append(word)

    return keywords or ["api"]


# ---------------------------------------------------------------------------
# Interface reference extraction
# ---------------------------------------------------------------------------

def _extract_signatures(file_path: Path, max_chars: int) -> Optional[str]:
    """
    Extract only function/class signatures from a Python file.
    Returns: "# From: <path>\ndef func(args):\n  # docstring first line\n..."
    """
    if not file_path.exists():
        return None
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = []
    content_lines = content.splitlines()
    i = 0
    while i < len(content_lines):
        line = content_lines[i]
        # Class or def line
        if re.match(r'^(class|def)\s+\w+', line):
            lines.append(line)
            # Include first docstring line if next non-empty line is a docstring
            if i + 1 < len(content_lines):
                next_line = content_lines[i + 1].strip()
                if next_line.startswith('"""') or next_line.startswith("'''"):
                    doc_text = next_line.strip('"\' ')[:80]
                    lines.append(f"  # {doc_text}")
            lines.append("")
        i += 1

    if not lines:
        return None

    result = f"# From: {file_path}\n" + "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... [truncated]"
    return result


# ---------------------------------------------------------------------------
# Interface files to include per task
# ---------------------------------------------------------------------------

def _find_interface_files(task: dict, project_root: Path) -> list[Path]:
    """
    Find files whose interfaces the task target must call or match.
    Uses simple dependency inference from the task description.
    """
    files = task.get("files", [])
    combined = (task.get("title", "") + " " + task.get("change", "")).lower()
    interfaces: list[Path] = []

    # Services create files that call other services
    if any("services/" in f for f in files):
        # If task mentions memory → include memory_service
        if "memory" in combined:
            p = project_root / "backend/app/services/memory_service.py"
            if p.exists():
                interfaces.append(p)
        # If task mentions chat → include chat_service
        if "chat" in combined:
            p = project_root / "backend/app/services/chat_service.py"
            if p.exists():
                interfaces.append(p)
        # If task mentions project → include project_service
        if "project" in combined:
            p = project_root / "backend/app/services/project_service.py"
            if p.exists():
                interfaces.append(p)
        # Always include db/session for service files
        sess = project_root / "backend/app/db/session.py"
        if sess.exists():
            interfaces.append(sess)

    # API files depend on their service
    if any("api/" in f for f in files):
        for f in files:
            if "api/" in f:
                stem = Path(f).stem
                svc = project_root / f"backend/app/services/{stem}_service.py"
                if svc.exists():
                    interfaces.append(svc)

    return interfaces[:4]  # cap at 4 interface files


# ---------------------------------------------------------------------------
# Prior notes from executive memory
# ---------------------------------------------------------------------------

def _get_prior_notes(task: dict, project_root: Path) -> list[str]:
    """Get false-accept / repair history for the task's target files."""
    notes = []
    try:
        from app.services.executive_memory import load as load_mem
        mem = load_mem(project_root)
        for fp in mem.get("false_positives", []):
            if fp.get("file") in task.get("files", []):
                notes.append(
                    f"WARNING: {fp['file']} was previously accepted as false positive: "
                    f"{fp.get('reason', '')[:100]}"
                )
        for stub in mem.get("stubs", []):
            if stub.get("path") in task.get("files", []):
                notes.append(
                    f"WARNING: {stub['path']} is recorded as a stub. "
                    f"Previous repair: {stub.get('repair_priority', '?')}"
                )
    except Exception:
        pass
    return notes


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------

def assemble(
    task: dict,
    level: int,
    project_root: Path,
) -> ReferencePack:
    """
    Assemble a reference pack for the given task at the given level.

    Respects context budget from CONTEXT_BUDGET_POLICY.md:
      max_doc_chars and max_code_chars per level.
    """
    from app.services.task_level_classifier import get_spec
    spec = get_spec(level)

    pack = ReferencePack(
        task_id=task.get("id", "?"),
        level=level,
        assembled_at=datetime.now().isoformat(),
    )

    # ── 1. Product goal (always, from memory — near zero cost) ─────────────
    try:
        from app.services.executive_memory import load as load_mem
        mem = load_mem(project_root)
        product = mem.get("product", {})
        pack.product_goal_summary = (
            f"Product: {product.get('name', 'AI Workspace Platform')}\n"
            f"Goal: {product.get('goal', '')}\n"
            f"MVP: {product.get('mvp_definition', '')}"
        )
        pack.phase_context = (
            f"{product.get('current_phase', '')} — {product.get('phase_summary', '')}"
        )
        # Architecture decisions (Level 3+)
        if level >= 3:
            for d in mem.get("architecture", {}).get("decisions", []):
                if d.get("must_preserve"):
                    pack.architecture_decisions.append(d["decision"])
    except Exception:
        pass

    # ── 2. Protected paths (always, minus any explicit task target) ────────────
    _always_protected = [
        "backend/app/main.py",
        "backend/app/db/session.py",
        "backend/requirements.txt",
        "docs/VISION_DOCUMENT.md",
        "docs/SYSTEM_ARCHITECTURE.md",
        "docs/DATA_MODEL.md",
    ]
    task_files_set = set(task.get("files", []))
    pack.protected_paths = [p for p in _always_protected if p not in task_files_set]

    # ── 3. Prior notes (false-accepts, stubs) ───────────────────────────────
    pack.prior_notes = _get_prior_notes(task, project_root)

    # ── 4. Doc excerpts (budget-bounded) ───────────────────────────────────
    if spec.max_doc_chars > 0:
        keywords = _get_doc_keywords(task)
        doc_budget = spec.max_doc_chars
        doc_char_used = 0

        doc_candidates = [
            project_root / "docs" / "SYSTEM_ARCHITECTURE.md",
            project_root / "docs" / "DATA_MODEL.md",
            project_root / "docs" / "VISION_DOCUMENT.md",
        ]
        for doc_path in doc_candidates:
            if doc_char_used >= doc_budget:
                break
            remaining = doc_budget - doc_char_used
            excerpt = _extract_section(doc_path, keywords, min(remaining, 600))
            if excerpt:
                pack.doc_excerpts.append(excerpt)
                doc_char_used += len(excerpt)

    # ── 5. Interface refs (budget-bounded) ─────────────────────────────────
    if spec.max_code_chars > 0:
        interface_files = _find_interface_files(task, project_root)
        code_budget = spec.max_code_chars
        code_char_used = 0
        for ifile in interface_files:
            if code_char_used >= code_budget:
                break
            remaining = code_budget - code_char_used
            sigs = _extract_signatures(ifile, min(remaining, 400))
            if sigs:
                pack.interface_refs.append(sigs)
                code_char_used += len(sigs)

    # ── 6. Compute total ───────────────────────────────────────────────────
    pack.total_chars = (
        len(pack.product_goal_summary)
        + len(pack.phase_context)
        + sum(len(e) for e in pack.doc_excerpts)
        + sum(len(r) for r in pack.interface_refs)
        + sum(len(n) for n in pack.prior_notes)
    )

    return pack


# ---------------------------------------------------------------------------
# Record pack usage in executive memory
# ---------------------------------------------------------------------------

def record_pack_usage(
    pack: ReferencePack,
    project_root: Path,
    memory_substitution_used: bool = False,
) -> None:
    """
    Append pack summary to executive_memory.recent_reference_packs.

    Also updates context_budget_stats including:
    - overrun_cycles: task IDs where pack exceeded the level's budget
    - memory_substitutions_used: count of cycles where memory saved a file read
    """
    try:
        from app.services.executive_memory import load as load_mem, _save as save_mem
        from app.services.task_level_classifier import get_spec
        mem = load_mem(project_root)
        packs = mem.setdefault("recent_reference_packs", [])
        packs.append(pack.to_summary_dict())
        mem["recent_reference_packs"] = packs[-20:]  # ring buffer

        # Update context_budget_stats
        _STATS_DEFAULTS = {
            "total_cycles": 0,
            "total_chars_assembled": 0,
            "avg_chars_per_cycle": 0,
            "budget_overruns": 0,
            "overrun_cycles": [],
            "memory_substitutions_used": 0,
            "most_expensive_task_type": None,
            "by_level": {},
        }
        stats = mem.setdefault("context_budget_stats", dict(_STATS_DEFAULTS))
        # Backfill missing keys without overwriting existing values
        for k, v in _STATS_DEFAULTS.items():
            stats.setdefault(k, v)

        stats["total_cycles"] = stats.get("total_cycles", 0) + 1
        stats["total_chars_assembled"] = stats.get("total_chars_assembled", 0) + pack.total_chars
        stats["avg_chars_per_cycle"] = (
            stats["total_chars_assembled"] // max(1, stats["total_cycles"])
        )

        # Detect overrun: compare pack.total_chars to level budget
        level_spec = get_spec(pack.level)
        level_budget = level_spec.max_doc_chars + level_spec.max_code_chars
        if level_budget > 0 and pack.total_chars > level_budget * 1.25:
            # > 25% over budget counts as overrun
            stats["budget_overruns"] = stats.get("budget_overruns", 0) + 1
            overruns = stats.setdefault("overrun_cycles", [])
            if pack.task_id not in overruns:
                overruns.append(pack.task_id)
            stats["overrun_cycles"] = overruns[-20:]  # keep last 20

        if memory_substitution_used:
            stats["memory_substitutions_used"] = stats.get("memory_substitutions_used", 0) + 1

        lvl = str(pack.level)
        lvl_stats = stats["by_level"].setdefault(lvl, {"cycles": 0, "total_chars": 0})
        lvl_stats["cycles"] += 1
        lvl_stats["total_chars"] += pack.total_chars
        lvl_stats["avg_chars"] = lvl_stats["total_chars"] // max(1, lvl_stats["cycles"])

        save_mem(mem, project_root)
    except Exception:
        pass
