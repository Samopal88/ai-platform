from __future__ import annotations

import json
from pathlib import Path

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
key = env.get("ANTHROPIC_AUTH_TOKEN", "") or env.get("CLAUDEHUB_API_KEY", "") or env.get("ANTHROPIC_API_KEY", "")
base = (env.get("ANTHROPIC_BASE_URL", "") or "https://api.claudehub.fun").rstrip("/")

models = ["claude-haiku-4.5", "claude-sonnet-4.6", "claude-opus-4.7"]
results = []
for model in models:
    if not key:
        results.append({"model": model, "ok": False, "error": "missing key"})
        continue
    try:
        response = httpx.post(
            f"{base}/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 20,
                "messages": [{"role": "user", "content": "Ответь одним словом: OK"}],
            },
            timeout=60,
        )
        results.append({
            "model": model,
            "ok": 200 <= response.status_code < 300,
            "status": response.status_code,
            "body_preview": response.text[:400],
        })
    except Exception as exc:
        results.append({"model": model, "ok": False, "error": f"{type(exc).__name__}: {exc}"})

print(json.dumps({"ok": any(item["ok"] for item in results), "results": results}, ensure_ascii=False, indent=2))
