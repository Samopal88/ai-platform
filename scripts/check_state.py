#!/usr/bin/env python3
"""
State consistency checker for AI Workspace Platform.

Checks:
  1. orchestrator_state.json status vs active jobs in storage/jobs/
  2. chatgpt_executor_state.json current_task vs orchestrator current_task
  3. Whether CURRENT_STATUS.md reflects the latest finished job

Usage:
    python3 scripts/check_state.py
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PROGRESS = PROJECT_ROOT / "docs" / "progress"
JOBS_DIR = PROJECT_ROOT / "storage" / "jobs"

issues = []
ok_count = 0


def read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            issues.append(f"Cannot parse {path.name}: {e}")
    return {}


def check(label: str, condition: bool, detail: str = ""):
    global ok_count
    if condition:
        ok_count += 1
        print(f"  OK  {label}")
    else:
        issues.append(f"{label}: {detail}" if detail else label)
        print(f"  !!  {label}" + (f" — {detail}" if detail else ""))


# --- Load state files ---
orch = read_json(PROGRESS / "orchestrator_state.json")
chatgpt = read_json(PROGRESS / "chatgpt_executor_state.json")
state = read_json(PROGRESS / "state.json")

# --- Load jobs ---
jobs = []
if JOBS_DIR.exists():
    for jf in JOBS_DIR.glob("*.json"):
        try:
            jobs.append(json.loads(jf.read_text(encoding="utf-8")))
        except Exception:
            pass

active_jobs = [j for j in jobs if j.get("status") in ("queued", "started", "in_progress")]
finished_jobs = sorted(
    [j for j in jobs if j.get("status") == "finished"],
    key=lambda j: j.get("finished_at", ""),
    reverse=True
)

print("\n=== State Consistency Check ===\n")

# 1. Orchestrator status vs active jobs
orch_status = orch.get("status", "idle")
if orch_status in ("running", "executing", "step_executing"):
    check(
        "Orchestrator status matches active jobs",
        len(active_jobs) > 0,
        f"orchestrator says '{orch_status}' but no active jobs found"
    )
else:
    check(
        "Orchestrator idle when no active jobs",
        len(active_jobs) == 0 or orch_status not in ("idle",),
        ""
    )

# 2. chatgpt_executor current_task vs orchestrator current_task
cg_task = chatgpt.get("current_task")
orch_task = orch.get("current_task")
if cg_task and orch_task:
    check(
        "chatgpt_executor and orchestrator agree on current_task",
        cg_task == orch_task or cg_task in orch_task or orch_task in cg_task,
        f"chatgpt='{str(cg_task)[:60]}' orch='{str(orch_task)[:60]}'"
    )
elif cg_task and not active_jobs:
    issues.append(
        f"chatgpt_executor has stale current_task '{str(cg_task)[:60]}' but no active jobs"
    )
    print(f"  !!  chatgpt_executor has stale current_task — '{str(cg_task)[:60]}'")
else:
    ok_count += 1
    print("  OK  chatgpt_executor current_task state consistent")

# 3. CURRENT_STATUS.md reflects latest finished job
status_file = PROGRESS / "CURRENT_STATUS.md"
if not status_file.exists():
    issues.append("CURRENT_STATUS.md does not exist")
    print("  !!  CURRENT_STATUS.md missing")
elif finished_jobs:
    latest_job_id = finished_jobs[0].get("job_id", "")
    content = status_file.read_text(encoding="utf-8")
    check(
        "CURRENT_STATUS.md references latest finished job",
        latest_job_id in content,
        f"latest job_id '{latest_job_id}' not found in CURRENT_STATUS.md"
    )
else:
    ok_count += 1
    print("  OK  No finished jobs yet, CURRENT_STATUS.md check skipped")

# 4. No stale blocked_tasks overflow (should be ≤20 after trim)
blocked = orch.get("blocked_tasks", [])
check(
    "orchestrator_state blocked_tasks within 20-entry limit",
    len(blocked) <= 20,
    f"found {len(blocked)} entries (should be ≤20)"
)

completed = orch.get("completed_tasks", [])
check(
    "orchestrator_state completed_tasks within 20-entry limit",
    len(completed) <= 20,
    f"found {len(completed)} entries (should be ≤20)"
)

# --- Summary ---
print(f"\n{'='*34}")
if issues:
    print(f"ISSUES ({len(issues)}):")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
    sys.exit(1)
else:
    print(f"All {ok_count} checks passed — state is consistent.")
    sys.exit(0)
