#!/usr/bin/env python3
"""
run_continuous.py — Standalone continuous autopilot for AI Workspace Platform.

Runs manager_loop cycles directly (no HTTP server required).
Handles blocked → skip → continue automatically.
Recovery/critical blocked tasks stop the loop.

Usage:
    cd /opt/ai-workspace/storage/projects/ai-platform
    python scripts/run_continuous.py
    python scripts/run_continuous.py --max-cycles 10 --pause 1
    python scripts/run_continuous.py --status        # show current + last-run state only
"""
import argparse
import signal
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from autopilot_reporting import (  # noqa: E402
    format_last_run_status_lines,
    load_last_run_report,
    report_paths,
    save_last_run_report,
    build_last_run_report,
)

_stop = False


def _sig(*_):
    global _stop
    _stop = True
    print("\n[continuous] Ctrl+C — finishing current cycle then stopping...")


signal.signal(signal.SIGINT, _sig)
signal.signal(signal.SIGTERM, _sig)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _iso_now() -> str:
    return datetime.now().isoformat()


def show_status(project_root: Path) -> None:
    """Print human-readable current state + last run report summary."""
    from app.services.manager_loop import get_manager_state
    from app.services.manager_human_status import build_human_status

    s = get_manager_state(project_root)
    hs = build_human_status(project_root)
    last_report = load_last_run_report(project_root)
    json_path, md_path = report_paths(project_root)

    print(f"\n{'='*60}")
    print(f"  Manager State — {_ts()}")
    print(f"{'='*60}")
    print(f"  status       : {s.get('status')}")
    print(f"  retry_count  : {s.get('retry_count', 0)} / {s.get('max_retries', 2)}")
    t = s.get("current_task") or {}
    if t:
        print(f"  task         : [{t.get('id', '?')}] {t.get('title', '')[:60]}")
    wr = s.get("worker_result") or {}
    if wr:
        print(f"  executor     : {wr.get('executor', '?')}")
        print(f"  files_changed: {wr.get('files_changed', [])}")
    r = s.get("review") or {}
    if r:
        print(f"  verdict      : {r.get('verdict', '?')}")
        print(f"  notes        : {(r.get('notes') or '')[:100]}")

    print(f"\n  human_summary : {hs.get('summary', '')[:100]}")

    print("\n  Last Run Report:")
    for line in format_last_run_status_lines(last_report):
        print(line)
    print(f"  report_json  : {json_path}")
    print(f"  report_md    : {md_path}")

    hist = s.get("history") or []
    if hist:
        print(f"\n  Last {min(5, len(hist))} outcomes:")
        for h in hist[-5:]:
            fc = h.get("files_changed") or []
            print(
                f"    [{h.get('verdict','?'):12s}] {h.get('task_id','?'):10s} "
                f"{h.get('task_title','')[:40]} ({len(fc)} files)"
            )
    print(f"{'='*60}\n")


def _load_sprint_config(project_root: Path) -> dict:
    """Load sprint limits from autopilot_config.json. Returns safe defaults if missing."""
    cfg_path = project_root / "docs" / "progress" / "autopilot_config.json"
    try:
        import json as _json
        cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
        return cfg.get("sprint") or {}
    except Exception:
        return {}


