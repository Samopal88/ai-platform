"""
Verification tests for project instructions behavior.

These tests start a temporary uvicorn server against a temp SQLite database and
exercise the real HTTP contract around project instructions without relying on
the deployed environment.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
TEST_AUTH_SECRET = "pytest-auth-secret-that-is-long-enough-for-tests"
os.environ["AUTH_TOKEN_SECRET"] = TEST_AUTH_SECRET

from app.db.base import Base  # noqa: E402
from app.models.chat import Chat  # noqa: E402,F401
from app.models.message import Message  # noqa: E402,F401
from app.models.project import Project  # noqa: E402,F401
from app.models.user import User  # noqa: E402


TEST_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
TEST_USER_EMAIL = "instructions-test@example.com"
TEST_AUTH_HEADER: dict[str, str] = {}
PROJECT_KEYS_WITH_INSTRUCTIONS = {
    "id",
    "name",
    "description",
    "instructions",
    "created_at",
    "updated_at",
    "chat_count",
    "file_count",
    "storage_used",
    "last_message_at",
}


def assert_uuid_like(value: str) -> uuid.UUID:
    parsed = uuid.UUID(str(value))
    assert str(parsed) == str(value)
    return parsed


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(method: str, url: str, body: dict | None = None) -> tuple[int, object]:
    data = None
    headers = dict(TEST_AUTH_HEADER)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with opener.open(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def request_json_allow_error(
    method: str,
    url: str,
    body: dict | None = None,
) -> tuple[int, object]:
    try:
        return request_json(method, url, body)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        parsed = json.loads(payload) if payload else {}
        return exc.code, parsed


@pytest.fixture()
def live_api(tmp_path):
    TEST_AUTH_HEADER.clear()
    db_path = tmp_path / "test_instructions_api.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        db.add(
            User(
                id=TEST_USER_ID,
                email=TEST_USER_EMAIL,
                password_hash="not-used",
                full_name="Instructions Test User",
                plan_type="pro",
            )
        )
        db.commit()

    stubs_root = tmp_path / "stubs"
    multipart_dir = stubs_root / "multipart"
    multipart_dir.mkdir(parents=True, exist_ok=True)
    (multipart_dir / "__init__.py").write_text('__version__ = "0.0-test"\n', encoding="utf-8")
    (multipart_dir / "multipart.py").write_text(
        "def parse_options_header(value):\n"
        "    return value, {}\n",
        encoding="utf-8",
    )

    anthropic_dir = stubs_root / "anthropic"
    anthropic_dir.mkdir(parents=True, exist_ok=True)
    (anthropic_dir / "__init__.py").write_text(
        "import json\n"
        "\n"
        "class _Content:\n"
        "    def __init__(self, text):\n"
        "        self.text = text\n"
        "\n"
        "class _Response:\n"
        "    def __init__(self, text):\n"
        "        self.content = [_Content(text)]\n"
        "\n"
        "class _Messages:\n"
        "    def create(self, **kwargs):\n"
        "        system = kwargs.get('system')\n"
        "        messages = kwargs.get('messages', [])\n"
        "        payload = {'system': system, 'messages': messages}\n"
        "        return _Response(json.dumps(payload, sort_keys=True))\n"
        "\n"
        "class Anthropic:\n"
        "    def __init__(self, api_key):\n"
        "        self.api_key = api_key\n"
        "        self.messages = _Messages()\n",
        encoding="utf-8",
    )

    httpx_dir = stubs_root / "httpx"
    httpx_dir.mkdir(parents=True, exist_ok=True)
    (httpx_dir / "__init__.py").write_text(
        "import json as _json\n"
        "class _Response:\n"
        "    def __init__(self, payload): self._payload = payload\n"
        "    def raise_for_status(self): return None\n"
        "    def json(self):\n"
        "        return {'content': [{'type': 'text', 'text': _json.dumps(self._payload, sort_keys=True)}], 'usage': {}}\n"
        "def post(url, json=None, headers=None, timeout=None):\n"
        "    return _Response(json or {})\n",
        encoding="utf-8",
    )

    port = find_free_port()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["ANTHROPIC_API_KEY"] = "instructions-test-key"
    env["AUTH_TOKEN_SECRET"] = TEST_AUTH_SECRET
    env["PYTHONPATH"] = (
        f"{stubs_root}:{BACKEND_ROOT}"
        if not env.get("PYTHONPATH")
        else f"{stubs_root}:{BACKEND_ROOT}:{env['PYTHONPATH']}"
    )
    log_path = tmp_path / "uvicorn_instructions_test_server.log"
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
    health_ok = False
    while time.time() < deadline:
        try:
            status, payload = request_json("GET", f"{base_url}/health")
            if status == 200 and payload.get("status") in {"healthy", "degraded"}:
                health_ok = True
                break
        except Exception:
            time.sleep(0.1)

    if not health_ok:
        process.terminate()
        process.wait(timeout=5)
        log_handle.close()
        raise RuntimeError(
            "temporary uvicorn test server did not become healthy: "
            f"{log_path.read_text(encoding='utf-8', errors='ignore')}"
        )

    status, payload = request_json_allow_error(
        "POST",
        f"{base_url}/api/auth/guest-or-login",
        {"email": TEST_USER_EMAIL, "accept_terms": True},
    )
    if status != 200:
        raise RuntimeError(f"test authentication failed: {status} {payload}")
    TEST_AUTH_HEADER["Authorization"] = f"Bearer {payload['token']}"

    yield base_url

    process.terminate()
    process.wait(timeout=5)
    log_handle.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_project(base_url: str, name: str, instructions: str) -> dict:
    status, payload = request_json_allow_error(
        "POST",
        f"{base_url}/api/projects",
        {
            "name": name,
            "description": "instructions verification",
            "instructions": instructions,
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201, payload
    assert_uuid_like(payload["id"])
    return payload


def test_create_project_persists_instructions(live_api: str):
    instructions = "Always answer tersely."
    project = create_project(live_api, f"instructions-create-{uuid.uuid4().hex[:8]}", instructions)

    assert set(project.keys()) == PROJECT_KEYS_WITH_INSTRUCTIONS, (
        "POST /api/projects should expose an instructions field on create response; "
        f"got keys {sorted(project.keys())}"
    )
    assert project["instructions"] == instructions


def test_fetch_project_again_returns_same_instructions(live_api: str):
    instructions = "Use markdown tables when helpful."
    created = create_project(live_api, f"instructions-fetch-{uuid.uuid4().hex[:8]}", instructions)

    status, fetched = request_json_allow_error("GET", f"{live_api}/api/projects/{created['id']}")
    assert status == 200, fetched
    assert set(fetched.keys()) == PROJECT_KEYS_WITH_INSTRUCTIONS, (
        "GET /api/projects/{project_id} should expose an instructions field; "
        f"got keys {sorted(fetched.keys())}"
    )
    assert fetched["instructions"] == instructions


def test_update_project_overwrites_instructions(live_api: str):
    original = "Start every answer with ORIGINAL."
    updated = "Start every answer with UPDATED."
    created = create_project(live_api, f"instructions-update-{uuid.uuid4().hex[:8]}", original)

    status, update_payload = request_json_allow_error(
        "PUT",
        f"{live_api}/api/projects/{created['id']}",
        {"instructions": updated},
    )
    assert status == 200, update_payload
    assert set(update_payload.keys()) == PROJECT_KEYS_WITH_INSTRUCTIONS, (
        "PUT /api/projects/{project_id} should expose an instructions field; "
        f"got keys {sorted(update_payload.keys())}"
    )
    assert update_payload["instructions"] == updated

    status, fetched = request_json_allow_error("GET", f"{live_api}/api/projects/{created['id']}")
    assert status == 200, fetched
    assert fetched["instructions"] == updated


def test_different_projects_keep_different_instructions(live_api: str):
    project_a = create_project(
        live_api,
        f"instructions-a-{uuid.uuid4().hex[:8]}",
        "Reply in exactly one sentence.",
    )
    project_b = create_project(
        live_api,
        f"instructions-b-{uuid.uuid4().hex[:8]}",
        "Reply in exactly two sentences.",
    )

    status_a, fetched_a = request_json_allow_error("GET", f"{live_api}/api/projects/{project_a['id']}")
    status_b, fetched_b = request_json_allow_error("GET", f"{live_api}/api/projects/{project_b['id']}")
    assert status_a == 200, fetched_a
    assert status_b == 200, fetched_b
    assert fetched_a["instructions"] != fetched_b["instructions"]
    assert fetched_a["instructions"] == "Reply in exactly one sentence."
    assert fetched_b["instructions"] == "Reply in exactly two sentences."


def test_completion_uses_project_instructions_when_present(live_api: str):
    instructions = "You must include the token PROJECT-INSTRUCTIONS-APPLIED."
    project = create_project(
        live_api,
        f"instructions-complete-{uuid.uuid4().hex[:8]}",
        instructions,
    )

    status, chat = request_json(
        "POST",
        f"{live_api}/api/projects/{project['id']}/chats",
        {
            "title": "instructions completion verification",
            "model": "claude-sonnet-4-20250514",
        },
    )
    assert status == 201

    status, _ = request_json(
        "POST",
        f"{live_api}/api/chats/{chat['id']}/messages",
        {
            "role": "user",
            "content": "Say hello.",
        },
    )
    assert status == 201

    status, completion = request_json("POST", f"{live_api}/api/chats/{chat['id']}/complete", {})
    assert status == 201
    content = completion["content"]

    try:
        routed_payload = json.loads(content)
    except json.JSONDecodeError as exc:
        pytest.fail(
            "POST /api/chats/{chat_id}/complete did not return the anthropic stub payload, "
            f"so instruction forwarding could not be verified: {exc}; content={content!r}"
        )

    assert instructions in (routed_payload.get("system") or ""), (
        "POST /api/chats/{chat_id}/complete should forward project instructions as the system prompt; "
        f"observed system={routed_payload.get('system')!r}"
    )
