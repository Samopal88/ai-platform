from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNTIME_MARKERS = (
    ".env",
    ".db",
    "__pycache__",
    ".pytest_cache",
    "storage/",
    "reports/",
    "logs/",
    ".runtime/",
)


def classify(path: str) -> str:
    normalized = path.replace("\\", "/")
    if any(marker in normalized for marker in RUNTIME_MARKERS):
        return "runtime_or_generated"
    if normalized.startswith(("backend/", "frontend/", "docs/", "scripts/", "tests/", "deploy/")):
        return "source_or_docs"
    return "other"


def main() -> None:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    entries = []
    counts: dict[str, int] = {}
    for line in lines:
        status = line[:2]
        path = line[3:].strip()
        kind = classify(path)
        counts[kind] = counts.get(kind, 0) + 1
        entries.append({
            "status": status,
            "path": path,
            "kind": kind,
        })

    print(json.dumps({
        "ok": True,
        "root": str(ROOT),
        "counts": counts,
        "entries": entries[:200],
        "notes": [
            "runtime_or_generated entries should stay out of commit-ready diffs where possible",
            "source_or_docs entries need intentional review before launch",
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
