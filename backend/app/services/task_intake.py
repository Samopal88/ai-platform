"""
AI Workspace Platform - Task Intake Service

Selects the next actionable task from docs/agent/ROADMAP.md,
resolves the minimal product context needed, and builds a compact
execution prompt for the executor pipeline.

No LLM calls. No full-document reads. Token-economical by design.
"""
import re
from pathlib import Path
from typing import Optional
from app.core.config import settings

PROJECT_ROOT = Path(settings.PROJECT_ROOT)
ROADMAP_PATH = PROJECT_ROOT / "docs" / "agent" / "ROADMAP.md"
PRODUCT_DOCS_DIR = PROJECT_ROOT / "docs"

# Completed-task markers written into ROADMAP.md
_DONE_MARKERS = ("[x]", "[done]", "[DONE]", "status: done")

# Product doc selection rules (mirrors PRODUCT_MAP.md decision table)
_PRODUCT_DOC_RULES = [
    (["api", "endpoint", "route", "router"],            "SYSTEM_ARCHITECTURE.md",   "API structure"),
    (["db", "database", "model", "schema", "entity"],   "DATA_MODEL.md",            "data entities"),
    (["agent", "executor", "orchestrat", "supervisor"],  "AGENT_INTERACTION_SPEC.md","agent interaction"),
    (["ux", "dashboard", "ui", "frontend", "user"],     "VISION_DOCUMENT.md",       "UX behaviour"),
    (["plan", "phase", "milestone", "sprint"],          "IMPLEMENTATION_PLAN.md",   "planning context"),
    (["prompt", "template", "task format"],             "TASK_PROMPT_TEMPLATES.md", "prompt templates"),
]


# ---------------------------------------------------------------------------
# Roadmap parsing
# ---------------------------------------------------------------------------

def _parse_phase(heading: str) -> str:
    m = re.search(r'Phase\s+(\d+)', heading, re.IGNORECASE)
    return f"Phase {m.group(1)}" if m else "Unknown"


def _section_status(lines: list[str]) -> str:
    """Derive task status from surrounding lines."""
    combined = " ".join(lines).lower()
    if any(m.lower() in combined for m in _DONE_MARKERS):
        return "done"
    return "todo"


