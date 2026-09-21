"""
Integration tests for project-scoped file management.

Covers:
  POST   /api/projects/{project_id}/files              — upload
  GET    /api/projects/{project_id}/files              — list + persistence
  GET    /api/projects/{project_id}/files/{id}/download — download
  DELETE /api/projects/{project_id}/files/{id}         — delete

All tests run against the active localhost backend.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
TEST_USER_EMAIL = "project-files-api-test@example.com"
AUTH_HEADER: dict[str, str] = {}

FILE_KEYS = {"id", "project_id", "filename", "size", "mime_type", "created_at"}
FILE_LIST_KEYS = {"files", "total"}

DOWNLOAD_ROUTE_PATH = "/api/projects/{project_id}/files/{file_id}/download"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_uuid_like(value: str) -> uuid.UUID:
    parsed = uuid.UUID(str(value))
    assert str(parsed) == str(value), f"not a canonical UUID: {value!r}"
    return parsed


def assert_exact_keys(payload: dict, expected_keys: set[str]) -> None:
    assert set(payload.keys()) == expected_keys, (
        f"expected keys {sorted(expected_keys)}, got {sorted(payload.keys())}"
    )


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(method: str, url: str, body: dict | None = None) -> tuple[int, object]:
    data = None
    headers: dict[str, str] = dict(AUTH_HEADER)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with opener.open(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw else None
        return exc.code, payload


def request_raw(method: str, url: str) -> tuple[int, bytes, dict[str, str]]:
    """Return (status, body_bytes, lowercase-keyed headers) without JSON parsing."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, method=method, headers=dict(AUTH_HEADER))
    try:
        with opener.open(req, timeout=30) as response:
            return response.status, response.read(), {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), {k.lower(): v for k, v in exc.headers.items()}


def upload_multipart(url: str, filename: str, content: bytes, content_type: str = "text/plain") -> tuple[int, dict]:
    with tempfile.NamedTemporaryFile(
        prefix="pytest-upload-", suffix=Path(filename).suffix, delete=False
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "curl", "--silent", "--show-error",
                "--write-out", "\n%{http_code}",
                "-X", "POST", url,
                "-H", f"Authorization: {AUTH_HEADER.get('Authorization', '')}",
                "-F", f"file=@{tmp_path};filename={filename};type={content_type}",
            ],
            check=False, capture_output=True, text=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"curl upload failed: {result.stderr.strip()}")

    body, status_text = result.stdout.rsplit("\n", 1)
    return int(status_text), json.loads(body)


def create_project(base_url: str, name: str) -> dict:
    status, payload = request_json(
        "POST",
        f"{base_url}/api/projects",
        {"name": name, "description": "pytest file verification", "user_id": TEST_USER_ID},
    )
    assert status == 201, f"create project failed: {status} {payload}"
    return payload


def ensure_auth(base_url: str) -> None:
    if AUTH_HEADER.get("Authorization"):
        return
    status, payload = request_json(
        "POST",
        f"{base_url}/api/auth/guest-or-login",
        {"email": TEST_USER_EMAIL, "accept_terms": True},
    )
    assert status == 200, f"auth failed: {status} {payload}"
    AUTH_HEADER["Authorization"] = f"Bearer {payload['token']}"


def delete_project(base_url: str, project_id: str) -> None:
    status, _ = request_json("DELETE", f"{base_url}/api/projects/{project_id}")
    assert status == 204, f"delete project returned {status}"


def list_files(base_url: str, project_id: str) -> dict:
    status, payload = request_json("GET", f"{base_url}/api/projects/{project_id}/files")
    assert status == 200, f"list files returned {status}: {payload}"
    return payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_api(tmp_path_factory):
    """Start an isolated backend instead of depending on localhost:8000."""
    runtime_dir = tmp_path_factory.mktemp("project_files_api")
    db_path = runtime_dir / "project_files.db"
    port = find_free_port()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PROJECT_ROOT"] = str(PROJECT_ROOT)
    env["ANTHROPIC_API_KEY"] = ""
    env["AUTH_TOKEN_SECRET"] = "pytest-project-files-auth-secret-long-enough"
    env["PYTHONPATH"] = (
        str(BACKEND_ROOT)
        if not env.get("PYTHONPATH")
        else f"{BACKEND_ROOT}{os.pathsep}{env['PYTHONPATH']}"
    )
    log_path = runtime_dir / "uvicorn.log"
    log_handle = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log_handle,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            status, payload = request_json("GET", f"{base_url}/health")
            if status == 200 and isinstance(payload, dict) and "status" in payload:
                break
        except urllib.error.URLError:
            time.sleep(0.1)
    else:
        process.terminate()
        process.wait(timeout=5)
        log_handle.close()
        raise RuntimeError(log_path.read_text(encoding="utf-8", errors="ignore"))

    ensure_auth(base_url)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE users SET plan_type = 'pro' WHERE email = ?",
            (TEST_USER_EMAIL,),
        )
        connection.commit()
    yield base_url

    process.terminate()
    process.wait(timeout=5)
    log_handle.close()


