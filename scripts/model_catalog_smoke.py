from __future__ import annotations

import json
import os
import urllib.request


BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


with urllib.request.urlopen(BASE_URL + "/api/models", timeout=30) as response:
    payload = json.loads(response.read().decode("utf-8"))

models = payload.get("models") or []
ids = [item.get("id") for item in models]
assert ids[:3] == ["claude-haiku-4.5", "gpt-4.1", "gpt-5.2"], ids[:5]
assert "claude-opus-4.7" in ids, ids
assert "gemini-3.1-pro-preview" in ids, ids

for item in models[:5]:
    assert item.get("label"), item
    assert item.get("description"), item
    assert "Р" not in str(item.get("description", ""))[:3], item

print(json.dumps({
    "ok": True,
    "count": len(models),
    "first_models": ids[:5],
}, ensure_ascii=False, indent=2))
