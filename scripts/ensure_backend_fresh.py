#!/usr/bin/env python3
"""Ensure smoke checks run against a fresh managed backend runtime."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
STATE_FILE = RUNTIME_DIR / "managed_backend.json"
LOG_FILE = RUNTIME_DIR / "managed_backend.log"

sys.path.insert(0, str(BACKEND_ROOT))

from app.runtime_freshness import compute_backend_code_stamp, payload_matches_code_stamp  # noqa: E402


def request_health(base_url: str) -> tuple[int, object]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(f"{base_url}/health", method="GET")
    try:
        with opener.open(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw) if raw else {}
    except Exception as exc:
        return 0, {"error": str(exc)}


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_managed_backend(state: dict) -> None:
    pid = state.get("pid")
    if not pid or not pid_running(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 10
    while time.time() < deadline:
        if not pid_running(pid):
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_managed_backend(port: int) -> dict:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(BACKEND_ROOT)
        if not env.get("PYTHONPATH")
        else f"{BACKEND_ROOT}:{env['PYTHONPATH']}"
    )
    log_handle = open(LOG_FILE, "a", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_ROOT),
        env=env,
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
    )
    state = {
        "pid": process.pid,
        "port": port,
        "base_url": f"http://127.0.0.1:{port}",
        "log_file": str(LOG_FILE),
    }
    save_state(state)
    return state


def wait_for_fresh_runtime(base_url: str, expected_stamp: str, timeout: int = 30) -> tuple[bool, object]:
    deadline = time.time() + timeout
    last_payload: object = {}
    while time.time() < deadline:
        status, payload = request_health(base_url)
        last_payload = payload
        if status == 200 and payload_matches_code_stamp(payload, expected_stamp):
            return True, payload
        time.sleep(0.5)
    return False, last_payload


def main() -> int:
    preferred_base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    expected_stamp = compute_backend_code_stamp(PROJECT_ROOT)

    status, payload = request_health(preferred_base_url)
    if status == 200 and payload_matches_code_stamp(payload, expected_stamp):
        print(json.dumps({
            "ok": True,
            "fresh": True,
            "base_url": preferred_base_url,
            "source": "preferred_runtime",
            "runtime_code_stamp": payload.get("runtime_code_stamp"),
        }))
        return 0

    state = load_state()
    managed_url = state.get("base_url")
    if managed_url:
        status, payload = request_health(managed_url)
        if status == 200 and payload_matches_code_stamp(payload, expected_stamp):
            print(json.dumps({
                "ok": True,
                "fresh": True,
                "base_url": managed_url,
                "source": "managed_runtime_reused",
                "runtime_code_stamp": payload.get("runtime_code_stamp"),
            }))
            return 0

    if state:
        stop_managed_backend(state)

    port = find_free_port()
    state = start_managed_backend(port)
    fresh, payload = wait_for_fresh_runtime(state["base_url"], expected_stamp)
    if not fresh:
        print(json.dumps({
            "ok": False,
            "base_url": state["base_url"],
            "source": "managed_runtime_started",
            "runtime_code_stamp": getattr(payload, "get", lambda *_: None)("runtime_code_stamp"),
            "expected_code_stamp": expected_stamp,
            "payload": payload,
            "log_file": state["log_file"],
        }, indent=2))
        return 1

    print(json.dumps({
        "ok": True,
        "fresh": True,
        "base_url": state["base_url"],
        "source": "managed_runtime_started",
        "runtime_code_stamp": payload.get("runtime_code_stamp"),
        "expected_code_stamp": expected_stamp,
        "log_file": state["log_file"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
