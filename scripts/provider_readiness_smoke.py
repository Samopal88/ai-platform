from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime


BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
STARTUP_RETRIES = int(os.environ.get("SMOKE_STARTUP_RETRIES", "15"))
STARTUP_DELAY_SECONDS = float(os.environ.get("SMOKE_STARTUP_DELAY_SECONDS", "1"))


def request_json(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE_URL + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def wait_for_health() -> None:
    last_error: Exception | None = None
    for _ in range(STARTUP_RETRIES):
        try:
            req = urllib.request.Request(BASE_URL + "/health", method="GET")
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - smoke retry path
            last_error = exc
        time.sleep(STARTUP_DELAY_SECONDS)
    raise RuntimeError(f"Health endpoint did not become ready: {last_error}")


wait_for_health()

stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
email = f"provider-readiness-{stamp}@example.com"
password = "StrongPass123"

status, auth = request_json("POST", "/api/auth/register", {
    "email": email,
    "password": password,
    "accept_terms": True,
})
assert status == 200 and auth.get("token"), (status, auth)

status, readiness = request_json("GET", "/api/system/readiness", token=auth["token"])
assert status == 200, (status, readiness)

print(json.dumps({
    "ok": True,
    "readiness": readiness,
}, ensure_ascii=False, indent=2))