def load_roadmap_tasks() -> list[dict]:
    """
    Parse docs/agent/ROADMAP.md into a list of structured task dicts.

    Each dict:
      id, title, phase, files, change, why, status (todo|done|deferred)
    """
    if not ROADMAP_PATH.exists():
        return []

    text = ROADMAP_PATH.read_text(encoding="utf-8")
    tasks: list[dict] = []
    current_phase = "Unknown"
    in_deferred = False

    # Split on task headings (### N.N Title)
    # Also track ## Phase headings and ## Deferred
    blocks = re.split(r'\n(?=##+ )', text)

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        first = lines[0].strip()

        # Phase heading
        if re.match(r'^## Phase', first, re.IGNORECASE):
            current_phase = _parse_phase(first)
            in_deferred = False
            continue

        # Deferred section
        if re.match(r'^## Deferred', first, re.IGNORECASE):
            in_deferred = True
            continue

        # Task heading: ### N.N Title
        m = re.match(r'^###\s+([\d\.]+)\s+(.+)', first)
        if not m:
            continue

        task_id = m.group(1).strip()
        title = m.group(2).strip()
        # Strip backtick wrapping from title if present
        title = title.strip('`')

        body = "\n".join(lines[1:])

        # Extract **Files:** list
        files: list[str] = []
        files_m = re.search(r'\*\*Files:\*\*\s*`?([^\n]+)`?', body)
        if files_m:
            raw = files_m.group(1)
            files = [f.strip().strip('`') for f in raw.split(',') if f.strip()]

        # Extract **Change:**
        change = ""
        change_m = re.search(r'\*\*Change:\*\*\s*(.+?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if change_m:
            change = re.sub(r'\s+', ' ', change_m.group(1)).strip()

        # Extract **Why:**
        why = ""
        why_m = re.search(r'\*\*Why:\*\*\s*(.+?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if why_m:
            why = re.sub(r'\s+', ' ', why_m.group(1)).strip()

        status = "deferred" if in_deferred else _section_status(lines)

        tasks.append({
            "id": task_id,
            "title": title,
            "phase": current_phase,
            "files": files,
            "change": change[:300],
            "why": why[:200],
            "status": status,
        })

    return tasks



# ---------------------------------------------------------------------------
# MVP Recovery roadmap parser
# ---------------------------------------------------------------------------

def _load_mvp_recovery_tasks() -> list[dict]:
    """
    Parse the MVP recovery roadmap when in mvp_recovery mode.
    Returns tasks in the form used by choose_next_task().
    """
    try:
        from app.services.executive_memory import get_mvp_recovery_roadmap_path
        roadmap_rel = get_mvp_recovery_roadmap_path(PROJECT_ROOT)
        if not roadmap_rel:
            return []
        roadmap_path = PROJECT_ROOT / roadmap_rel
        if not roadmap_path.exists():
            return []

        # Reuse the same parser but point at the recovery roadmap
        import importlib, sys
        text = roadmap_path.read_text(encoding="utf-8")
        tasks = []
        # Recovery tasks use "### R1", "### R2" etc.
        import re
        blocks = re.split(r'\n(?=##+ )', text)
        current_phase = "Recovery"
        for block in blocks:
            lines = block.strip().splitlines()
            if not lines:
                continue
            first = lines[0].strip()
            if re.match(r'^## Phase', first, re.IGNORECASE):
                current_phase = first.lstrip('#').strip()
                continue
            # Task heading: ### R1 — Title or ### S1 — Title etc.
            m = re.match(r'^###\s+(R\d+|S\d+|D\d+)\s+[—-]\s+(.+)', first)
            if not m:
                continue
            task_id = m.group(1).strip()
            title = m.group(2).strip()
            body = "\n".join(lines[1:])

            # Extract **Files:**
            files = []
            files_m = re.search(r'\*\*Files:\*\*\s*`?([^\n]+)`?', body)
            if files_m:
                raw = files_m.group(1)
                files = [f.strip().strip('`') for f in raw.split(',') if f.strip()]

            # Extract **Change:**
            change = ""
            change_m = re.search(r'\*\*Change:\*\*\s*(.+?)(?=\n\*\*|\Z)', body, re.DOTALL)
            if change_m:
                change = re.sub(r'\s+', ' ', change_m.group(1)).strip()[:300]

            # Check if done (marked in autopilot_config completed_tasks)
            try:
                from app.services.executive_memory import get_mvp_recovery_roadmap_path as _g
                import json
                cfg = json.loads((PROJECT_ROOT / "docs/progress/autopilot_config.json").read_text())
                completed = cfg.get("mvp_recovery", {}).get("completed_tasks", [])
            except Exception:
                completed = []

            status = "done" if task_id in completed else "todo"

            tasks.append({
                "id": task_id,
                "title": title,
                "phase": current_phase,
                "files": files,
                "change": change,
                "why": "MVP recovery — critical path to runnable product",
                "status": status,
                "_is_mvp_recovery": True,
            })
        return tasks
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Task selection — with repair-first and risk-aware ordering
# ---------------------------------------------------------------------------

def choose_next_task() -> Optional[dict]:
    """
    Select the next task using executive-standard priority order.

    In MVP_RECOVERY_MODE:
    0. MVP recovery roadmap tasks override normal roadmap

    Normal mode:
    1. P0/P1/P2 repairs from repair_queue (override roadmap)
    2. Phase gate check for next roadmap task phase
    3. Roadmap tasks with explicit file targets
    4. Roadmap tasks without file targets
    """
    root = PROJECT_ROOT

    # ── Step 0: MVP Recovery Mode check ───────────────────────────────────
    try:
        from app.services.executive_memory import is_mvp_recovery_mode
        if is_mvp_recovery_mode(root):
            mvp_tasks = _load_mvp_recovery_tasks()
            todo = [t for t in mvp_tasks if t["status"] == "todo"]
            if todo:
                return todo[0]
            # MVP tasks exhausted — fall through to normal selection
    except Exception:
        pass

    # ── Step 1: Check repair queue first ──────────────────────────────────
    try:
        from app.services.repair_queue import has_override_repairs, next_repair, repair_to_task
        if has_override_repairs(root):
            repair = next_repair(root)
            if repair:
                return repair_to_task(repair)
    except Exception:
        pass

    # ── Step 2: Select from roadmap with phase gate awareness ──────────────
    tasks = load_roadmap_tasks()
    todo_tasks_with_files = [t for t in tasks if t["status"] == "todo" and t["files"]]
    todo_tasks_any = [t for t in tasks if t["status"] == "todo"]

    candidates = todo_tasks_with_files or todo_tasks_any
    if not candidates:
        return None

    # Check phase gate for the candidate's phase
    next_candidate = candidates[0]
    phase = next_candidate.get("phase", "")

    if phase:
        try:
            from app.services.phase_gate import check as gate_check, persist_result
            gate_result = gate_check(phase, root)
            persist_result(gate_result, root)

            if gate_result.verdict == "blocked":
                # Look for repair tasks that fix the blocking issues
                from app.services.repair_queue import next_repair as nr, repair_to_task as r2t
                deferred_repair = nr(root, allow_deferred=True)
                if deferred_repair:
                    return r2t(deferred_repair)
                # If no repair available, still return the task but mark the blocking context
                # (manager_loop will see the phase gate in review)
                next_candidate["_phase_gate_blocked"] = True
                next_candidate["_phase_gate_reasons"] = gate_result.blocking_reasons
        except Exception:
            pass

    return next_candidate


# ---------------------------------------------------------------------------
# Product context resolution
# ---------------------------------------------------------------------------

def resolve_product_context(task: dict) -> dict:
    """
    Determine which product docs are relevant for this task.
    Uses keyword matching against title + change + files.

    Returns:
      {
        "product_docs": ["SYSTEM_ARCHITECTURE.md", ...],
        "reason": "API change detected",
        "sections_hint": ["API endpoints", ...]
      }
    """
    needle = " ".join([
        task.get("title", ""),
        task.get("change", ""),
        " ".join(task.get("files", [])),
    ]).lower()

    matched_docs: list[str] = []
    reasons: list[str] = []
    hints: list[str] = []

    for keywords, doc, reason in _PRODUCT_DOC_RULES:
        if any(kw in needle for kw in keywords):
            if doc not in matched_docs:
                matched_docs.append(doc)
                reasons.append(reason)
                hints.append(reason.replace(" ", "_").upper())

    return {
        "product_docs": matched_docs,
        "reason": "; ".join(reasons) if reasons else "no product context required",
        "sections_hint": hints,
    }


# ---------------------------------------------------------------------------
# Task level classification (exposed for manager_loop and callers)
# ---------------------------------------------------------------------------

def classify_task(task: dict):
    """Classify a task and return a ClassificationResult."""
    try:
        from app.services.task_level_classifier import classify
        return classify(task)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def _build_must_not_touch(task_files: list[str]) -> str:
    """Build the Must Not Touch section based on task targets.

    Target files are NEVER listed here — a file cannot be both a target and protected.
    """
    always_protected = [
        "backend/app/main.py",
        "backend/app/db/session.py",
        "backend/requirements.txt",
        "backend/.env",
        "docs/VISION_DOCUMENT.md",
        "docs/SYSTEM_ARCHITECTURE.md",
        "docs/DATA_MODEL.md",
    ]
    # Remove any file that is explicitly listed as a target for this task
    task_files_set = set(task_files)
    protected = [p for p in always_protected if p not in task_files_set]
    # Never touch sibling code files not in task scope
    return "\n".join(f"  - {p}" for p in protected)


def _build_acceptance_criteria(task: dict) -> str:
    """Generate verifiable acceptance criteria from the task definition."""
    files = task.get("files", [])
    lines = []
    for f in files:
        lines.append(f"  - File exists and is non-empty: {f}")
        if f.endswith(".py") and "api/" in f:
            lines.append(f"  - Contains: APIRouter")
            lines.append(f"  - Contains at least 1: @router.get or @router.post or @router.put or @router.delete")
            lines.append(f"  - No route handler body is only 'pass'")
        elif f.endswith(".py") and "services/" in f:
            lines.append(f"  - No function body consisting only of 'pass'")
            lines.append(f"  - Does NOT contain: def main(): pass")
            lines.append(f"  - Is NOT a script wrapper (no if __name__ == '__main__')")
        elif f.endswith(".html"):
            stem = f.split("/")[-1].replace(".html", "")
            lines.append(f"  - Title is appropriate for '{stem}' page (not 'Generated Content')")
            lines.append(f"  - Contains at least one interactive element (input/button/textarea)")
            lines.append(f"  - Contains JavaScript functions (not just static HTML)")
    lines.append("  - No placeholder text: 'Generated Content', 'Lorem ipsum', 'TODO Placeholder'")
    lines.append("  - No line containing only: pass  (for Python files)")
    return "\n".join(lines)


def _build_regression_risks(task: dict) -> str:
    """Identify regression risks based on task files."""
    files = task.get("files", [])
    risks = []
    for f in files:
        if "main.py" in f:
            risks.append(f"  - backend/app/main.py: do not remove existing router registrations")
        if f.endswith(".html"):
            risks.append(f"  - {f}: preserve all existing JavaScript functions by name")
    if not risks:
        risks.append("  - (none identified for this task)")
    return "\n".join(risks)


def build_execution_prompt(task: dict, context: dict) -> str:
    """
    Build an executive-standard task brief for the worker.

    If the task is a repair task (_is_repair flag), uses the repair brief directly.
    Otherwise builds a full level-aware brief with reference pack injected.

    Conforms to docs/agent/DELEGATION_STANDARD.md and REFERENCE_PACK_STANDARD.md.
    """
    # ── Repair tasks use their pre-built brief ─────────────────────────────
    if task.get("_is_repair") and task.get("_repair_brief"):
        return task["_repair_brief"]

    # ── Classify the task ──────────────────────────────────────────────────
    level = 2  # default
    level_spec_name = "Semantic Implementation"
    level_reasons = []
    try:
        from app.services.task_level_classifier import classify
        clf = classify(task)
        level = clf.level
        level_spec_name = clf.spec.name
        level_reasons = clf.reasons
    except Exception:
        pass

    # ── Assemble reference pack ────────────────────────────────────────────
    pack_rendered = ""
    try:
        from app.services.reference_pack import assemble, record_pack_usage
        pack = assemble(task, level, PROJECT_ROOT)
        record_pack_usage(pack, PROJECT_ROOT)
        if pack.doc_excerpts or pack.interface_refs or pack.prior_notes:
            pack_rendered = pack.render()
    except Exception:
        pass
    task_id = task.get("id", "?")
    title = task.get("title", "")
    files = task.get("files", [])
    change = task.get("change", "")
    why = task.get("why", "")
    phase = task.get("phase", "")

    # Phase gate warning injection
    gate_warning = ""
    if task.get("_phase_gate_blocked"):
        reasons = task.get("_phase_gate_reasons", [])
        gate_warning = (
            "\nPHASE GATE WARNING — earlier foundation issues detected:\n"
            + "\n".join(f"  - {r}" for r in reasons[:3])
            + "\nProceed carefully. Ensure this task does not depend on broken foundations.\n"
        )

    files_str = "\n".join(f"  {f}" for f in files) if files else "  (see change description)"
    product_refs = context.get("product_docs", [])

    # Determine relevant reference docs
    is_frontend = any(f.startswith("frontend/") for f in files)
    is_api = any("app/api/" in f for f in files)
    is_service = any("app/services/" in f for f in files)

    ref_docs = list(product_refs)
    if is_frontend and "VISION_DOCUMENT.md" not in ref_docs:
        ref_docs.extend(["VISION_DOCUMENT.md", "SYSTEM_ARCHITECTURE.md"])
    if is_api and "SYSTEM_ARCHITECTURE.md" not in ref_docs:
        ref_docs.append("SYSTEM_ARCHITECTURE.md")
    if is_service and "DATA_MODEL.md" not in ref_docs:
        ref_docs.append("DATA_MODEL.md")

    refs_str = "\n".join(f"  docs/{d}" for d in ref_docs) if ref_docs else "  (none required)"
    refs_readonly_note = (
        "  *** Reference files are read-only unless explicitly listed in Target Files. ***\n"
        "  Do NOT modify any reference file. Read them for context only."
    )

    # Executive memory summary
    exec_state = ""
    try:
        from app.services.executive_memory import get_implemented_summary
        exec_state = get_implemented_summary(PROJECT_ROOT)
    except Exception:
        try:
            from app.services.product_memory import get_summary
            exec_state = get_summary(PROJECT_ROOT)
        except Exception:
            pass

    # Constraints block
    if is_frontend:
        constraints = (
            "  - Page title MUST match the page purpose (not 'Generated Content')\n"
            "  - Implement real interactive UI — not static placeholder HTML\n"
            "  - Page identity must match the file name (chat.html = chat UI, dashboard.html = dashboard UI)\n"
            "  - All API calls must use the endpoints documented in SYSTEM_ARCHITECTURE.md"
        )
    elif is_api:
        constraints = (
            "  - MUST create an APIRouter instance: router = APIRouter(...)\n"
            "  - MUST add at least one @router.get/post/put/delete decorated route\n"
            "  - Route handlers must have real bodies, not 'pass'\n"
            "  - DO NOT register the router in main.py (separate task)"
        )
    elif is_service:
        constraints = (
            "  - MUST implement real function bodies — no pass-only stubs\n"
            "  - DO NOT write a def main(): script wrapper\n"
            "  - DO NOT write if __name__ == '__main__' blocks\n"
            "  - Import from existing modules in backend/app/ where needed"
        )
    else:
        constraints = "  - No placeholder or filler content"

    brief = f"""TASK BRIEF
==========
Phase: {phase}

## Objective
{title}

## Product Reason
{why or change}

## Target Files (ONLY modify these)
{files_str}

## Must Not Touch
{_build_must_not_touch(files)}

## Required References (read-only — do NOT modify)
{refs_str}
{refs_readonly_note}

## Implementation Requirements
{change}

## Implementation Constraints
{constraints}

## Non-Goals (HARD RULES — violation = task failure)
  - Do NOT modify docs/ files unless they are listed in Target Files
  - "Updating docs/ to reflect the change" is NOT acceptable — modify code only
  - Writing to docs/ when target is backend/ or frontend/ counts as doc-drift and fails review
  - Do not add print() debug statements
  - Do not modify files not listed in Target Files
  - Do not add TODO comments (implement completely or raise an error)

## Acceptance Criteria
{_build_acceptance_criteria(task)}

## Regression Risks
{_build_regression_risks(task)}

## Expected Output Quality
Production-quality implementation. No stubs. No placeholders. No TODO bodies.
Task Level: {level} — {level_spec_name}
{gate_warning}
{pack_rendered}"""

    return brief
