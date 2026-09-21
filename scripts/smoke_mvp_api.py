"""Minimal smoke verification for the local MVP API."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


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


@dataclass
class Check:
    name: str
    ok: bool
    endpoint: str
    detail: str


@dataclass
class Audit:
    passes: list[Check] = field(default_factory=list)
    failures: list[Check] = field(default_factory=list)

    def record(self, name: str, endpoint: str, detail: str, ok: bool) -> None:
        item = Check(name=name, endpoint=endpoint, detail=detail, ok=ok)
        if ok:
            self.passes.append(item)
        else:
            self.failures.append(item)


def request_json(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with opener.open(request, timeout=60) as response:
        status = response.status
        raw = response.read().decode("utf-8")
        return status, json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    base_url = ensure_fresh_base_url(args.base_url.rstrip("/"))
    audit = Audit()

    try:
        status, payload = request_json("GET", f"{base_url}/health")
        if status != 200:
            raise AssertionError(f"expected 200, got {status}")
        if not isinstance(payload, dict) or payload.get("status") not in {"healthy", "degraded"}:
            raise AssertionError(f"unexpected health payload: {payload}")
        audit.record("GET /health", "/health", json.dumps(payload, ensure_ascii=False), True)

        project_list_url = f"{base_url}/api/projects?user_id={urllib.parse.quote(TEST_USER_ID)}"
        status, projects = request_json("GET", project_list_url)
        if status != 200:
            raise AssertionError(f"expected 200, got {status}")
        if not isinstance(projects, list):
            raise AssertionError(f"expected list payload, got {type(projects).__name__}")
        audit.record("GET /api/projects", "/api/projects", f"count={len(projects)}", True)

    except Exception as exc:
        failing_endpoint = audit.failures[-1].endpoint if audit.failures else "unknown"
        audit.record("Smoke run", failing_endpoint, str(exc), False)

    report = {
        "passes": [check.__dict__ for check in audit.passes],
        "failures": [check.__dict__ for check in audit.failures],
    }
    print(json.dumps(report, indent=2))
    return 0 if not audit.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
