#!/usr/bin/env python3
"""Helpers for last-run reporting in autonomous dev loop scripts."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def report_paths(project_root: Path) -> tuple[Path, Path]:
    reports_dir = project_root / "reports"
    return reports_dir / "autopilot_last_run.json", reports_dir / "autopilot_last_run.md"


def load_last_run_report(project_root: Path) -> Optional[dict]:
    json_path, _ = report_paths(project_root)
    data = _safe_read_json(json_path)
    return data or None


def collect_confidence_wave(project_root: Path) -> dict:
    """
    Build a compact confidence/completion snapshot from executive memory.

    confidence_counts: from implemented entries (confidence field)
    completion_level_counts: from completion_levels map
    """
    mem_path = project_root / "docs" / "progress" / "executive_memory.json"
    mem = _safe_read_json(mem_path)
    if not mem:
        return {
            "source": str(mem_path),
            "available": False,
            "confidence_counts": {},
            "completion_level_counts": {},
            "updated_at": None,
        }

    confidence_counts: Counter[str] = Counter()
    implemented = mem.get("implemented") or {}
    for cat in ("pages", "api_routers", "services", "schemas", "migrations"):
        for entry in implemented.get(cat) or []:
            confidence = str(entry.get("confidence") or "unknown")
            confidence_counts[confidence] += 1

    completion_counts: Counter[str] = Counter()
    for _path, level in (mem.get("completion_levels") or {}).items():
        completion_counts[str(level or "unknown")] += 1

    return {
        "source": str(mem_path),
        "available": True,
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "completion_level_counts": dict(sorted(completion_counts.items())),
        "updated_at": mem.get("updated_at"),
    }


def build_last_run_report(
    *,
    project_root: Path,
    loop_name: str,
    mode: str,
    started_at: str,
    finished_at: str,
    counters: dict,
    stop_reason: str,
    last_status: Optional[str],
    task_outcomes: list[dict],
    extra: Optional[dict[str, Any]] = None,
) -> dict:
    files_all = counters.get("files_changed_total") or []
    unique_files = sorted(set(files_all))
    confidence_wave = collect_confidence_wave(project_root)

    return {
        "generated_at": _utc_now_iso(),
        "project_root": str(project_root),
        "loop": loop_name,
        "mode": mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": counters.get("duration_sec"),
        "stop_reason": stop_reason,
        "last_status": last_status,
        "summary": {
            "cycles": counters.get("cycles", 0),
            "accepted": counters.get("accepted", 0),
            "retry": counters.get("retry", 0),
            "blocked_skip": counters.get("blocked_skip", 0),
            "executor_counts": counters.get("executor_counts") or {},
            "files_changed_total": len(files_all),
            "files_changed_unique": len(unique_files),
        },
        "files_changed": unique_files,
        "task_outcomes": task_outcomes,
        "confidence_wave": confidence_wave,
        "extra": extra or {},
    }


def _render_md(report: dict) -> str:
    s = report.get("summary") or {}
    lines: list[str] = []
    lines.append("# Autopilot Last Run Report")
    lines.append("")
    lines.append(f"- Loop: `{report.get('loop')}` / mode: `{report.get('mode')}`")
    lines.append(f"- Started: `{report.get('started_at')}`")
    lines.append(f"- Finished: `{report.get('finished_at')}`")
    lines.append(f"- Duration (sec): `{report.get('duration_sec')}`")
    lines.append(f"- Stop reason: `{report.get('stop_reason')}`")
    lines.append(f"- Final status: `{report.get('last_status')}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Cycles: `{s.get('cycles', 0)}`")
    lines.append(f"- Accepted: `{s.get('accepted', 0)}`")
    lines.append(f"- Retries: `{s.get('retry', 0)}`")
    lines.append(f"- Blocked(skip): `{s.get('blocked_skip', 0)}`")
    lines.append(f"- Files changed (unique): `{s.get('files_changed_unique', 0)}`")
    lines.append("")
    lines.append("## Executors")
    lines.append("")
    executors = s.get("executor_counts") or {}
    if executors:
        for name, count in sorted(executors.items()):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Confidence Wave")
    lines.append("")
    wave = report.get("confidence_wave") or {}
    if wave.get("available"):
        lines.append(f"- Source updated at: `{wave.get('updated_at')}`")
        cc = wave.get("confidence_counts") or {}
        cl = wave.get("completion_level_counts") or {}
        lines.append(f"- confidence_counts: `{json.dumps(cc, ensure_ascii=False)}`")
        lines.append(f"- completion_level_counts: `{json.dumps(cl, ensure_ascii=False)}`")
    else:
        lines.append("- executive memory not available")
    lines.append("")
    lines.append("## Files Changed")
    lines.append("")
    files = report.get("files_changed") or []
    if files:
        for rel in files:
            lines.append(f"- `{rel}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Task Outcomes")
    lines.append("")
    outcomes = report.get("task_outcomes") or []
    if outcomes:
        for row in outcomes[-30:]:
            lines.append(
                f"- cycle `{row.get('cycle')}`: `{row.get('verdict')}` [{row.get('task_id')}] "
                f"`{row.get('executor')}` files={row.get('files_changed_count', 0)}"
            )
    else:
        lines.append("- no outcomes recorded")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def save_last_run_report(project_root: Path, report: dict) -> tuple[Path, Path]:
    json_path, md_path = report_paths(project_root)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_render_md(report), encoding="utf-8")

    # Append to cumulative usage log
    _append_usage_log(project_root, report)

    return json_path, md_path


def _usage_log_path(project_root: Path) -> Path:
    return project_root / "reports" / "autopilot_usage.json"


def _append_usage_log(project_root: Path, report: dict) -> None:
    """
    Append per-task accounting entries from this run to reports/autopilot_usage.json.

    Each entry records: run metadata + per-task accounting block.
    Token counts are NOT available from the claude CLI — only char estimates.
    The structure is prepared for future exact accounting (exact_input_tokens field).
    """
    path = _usage_log_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing log
    existing: list[dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    run_meta = {
        "run_id": report.get("generated_at", _utc_now_iso()),
        "loop": report.get("loop"),
        "mode": report.get("mode"),
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "duration_sec": report.get("duration_sec"),
        "stop_reason": report.get("stop_reason"),
    }
    summary = report.get("summary") or {}

    for outcome in (report.get("task_outcomes") or []):
        acct = outcome.get("accounting") or {}
        entry: dict = {
            **run_meta,
            "task_id": outcome.get("task_id"),
            "task_title": (outcome.get("task_title") or "")[:120],
            "verdict": outcome.get("verdict"),
            "executor": outcome.get("executor") or acct.get("executor"),
            "model": outcome.get("model") or acct.get("model", "claude-sonnet-4.6"),
            "cycle_duration_sec": outcome.get("duration_sec") or acct.get("duration_sec"),
            "files_changed_count": outcome.get("files_changed_count", 0),
            "accounting_mode": acct.get("accounting_mode", "estimated_chars"),
            "estimated_prompt_chars": acct.get("estimated_prompt_chars"),
            "estimated_output_chars": acct.get("estimated_output_chars"),
            # Placeholders — will be non-None when exact token APIs are available
            "exact_input_tokens": acct.get("exact_input_tokens"),
            "exact_output_tokens": acct.get("exact_output_tokens"),
        }
        existing.append(entry)

    # Keep last 1000 entries to bound file size
    existing = existing[-1000:]
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def format_last_run_status_lines(report: Optional[dict]) -> list[str]:
    if not report:
        return ["  last_run     : not found (run loop first)"]

    s = report.get("summary") or {}
    lines = [
        f"  last_run_at  : {report.get('finished_at')}",
        f"  last_mode    : {report.get('mode')} ({report.get('loop')})",
        f"  stop_reason  : {report.get('stop_reason')}",
        (
            f"  last_counts  : cycles={s.get('cycles', 0)} accepted={s.get('accepted', 0)} "
            f"retry={s.get('retry', 0)} blocked={s.get('blocked_skip', 0)}"
        ),
        f"  files_unique : {s.get('files_changed_unique', 0)}",
    ]

    executors = s.get("executor_counts") or {}
    if executors:
        ex_str = ", ".join(f"{k}:{v}" for k, v in sorted(executors.items()))
        lines.append(f"  executors    : {ex_str}")

    wave = report.get("confidence_wave") or {}
    if wave.get("available"):
        cc = wave.get("confidence_counts") or {}
        cl = wave.get("completion_level_counts") or {}
        lines.append(f"  conf_counts  : {cc}")
        lines.append(f"  compl_levels : {cl}")

    return lines
