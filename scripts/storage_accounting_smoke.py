from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime


BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def request_json(method: str, path: str, body: dict | None = None, token: str | None = None):
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


def request_delete(path: str, token: str):
    req = urllib.request.Request(BASE_URL + path, method="DELETE", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as response:
        response.read()
        return response.status


def request_multipart(path: str, filename: str, content: bytes, token: str):
    boundary = "----ai-platform-storage-smoke"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/plain\r\n\r\n"
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
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw) if raw else {}


stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
email = f"storage-accounting-{stamp}@example.com"
password = "StrongPass123"
for attempt in range(3):
    status, auth = request_json("POST", "/api/auth/register", {
        "email": email,
        "password": password,
        "accept_terms": True,
    })
    if status != 429:
        break
    time.sleep(65 if attempt == 0 else 10)
assert status == 200, auth
token = auth["token"]

status, before = request_json("GET", "/api/billing/me", token=token)
assert status == 200, before
before_used = int(before["usage"]["storage_used"])

status, project = request_json("POST", "/api/projects", {"name": "Storage accounting"}, token)
assert status == 201, project
project_id = project["id"]

content = b"storage accounting smoke"
status, uploaded = request_multipart(f"/api/projects/{project_id}/files", "storage.txt", content, token)
assert status == 201, uploaded
file_id = uploaded["id"]

status, after_upload = request_json("GET", "/api/billing/me", token=token)
assert status == 200, after_upload
upload_used = int(after_upload["usage"]["storage_used"])
assert upload_used >= before_used + len(content), (before_used, upload_used, len(content))

delete_status = request_delete(f"/api/projects/{project_id}/files/{file_id}", token)
assert delete_status == 204, delete_status

status, after_delete = request_json("GET", "/api/billing/me", token=token)
assert status == 200, after_delete
delete_used = int(after_delete["usage"]["storage_used"])
assert delete_used <= upload_used - len(content), (upload_used, delete_used, len(content))

print(json.dumps({
    "ok": True,
    "before": before_used,
    "after_upload": upload_used,
    "after_delete": delete_used,
}, ensure_ascii=False, indent=2))
