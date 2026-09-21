from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import Base  # noqa: E402
from app.models.chat import Chat  # noqa: E402,F401
from app.models.file import File  # noqa: E402,F401
from app.models.message import Message  # noqa: E402,F401
from app.models.project import Project  # noqa: E402,F401
from app.models.user import User  # noqa: E402,F401
from app.runtime_freshness import compute_backend_code_stamp, payload_matches_code_stamp  # noqa: E402


def request_json(url: str) -> tuple[int, object]:
    import urllib.error
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method="GET")
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw) if raw else {}
    except Exception as exc:
        return 0, {"error": str(exc)}


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_compute_backend_code_stamp_is_stable():
    stamp_a = compute_backend_code_stamp(PROJECT_ROOT)
    stamp_b = compute_backend_code_stamp(PROJECT_ROOT)
    assert stamp_a == stamp_b
    assert len(stamp_a) == 16


def test_payload_matches_code_stamp():
    assert payload_matches_code_stamp({"runtime_code_stamp": "abc"}, "abc") is True
    assert payload_matches_code_stamp({"runtime_code_stamp": "abc"}, "def") is False
    assert payload_matches_code_stamp({}, "abc") is False


def test_health_exposes_runtime_code_stamp(tmp_path):
    db_path = tmp_path / "test_runtime_freshness.db"
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
                email="freshness@example.com",
                password_hash="not-used",
                full_name="Freshness User",
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
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        status, payload = request_json(f"{base_url}/health")
        if status == 200 and isinstance(payload, dict) and "runtime_code_stamp" in payload:
            break
        time.sleep(0.2)
    else:
        process.terminate()
        process.wait(timeout=5)
        raise AssertionError("freshness health payload did not appear")

    assert payload["runtime_code_stamp"] == compute_backend_code_stamp(PROJECT_ROOT)
    assert "runtime_started_at" in payload

    process.terminate()
    process.wait(timeout=5)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
