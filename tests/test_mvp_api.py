"""
Integration tests for the current MVP chat/project API.

These tests start a temporary uvicorn server against a temp SQLite database and
exercise the real HTTP contract without requiring httpx.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
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
from app.api.files import upload_file as upload_project_file  # noqa: E402
from app.schemas.chat import ChatRead, MessageRead  # noqa: E402
from app.schemas.project import ProjectRead  # noqa: E402


TEST_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
SECOND_TEST_USER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
TEST_USER_EMAIL = "api-test@example.com"
SECOND_TEST_USER_EMAIL = "api-test-2@example.com"
TEST_AUTH_HEADER: dict[str, str] = {}
SECOND_TEST_AUTH_HEADER: dict[str, str] = {}


def assert_uuid_like(value: str) -> uuid.UUID:
    parsed = uuid.UUID(str(value))
    assert str(parsed) == str(value)
    return parsed


def assert_schema(model_cls, payload: dict):
    model = model_cls.model_validate(payload)
    dumped = model.model_dump(mode="json")
    assert set(dumped.keys()) == set(payload.keys())
    return model


@pytest.fixture()
def live_api(tmp_path):
    TEST_AUTH_HEADER.clear()
    SECOND_TEST_AUTH_HEADER.clear()
    db_path = tmp_path / "test_api.db"
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
                full_name="API Test User",
                plan_type="pro",
            )
        )
        db.add(
            User(
                id=SECOND_TEST_USER_ID,
                email=SECOND_TEST_USER_EMAIL,
                password_hash="not-used",
                full_name="API Test User Two",
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

    port = find_free_port()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["ANTHROPIC_API_KEY"] = ""
    env["AUTH_TOKEN_SECRET"] = TEST_AUTH_SECRET
    env["PYTHONPATH"] = (
        f"{stubs_root}:{BACKEND_ROOT}"
        if not env.get("PYTHONPATH")
        else f"{stubs_root}:{BACKEND_ROOT}:{env['PYTHONPATH']}"
    )
    log_path = tmp_path / "uvicorn_test_server.log"
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

    for email, header in (
        (TEST_USER_EMAIL, TEST_AUTH_HEADER),
        (SECOND_TEST_USER_EMAIL, SECOND_TEST_AUTH_HEADER),
    ):
        status, payload = request_json(
            "POST",
            f"{base_url}/api/auth/guest-or-login",
            {"email": email, "accept_terms": True},
        )
        if status != 200:
            raise RuntimeError(f"test authentication failed: {status} {payload}")
        header["Authorization"] = f"Bearer {payload['token']}"

    yield base_url

    process.terminate()
    process.wait(timeout=5)
    log_handle.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    method: str,
    url: str,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    data = None
    request_headers = dict(TEST_AUTH_HEADER)
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method=method, data=data, headers=request_headers)
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw) if raw else {}


def upload_multipart(url: str, filename: str, content: bytes, content_type: str = "application/octet-stream") -> tuple[int, object]:
    with tempfile.NamedTemporaryFile(
        prefix="pytest-upload-",
        suffix=Path(filename).suffix,
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--write-out",
                "\n%{http_code}",
                "-X",
                "POST",
                url,
                "-H",
                TEST_AUTH_HEADER["Authorization"],
                "-F",
                f"file=@{tmp_path};filename={filename};type={content_type}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"curl upload failed: {result.stderr.strip()}")

    body, status_text = result.stdout.rsplit("\n", 1)
    return int(status_text), json.loads(body) if body else {}


def test_mvp_api_flow_and_schema_consistency(live_api: str):
    status, projects_before = request_json("GET", f"{live_api}/api/projects?user_id={TEST_USER_ID}")
    assert status == 200
    assert projects_before == []

    project_name = f"pytest-project-{uuid.uuid4().hex[:8]}"
    status, project_payload = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": project_name,
            "description": "pytest verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201
    assert_uuid_like(project_payload["id"])
    assert_schema(ProjectRead, project_payload)
    assert project_payload["name"] == project_name
    project_id = project_payload["id"]

    status, projects_payload = request_json("GET", f"{live_api}/api/projects?user_id={TEST_USER_ID}")
    assert status == 200
    assert len(projects_payload) == 1
    for item in projects_payload:
        assert_uuid_like(item["id"])
        assert_schema(ProjectRead, item)
    assert projects_payload[0]["id"] == project_id

    chat_title = f"pytest-chat-{uuid.uuid4().hex[:8]}"
    status, chat_payload = request_json(
        "POST",
        f"{live_api}/api/projects/{project_id}/chats",
        {
            "title": chat_title,
            "model": "claude-sonnet-4-20250514",
        },
    )
    assert status == 201
    assert_uuid_like(chat_payload["id"])
    assert_uuid_like(chat_payload["project_id"])
    assert_schema(ChatRead, chat_payload)
    assert chat_payload["project_id"] == project_id
    assert chat_payload["title"] == chat_title
    chat_id = chat_payload["id"]

    status, chats_payload = request_json("GET", f"{live_api}/api/projects/{project_id}/chats")
    assert status == 200
    assert len(chats_payload) == 1
    for item in chats_payload:
        assert_uuid_like(item["id"])
        assert_uuid_like(item["project_id"])
        assert_schema(ChatRead, item)
    assert chats_payload[0]["id"] == chat_id

    user_message_text = "Hello from pytest"
    status, message_payload = request_json(
        "POST",
        f"{live_api}/api/chats/{chat_id}/messages",
        {
            "role": "user",
            "content": user_message_text,
        },
    )
    assert status == 201
    assert_uuid_like(message_payload["id"])
    assert_uuid_like(message_payload["chat_id"])
    assert_schema(MessageRead, message_payload)
    assert message_payload["role"] == "user"
    assert message_payload["content"] == user_message_text
    user_message_id = message_payload["id"]

    status, messages_payload = request_json("GET", f"{live_api}/api/chats/{chat_id}/messages")
    assert status == 200
    assert len(messages_payload) == 1
    for item in messages_payload:
        assert_uuid_like(item["id"])
        assert_uuid_like(item["chat_id"])
        assert_schema(MessageRead, item)
    assert messages_payload[0]["id"] == user_message_id

    status, complete_payload = request_json("POST", f"{live_api}/api/chats/{chat_id}/complete", {})
    assert status == 201
    assert_uuid_like(complete_payload["id"])
    assert_uuid_like(complete_payload["chat_id"])
    assert_schema(MessageRead, complete_payload)
    assert complete_payload["role"] == "assistant"
    assert complete_payload["chat_id"] == chat_id
    assert complete_payload["content"]
    assistant_message_id = complete_payload["id"]

    status, persisted_messages = request_json("GET", f"{live_api}/api/chats/{chat_id}/messages")
    assert status == 200
    assert [item["role"] for item in persisted_messages] == ["user", "assistant"]
    assert [item["id"] for item in persisted_messages] == [user_message_id, assistant_message_id]

    # Refresh persistence scenario:
    # reproduce the frontend flow after a reload using only persisted API state.
    status, refreshed_projects = request_json("GET", f"{live_api}/api/projects?user_id={TEST_USER_ID}")
    assert status == 200
    refreshed_project = next(item for item in refreshed_projects if item["id"] == project_id)
    assert_schema(ProjectRead, refreshed_project)

    status, refreshed_chats = request_json("GET", f"{live_api}/api/projects/{project_id}/chats")
    assert status == 200
    refreshed_chat = next(item for item in refreshed_chats if item["id"] == chat_id)
    assert_schema(ChatRead, refreshed_chat)

    status, refreshed_messages_payload = request_json("GET", f"{live_api}/api/chats/{chat_id}/messages")
    assert status == 200
    assert [item["id"] for item in refreshed_messages_payload] == [user_message_id, assistant_message_id]


def test_list_personal_chats_filters_by_user_id_when_requested(tmp_path):
    db_path = tmp_path / "personal_chats.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        first_chat = Chat(project_id=None, user_id=TEST_USER_ID, title="personal-a", model="gpt-4o")
        second_chat = Chat(project_id=None, user_id=SECOND_TEST_USER_ID, title="personal-b", model="gpt-4o")
        db.add_all([first_chat, second_chat])
        db.commit()

        from app.services import chat_service

        chats = chat_service.list_personal_chats(db=db, user_id=TEST_USER_ID)
        assert [chat.title for chat in chats] == ["personal-a"]
        all_chats = chat_service.list_personal_chats(db=db, user_id=None)
        assert [chat.title for chat in all_chats] == ["personal-b", "personal-a"]

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_personal_chat_api_filters_by_user_id(live_api: str):
    status, chat_a = request_json(
        "POST",
        f"{live_api}/api/chats",
        {
            "title": "personal-user-a",
            "model": "gpt-4o",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201

    status, chat_b = request_json(
        "POST",
        f"{live_api}/api/chats",
        {
            "title": "personal-user-b",
            "model": "gpt-4o",
            "user_id": str(SECOND_TEST_USER_ID),
        },
        headers=SECOND_TEST_AUTH_HEADER,
    )
    assert status == 201

    status, filtered = request_json("GET", f"{live_api}/api/chats?user_id={TEST_USER_ID}")
    assert status == 200
    assert [item["id"] for item in filtered] == [chat_a["id"]]

    status, unfiltered = request_json("GET", f"{live_api}/api/chats", headers=SECOND_TEST_AUTH_HEADER)
    assert status == 200
    assert [item["id"] for item in unfiltered] == [chat_b["id"]]


def test_patch_chat_updates_title_and_returns_chat_read(live_api: str):
    project_name = f"patch-chat-project-{uuid.uuid4().hex[:8]}"
    status, project_payload = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": project_name,
            "description": "patch verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201
    project_id = project_payload["id"]

    status, chat_payload = request_json(
        "POST",
        f"{live_api}/api/projects/{project_id}/chats",
        {
            "title": "before-patch",
            "model": "gpt-4o",
        },
    )
    assert status == 201
    chat_id = chat_payload["id"]

    status, patched = request_json(
        "PATCH",
        f"{live_api}/api/chats/{chat_id}",
        {"title": "after-patch"},
    )
    assert status == 200
    assert_schema(ChatRead, patched)
    assert patched["title"] == "after-patch"
    assert patched["id"] == chat_id

    status, fetched = request_json("GET", f"{live_api}/api/chats/{chat_id}")
    assert status == 200
    assert fetched["title"] == "after-patch"


def test_patch_chat_returns_404_for_missing_chat(live_api: str):
    missing_chat_id = uuid.uuid4()
    status, payload = request_json(
        "PATCH",
        f"{live_api}/api/chats/{missing_chat_id}",
        {"title": "missing"},
    )
    assert status == 404
    assert payload == {"detail": "Chat not found"}


def test_project_file_upload_rejects_oversized_payload_with_413(tmp_path):
    db_path = tmp_path / "upload_limit.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    class FakeUploadFile:
        filename = "too-large.bin"
        content_type = "application/octet-stream"

        def __init__(self, content: bytes):
            self._content = content

        async def read(self) -> bytes:
            return self._content

    with SessionLocal() as db:
        db.add(
            User(
                id=TEST_USER_ID,
                email="upload-limit@example.com",
                password_hash="not-used",
                full_name="Upload Limit User",
            )
        )
        project = Project(
            user_id=TEST_USER_ID,
            name="upload-limit-project",
            description="upload limit verification",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                upload_project_file(
                    project_id=project.id,
                    file=FakeUploadFile(b"x" * ((50 * 1024 * 1024) + 1)),
                    db=db,
                    current_user=db.query(User).filter(User.id == TEST_USER_ID).first(),
                )
            )

        assert exc_info.value.status_code == 413
        assert exc_info.value.detail == "Uploaded file exceeds 52428800 bytes"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_get_single_chat_by_id_returns_200_and_404(live_api: str):
    project_name = f"get-chat-project-{uuid.uuid4().hex[:8]}"
    status, project_payload = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": project_name,
            "description": "single chat verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201
    project_id = project_payload["id"]

    status, chat_payload = request_json(
        "POST",
        f"{live_api}/api/projects/{project_id}/chats",
        {
            "title": "single-chat",
            "model": "gpt-4o",
        },
    )
    assert status == 201
    chat_id = chat_payload["id"]

    status, fetched = request_json("GET", f"{live_api}/api/chats/{chat_id}")
    assert status == 200
    assert_schema(ChatRead, fetched)
    assert fetched["id"] == chat_id

    missing_chat_id = uuid.uuid4()
    status, payload = request_json("GET", f"{live_api}/api/chats/{missing_chat_id}")
    assert status == 404
    assert payload == {"detail": "Chat not found"}


def test_delete_project_chat_route_enforces_project_binding(live_api: str):
    run_id = uuid.uuid4().hex[:8]
    status, project_a = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": f"delete-chat-a-{run_id}",
            "description": "delete project chat verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201
    status, project_b = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": f"delete-chat-b-{run_id}",
            "description": "delete project chat verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201

    status, chat_payload = request_json(
        "POST",
        f"{live_api}/api/projects/{project_a['id']}/chats",
        {
            "title": "project-chat-delete",
            "model": "gpt-4o",
        },
    )
    assert status == 201
    chat_id = chat_payload["id"]

    status, payload = request_json(
        "DELETE",
        f"{live_api}/api/projects/{project_b['id']}/chats/{chat_id}",
    )
    assert status == 404
    assert payload == {"detail": "Chat not found"}

    status, payload = request_json(
        "DELETE",
        f"{live_api}/api/projects/{project_a['id']}/chats/{chat_id}",
    )
    assert status == 204
    assert payload == {}

    status, payload = request_json("GET", f"{live_api}/api/chats/{chat_id}")
    assert status == 404
    assert payload == {"detail": "Chat not found"}


def test_delete_personal_chat_route_removes_personal_chat(live_api: str):
    status, chat_payload = request_json(
        "POST",
        f"{live_api}/api/chats",
        {
            "title": "personal-chat-delete",
            "model": "gpt-4o",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201
    chat_id = chat_payload["id"]

    status, payload = request_json("DELETE", f"{live_api}/api/chats/{chat_id}")
    assert status == 204
    assert payload == {}

    status, payload = request_json("GET", f"{live_api}/api/chats/{chat_id}")
    assert status == 404
    assert payload == {"detail": "Chat not found"}


def test_nested_project_chat_messages_route_returns_messages_and_404_on_mismatch(live_api: str):
    run_id = uuid.uuid4().hex[:8]
    status, project_a = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": f"nested-msg-a-{run_id}",
            "description": "nested messages verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201
    status, project_b = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": f"nested-msg-b-{run_id}",
            "description": "nested messages verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201

    status, chat_payload = request_json(
        "POST",
        f"{live_api}/api/projects/{project_a['id']}/chats",
        {
            "title": "nested-chat",
            "model": "gpt-4o",
        },
    )
    assert status == 201
    chat_id = chat_payload["id"]

    status, first_message = request_json(
        "POST",
        f"{live_api}/api/chats/{chat_id}/messages",
        {
            "role": "user",
            "content": "nested one",
        },
    )
    assert status == 201
    status, second_message = request_json(
        "POST",
        f"{live_api}/api/chats/{chat_id}/messages",
        {
            "role": "assistant",
            "content": "nested two",
        },
    )
    assert status == 201

    status, payload = request_json(
        "GET",
        f"{live_api}/api/projects/{project_a['id']}/chats/{chat_id}/messages",
    )
    assert status == 200
    assert [item["id"] for item in payload] == [first_message["id"], second_message["id"]]

    status, payload = request_json(
        "GET",
        f"{live_api}/api/projects/{project_b['id']}/chats/{chat_id}/messages",
    )
    assert status == 404
    assert payload == {"detail": "Chat not found"}


def test_delete_project_returns_404_then_204_then_get_404(live_api: str):
    missing_project_id = uuid.uuid4()
    status, payload = request_json("DELETE", f"{live_api}/api/projects/{missing_project_id}")
    assert status == 404
    assert payload == {"detail": "Project not found"}

    project_name = f"delete-project-{uuid.uuid4().hex[:8]}"
    status, project_payload = request_json(
        "POST",
        f"{live_api}/api/projects",
        {
            "name": project_name,
            "description": "delete project verification",
            "user_id": str(TEST_USER_ID),
        },
    )
    assert status == 201
    project_id = project_payload["id"]

    status, payload = request_json("DELETE", f"{live_api}/api/projects/{project_id}")
    assert status == 204
    assert payload == {}

    status, payload = request_json("GET", f"{live_api}/api/projects/{project_id}")
    assert status == 404
    assert payload == {"detail": "Project not found"}
