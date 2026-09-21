#!/usr/bin/env python3
"""Smoke verification for job-status, health, and deferred memory wiring."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def ensure_fresh_base_url(base_url: str) -> str:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("ensure_backend_fresh.py")), base_url],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ensure_backend_fresh failed: {result.stdout or result.stderr}")
    payload = json.loads(result.stdout)
    return payload["base_url"]


def request_json(path: str) -> tuple[int, object]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw) if raw else {}


def main() -> int:
    global BASE_URL
    BASE_URL = ensure_fresh_base_url(BASE_URL)
    checks: list[tuple[str, bool, object]] = []

    for path in ("/health", "/api/health"):
        status, payload = request_json(path)
        ok = (
            status == 200
            and isinstance(payload, dict)
            and payload.get("status") in {"healthy", "degraded"}
            and payload.get("redis") in {"ok", "error"}
        )
        checks.append((path, ok, payload))

    status, payload = request_json("/api/job-status/fake-id")
    checks.append(("/api/job-status/fake-id", status == 404 and isinstance(payload, dict), payload))

    status, payload = request_json("/api/memory")
    checks.append(("/api/memory", status == 501 and isinstance(payload, dict) and payload.get("status") == "deferred", payload))

    result = {
        "base_url": BASE_URL,
        "checks": [
            {"path": path, "ok": ok, "payload": payload}
            for path, ok, payload in checks
        ],
    }
    print(json.dumps(result, indent=2))
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
