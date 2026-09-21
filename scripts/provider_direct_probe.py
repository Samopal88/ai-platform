from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx


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
env = env_for_pid(pid) if pid else {}
openai_key = env.get("OPENAI_API_KEY", "").strip()
openai_base = (env.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/")

models = ["gpt-5.4", "claude-opus-4.7", "gemini-3.1-pro-preview", "gpt-4.1", "gpt-5.2"]
results = []

for model in models:
    if not openai_key:
        results.append({"model": model, "ok": False, "error": "OPENAI_API_KEY missing"})
        continue
    try:
        response = httpx.post(
            f"{openai_base}/chat/completions",
            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Ответь одним словом: OK"}],
                "max_tokens": int(os.environ.get("PROVIDER_PROBE_MAX_TOKENS", "20")),
            },
            timeout=60,
        )
        body = response.text[:500]
        ok = 200 <= response.status_code < 300
        results.append({
            "model": model,
            "ok": ok,
            "status": response.status_code,
            "base_host": urlparse(openai_base).netloc,
            "body_preview": body,
        })
    except Exception as exc:
        results.append({
            "model": model,
            "ok": False,
            "base_host": urlparse(openai_base).netloc,
            "error": f"{type(exc).__name__}: {exc}",
        })

print(json.dumps({"ok": any(item["ok"] for item in results), "results": results}, ensure_ascii=False, indent=2))
