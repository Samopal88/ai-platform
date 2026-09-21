"""Helpers for backend runtime freshness detection."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def iter_backend_code_files(project_root: Path) -> Iterable[Path]:
    backend_app = project_root / "backend" / "app"
    return sorted(path for path in backend_app.rglob("*.py") if path.is_file())


def compute_backend_code_stamp(project_root: Path) -> str:
    digest = hashlib.sha256()
    for path in iter_backend_code_files(project_root):
        stat = path.stat()
        digest.update(str(path.relative_to(project_root)).encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))
    return digest.hexdigest()[:16]


def payload_matches_code_stamp(payload: object, expected_stamp: str) -> bool:
    return isinstance(payload, dict) and payload.get("runtime_code_stamp") == expected_stamp