def run_loop(
    project_root: Path,
    max_cycles: int,
    pause: float,
    stop_on_mvp_block: bool = True,
    executor_timeout: int = 300,
) -> dict:
    """
    Run manager cycles continuously.

    Reads sprint limits (max_time_minutes, max_blocked, executor_timeout_seconds)
    from docs/progress/autopilot_config.json sprint section.

    Returns summary dict with counts + stop metadata + task outcomes.
    """
    from app.services.manager_loop import (
        get_manager_state,
        run_manager_cycle,
        reset_manager_state,
        sync_completed_recovery_tasks,
    )
    from app.services.task_intake import choose_next_task

    # SP-4: load sprint limits from config
    sprint_cfg = _load_sprint_config(project_root)
    max_time_sec = (sprint_cfg.get("max_time_minutes") or 0) * 60
    max_blocked = sprint_cfg.get("max_blocked") or 0
    cfg_executor_timeout = sprint_cfg.get("executor_timeout_seconds") or executor_timeout
    effective_executor_timeout = cfg_executor_timeout

    started_at = _iso_now()
    loop_start_ts = time.time()
    stop_reason = "max_cycles_reached"
    last_status = None
    task_outcomes: list[dict] = []

    counters = {
        "cycles": 0,
        "accepted": 0,
        "blocked_skip": 0,
        "retry": 0,
        "mvp_stop": False,
        "files_changed_total": [],
        "executor_counts": {},
        "duration_sec": 0,
    }
    executor_counts: Counter[str] = Counter()

    print(f"\n[continuous] Starting — max_cycles={max_cycles}, pause={pause}s")
    print(f"[continuous] project_root={project_root}")
    if max_time_sec:
        print(f"[continuous] Sprint limit: max_time={sprint_cfg.get('max_time_minutes')}min, max_blocked={max_blocked or 'unlimited'}, executor_timeout={effective_executor_timeout}s")
    print("[continuous] Press Ctrl+C to stop after current cycle\n")

    # Pre-flight sync
    sync_result = sync_completed_recovery_tasks(project_root)
    if sync_result.get("changes"):
        print(f"[continuous] State sync: {sync_result['changes']}")

    # Reset if stuck in a terminal/broken state from previous runs
    s = get_manager_state(project_root)
    if s.get("status") in ("retry_required", "blocked") and s.get("retry_count", 0) >= s.get("max_retries", 2):
        print("[continuous] Previous cycle exhausted retries — resetting to idle")
        reset_manager_state(project_root)

    for i in range(1, max_cycles + 1):
        if _stop:
            stop_reason = "user_interrupt"
            break

        # SP-4: wall-clock time limit
        if max_time_sec and (time.time() - loop_start_ts) >= max_time_sec:
            stop_reason = "time_limit_reached"
            print(f"[continuous] Time limit reached ({sprint_cfg.get('max_time_minutes')}min) — stopping.")
            break

        # SP-4: max-blocked stop
        if max_blocked and counters["blocked_skip"] >= max_blocked:
            stop_reason = "max_blocked_reached"
            print(f"[continuous] Max blocked ({max_blocked}) reached — stopping.")
            break

        # Sync before each cycle
        sync_completed_recovery_tasks(project_root)

        # Check tasks remain
        task = choose_next_task()
        if not task:
            print(f"[continuous] [{_ts()}] No actionable tasks — roadmap exhausted.")
            stop_reason = "roadmap_exhausted"
            break

        tid = task.get("id", "?")
        ttitle = task.get("title", "")[:50]
        is_recovery = task.get("_is_mvp_recovery", False)

        print(f"[continuous] [{_ts()}] Cycle {i}/{max_cycles} — [{tid}] {ttitle!r}", end=" ", flush=True)

        cycle_start_ts = time.time()

        # Run one cycle
        try:
            state = run_manager_cycle(project_root=project_root, executor_timeout=effective_executor_timeout)
        except Exception as e:
            print(f"ERROR: {e}")
            stop_reason = "cycle_exception"
            break

        verdict = state.get("status", "?")
        last_status = verdict
        wr = state.get("worker_result") or {}
        review = state.get("review") or {}
        files_changed = wr.get("files_changed") or []
        executor = wr.get("executor", "?")
        executor_counts[str(executor)] += 1
        counters["cycles"] += 1
        cycle_duration_sec = round(time.time() - cycle_start_ts, 2)

        outcome = {
            "cycle": i,
            "ts": _iso_now(),
            "task_id": tid,
            "task_title": task.get("title", "")[:120],
            "verdict": verdict,
            "retry_count": state.get("retry_count", 0),
            "executor": executor,
            "model": wr.get("model", "claude-sonnet-4.6"),  # estimated if not provided
            "duration_sec": cycle_duration_sec,
            "files_changed_count": len(files_changed),
            "files_changed": files_changed,
            "review_notes": (review.get("notes") or "")[:240],
            # Estimated accounting — claude CLI does not expose exact token counts.
            # We store prompt/output char lengths as a lower-bound proxy.
            "accounting": {
                "accounting_mode": "estimated_chars",  # not exact tokens
                "executor": executor,
                "model": wr.get("model", "claude-sonnet-4.6"),
                "duration_sec": cycle_duration_sec,
                "estimated_prompt_chars": len(state.get("current_step") or ""),
                "estimated_output_chars": len(wr.get("output") or ""),
                "exact_input_tokens": None,   # not available from claude CLI
                "exact_output_tokens": None,  # not available from claude CLI
            },
        }
        task_outcomes.append(outcome)

        if verdict == "accepted":
            counters["accepted"] += 1
            counters["files_changed_total"].extend(files_changed)
            print(f"→ accepted via {executor} ({len(files_changed)} files)")
        elif verdict == "blocked":
            # Distinguish recovery-critical blocks from ordinary blocks
            if is_recovery and stop_on_mvp_block:
                counters["mvp_stop"] = True
                stop_reason = "mvp_critical_block"
                print(f"→ BLOCKED (MVP-critical [{tid}]) — stopping loop")
                print(f"  reason: {(state.get('review') or {}).get('notes', '')[:150]}")
                break
            else:
                counters["blocked_skip"] += 1
                print("→ blocked — skipping")
                reset_manager_state(project_root)
        elif verdict == "retry_required":
            counters["retry"] += 1
            retry_n = state.get("retry_count", 0)
            max_r = state.get("max_retries", 2)
            print(f"→ retry {retry_n}/{max_r}")
            # Let the next cycle handle the retry (state preserved)
        elif verdict == "idle":
            print("→ idle — no tasks remain")
            stop_reason = "idle_no_tasks"
            break
        else:
            print(f"→ {verdict}")

        if not _stop and i < max_cycles:
            time.sleep(pause)

    if _stop and stop_reason == "max_cycles_reached":
        stop_reason = "user_interrupt"

    finished_at = _iso_now()
    counters["duration_sec"] = round(max(0.0, datetime.fromisoformat(finished_at).timestamp() - datetime.fromisoformat(started_at).timestamp()), 2)
    counters["executor_counts"] = dict(sorted(executor_counts.items()))

    return {
        "counters": counters,
        "started_at": started_at,
        "finished_at": finished_at,
        "stop_reason": stop_reason,
        "last_status": last_status,
        "task_outcomes": task_outcomes,
    }


