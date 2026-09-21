"""
Sprint runner glue for manager dashboard.

Executes a bounded autonomous sprint using existing continuous-loop logic and
writes the standard last-run report files.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _ensure_scripts_on_path(project_root: Path) -> None:
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def run_sprint(
    project_root: Path,
    max_cycles: int = 50,
    pause: float = 0.5,
    stop_on_mvp_block: bool = True,
) -> dict[str, Any]:
    """
    Run a bounded sprint and persist report artifacts.

    Returns a summary including saved report paths.
    """
    root = Path(project_root)
    _ensure_scripts_on_path(root)

    from run_continuous import run_loop  # type: ignore[import]
    from autopilot_reporting import (  # type: ignore[import]
        build_last_run_report,
        save_last_run_report,
    )

    run = run_loop(
        project_root=root,
        max_cycles=max_cycles,
        pause=pause,
        stop_on_mvp_block=stop_on_mvp_block,
    )

    report = build_last_run_report(
        project_root=root,
        loop_name="run_sprint",
        mode="sprint",
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        counters=run["counters"],
        stop_reason=run["stop_reason"],
        last_status=run["last_status"],
        task_outcomes=run["task_outcomes"],
        extra={
            "max_cycles": max_cycles,
            "pause": pause,
            "stop_on_mvp_block": stop_on_mvp_block,
        },
    )
    report_json, report_md = save_last_run_report(root, report)

    return {
        "status": "finished",
        "mode": "sprint",
        "report_json": str(report_json),
        "report_md": str(report_md),
        "stop_reason": run["stop_reason"],
        "counters": run["counters"],
    }

