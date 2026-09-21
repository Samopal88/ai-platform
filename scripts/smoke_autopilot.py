#!/usr/bin/env python3
"""
smoke_autopilot.py — Smoke verification of the autonomous manager loop.

Checks:
1. Backend is healthy
2. /api/manager/state is reachable and returns valid structure
3. manager_loop source contains ClaudeExecutor -> FileExecutor fallback markers
4. /api/manager/run-cycle-sync runs one cycle without crashing
5. Cycle returns a known verdict (accepted | retry_required | blocked | idle)
6. /api/manager/run-auto starts successfully
7. manager.py source contains blocked-skip markers for run-auto
8. Reports which executor was used (claude / file_executor / none)

Exit code 0 = all checks passed
Exit code 1 = one or more checks failed
"""
import json
import sys
from pathlib import Path
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"
if len(sys.argv) > 1:
    BASE_URL = sys.argv[1].rstrip("/")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANAGER_LOOP_FILE = PROJECT_ROOT / "backend" / "app" / "services" / "manager_loop.py"
MANAGER_API_FILE = PROJECT_ROOT / "backend" / "app" / "api" / "manager.py"

PASS = "OK"
FAIL = "FAIL"
results = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    tag = PASS if ok else FAIL
    line = f"  [{tag}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    results.append(ok)
    return ok


def _get(path: str, timeout: int = 10):
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")}
    except Exception as e:
        return 0, {"error": str(e)}


def _post(path: str, body: dict | None = None, timeout: int = 300):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")}
    except Exception as e:
        return 0, {"error": str(e)}


print(f"\nsmoke_autopilot — target: {BASE_URL}\n")

# ── Check 1: health ─────────────────────────────────────────────────────────
code, health = _get("/health")
check("backend /health reachable", code == 200, f"HTTP {code}")

# ── Check 2: manager state endpoint ────────────────────────────────────────
code, state = _get("/api/manager/state")
state_ok = code == 200 and "status" in state
check("GET /api/manager/state returns status field", state_ok,
      f"HTTP {code}, keys={list(state.keys())[:6]}")

if state_ok:
    check("state.status is a known value",
          state["status"] in ("idle", "selecting", "planning", "executing", "reviewing",
                               "accepted", "retry_required", "blocked"),
          f"status={state['status']!r}")

# ── Check 3: source-level contract for fallback wiring ─────────────────────
manager_loop_text = MANAGER_LOOP_FILE.read_text(encoding="utf-8", errors="ignore")
check(
    "manager_loop has Claude->FileExecutor fallback markers",
    "ClaudeExecutor returned unsuccessful result" in manager_loop_text and "falling back to FileExecutor" in manager_loop_text,
    str(MANAGER_LOOP_FILE),
)

# ── Check 4: run one cycle ──────────────────────────────────────────────────
print("\n  Running one cycle via /api/manager/run-cycle-sync ...")
code, cycle = _post("/api/manager/run-cycle-sync", timeout=300)
cycle_ok = code == 200 and "status" in cycle
check("POST /api/manager/run-cycle-sync HTTP 200", code == 200, f"HTTP {code}")
check("cycle response contains 'status' field", cycle_ok,
      f"keys={list(cycle.keys())[:8]}")

if cycle_ok:
    verdict = cycle.get("status", "?")
    KNOWN_VERDICTS = {"accepted", "retry_required", "blocked", "idle"}
    check(f"cycle verdict is known ({verdict!r})", verdict in KNOWN_VERDICTS,
          f"verdict={verdict!r}")

    # Report executor used
    executor_used = (cycle.get("worker_result") or {}).get("executor", "unknown")
    task = cycle.get("task") or {}
    task_id = task.get("id", "—")
    task_title = (task.get("title") or "")[:60]

    print(f"\n  Cycle details:")
    print(f"    verdict   : {verdict}")
    print(f"    task_id   : {task_id}")
    print(f"    task_title: {task_title!r}")
    print(f"    executor  : {executor_used}")
    files_changed = (cycle.get("worker_result") or {}).get("files_changed") or []
    print(f"    files_chg : {len(files_changed)}")

# ── Check 6: run-auto starts ────────────────────────────────────────────────
code, run_auto = _post("/api/manager/run-auto?max_cycles=1", timeout=30)
check("POST /api/manager/run-auto starts", code == 200 and run_auto.get("started") is True,
      f"HTTP {code}, payload_keys={list(run_auto.keys())[:6]}")

# ── Check 7: source-level contract for blocked skip logic ──────────────────
manager_api_text = MANAGER_API_FILE.read_text(encoding="utf-8", errors="ignore")
check(
    "run-auto contains blocked-skip markers",
    "preflight-blocked, skipping to next" in manager_api_text and "blocked, skipping to next" in manager_api_text,
    str(MANAGER_API_FILE),
)

# ── Summary ─────────────────────────────────────────────────────────────────
total = len(results)
passed = sum(results)
failed = total - passed
print(f"\n{'='*50}")
print(f"Result: {passed}/{total} checks passed")
if failed:
    print("SOME CHECKS FAILED — see FAIL lines above")
else:
    print("ALL CHECKS PASSED")
print(f"{'='*50}\n")

sys.exit(0 if failed == 0 else 1)
