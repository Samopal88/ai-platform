from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


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
            return response.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


status, raw = request("POST", "/api/auth/guest", {})
assert status == 200, (status, raw)
token = json.loads(raw)["token"]

html_checks = [
    ("/chat", "2026-04-30-auth-qa-hardening-1"),
    ("/chat", "forgotPasswordBtn"),
    ("/chat", "accountModeNote"),
    ("/chat", "audioFileInput"),
    ("/chat", "model-menu-empty"),
    ("/chat", "YooKassa"),
    ("/documentation", "release-readiness"),
    ("/docs-public/getting-started", "Гостевой режим"),
    ("/docs-public/models", "DeepSeek Reasoner"),
    ("/docs-public/image-generation", "демо-режиме"),
    ("/docs-public/speech-to-text", "Распознать аудио"),
]

for path, needle in html_checks:
    status, raw = request("GET", path)
    assert status == 200, (path, status, raw[:200])
    assert needle in raw, (path, needle)

for path in ["/api/models", "/api/plans", "/api/billing/me"]:
    status, raw = request("GET", path, token=token if path.endswith("/me") else None)
    assert status == 200, (path, status, raw[:200])

status, raw = request("POST", "/api/media/images", {"prompt": "test"}, token)
assert status == 503, (status, raw)

print(json.dumps({"ok": True, "base_url": BASE_URL, "checks": len(html_checks)}, ensure_ascii=False, indent=2))