def print_summary(counters: dict, stop_reason: str, last_status: str | None, report_json: Path, report_md: Path) -> None:
    files = counters.get("files_changed_total", [])
    print(f"\n{'='*60}")
    print("  Continuous loop complete")
    print(f"  Cycles run    : {counters['cycles']}")
    print(f"  Accepted      : {counters['accepted']}")
    print(f"  Blocked(skip) : {counters['blocked_skip']}")
    print(f"  Retries       : {counters['retry']}")
    print(f"  Last status   : {last_status}")
    print(f"  Stop reason   : {stop_reason}")
    print(f"  Files changed : {len(files)}")
    print(f"  Executors     : {counters.get('executor_counts', {})}")
    print(f"  Report JSON   : {report_json}")
    print(f"  Report MD     : {report_md}")
    if files:
        for f in sorted(set(files)):
            print(f"    + {f}")
    if counters.get("mvp_stop"):
        print("  *** Stopped on MVP-critical block ***")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Continuous standalone autopilot for AI Workspace Platform"
    )
    parser.add_argument(
        "--max-cycles", type=int, default=20,
        help="Maximum cycles to run (default 20)",
    )
    parser.add_argument(
        "--pause", type=float, default=1.0,
        help="Seconds between cycles (default 1)",
    )
    parser.add_argument(
        "--project-root", default=str(PROJECT_ROOT),
        help="Project root path",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current manager + last run report state and exit",
    )
    parser.add_argument(
        "--no-mvp-stop", action="store_true",
        help="Do NOT stop on MVP-critical blocks (skip them too)",
    )
    args = parser.parse_args()

    root = Path(args.project_root)

    if args.status:
        show_status(root)
        return

    run = run_loop(
        project_root=root,
        max_cycles=args.max_cycles,
        pause=args.pause,
        stop_on_mvp_block=not args.no_mvp_stop,
    )
    counters = run["counters"]

    report = build_last_run_report(
        project_root=root,
        loop_name="run_continuous",
        mode="continuous",
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        counters=counters,
        stop_reason=run["stop_reason"],
        last_status=run["last_status"],
        task_outcomes=run["task_outcomes"],
        extra={
            "max_cycles": args.max_cycles,
            "pause": args.pause,
            "stop_on_mvp_block": not args.no_mvp_stop,
        },
    )
    report_json, report_md = save_last_run_report(root, report)

    print_summary(
        counters=counters,
        stop_reason=run["stop_reason"],
        last_status=run["last_status"],
        report_json=report_json,
        report_md=report_md,
    )


if __name__ == "__main__":
    main()
