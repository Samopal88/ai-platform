#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"

echo "=== HUMAN STATUS REPORT ==="
echo

echo "[1] Health"
curl -s "$BASE_URL/health" | python3 - <<'PY'
import json, sys
d = json.load(sys.stdin)
print(f"Backend: {d.get('status', 'unknown')}")
print(f"Service: {d.get('service', 'unknown')}")
print(f"Time: {d.get('timestamp', 'unknown')}")
PY
echo

echo "[2] Next task"
curl -s "$BASE_URL/api/manager/next-task" | python3 - <<'PY'
import json, sys
d = json.load(sys.stdin)
task = d.get("task")
if not task:
    print("Next task: none")
    print("Meaning: no actionable tasks found")
else:
    print(f"ID: {task.get('id')}")
    print(f"Title: {task.get('title')}")
    print(f"Phase: {task.get('phase')}")
    print(f"Files: {', '.join(task.get('files', [])) or 'none'}")
    print(f"Why: {task.get('why', '')}")
PY
echo

echo "[3] Current manager state"
curl -s "$BASE_URL/api/manager/state" | python3 - <<'PY'
import json, sys
d = json.load(sys.stdin)

print(f"Manager status: {d.get('status', 'unknown')}")
task = d.get("current_task")
if task:
    print(f"Current task: {task.get('id')} — {task.get('title')}")
else:
    print("Current task: none")

review = d.get("review") or {}
if review:
    print(f"Last verdict: {review.get('verdict', 'unknown')}")
    notes = review.get("notes", "")
    if notes:
        print(f"Reason: {notes}")

worker = d.get("worker_result") or {}
files = worker.get("files_changed") or []
print(f"Files changed by worker: {', '.join(files) if files else 'none'}")

print(f"Retry count: {d.get('retry_count', 0)} / {d.get('max_retries', 0)}")

accepted = d.get("accepted_tasks") or []
blocked = d.get("blocked_tasks") or []
print(f"Accepted tasks total: {len(accepted)}")
print(f"Blocked tasks total: {len(blocked)}")
PY
echo

echo "[4] Plain English summary"
curl -s "$BASE_URL/api/manager/state" | python3 - <<'PY'
import json, sys
d = json.load(sys.stdin)
status = d.get("status")
task = d.get("current_task") or {}
review = d.get("review") or {}
worker = d.get("worker_result") or {}

if status == "accepted":
    print("Summary: the last task was accepted.")
elif status == "retry_required":
    print("Summary: the last task failed review and must be retried.")
elif status == "blocked":
    print("Summary: the task is blocked.")
elif status == "idle":
    print("Summary: manager is idle.")
else:
    print(f"Summary: manager status is {status}.")

if task:
    print(f"Task in focus: {task.get('id')} — {task.get('title')}")

notes = review.get("notes")
if notes:
    print(f"Main problem: {notes}")

files = worker.get("files_changed") or []
if files:
    print("Worker touched these files:")
    for f in files:
        print(f"  - {f}")
else:
    print("Worker did not report file changes.")

print()
print("Recommended next action:")
if status == "retry_required":
    print("  1. Do NOT run auto mode.")
    print("  2. Fix the manager prompt/task builder.")
    print("  3. Re-run one cycle only after the prompt bug is fixed.")
elif status == "accepted":
    print("  1. Inspect the changed target file.")
    print("  2. If it looks real, run the next single cycle.")
    print("  3. Do not enable long auto-run yet.")
elif status == "blocked":
    print("  1. Inspect the blocker.")
    print("  2. Create or select a repair task.")
else:
    print("  1. Check the next task.")
    print("  2. Run only one cycle at a time.")
PY
