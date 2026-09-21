#!/usr/bin/env python3
"""
run_autopilot.py — Continuous safe autopilot for AI Workspace Platform.

Calls /api/manager/run-cycle-sync in a loop until no tasks remain or
Ctrl+C is pressed. Server-side /run-auto mode logs blocked tasks and skips them.

Usage:
    python scripts/run_autopilot.py
    python scripts/run_autopilot.py --base-url http://127.0.0.1:8000
    python scripts/run_autopilot.py --max-cycles 20 --pause 5
    python scripts/run_autopilot.py --mode batch  # calls /run-auto once
    python scripts/run_autopilot.py --status      # show last-run report
"""
import argparse
import json
import signal
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from autopilot_reporting import (  # noqa: E402
    build_last_run_report,
    format_last_run_status_lines,
    load_last_run_report,
    report_paths,
    save_last_run_report,
)

_stop = False


def _sig(*_):
    global _stop
    _stop = True
    print("\n[autopilot] Ctrl+C — finishing current cycle then stopping...")


signal.signal(signal.SIGINT, _sig)
signal.signal(signal.SIGTERM, _sig)


def _iso_now() -> str:
    return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post(url: str, body: dict | None = None, timeout: int = 300) -> tuple[int, dict]:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        return e.code, {"error": body_text}
    except Exception as e:
        return 0, {"error": str(e)}


def _get(url: str, timeout: int = 10) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except Exception as e:
        return 0, {"error": str(e)}


# ---------------------------------------------------------------------------
# Status output
# ---------------------------------------------------------------------------

def show_status(project_root: Path) -> None:
    report = load_last_run_report(project_root)
    json_path, md_path = report_paths(project_root)

    print(f"\n{'='*60}")
    print("  Autopilot Last Run Status")
    print(f"{'='*60}")
    for line in format_last_run_status_lines(report):
        print(line)
    print(f"  report_json  : {json_path}")
    print(f"  report_md    : {md_path}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_cycle_loop(base_url: str, max_cycles: int, pause: float) -> dict:
    """Call /run-cycle-sync in a loop. Stops on no-tasks or Ctrl+C."""
    print(f"[autopilot] Starting cycle loop → {base_url}")
    print(f"[autopilot] Max cycles: {max_cycles} | Pause between: {pause}s")
    print("[autopilot] Press Ctrl+C to stop after current cycle\n")

    cycle_url = f"{base_url}/api/manager/run-cycle-sync"

    started_at = _iso_now()
    stop_reason = "max_cycles_reached"
    last_status = None

    total = 0
    accepted = 0
    blocked_skip = 0
    retry_count = 0
    all_files: list[str] = []
    executor_counts: Counter[str] = Counter()
    outcomes: list[dict] = []

    for i in range(1, max_cycles + 1):
        if _stop:
            stop_reason = "user_interrupt"
            break

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[autopilot] [{ts}] Cycle {i}/{max_cycles} ...", end=" ", flush=True)

        status_code, result = _post(cycle_url, timeout=300)

        if status_code == 0:
            print(f"CONN ERROR: {result.get('error')}")
            print("[autopilot] Backend unreachable — stopping.")
            stop_reason = "backend_unreachable"
            break

        if status_code != 200:
            print(f"HTTP {status_code}: {result.get('error', result)}")
            stop_reason = f"http_{status_code}"
            break

        verdict = result.get("status", "?")
        last_status = verdict
        task = result.get("task") or {}
        task_id = task.get("id", "—")
        task_title = task.get("title", "")[:80]
        wr = result.get("worker_result") or {}
        executor = wr.get("executor", "?")
        files_changed = wr.get("files_changed") or []
        files_n = len(files_changed)

        total += 1
        all_files.extend(files_changed)
        executor_counts[str(executor)] += 1
        outcomes.append(
            {
                "cycle": i,
                "ts": _iso_now(),
                "task_id": task_id,
                "task_title": task_title,
                "verdict": verdict,
                "retry_count": result.get("retry_count", 0),
                "executor": executor,
                "files_changed_count": files_n,
                "files_changed": files_changed,
                "review_notes": ((result.get("review") or {}).get("notes") or "")[:240],
            }
        )

        if verdict == "idle":
            print("idle — no tasks remain.")
            print("[autopilot] Roadmap exhausted — stopping.")
            stop_reason = "roadmap_exhausted"
            break
        elif verdict == "accepted":
            accepted += 1
            print(f"accepted [{task_id}] {task_title!r} via {executor} ({files_n} files)")
        elif verdict == "blocked":
            blocked_skip += 1
            print(f"blocked  [{task_id}] {task_title!r} — logged, skipping")
        elif verdict == "retry_required":
            retry_count += 1
            print(f"retry    [{task_id}] {task_title!r} — will retry next cycle")
        else:
            print(f"{verdict} [{task_id}] {task_title!r}")

        if not _stop and i < max_cycles:
            time.sleep(pause)

    finished_at = _iso_now()
    duration_sec = round(max(0.0, datetime.fromisoformat(finished_at).timestamp() - datetime.fromisoformat(started_at).timestamp()), 2)

    print(
        f"\n[autopilot] Done. Cycles: {total} | Accepted: {accepted} | "
        f"Blocked(skip): {blocked_skip} | Retries: {retry_count}"
    )

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "stop_reason": stop_reason,
        "last_status": last_status,
        "task_outcomes": outcomes,
        "counters": {
            "cycles": total,
            "accepted": accepted,
            "blocked_skip": blocked_skip,
            "retry": retry_count,
            "files_changed_total": all_files,
            "executor_counts": dict(sorted(executor_counts.items())),
            "duration_sec": duration_sec,
        },
    }


