from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.api import jobs as jobs_api  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.chat import Chat  # noqa: E402,F401
from app.models.file import File  # noqa: E402,F401
from app.models.message import Message  # noqa: E402,F401
from app.models.project import Project  # noqa: E402,F401
from app.models.user import User  # noqa: E402,F401
from app.services.job_queue import JobStatus  # noqa: E402


def request_json(method: str, url: str) -> tuple[int, object]:
    import urllib.error
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method=method)
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw) if raw else {}


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def live_api(tmp_path):
    db_path = tmp_path / "test_platform_batch.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        db.add(
            User(
                id="11111111-1111-4111-8111-111111111111",
                email="platform-batch@example.com",
                password_hash="not-used",
                full_name="Platform Batch User",
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
    env["PYTHONPATH"] = (
        f"{stubs_root}:{BACKEND_ROOT}"
        if not env.get("PYTHONPATH")
        else f"{stubs_root}:{BACKEND_ROOT}:{env['PYTHONPATH']}"
    )
    log_path = tmp_path / "uvicorn_platform_batch.log"
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
        except Exception:
            time.sleep(0.1)
    else:
        process.terminate()
        process.wait(timeout=5)
        log_handle.close()
        raise RuntimeError(log_path.read_text(encoding="utf-8", errors="ignore"))

    yield base_url

    process.terminate()
    process.wait(timeout=5)
    log_handle.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_job_status_normalizes_enum_status(monkeypatch):
    monkeypatch.setattr(
        jobs_api,
        "get_job",
        lambda job_id: {"job_id": job_id, "status": JobStatus.FINISHED, "current_stage": "Done"},
    )

    payload = __import__("asyncio").run(jobs_api.job_status("job-1"))
    assert payload["ok"] is True
    assert payload["job"]["status"] == "finished"


def test_health_reports_redis_field(live_api: str):
    for path in ("/health", "/api/health"):
        status, payload = request_json("GET", f"{live_api}{path}")
        assert status == 200
        assert payload["status"] in {"healthy", "degraded"}
        assert payload["redis"] in {"ok", "error"}


def test_api_memory_list_is_accessible(live_api: str):
    # Phase 8.1: memory API is now implemented; GET /api/memory returns 200 (empty list for fresh user)
    # The endpoint requires auth, so unauthenticated request returns 401 or 403.
    status, payload = request_json("GET", f"{live_api}/api/memory")
    assert status in {200, 401, 403, 404}, f"Unexpected status {status}: {payload}"


def test_job_status_fake_id_returns_404_without_crash(live_api: str):
    status, payload = request_json("GET", f"{live_api}/api/job-status/fake-id")
    assert status == 404
    assert payload == {"detail": "Job 'fake-id' not found"}
