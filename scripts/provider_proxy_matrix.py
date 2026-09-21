from __future__ import annotations

import json
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

endpoints = [
    ("routerai", env.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1"), env.get("ROUTERAI_API_KEY", "")),
    ("ruapi_official", "https://ruapi.shop/api/v1", env.get("OPENAI_API_KEY", "")),
    ("openai_proxy", env.get("OPENAI_BASE_URL", ""), env.get("OPENAI_API_KEY", "")),
    ("anthropic_proxy", env.get("ANTHROPIC_BASE_URL", ""), env.get("ANTHROPIC_API_KEY", "") or env.get("ANTHROPIC_AUTH_TOKEN", "")),
    ("claudehub_openai", "https://api.claudehub.fun/v1", env.get("CLAUDEHUB_API_KEY", "") or env.get("ANTHROPIC_API_KEY", "")),
]
models = [
    "claude-opus-4.7",
    "claude-opus-4.6",
    "claude-sonnet-4.6",
    "claude-haiku-4.5",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-7",
    "gpt-5.4",
    "gpt-5.2",
    "gpt-4.1",
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
]

results = []
for endpoint_name, base, key in endpoints:
    base = (base or "").rstrip("/")
    for model in models:
        if not base or not key:
            results.append({"endpoint": endpoint_name, "model": model, "ok": False, "skip": "missing base/key"})
            continue
        try:
            response = httpx.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Ответь одним словом: OK"}],
                    "max_tokens": 20,
                },
                timeout=60,
            )
            results.append({
                "endpoint": endpoint_name,
                "host": urlparse(base).netloc,
                "model": model,
                "ok": 200 <= response.status_code < 300,
                "status": response.status_code,
                "body_preview": response.text[:260],
            })
        except Exception as exc:
            results.append({
                "endpoint": endpoint_name,
                "host": urlparse(base).netloc,
                "model": model,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })

print(json.dumps({"ok": any(item["ok"] for item in results), "results": results}, ensure_ascii=False, indent=2))
