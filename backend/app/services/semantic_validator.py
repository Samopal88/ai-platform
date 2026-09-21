"""
Semantic Validator — Content-level acceptance checks for manager review.

Runs AFTER the standard file-existence checks to answer the question:
  "Does the result match the PRODUCT INTENT?"

Exported entry point:
  validate_task_result(task, project_root) -> SemanticResult

SemanticResult fields:
  passed: bool
  checks: list[str]   — human-readable pass/fail lines
  issues: list[str]   — only failures, used to build retry/block reason
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SemanticResult:
    passed: bool
    checks: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Placeholder / filler detection
# ---------------------------------------------------------------------------

_PLACEHOLDER_PATTERNS: list[str] = [
    r"generated\s+content",
    r"todo\s+placeholder",
    r"example\s+placeholder",
    r"lorem ipsum",
    r"insert\s+content\s+here",
    r"coming\s+soon",
    r"<title>generated\s+content</title>",
    r"<h1>generated\s+content</h1>",
    # Python stubs
    r"def\s+\w+\(\w*\):\s*\n\s+\"\"\"[^\"]+\"\"\"\s*\n\s+pass\s*$",
]

def _has_placeholder(content: str) -> Optional[str]:
    """Return the matched placeholder phrase, or None."""
    lower = content.lower()
    for pat in _PLACEHOLDER_PATTERNS:
        m = re.search(pat, lower, re.MULTILINE | re.DOTALL)
        if m:
            return m.group(0)[:80].replace("\n", " ")
    return None


# ---------------------------------------------------------------------------
# HTML semantic checks
# ---------------------------------------------------------------------------

# Per-page rules: file_stem → (required_keywords, forbidden_titles, purpose_label)
_HTML_PAGE_RULES: dict[str, dict] = {
    "chat": {
        "required_keywords": ["chat", "message", "send", "input"],
        "required_elements": [
            # At least one of these CSS class/id patterns must appear
            ("chat", r'(id|class)\s*=\s*["\'][^"\']*chat[^"\']*["\']'),
            ("messages", r'(id|class)\s*=\s*["\'][^"\']*message[^"\']*["\']'),
            ("input", r'<(textarea|input)[^>]*>'),
            ("send", r'(onclick\s*=\s*["\'][^"\']*send|id\s*=\s*["\'][^"\']*send[^"\']*["\']|btnSend)'),
        ],
        "forbidden_titles": ["ai workspace dashboard", "generated content"],
        "required_title_hint": "should relate to 'chat' or 'AI Chat'",
        "required_api_patterns": [
            r"/api/projects",
            r"/api/chats",
        ],
    },
    "dashboard": {
        "required_keywords": ["manager", "status", "task"],
        "required_elements": [
            ("status", r'(id|class)\s*=\s*["\'][^"\']*status[^"\']*["\']'),
            ("tasks", r'(task|manager|loop)'),
        ],
        "forbidden_titles": ["generated content"],
        "required_title_hint": "should relate to 'Dashboard'",
        "required_api_patterns": [],
    },
}


def _validate_html(file_stem: str, content: str, checks: list, issues: list) -> None:
    rules = _HTML_PAGE_RULES.get(file_stem)
    if not rules:
        checks.append(f"html_rules({file_stem}): no rules defined, skipped")
        return

    lower = content.lower()

    # 1. Placeholder check
    ph = _has_placeholder(content)
    if ph:
        issues.append(f"Placeholder/filler content detected: '{ph}'")
        checks.append(f"html_no_placeholder({file_stem}): FAIL")
    else:
        checks.append(f"html_no_placeholder({file_stem}): OK")

    # 2. Forbidden title check
    title_m = re.search(r'<title[^>]*>([^<]*)</title>', content, re.IGNORECASE)
    page_title = title_m.group(1).strip().lower() if title_m else ""
    forbidden_hit = any(ft in page_title for ft in rules["forbidden_titles"])
    if forbidden_hit:
        issues.append(f"Page title '{page_title}' is forbidden for {file_stem}.html ({rules['required_title_hint']})")
        checks.append(f"html_title({file_stem}): FAIL — '{page_title}'")
    else:
        checks.append(f"html_title({file_stem}): OK — '{page_title}'")

    # 3. Required keywords
    missing_kw = [kw for kw in rules["required_keywords"] if kw not in lower]
    if missing_kw:
        issues.append(f"{file_stem}.html missing required keywords: {missing_kw}")
        checks.append(f"html_keywords({file_stem}): FAIL — missing {missing_kw}")
    else:
        checks.append(f"html_keywords({file_stem}): OK")

    # 4. Required UI element patterns
    missing_el = []
    for label, pattern in rules["required_elements"]:
        if not re.search(pattern, content, re.IGNORECASE):
            missing_el.append(label)
    if missing_el:
        issues.append(f"{file_stem}.html missing UI elements: {missing_el}")
        checks.append(f"html_elements({file_stem}): FAIL — missing {missing_el}")
    else:
        checks.append(f"html_elements({file_stem}): OK")

    # 5. Required API endpoint references
    missing_api = [p for p in rules["required_api_patterns"] if not re.search(p, content)]
    if missing_api:
        issues.append(f"{file_stem}.html does not reference required API endpoints: {missing_api}")
        checks.append(f"html_api_refs({file_stem}): FAIL — missing {missing_api}")
    else:
        if rules["required_api_patterns"]:
            checks.append(f"html_api_refs({file_stem}): OK")


# ---------------------------------------------------------------------------
# HTML cross-page identity check (prevents dashboard overwriting chat)
# ---------------------------------------------------------------------------

_IDENTITY_FINGERPRINTS: dict[str, list[str]] = {
    "dashboard": [
        "ai workspace dashboard",
        "autonomous build runner",
        "manager loop",
        "orchestrator",
    ],
    "chat": [
        "ai chat",
        "messages-scroll",
        "msginput",
        "sendmessage",
    ],
}


def _detect_page_identity(content: str) -> Optional[str]:
    """Return which page this content looks like, based on fingerprints."""
    lower = content.lower()
    scores: dict[str, int] = {}
    for page, fingerprints in _IDENTITY_FINGERPRINTS.items():
        scores[page] = sum(1 for fp in fingerprints if fp in lower)
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] >= 2 else None


def _validate_html_identity(file_stem: str, content: str, checks: list, issues: list) -> None:
    detected = _detect_page_identity(content)
    if detected and detected != file_stem:
        issues.append(
            f"{file_stem}.html appears to contain {detected}-page content "
            f"(identity fingerprint mismatch — possible page overwrite)"
        )
        checks.append(f"html_identity({file_stem}): FAIL — detected as '{detected}'")
    else:
        checks.append(f"html_identity({file_stem}): OK")


# ---------------------------------------------------------------------------
# Python API stub checks
# ---------------------------------------------------------------------------

_PYTHON_API_REQUIRED: dict[str, dict] = {
    # file stem → what the real implementation must contain
    "projects": {
        "router_pattern": r"APIRouter",
        "route_pattern": r'@router\.(get|post|put|delete)',
        "min_routes": 1,
        "label": "projects router",
    },
    "chats": {
        "router_pattern": r"APIRouter",
        "route_pattern": r'@router\.(get|post|put|delete)',
        "min_routes": 1,
        "label": "chats router",
    },
    "ai_chat": {
        "router_pattern": r"APIRouter",
        "route_pattern": r'@router\.(get|post|put|delete)',
        "min_routes": 1,
        "label": "ai_chat router",
    },
    "files": {
        "router_pattern": r"APIRouter",
        "route_pattern": r'@router\.(get|post|put|delete)',
        "min_routes": 1,
        "label": "files router",
    },
    "memory": {
        "router_pattern": r"APIRouter",
        "route_pattern": r'@router\.(get|post|put|delete)',
        "min_routes": 1,
        "label": "memory router",
    },
}


def _validate_python_api(file_stem: str, content: str, checks: list, issues: list) -> None:
    rules = _PYTHON_API_REQUIRED.get(file_stem)
    if not rules:
        checks.append(f"python_api({file_stem}): no rules defined, skipped")
        return

    label = rules["label"]

    # Placeholder / stub detection first
    ph = _has_placeholder(content)
    if ph:
        issues.append(f"{file_stem}.py is a stub (placeholder detected: '{ph[:60]}')")
        checks.append(f"python_no_stub({file_stem}): FAIL")
        return
    else:
        checks.append(f"python_no_stub({file_stem}): OK")

    if not re.search(rules["router_pattern"], content):
        issues.append(f"{file_stem}.py missing APIRouter — file is a stub, not a real {label}")
        checks.append(f"python_has_router({file_stem}): FAIL")
    else:
        checks.append(f"python_has_router({file_stem}): OK")

    route_count = len(re.findall(rules["route_pattern"], content))
    if route_count < rules["min_routes"]:
        issues.append(
            f"{file_stem}.py has {route_count} route decorators, "
            f"expected at least {rules['min_routes']}"
        )
        checks.append(f"python_routes({file_stem}): FAIL — {route_count} routes")
    else:
        checks.append(f"python_routes({file_stem}): OK — {route_count} routes")


# ---------------------------------------------------------------------------
# Regression detection
# ---------------------------------------------------------------------------

def _snapshot_file(project_root: Path, rel_path: str) -> Path:
    """Where we store the content fingerprint of a previously accepted file."""
    safe = rel_path.replace("/", "_").replace("\\", "_")
    return project_root / "docs" / "progress" / "file_snapshots" / f"{safe}.snapshot"


def record_file_snapshot(project_root: Path, rel_path: str, content: str) -> None:
    """
    Save a content fingerprint after a file is accepted.
    Called by manager_loop after acceptance.
    """
    snap_file = _snapshot_file(project_root, rel_path)
    snap_file.parent.mkdir(parents=True, exist_ok=True)

    # Store: line count, key-structure tokens (function/class names, route decorators)
    tokens = _extract_structure_tokens(content)
    import json
    snap_file.write_text(json.dumps({
        "rel_path": rel_path,
        "line_count": content.count("\n"),
        "char_count": len(content),
        "tokens": tokens,
    }, indent=2))


def _extract_structure_tokens(content: str) -> list[str]:
    """Extract structural markers: class/def names, route paths, HTML ids."""
    tokens = []
    # Python: class and def names
    for m in re.finditer(r'^(class|def)\s+(\w+)', content, re.MULTILINE):
        tokens.append(f"{m.group(1)}:{m.group(2)}")
    # Python: FastAPI routes
    for m in re.finditer(r'@router\.(get|post|put|delete)\(["\']([^"\']+)', content):
        tokens.append(f"route:{m.group(2)}")
    # HTML: id= values
    for m in re.finditer(r'\bid\s*=\s*["\']([^"\']+)["\']', content, re.IGNORECASE):
        tokens.append(f"id:{m.group(1)}")
    return tokens[:60]  # cap to avoid bloat


def _validate_regression(
    rel_path: str,
    content: str,
    project_root: Path,
    checks: list,
    issues: list,
) -> None:
    snap_file = _snapshot_file(project_root, rel_path)
    if not snap_file.exists():
        checks.append(f"regression({rel_path}): no snapshot yet, skipped")
        return

    import json
    try:
        prev = json.loads(snap_file.read_text())
    except Exception:
        checks.append(f"regression({rel_path}): snapshot unreadable, skipped")
        return

    current_tokens = set(_extract_structure_tokens(content))
    prev_tokens = set(prev.get("tokens", []))

    removed = prev_tokens - current_tokens
    # Route and def removals are regressions; id removals may be UI rewrites (warn only)
    route_removals = [t for t in removed if t.startswith("route:") or t.startswith("def:")]
    id_removals = [t for t in removed if t.startswith("id:")]

    if route_removals:
        issues.append(
            f"Regression in {rel_path}: previously accepted routes/functions removed: "
            f"{route_removals[:5]}"
        )
        checks.append(f"regression({rel_path}): FAIL — removed {route_removals[:3]}")
    elif id_removals and len(id_removals) > 5:
        # Many HTML ids removed → possible wholesale page replacement
        issues.append(
            f"Possible regression in {rel_path}: {len(id_removals)} previously accepted "
            f"HTML element ids removed (possible page overwrite)"
        )
        checks.append(f"regression({rel_path}): WARN — {len(id_removals)} ids removed")
    else:
        checks.append(f"regression({rel_path}): OK")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _validate_python_service(file_stem: str, content: str, checks: list, issues: list) -> None:
    """
    Validate that a backend/app/services/*.py file is a real implementation,
    not a stub or def main(): pass wrapper.
    """
    # Placeholder check
    ph = _has_placeholder(content)
    if ph:
        issues.append(f"{file_stem}.py service is a stub (placeholder: '{ph[:60]}')")
        checks.append(f"service_no_stub({file_stem}): FAIL")
        return
    checks.append(f"service_no_placeholder({file_stem}): OK")

    # Detect def main(): pass pattern (file_executor default fallback)
    import re as _re
    main_stub = _re.search(
        r'def main\s*\(\s*\):\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass',
        content, _re.DOTALL
    )
    if main_stub:
        issues.append(
            f"{file_stem}.py is a def main(): pass stub — "
            f"worker produced boilerplate, not a real service"
        )
        checks.append(f"service_not_main_stub({file_stem}): FAIL")
        return
    checks.append(f"service_not_main_stub({file_stem}): OK")

    # Detect all-pass function bodies
    all_defs = _re.findall(r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:', content)
    pass_bodies = _re.findall(
        r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass\b',
        content, _re.DOTALL
    )
    if all_defs and len(pass_bodies) == len(all_defs):
        issues.append(
            f"{file_stem}.py: all {len(all_defs)} function(s) have pass-only bodies — "
            f"this is a stub, not an implementation"
        )
        checks.append(f"service_real_bodies({file_stem}): FAIL — {len(pass_bodies)}/{len(all_defs)} are stubs")
    else:
        checks.append(f"service_real_bodies({file_stem}): OK")


def _validate_doc_only_change(task: dict, project_root: Path, checks: list, issues: list,
                               verified_unchanged: Optional[list] = None) -> None:
    """
    Detect pattern: worker changed only doc files while task declared code targets.

    This fires when files_changed (from the actual changed files on disk, compared
    to snapshot ages) are all in docs/ but task.files contains backend/ or frontend/ paths.
    Since we don't have direct access to files_changed here, we check whether
    task.files exist AND whether any of them have recent modification times
    relative to known doc files that were listed.

    verified_unchanged: files the executor confirmed were already correct (no write needed).
    These are NOT stale — they satisfy the requirement already.
    """
    import time as _time
    task_files = task.get("files", [])
    if not task_files:
        return

    code_targets = [f for f in task_files if not f.startswith("docs/")]
    if not code_targets:
        return  # Task is doc-only by design

    # Files confirmed already-correct by the executor — do not count as stale
    already_ok = set(verified_unchanged or [])

    # Check each code target: does it exist and was it recently modified?
    # We consider a file "stale" if it is >1 hour old AND not in already_ok
    now = _time.time()
    stale_targets = []
    for rel in code_targets:
        if rel in already_ok:
            continue  # executor verified this file is already correct
        full = project_root / rel
        if not full.exists():
            continue  # structural check handles missing
        age = now - full.stat().st_mtime
        if age > 3600:  # older than 1 hour = was not changed this cycle
            stale_targets.append(rel)

    if stale_targets and len(stale_targets) == len([c for c in code_targets if c not in already_ok]):
        issues.append(
            f"Suspected doc-only change: task targets {code_targets} "
            f"but none appear recently modified. "
            f"Worker may have changed only docs/ files."
        )
        checks.append(f"doc_only_guard: WARN — code targets not recently modified")
    else:
        checks.append(f"doc_only_guard: OK")


def validate_task_result(
    task: dict,
    project_root: Path,
    verified_unchanged: Optional[list] = None,
) -> SemanticResult:
    """
    Run all semantic checks relevant to this task's changed files.

    Called by manager_loop._review_result after structural checks pass.

    Returns SemanticResult(passed, checks, issues).
    """
    checks: list[str] = []
    issues: list[str] = []

    files_required: list[str] = task.get("files", [])

    # Doc-only change detection (task-level, not per-file)
    _validate_doc_only_change(task, project_root, checks, issues, verified_unchanged)

    for rel_path in files_required:
        full = project_root / rel_path
        if not full.exists():
            continue  # structural check already caught this

        try:
            content = full.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            checks.append(f"read({rel_path}): FAIL — {e}")
            issues.append(f"Cannot read {rel_path}: {e}")
            continue

        suffix = full.suffix.lower()
        stem = full.stem.lower()

        # ── HTML pages ────────────────────────────────────────────────────
        if suffix in (".html", ".htm"):
            _validate_html(stem, content, checks, issues)
            _validate_html_identity(stem, content, checks, issues)
            _validate_regression(rel_path, content, project_root, checks, issues)

        # ── Python API files ──────────────────────────────────────────────
        elif suffix == ".py" and rel_path.startswith("backend/app/api/"):
            _validate_python_api(stem, content, checks, issues)
            _validate_regression(rel_path, content, project_root, checks, issues)

        # ── Python service files ───────────────────────────────────────────
        elif suffix == ".py" and rel_path.startswith("backend/app/services/"):
            _validate_python_service(stem, content, checks, issues)
            _validate_regression(rel_path, content, project_root, checks, issues)

        # ── Generic placeholder check for any other file ──────────────────
        else:
            ph = _has_placeholder(content)
            if ph:
                issues.append(f"{rel_path} contains placeholder/filler: '{ph[:60]}'")
                checks.append(f"no_placeholder({rel_path}): FAIL")
            else:
                checks.append(f"no_placeholder({rel_path}): OK")

    return SemanticResult(
        passed=len(issues) == 0,
        checks=checks,
        issues=issues,
    )
