from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse


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


def base_shape(value: str) -> dict:
    if not value.strip():
        return {"configured": False, "host": ""}
    parsed = urlparse(value.strip())
    return {"configured": True, "host": parsed.netloc or value.strip().split("/")[0]}


pid = find_uvicorn_pid()
env = env_for_pid(pid) if pid else os.environ
names = [
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "CLAUDEHUB_API_KEY",
    "CLAUDEHUB_BASE_URL",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "YOOKASSA_SHOP_ID",
    "YOOKASSA_SECRET_KEY",
    "SMTP_HOST",
]

result = {"pid": pid, "vars": {}}
for name in names:
    value = env.get(name, "")
    if name.endswith("BASE_URL") or name == "SMTP_HOST":
        result["vars"][name] = base_shape(value)
    else:
        result["vars"][name] = {"configured": bool(value.strip()), "len": len(value.strip())}

print(json.dumps(result, ensure_ascii=False, indent=2))
