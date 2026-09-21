from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def request(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE_URL + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def create_reset_token(user_id: str, email: str) -> str:
    from app.core.auth_token import create_auth_token

    return create_auth_token(
        user_id,
        email,
        ttl_seconds=60 * 60,
        token_type="password_reset",
    )


stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
email = f"reset-smoke-{stamp}@example.com"
password = "StrongPass123!"
new_password = "NewStrongPass456!"

status, registered = request("POST", "/api/auth/register", {
    "email": email,
    "password": password,
    "accept_terms": True,
})
assert status == 200 and registered.get("user_id"), (status, registered)

status, forgot = request("POST", "/api/auth/forgot-password", {
    "email": email,
})
assert status == 200 and forgot.get("ok") is True, (status, forgot)

reset_token = create_reset_token(registered["user_id"], email)
status, reset = request("POST", "/api/auth/reset-password", {
    "token": reset_token,
    "password": new_password,
})
assert status == 200 and reset.get("ok") is True, (status, reset)

status, old_login = request("POST", "/api/auth/login", {
    "email": email,
    "password": password,
})
assert status == 401, (status, old_login)

status, new_login = request("POST", "/api/auth/login", {
    "email": email,
    "password": new_password,
})
assert status == 200 and new_login.get("token"), (status, new_login)

print(json.dumps({
    "ok": True,
    "base_url": BASE_URL,
    "email": email,
    "forgot": forgot,
    "reset": reset,
}, ensure_ascii=False, indent=2))
