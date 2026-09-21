#!/usr/bin/env python3
"""Minimal smoke verification for project/personal chat endpoints."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
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


def request_json(method: str, url: str, body: dict | None = None) -> tuple[int, object]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw) if raw else {}


def main() -> int:
    global BASE_URL
    BASE_URL = ensure_fresh_base_url(BASE_URL)
    run_id = uuid.uuid4().hex[:8]

    status, project = request_json(
        "POST",
        f"{BASE_URL}/api/projects",
        {
            "name": f"smoke-chat-routes-{run_id}",
            "description": "smoke chat routes",
            "user_id": TEST_USER_ID,
        },
    )
    if status != 201:
        print(json.dumps({"ok": False, "step": "create_project", "status": status, "payload": project}, indent=2))
        return 1
    project_id = project["id"]

    status, chat = request_json(
        "POST",
        f"{BASE_URL}/api/projects/{project_id}/chats",
        {"title": "smoke chat", "model": "gpt-4o"},
    )
    if status != 201:
        print(json.dumps({"ok": False, "step": "create_project_chat", "status": status, "payload": chat}, indent=2))
        return 1
    chat_id = chat["id"]

    status, single_chat = request_json("GET", f"{BASE_URL}/api/chats/{chat_id}")
    if status != 200:
        print(json.dumps({"ok": False, "step": "get_single_chat", "status": status, "payload": single_chat}, indent=2))
        return 1

    status, message = request_json(
        "POST",
        f"{BASE_URL}/api/chats/{chat_id}/messages",
        {"role": "user", "content": "smoke message"},
    )
    if status != 201:
        print(json.dumps({"ok": False, "step": "add_message", "status": status, "payload": message}, indent=2))
        return 1

    status, nested_messages = request_json("GET", f"{BASE_URL}/api/projects/{project_id}/chats/{chat_id}/messages")
    if status != 200 or len(nested_messages) != 1:
        print(json.dumps({"ok": False, "step": "get_nested_messages", "status": status, "payload": nested_messages}, indent=2))
        return 1

    status, delete_chat_payload = request_json("DELETE", f"{BASE_URL}/api/projects/{project_id}/chats/{chat_id}")
    if status != 204:
        print(json.dumps({"ok": False, "step": "delete_project_chat", "status": status, "payload": delete_chat_payload}, indent=2))
        return 1

    status, deleted_chat = request_json("GET", f"{BASE_URL}/api/chats/{chat_id}")
    if status != 404:
        print(json.dumps({"ok": False, "step": "verify_deleted_chat", "status": status, "payload": deleted_chat}, indent=2))
        return 1

    status, personal_chat = request_json(
        "POST",
        f"{BASE_URL}/api/chats",
        {"title": "smoke personal", "model": "gpt-4o", "user_id": TEST_USER_ID},
    )
    if status != 201:
        print(json.dumps({"ok": False, "step": "create_personal_chat", "status": status, "payload": personal_chat}, indent=2))
        return 1

    status, delete_personal_payload = request_json("DELETE", f"{BASE_URL}/api/chats/{personal_chat['id']}")
    if status != 204:
        print(json.dumps({"ok": False, "step": "delete_personal_chat", "status": status, "payload": delete_personal_payload}, indent=2))
        return 1

    print(json.dumps(
        {
            "ok": True,
            "project_id": project_id,
            "deleted_project_chat_id": chat_id,
            "deleted_personal_chat_id": personal_chat["id"],
            "nested_message_ids": [item["id"] for item in nested_messages],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
