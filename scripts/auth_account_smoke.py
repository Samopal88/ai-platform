from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime


BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


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


stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
email = f"surface-{stamp}@example.com"
password = "StrongPass123"

status, guest = request("POST", "/api/auth/guest", {})
assert status == 200 and guest.get("token"), guest

status, registered = request("POST", "/api/auth/register", {
    "email": email,
    "password": password,
    "accept_terms": True,
})
assert status == 200 and registered.get("token"), registered

status, login = request("POST", "/api/auth/login", {
    "email": email,
    "password": password,
})
assert status == 200 and login.get("token"), login

status, billing = request("GET", "/api/billing/me", token=login["token"])
assert status == 200 and billing.get("plan"), billing

print(json.dumps({
    "ok": True,
    "base_url": BASE_URL,
    "guest": bool(guest.get("token")),
    "email": email,
    "plan": billing["plan"]["code"],
}, ensure_ascii=False, indent=2))