@pytest.fixture()
def project_pair(live_api):
    """Create two isolated projects; delete both after the test."""
    run = uuid.uuid4().hex[:8]
    proj_a = create_project(live_api, f"pytest-a-{run}")
    proj_b = create_project(live_api, f"pytest-b-{run}")
    yield live_api, proj_a["id"], proj_b["id"]
    # Cleanup — ignore errors; project may already be gone
    for pid in (proj_a["id"], proj_b["id"]):
        try:
            delete_project(live_api, pid)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUpload:
    def test_upload_returns_201_and_file_shape(self, project_pair):
        base, pa, _ = project_pair
        content = b"hello pytest upload"
        status, payload = upload_multipart(
            f"{base}/api/projects/{pa}/files",
            filename="upload_test.txt",
            content=content,
        )
        assert status == 201
        assert_exact_keys(payload, FILE_KEYS)
        assert_uuid_like(payload["id"])
        assert_uuid_like(payload["project_id"])
        assert payload["project_id"] == pa
        assert payload["filename"] == "upload_test.txt"
        assert payload["size"] == len(content)
        assert payload["mime_type"] is not None

    def test_upload_id_is_stable_across_calls(self, project_pair):
        """Two uploads of different content get different stable IDs."""
        base, pa, _ = project_pair
        _, p1 = upload_multipart(f"{base}/api/projects/{pa}/files", "f1.txt", b"aaa")
        _, p2 = upload_multipart(f"{base}/api/projects/{pa}/files", "f2.txt", b"bbb")
        assert p1["id"] != p2["id"]
        # IDs survive a fresh fetch
        listed = list_files(base, pa)
        listed_ids = {f["id"] for f in listed["files"]}
        assert p1["id"] in listed_ids
        assert p2["id"] in listed_ids

    def test_upload_empty_file_rejected(self, project_pair):
        base, pa, _ = project_pair
        status, payload = upload_multipart(
            f"{base}/api/projects/{pa}/files",
            filename="empty.txt",
            content=b"",
        )
        assert status == 400

    def test_upload_too_large_file_rejected_with_413(self, project_pair):
        base, pa, _ = project_pair
        content = b"x" * ((50 * 1024 * 1024) + 1)
        status, payload = upload_multipart(
            f"{base}/api/projects/{pa}/files",
            filename="too-large.bin",
            content=content,
            content_type="application/octet-stream",
        )
        assert status == 413
        assert payload["detail"] == "Uploaded file exceeds 52428800 bytes"


class TestList:
    def test_fresh_project_has_empty_file_list(self, project_pair):
        base, pa, _ = project_pair
        result = list_files(base, pa)
        assert_exact_keys(result, FILE_LIST_KEYS)
        assert result == {"files": [], "total": 0}

    def test_list_shows_uploaded_file(self, project_pair):
        base, pa, _ = project_pair
        content = b"list test content"
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "listed.txt", content
        )
        file_id = uploaded["id"]

        result = list_files(base, pa)
        assert result["total"] == 1
        assert result["files"][0]["id"] == file_id
        assert result["files"][0]["filename"] == "listed.txt"
        assert result["files"][0]["project_id"] == pa

    def test_list_response_file_items_have_correct_keys(self, project_pair):
        base, pa, _ = project_pair
        upload_multipart(f"{base}/api/projects/{pa}/files", "keys.txt", b"keys test")
        result = list_files(base, pa)
        for item in result["files"]:
            assert_exact_keys(item, FILE_KEYS)

    def test_persistence_second_fetch_returns_same_data(self, project_pair):
        """A file present in the first list must appear in a fresh second fetch."""
        base, pa, _ = project_pair
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "persist.txt", b"persistence check"
        )
        file_id = uploaded["id"]

        first = list_files(base, pa)
        second = list_files(base, pa)

        assert first["total"] == second["total"] == 1
        assert [f["id"] for f in first["files"]] == [f["id"] for f in second["files"]] == [file_id]

    def test_file_belongs_to_correct_project(self, project_pair):
        """File uploaded to project A does not appear in project B's list."""
        base, pa, pb = project_pair
        upload_multipart(f"{base}/api/projects/{pa}/files", "scoped.txt", b"scope test")

        b_files = list_files(base, pb)
        assert b_files == {"files": [], "total": 0}


