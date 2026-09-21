from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


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


def request_multipart(path: str, field_name: str, filename: str, content: bytes, token: str):
    boundary = "----ai-platform-smoke-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        method="POST",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def create_account(prefix: str):
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    email = f"{prefix}-{stamp}@example.com"
    password = "StrongPass123"
    for attempt in range(3):
        status, payload = request_json("POST", "/api/auth/register", {
            "email": email,
            "password": password,
            "accept_terms": True,
        })
        if status != 429:
            break
        time.sleep(65 if attempt == 0 else 10)
    assert status == 200, (status, payload)
    return email, payload["token"]


def seed_token_usage(email: str, tokens: int) -> None:
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="ignore")
        except OSError:
            continue
        if "uvicorn" in cmdline and "app.main:app" in cmdline:
            raw_env = (proc / "environ").read_bytes().split(b"\0")
            for item in raw_env:
                if b"=" in item:
                    key, value = item.split(b"=", 1)
                    if key == b"DATABASE_URL":
                        os.environ["DATABASE_URL"] = value.decode("utf-8", errors="ignore")
            try:
                os.chdir((proc / "cwd").resolve())
            except OSError:
                os.chdir(BACKEND)
            break
    else:
        os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    from app.db.session import SessionLocal
    from app.models.user import User
    from app.services.usage_service import record_usage

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None, email
        record_usage(
            db,
            user=user,
            operation="smoke_token_seed",
            tokens_input=tokens,
            tokens_output=0,
        )
    finally:
        db.close()


email, token = create_account("negative-limit")
status, first_project = request_json("POST", "/api/projects", {"name": "One"}, token)
assert status == 201, (status, first_project)
status, second_project = request_json("POST", "/api/projects", {"name": "Two"}, token)
assert status == 402, (status, second_project)

project_id = first_project["id"]
chunk = b"x" * (26 * 1024 * 1024)
status, upload_one = request_multipart(f"/api/projects/{project_id}/files", "file", "one.bin", chunk, token)
assert status == 201, (status, upload_one)
status, upload_two = request_multipart(f"/api/projects/{project_id}/files", "file", "two.bin", chunk, token)
assert status == 402, (status, upload_two)

seed_token_usage(email, 49_950)
status, chat = request_json("POST", "/api/chats", {"title": "Token limit", "model": "claude-haiku-4.5"}, token)
assert status == 201, (status, chat)
chat_id = chat["id"]
status, _ = request_json("POST", f"/api/chats/{chat_id}/messages", {"role": "user", "content": "x" * 2000}, token)
assert status == 201, (status, _)
status, completion = request_json("POST", f"/api/chats/{chat_id}/complete", {}, token)
assert status == 402, (status, completion)

print(json.dumps({
    "ok": True,
    "project_limit": second_project,
    "storage_limit": upload_two,
    "token_limit": completion,
}, ensure_ascii=False, indent=2))