def _extract_new_history(before: list[dict], after: list[dict]) -> list[dict]:
    before_keys = {
        (
            x.get("task_id"),
            x.get("verdict"),
            x.get("timestamp"),
            tuple(x.get("files_changed") or []),
        )
        for x in before
    }
    out = []
    for item in after:
        key = (
            item.get("task_id"),
            item.get("verdict"),
            item.get("timestamp"),
            tuple(item.get("files_changed") or []),
        )
        if key not in before_keys:
            out.append(item)
    return out


def run_batch_mode(base_url: str, max_cycles: int) -> dict:
    """Call /run-auto once with max_cycles. Polls state until idle/blocked."""
    print(f"[autopilot] Batch mode → {base_url}")
    print(f"[autopilot] Calling /api/manager/run-auto (max_cycles={max_cycles})")

    started_at = _iso_now()
    stop_reason = "unknown"
    last_status = None

    history_url = f"{base_url}/api/manager/history?limit=20"
    state_url = f"{base_url}/api/manager/state"

    _, history_before_payload = _get(history_url, timeout=10)
    history_before = history_before_payload.get("history") or []

    url = f"{base_url}/api/manager/run-auto?max_cycles={max_cycles}"
    status_code, result = _post(url, timeout=30)

    if status_code != 200 or not result.get("started"):
        print(f"Failed to start: HTTP {status_code} — {result}")
        sys.exit(1)

    print("[autopilot] Auto-run started. Polling /api/manager/state ...")

    TERMINAL = {"idle", "accepted", "blocked"}
    poll_transitions = []

    while not _stop:
        time.sleep(2)
        s_code, state = _get(state_url, timeout=10)
        if s_code != 200:
            print(f"[autopilot] State poll failed: {s_code}")
            continue

        cur = state.get("status", "?")
        if not poll_transitions or cur != poll_transitions[-1].get("status"):
            ts = datetime.now().strftime("%H:%M:%S")
            task = (state.get("current_task") or {})
            tid = task.get("id", "—")
            ttitle = task.get("title", "")[:50]
            print(f"[autopilot] [{ts}] status={cur} task=[{tid}] {ttitle!r}")
            poll_transitions.append(
                {
                    "ts": _iso_now(),
                    "status": cur,
                    "task_id": tid,
                    "task_title": ttitle,
                }
            )

        last_status = cur
        if cur in TERMINAL:
            stop_reason = f"terminal_{cur}"
            break

    if _stop and stop_reason == "unknown":
        stop_reason = "user_interrupt"

    _, history_after_payload = _get(history_url, timeout=10)
    history_after = history_after_payload.get("history") or []
    new_entries = _extract_new_history(history_before, history_after)

    counts = Counter((x.get("verdict") or "unknown") for x in new_entries)
    files_all: list[str] = []
    outcomes: list[dict] = []
    for idx, item in enumerate(new_entries, 1):
        files = item.get("files_changed") or []
        files_all.extend(files)
        outcomes.append(
            {
                "cycle": idx,
                "ts": item.get("timestamp"),
                "task_id": item.get("task_id"),
                "task_title": item.get("task_title", "")[:80],
                "verdict": item.get("verdict"),
                "retry_count": None,
                "executor": "unknown",
                "files_changed_count": len(files),
                "files_changed": files,
                "review_notes": (item.get("notes") or "")[:240],
            }
        )

    finished_at = _iso_now()
    duration_sec = round(max(0.0, datetime.fromisoformat(finished_at).timestamp() - datetime.fromisoformat(started_at).timestamp()), 2)

    print("[autopilot] Batch mode finished.")

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "stop_reason": stop_reason,
        "last_status": last_status,
        "task_outcomes": outcomes,
        "counters": {
            "cycles": len(new_entries),
            "accepted": counts.get("accepted", 0),
            "blocked_skip": counts.get("blocked", 0),
            "retry": counts.get("retry_required", 0),
            "files_changed_total": files_all,
            "executor_counts": {"unknown": len(new_entries)} if new_entries else {},
            "duration_sec": duration_sec,
        },
        "extra": {
            "poll_transitions": poll_transitions[-20:],
            "run_auto_response": result,
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Continuous autopilot for AI Workspace Platform")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--max-cycles", type=int, default=50, help="Maximum cycles to run")
    parser.add_argument("--pause", type=float, default=2.0, help="Seconds between cycles")
    parser.add_argument(
        "--mode",
        choices=["cycle", "batch"],
        default="cycle",
        help="cycle: call /run-cycle-sync in loop | batch: call /run-auto once",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show last-run report summary and exit",
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Project root path for saving/reading reports",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root)

    if args.status:
        show_status(project_root)
        return

    # Quick health check
    code, health = _get(f"{args.base_url}/health", timeout=5)
    if code != 200:
        print(f"[autopilot] ERROR: backend not reachable at {args.base_url} (HTTP {code})")
        sys.exit(1)
    print(f"[autopilot] Backend healthy: {health}")

    if args.mode == "batch":
        run = run_batch_mode(args.base_url, args.max_cycles)
        loop_name = "run_autopilot"
        mode = "http-batch"
    else:
        run = run_cycle_loop(args.base_url, args.max_cycles, args.pause)
        loop_name = "run_autopilot"
        mode = "http-cycle"

    report = build_last_run_report(
        project_root=project_root,
        loop_name=loop_name,
        mode=mode,
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        counters=run["counters"],
        stop_reason=run["stop_reason"],
        last_status=run["last_status"],
        task_outcomes=run["task_outcomes"],
        extra={
            "base_url": args.base_url,
            "mode": args.mode,
            "max_cycles": args.max_cycles,
            "pause": args.pause,
            **(run.get("extra") or {}),
        },
    )
    report_json, report_md = save_last_run_report(project_root, report)

    s = run["counters"]
    print(
        f"[autopilot] Last-run report saved: {report_json} | {report_md}\n"
        f"[autopilot] Summary → cycles={s.get('cycles', 0)} accepted={s.get('accepted', 0)} "
        f"retry={s.get('retry', 0)} blocked={s.get('blocked_skip', 0)} "
        f"stop_reason={run.get('stop_reason')}"
    )


if __name__ == "__main__":
    main()
