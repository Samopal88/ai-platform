"""One-command smoke test for the local AI Workspace backend.

Checks the core public API path:
health -> auth -> project -> chat -> message -> completion.

The script uses only the Python standard library so it can run before test
dependencies are fully installed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime


BASE_URL = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def request_json(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, object]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(BASE_URL + path, method=method, data=data, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def assert_status(label: str, got: int, expected: int, payload: object) -> None:
    if got != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {got}: {payload}")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    status, health = request_json("GET", "/health")
    assert_status("health", status, 200, health)

    status, auth = request_json(
        "POST",
        "/api/auth/guest-or-login",
        {"email": f"smoke-{stamp}@example.com", "accept_terms": True},
    )
    assert_status("auth", status, 200, auth)
    token = auth["token"]

    status, project = request_json(
        "POST",
        "/api/projects",
        {"name": f"smoke-project-{stamp}", "description": "smoke verification"},
        token=token,
    )
    assert_status("create project", status, 201, project)
    project_id = project["id"]

    status, chat = request_json(
        "POST",
        f"/api/projects/{project_id}/chats",
        {"title": "smoke-chat", "model": "gpt-4o"},
        token=token,
    )
    assert_status("create chat", status, 201, chat)
    chat_id = chat["id"]

    status, message = request_json(
        "POST",
        f"/api/chats/{chat_id}/messages",
        {"role": "user", "content": "Smoke test message"},
        token=token,
    )
    assert_status("create message", status, 201, message)

    status, completion = request_json("POST", f"/api/chats/{chat_id}/complete", {}, token=token)
    assert_status("complete chat", status, 201, completion)

    print(json.dumps({
        "ok": True,
        "health": health,
        "user_id": auth["user_id"],
        "project_id": project_id,
        "chat_id": chat_id,
        "completion_id": completion["id"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
