"""
False Accept Auditor — Retroactive detection of incorrectly accepted tasks.

Problem:
  The manager may accept tasks that pass structural checks but are semantically
  empty: stubs, pass-only functions, wrong-page content, doc-only changes.

This module provides:
  1. audit_single(rel_path, project_root) — re-examine one file
  2. audit_all_accepted(manager_state, project_root) — scan full accepted list
  3. Results feed back into executive_memory as false_positives

Run:
  - After any suspiciously fast acceptance (file changed in <2s)
  - When the roadmap shows all tasks done but product visibly broken
  - On-demand via /api/manager/audit endpoint
  - At cycle start if executive_memory has pending false_positives

Returns list[AuditFinding] — each finding describes one false positive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class AuditFinding:
    rel_path: str
    task_id: str
    task_title: str
    accepted_at: str
    finding: str          # short code: STUB | WRONG_CONTENT | DOC_ONLY | EMPTY | PLACEHOLDER
    detail: str           # human-readable explanation
    severity: str         # critical | high | medium
    repair_action: str    # what the manager should do


@dataclass
class AuditReport:
    audited_at: str
    files_checked: int
    findings: list[AuditFinding] = field(default_factory=list)
    clean: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return len(self.findings) > 0


# ---------------------------------------------------------------------------
# Stub / false-positive detection rules
# ---------------------------------------------------------------------------

def _is_stub_python(content: str) -> Optional[str]:
    """
    Return a description if the Python file is a stub, else None.

    Patterns detected:
    1. def main(): ... pass  (script wrapper with no real logic)
    2. All non-trivial functions have pass-only bodies
    3. File is entirely a docstring + pass
    """
    # Pattern 1: main() stub — the file_executor's default fallback
    if re.search(
        r'def main\s*\(\s*\):\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass',
        content, re.DOTALL
    ):
        return "File contains only def main(): pass stub — no real implementation"

    # Pattern 2: All def bodies are pass
    all_defs = re.findall(r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:', content)
    pass_bodies = re.findall(
        r'def \w+\s*\([^)]*\)\s*(?:->[^:]+)?:\s*\n(\s+"""[^"]*"""\s*\n)?\s+pass\b',
        content, re.DOTALL
    )
    if all_defs and len(all_defs) > 0 and len(pass_bodies) == len(all_defs):
        return f"All {len(all_defs)} function(s) have pass-only bodies"

    # Pattern 3: Docstring copies the task description
    if re.search(r'""".*?Task \d+[\.\d]*:.*?"""', content, re.DOTALL):
        if len(content.strip().splitlines()) < 15:
            return "File appears to be a task-description wrapper, not a real implementation"

    return None


def _is_wrong_html_content(file_stem: str, content: str) -> Optional[str]:
    """Return description if HTML page has wrong identity content."""
    _IDENTITY: dict[str, dict] = {
        "chat": {
            "required": ["chat", "message"],
            "forbidden_primary": ["ai workspace dashboard", "orchestrator", "build runner"],
        },
        "dashboard": {
            "required": ["status", "manager"],
            "forbidden_primary": ["msginput", "sendmessage", "messages-scroll"],
        },
    }
    rules = _IDENTITY.get(file_stem)
    if not rules:
        return None

    lower = content.lower()
    missing = [kw for kw in rules["required"] if kw not in lower]
    if missing:
        return f"{file_stem}.html missing expected content keywords: {missing}"
    for forbidden in rules["forbidden_primary"]:
        if forbidden in lower:
            return f"{file_stem}.html appears to contain {forbidden!r} — wrong page identity"
    return None


def _has_placeholder(content: str) -> Optional[str]:
    """Return matched placeholder phrase if found."""
    patterns = [
        r"generated\s+content",
        r"todo\s+placeholder",
        r"lorem ipsum",
        r"insert\s+content\s+here",
        r"coming\s+soon",
    ]
    lower = content.lower()
    for p in patterns:
        m = re.search(p, lower)
        if m:
            return m.group(0)[:60]
    return None


def _is_doc_only_change(task_files: list[str], files_changed: list[str]) -> bool:
    """
    Return True if none of the task's declared target files appear in files_changed.
    (Worker changed only doc files while the real target was untouched.)
    """
    if not task_files:
        return False
    task_set = set(task_files)
    changed_set = set(files_changed)
    return task_set.isdisjoint(changed_set)


# ---------------------------------------------------------------------------
# Single file audit
# ---------------------------------------------------------------------------

