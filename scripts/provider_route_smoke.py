from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime


BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MODELS = [
    item.strip()
    for item in os.environ.get("PROVIDER_ROUTE_MODELS", "gpt-5.4,claude-opus-4.7,gemini-3.1-pro-preview").split(",")
    if item.strip()
]


def request_json(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE_URL + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def assert_no_product_error(model_id: str, payload: dict):
    content = str(payload.get("content", ""))
    lowered = content.lower()
    bad_markers = [
        "не удалось получить ответ",
        "сервис временно недоступен",
        "попробуйте ещё раз",
        "temporarily unavailable",
    ]
    assert content.strip(), (model_id, payload)
    assert not any(marker in lowered for marker in bad_markers), (model_id, content)


stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
email = f"provider-route-{stamp}@example.com"
password = "StrongPass123"

status, auth = request_json("POST", "/api/auth/register", {
    "email": email,
    "password": password,
    "accept_terms": True,
})
assert status == 200 and auth.get("token"), (status, auth)
token = auth["token"]

results = []
failures = []
for model_id in MODELS:
    try:
        status, chat = request_json("POST", "/api/chats", {"title": f"Route {model_id}", "model": model_id}, token)
        assert status == 201, (model_id, status, chat)
        chat_id = chat["id"]
        status, message = request_json(
            "POST",
            f"/api/chats/{chat_id}/messages",
            {"role": "user", "content": "Ответь одним коротким русским предложением: проверка маршрута модели успешна."},
            token,
        )
        assert status == 201, (model_id, status, message)
        status, completion = request_json("POST", f"/api/chats/{chat_id}/complete", {}, token)
        assert status == 201, (model_id, status, completion)
        assert_no_product_error(model_id, completion)
        results.append({
            "model": model_id,
            "ok": True,
            "answer_preview": str(completion.get("content", ""))[:160],
            "tokens": completion.get("extra_data", {}).get("usage") or {},
        })
    except Exception as exc:
        failures.append({"model": model_id, "ok": False, "error": str(exc)[:500]})

print(json.dumps({
    "ok": not failures,
    "models": results,
    "failures": failures,
}, ensure_ascii=False, indent=2))

if failures:
    raise SystemExit(1)