class TestDownload:
    def test_download_returns_200_and_correct_content(self, project_pair):
        base, pa, _ = project_pair
        content = b"download test payload"
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "dl.txt", content
        )
        file_id = uploaded["id"]

        status, body, headers = request_raw(
            "GET", f"{base}/api/projects/{pa}/files/{file_id}/download"
        )
        assert status == 200, f"download returned {status}: {body[:200]}"
        assert body == content

    def test_download_sets_content_disposition_attachment(self, project_pair):
        base, pa, _ = project_pair
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "named.txt", b"disposition test"
        )
        file_id = uploaded["id"]

        status, _, headers = request_raw(
            "GET", f"{base}/api/projects/{pa}/files/{file_id}/download"
        )
        assert status == 200
        cd = headers.get("content-disposition", "")
        assert "attachment" in cd.lower(), f"expected attachment disposition, got: {cd!r}"

    def test_download_content_type_matches_upload(self, project_pair):
        base, pa, _ = project_pair
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "typed.txt", b"ct test",
            content_type="text/plain",
        )
        file_id = uploaded["id"]

        status, _, headers = request_raw(
            "GET", f"{base}/api/projects/{pa}/files/{file_id}/download"
        )
        assert status == 200
        ct = headers.get("content-type", "")
        assert "text/plain" in ct, f"expected text/plain content-type, got: {ct!r}"

    def test_download_wrong_project_returns_404(self, project_pair):
        """File ID is project-scoped; fetching via the wrong project returns 404."""
        base, pa, pb = project_pair
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "scoped_dl.txt", b"scope dl test"
        )
        file_id = uploaded["id"]

        status, _, _ = request_raw(
            "GET", f"{base}/api/projects/{pb}/files/{file_id}/download"
        )
        assert status == 404

    def test_download_nonexistent_file_returns_404(self, project_pair):
        base, pa, _ = project_pair
        fake_id = str(uuid.uuid4())
        status, _, _ = request_raw(
            "GET", f"{base}/api/projects/{pa}/files/{fake_id}/download"
        )
        assert status == 404

    def test_download_route_registered_in_openapi(self, live_api):
        status, payload = request_json("GET", f"{live_api}/api/openapi.json")
        assert status == 200
        paths = set(payload["paths"].keys())
        assert "/api/projects/{project_id}/files/{file_id}/download" in paths, (
            f"download route missing from OpenAPI spec. Present paths: {sorted(p for p in paths if 'file' in p)}"
        )


class TestDelete:
    def test_delete_returns_204(self, project_pair):
        base, pa, _ = project_pair
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "del.txt", b"delete me"
        )
        file_id = uploaded["id"]

        status, _, _ = request_raw("DELETE", f"{base}/api/projects/{pa}/files/{file_id}")
        assert status == 204

    def test_deleted_file_absent_from_list(self, project_pair):
        base, pa, _ = project_pair
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "gone.txt", b"going away"
        )
        file_id = uploaded["id"]

        request_raw("DELETE", f"{base}/api/projects/{pa}/files/{file_id}")

        after = list_files(base, pa)
        assert after == {"files": [], "total": 0}

    def test_deleted_file_download_returns_404(self, project_pair):
        base, pa, _ = project_pair
        _, uploaded = upload_multipart(
            f"{base}/api/projects/{pa}/files", "gone_dl.txt", b"will be deleted"
        )
        file_id = uploaded["id"]

        request_raw("DELETE", f"{base}/api/projects/{pa}/files/{file_id}")

        status, _, _ = request_raw(
            "GET", f"{base}/api/projects/{pa}/files/{file_id}/download"
        )
        assert status == 404

    def test_delete_nonexistent_returns_404(self, project_pair):
        base, pa, _ = project_pair
        fake_id = str(uuid.uuid4())
        status, _, _ = request_raw("DELETE", f"{base}/api/projects/{pa}/files/{fake_id}")
        assert status == 404

    def test_deleting_file_in_a_does_not_affect_project_b(self, project_pair):
        """Cross-project isolation: deleting a file in A must not touch B's files."""
        base, pa, pb = project_pair
        content = b"isolation check"

        _, fa = upload_multipart(f"{base}/api/projects/{pa}/files", "fa.txt", content)
        _, fb = upload_multipart(f"{base}/api/projects/{pb}/files", "fb.txt", content)

        # Delete A's file
        request_raw("DELETE", f"{base}/api/projects/{pa}/files/{fa['id']}")

        # A should be empty
        a_files = list_files(base, pa)
        assert a_files == {"files": [], "total": 0}

        # B should still have its file
        b_files = list_files(base, pb)
        assert b_files["total"] == 1
        assert b_files["files"][0]["id"] == fb["id"]
