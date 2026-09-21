from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def find_uvicorn_pid() -> int | None:
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="ignore")
        except OSError:
            continue
        if "uvicorn" in cmdline and "app.main:app" in cmdline:
            return int(proc.name)
    return None


def env_for_pid(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    values: dict[str, str] = {}
    for item in raw:
        if b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        values[key.decode("utf-8", errors="ignore")] = value.decode("utf-8", errors="ignore")
    return values


pid = find_uvicorn_pid()
if pid:
    os.environ.update(env_for_pid(pid))

from app.services.model_router import ModelRouter


router = ModelRouter()
models = ["gpt-5.4", "claude-opus-4.7", "gemini-3.1-pro-preview"]
results = []
for model in models:
    try:
        text = router.route([{"role": "user", "content": "Ответь одним словом: OK"}], model, max_tokens=20)
        results.append({
            "model": model,
            "ok": bool(text.strip()) and "Не удалось получить ответ" not in text,
            "answer_preview": text[:200],
        })
    except Exception as exc:
        results.append({"model": model, "ok": False, "error": f"{type(exc).__name__}: {exc}"})

print(json.dumps({"ok": all(item["ok"] for item in results), "results": results}, ensure_ascii=False, indent=2))