def audit_single(
    rel_path: str,
    task_id: str,
    task_title: str,
    accepted_at: str,
    project_root: Path,
) -> Optional[AuditFinding]:
    """
    Re-examine one accepted file for false-positive patterns.
    Returns an AuditFinding if a problem is found, else None.
    """
    full = project_root / rel_path
    if not full.exists():
        return AuditFinding(
            rel_path=rel_path,
            task_id=task_id,
            task_title=task_title,
            accepted_at=accepted_at,
            finding="EMPTY",
            detail="File no longer exists on disk",
            severity="critical",
            repair_action="Re-run task to recreate the file",
        )

    try:
        content = full.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return AuditFinding(
            rel_path=rel_path,
            task_id=task_id,
            task_title=task_title,
            accepted_at=accepted_at,
            finding="EMPTY",
            detail=f"Cannot read file: {e}",
            severity="high",
            repair_action="Investigate file corruption, re-run task",
        )

    if not content.strip():
        return AuditFinding(
            rel_path=rel_path,
            task_id=task_id,
            task_title=task_title,
            accepted_at=accepted_at,
            finding="EMPTY",
            detail="File exists but is empty",
            severity="critical",
            repair_action="Re-run task with explicit minimum line count requirement",
        )

    suffix = full.suffix.lower()
    stem = full.stem.lower()

    # Placeholder check (all types)
    ph = _has_placeholder(content)
    if ph:
        return AuditFinding(
            rel_path=rel_path,
            task_id=task_id,
            task_title=task_title,
            accepted_at=accepted_at,
            finding="PLACEHOLDER",
            detail=f"Placeholder content detected: '{ph}'",
            severity="high",
            repair_action="Re-run task with explicit instruction: no placeholder text",
        )

    # Python-specific
    if suffix == ".py":
        stub = _is_stub_python(content)
        if stub:
            return AuditFinding(
                rel_path=rel_path,
                task_id=task_id,
                task_title=task_title,
                accepted_at=accepted_at,
                finding="STUB",
                detail=stub,
                severity="critical",
                repair_action=(
                    "Rewrite task brief with explicit function signatures, "
                    "implementation requirements, and instruction: "
                    "'no pass-only function bodies'"
                ),
            )

    # HTML-specific
    elif suffix in (".html", ".htm"):
        wrong = _is_wrong_html_content(stem, content)
        if wrong:
            return AuditFinding(
                rel_path=rel_path,
                task_id=task_id,
                task_title=task_title,
                accepted_at=accepted_at,
                finding="WRONG_CONTENT",
                detail=wrong,
                severity="high",
                repair_action=(
                    "Re-run task with page identity requirements and "
                    "explicit forbidden-content list"
                ),
            )

    return None  # No issue found


# ---------------------------------------------------------------------------
# Full audit of all accepted tasks
# ---------------------------------------------------------------------------

def audit_all_accepted(
    accepted_tasks: list[dict],
    project_root: Path,
) -> AuditReport:
    """
    Audit all entries in manager_state.accepted_tasks.

    accepted_tasks: list of dicts with keys:
      task_id, task_title, files_changed, accepted_at
    """
    report = AuditReport(
        audited_at=datetime.now().isoformat(),
        files_checked=0,
    )

    for entry in accepted_tasks:
        task_id = entry.get("task_id", "?")
        task_title = entry.get("task_title", "")
        accepted_at = entry.get("accepted_at", "")
        files_changed = entry.get("files_changed", [])

        for rel_path in files_changed:
            report.files_checked += 1
            finding = audit_single(rel_path, task_id, task_title, accepted_at, project_root)
            if finding:
                report.findings.append(finding)
            else:
                report.clean.append(rel_path)

    return report


# ---------------------------------------------------------------------------
# Doc-only false positive detection
# ---------------------------------------------------------------------------

def check_doc_only_acceptance(
    task: dict,
    files_changed: list[str],
) -> Optional[AuditFinding]:
    """
    Detect the pattern where the worker changed only docs while the task
    required code file changes.

    Called during review, before acceptance is recorded.
    """
    task_files = task.get("files", [])
    if not task_files:
        return None

    if _is_doc_only_change(task_files, files_changed):
        # Which required files were not touched?
        untouched = [f for f in task_files if f not in files_changed]
        return AuditFinding(
            rel_path=", ".join(untouched),
            task_id=task.get("id", "?"),
            task_title=task.get("title", ""),
            accepted_at=datetime.now().isoformat(),
            finding="DOC_ONLY",
            detail=(
                f"Worker changed only documentation files. "
                f"Required target file(s) not touched: {untouched}"
            ),
            severity="critical",
            repair_action=(
                "Retry with explicit instruction: "
                "'ONLY modify the files listed in Target Files. "
                "Do not modify docs/ files.'"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Write findings to executive memory
# ---------------------------------------------------------------------------

def record_findings_in_memory(
    findings: list[AuditFinding],
    project_root: Path,
) -> None:
    """Write audit findings into executive_memory.false_positives."""
    if not findings:
        return
    try:
        from app.services.executive_memory import load, _save
        mem = load(project_root)
        existing_files = {fp.get("file") for fp in mem.get("false_positives", [])}
        for f in findings:
            if f.rel_path not in existing_files:
                mem.setdefault("false_positives", []).append({
                    "task_id": f.task_id,
                    "file": f.rel_path,
                    "accepted_at": f.accepted_at,
                    "detected_at": datetime.now().isoformat(),
                    "reason": f.detail,
                    "detection_method": "false_accept_auditor",
                    "repair_task_id": f"{f.task_id}-repair",
                    "status": "pending_repair",
                    "severity": f.severity,
                    "repair_action": f.repair_action,
                })
        _save(mem, project_root)
    except Exception:
        pass  # Never block on memory write failure
