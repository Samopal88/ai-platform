from __future__ import annotations

import re
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"
KEY_PATH = ROOT / "scripts" / ".claudehub_key_upload.txt"


def parse_key(raw: str) -> str:
    try:
        data = json.loads(raw)
        providers = data.get("provider") or {}
        for provider in providers.values():
            options = provider.get("options") if isinstance(provider, dict) else None
            if isinstance(options, dict):
                api_key = str(options.get("apiKey") or "").strip()
                if api_key:
                    return api_key
    except Exception:
        pass

    candidates: list[str] = []
    for line in raw.splitlines():
        value = line.strip()
        if not value:
            continue
        if "=" in value:
            name, candidate = value.split("=", 1)
            if name.strip() in {"CLAUDEHUB_API_KEY", "API_KEY", "ANTHROPIC_API_KEY"}:
                value = candidate
        elif ":" in value:
            _, candidate = value.split(":", 1)
            value = candidate
        value = value.strip().strip(",").strip('"').strip("'")
        candidates.extend(re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{20,}", value))
        if len(value) >= 20 and " " not in value and not value.startswith(("http://", "https://")):
            candidates.append(value)
    if candidates:
        return max(candidates, key=len)
    raise SystemExit("No key found")


key = parse_key(KEY_PATH.read_text(encoding="utf-8-sig"))
lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
updates = {
    "CLAUDEHUB_API_KEY": key,
    "CLAUDEHUB_BASE_URL": "https://api.claudehub.fun/v1",
    "ANTHROPIC_AUTH_TOKEN": key,
    "ANTHROPIC_BASE_URL": "https://api.claudehub.fun",
}

seen = set()
next_lines = []
for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        next_lines.append(line)
        continue
    name = line.split("=", 1)[0].strip()
    if name in updates:
        next_lines.append(f"{name}={updates[name]}")
        seen.add(name)
    else:
        next_lines.append(line)

for name, value in updates.items():
    if name not in seen:
        next_lines.append(f"{name}={value}")

ENV_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
KEY_PATH.unlink(missing_ok=True)
print("claudehub env updated")
