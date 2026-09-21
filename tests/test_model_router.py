from __future__ import annotations

from base64 import b64encode
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.model_router import ModelRouter, model_supports_vision  # noqa: E402


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-sonnet-4.6", True),
        ("gpt-4o", True),
        ("gpt-4o-mini", True),
        ("claude-unknown-x", False),
        ("", False),
        ("gpt-4.1", True),
        ("gemini-2.5-pro", True),
        ("text-only-model", False),
    ],
)
def test_model_supports_vision_matrix(model_id, expected):
    assert model_supports_vision(model_id) is expected


def test_model_supports_vision_none_input_returns_false():
    assert model_supports_vision(None) is False  # type: ignore[arg-type]


def test_router_prefers_settings_backed_routerai_provider(monkeypatch):
    monkeypatch.delenv("ROUTERAI_API_KEY", raising=False)
    monkeypatch.delenv("ROUTERAI_BASE_URL", raising=False)
    monkeypatch.setattr("app.services.model_router.settings.ROUTERAI_API_KEY", "routerai-key")
    monkeypatch.setattr("app.services.model_router.settings.ROUTERAI_BASE_URL", "https://routerai.example/v1")

    captured = {}

    def fake_call(self, **kwargs):
        captured.update(kwargs)
        from app.services.model_router import ModelResponse

        return ModelResponse(text="ok", provider=kwargs["provider_name"], model_id=kwargs["model_id"])

    monkeypatch.setattr(ModelRouter, "_call_openai_compat", fake_call)

    result = ModelRouter().route_response([{"role": "user", "content": "ping"}], "gpt-4o")
    assert result.provider == "routerai"
    assert captured["api_key"] == "routerai-key"
    assert captured["base_url"] == "https://routerai.example/v1"
    assert result.model_id == "gpt-4o"


def test_router_resolves_routerai_model_aliases():
    router = ModelRouter()
    assert router._resolve_provider_model_id("gpt-4o", "routerai") == "openai/gpt-4o"
    assert router._resolve_provider_model_id("openai-image", "routerai") == "google/gemini-2.5-flash-image"


def test_router_image_generation_decodes_openai_compatible_payload(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "images": [
                                {
                                    "image_url": {
                                        "url": f"data:image/png;base64,{b64encode(b'png-bytes').decode('ascii')}",
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr("httpx.post", fake_post)

    result = ModelRouter()._call_openai_compat_image_generation(
        prompt="test image",
        model_id="openai-image",
        size="1024x1024",
        api_key="key",
        base_url="https://routerai.example/v1",
        provider_name="routerai",
    )
    assert result.provider == "routerai"
    assert result.model_id == "google/gemini-2.5-flash-image"
    assert result.images[0].media_type == "image/png"
    assert result.images[0].data == b"png-bytes"
