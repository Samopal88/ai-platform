"""
AI Workspace Platform - Model Router.

Provider chain:
  1. RouterAI OpenAI-compatible endpoint (future paid provider)
     ROUTERAI_API_KEY + ROUTERAI_BASE_URL
  2. RuAPI/OpenAI-compatible endpoint (current primary provider)
     RUAPI_API_KEY + RUAPI_BASE_URL
  3. ClaudeHub OpenAI-compatible endpoint (fallback cheap Claude provider)
     CLAUDEHUB_API_KEY + CLAUDEHUB_BASE_URL
  4. Native Anthropic fallback for claude-* models
     ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL
"""
from __future__ import annotations

import os
from base64 import b64decode
from dataclasses import dataclass
from typing import Generator, Optional

from app.core.config import settings
from app.services.model_catalog import get_model, model_has_capability


def _setting_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
        setting_value = str(getattr(settings, name, "") or "").strip()
        if setting_value:
            return setting_value
    return default


def model_supports_vision(model_id: str) -> bool:
    normalized = (model_id or "").strip()
    if not normalized:
        return False
    if model_has_capability(normalized, "vision"):
        return True
    lower = normalized.lower()
    return (
        lower.startswith(("claude-opus-4", "claude-sonnet-4", "claude-haiku-4"))
        or lower.startswith(("gpt-4o", "gpt-4.1", "gpt-4-turbo", "gpt-5"))
        or lower.startswith(("gemini-2.5", "gemini-3.1"))
    )


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class ModelResponse:
    text: str
    provider: str
    model_id: str
    usage: ModelUsage = ModelUsage()


@dataclass(frozen=True)
class StreamChunk:
    delta: str
    provider: str
    model_id: str


@dataclass(frozen=True)
class GeneratedImage:
    media_type: str
    data: bytes


@dataclass(frozen=True)
class ImageGenerationResponse:
    provider: str
    model_id: str
    images: tuple[GeneratedImage, ...]


@dataclass(frozen=True)
class OpenAICompatProvider:
    name: str
    key_envs: tuple[str, ...]
    base_url_envs: tuple[str, ...]
    default_base_url: str = ""
    require_explicit_base_url: bool = False

    def _first_env(self, names: tuple[str, ...]) -> str:
        return _setting_value(*names)

    def configured(self) -> bool:
        if not self.key():
            return False
        if self.require_explicit_base_url:
            return bool(self.base_url())
        return True

    def key(self) -> str:
        return self._first_env(self.key_envs)

    def base_url(self) -> str:
        return (self._first_env(self.base_url_envs) or self.default_base_url).rstrip("/")


OPENAI_COMPAT_PROVIDERS = [
    OpenAICompatProvider(
        name="routerai",
        key_envs=("ROUTERAI_API_KEY",),
        base_url_envs=("ROUTERAI_BASE_URL",),
        default_base_url="https://routerai.ru/api/v1",
    ),
    OpenAICompatProvider(
        name="ruapi",
        key_envs=("RUAPI_API_KEY", "OPENAI_API_KEY"),
        base_url_envs=("RUAPI_BASE_URL", "OPENAI_BASE_URL"),
        require_explicit_base_url=True,
    ),
    OpenAICompatProvider(
        name="claudehub",
        key_envs=("CLAUDEHUB_API_KEY",),
        base_url_envs=("CLAUDEHUB_BASE_URL",),
        default_base_url="https://api.claudehub.fun/v1",
    ),
]

ROUTERAI_MODEL_ALIASES = {
    "openai-image": "google/gemini-2.5-flash-image",
}


class ModelRouter:
    """Routes chat completion and image generation requests to the appropriate AI provider."""

    def route(self, messages: list[dict], model_id: str, max_tokens: int = 1024) -> str:
        return self.route_response(messages, model_id, max_tokens=max_tokens).text

    def route_response(self, messages: list[dict], model_id: str, max_tokens: int = 1024) -> ModelResponse:
        import logging

        log = logging.getLogger(__name__)

        for provider in OPENAI_COMPAT_PROVIDERS:
            if not provider.configured():
                continue
            try:
                return self._call_openai_compat(
                    messages=messages,
                    model_id=model_id,
                    max_tokens=max_tokens,
                    api_key=provider.key(),
                    base_url=provider.base_url(),
                    provider_name=provider.name,
                )
            except Exception as exc:
                log.warning(
                    "%s OpenAI-compatible API call failed for model %s (%s): %s",
                    provider.name,
                    model_id,
                    type(exc).__name__,
                    exc,
                )

        anthropic_key = _setting_value("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
        if anthropic_key and model_id.startswith("claude"):
            try:
                return self._call_anthropic(messages, model_id, max_tokens, anthropic_key)
            except Exception as exc:
                log.warning("Anthropic API call failed for model %s (%s): %s", model_id, type(exc).__name__, exc)

        return ModelResponse(
            text="AI provider is not available right now. Try again or switch the model.",
            provider="unavailable",
            model_id=model_id,
        )

    def generate_image(self, prompt: str, model_id: str, size: str = "1024x1024") -> ImageGenerationResponse:
        import logging

        log = logging.getLogger(__name__)

        for provider in OPENAI_COMPAT_PROVIDERS:
            if not provider.configured():
                continue
            try:
                return self._call_openai_compat_image_generation(
                    prompt=prompt,
                    model_id=model_id,
                    size=size,
                    api_key=provider.key(),
                    base_url=provider.base_url(),
                    provider_name=provider.name,
                )
            except Exception as exc:
                log.warning(
                    "%s image generation API call failed for model %s (%s): %s",
                    provider.name,
                    model_id,
                    type(exc).__name__,
                    exc,
                )

        raise RuntimeError("Image generation provider is not available right now")

    def preferred_provider_name(self, model_id: str) -> str:
        known_model = get_model(model_id or "")
        if known_model and known_model.get("provider"):
            return str(known_model["provider"])
        if (model_id or "").lower().startswith("claude"):
            return "anthropic"
        if (model_id or "").lower().startswith("gemini"):
            return "google"
        return "openai_compatible"

    def stream_response(
        self,
        messages: list[dict],
        model_id: str,
        max_tokens: int = 1024,
    ) -> Generator[StreamChunk, None, None]:
        import logging

        log = logging.getLogger(__name__)
        for provider in OPENAI_COMPAT_PROVIDERS:
            if not provider.configured():
                continue
            try:
                yield from self._stream_openai_compat(
                    messages=messages,
                    model_id=model_id,
                    max_tokens=max_tokens,
                    api_key=provider.key(),
                    base_url=provider.base_url(),
                    provider_name=provider.name,
                )
                return
            except Exception as exc:
                log.warning(
                    "%s streaming API call failed for model %s (%s): %s",
                    provider.name,
                    model_id,
                    type(exc).__name__,
                    exc,
                )

        anthropic_key = _setting_value("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
        if anthropic_key and model_id.startswith("claude"):
            yield from self._stream_anthropic(messages, model_id, max_tokens, anthropic_key)

    def _build_anthropic_content(self, content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            blocks = []
            for item in content:
                if item.get("type") == "text":
                    blocks.append({"type": "text", "text": item["text"]})
                elif item.get("type") == "image_base64":
                    blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": item["media_type"],
                            "data": item["data"],
                        },
                    })
            return blocks
        return str(content)

    def _build_openai_content(self, content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            blocks = []
            for item in content:
                if item.get("type") == "text":
                    blocks.append({"type": "text", "text": item["text"]})
                elif item.get("type") == "image_base64":
                    data_url = f"data:{item['media_type']};base64,{item['data']}"
                    blocks.append({"type": "image_url", "image_url": {"url": data_url}})
            return blocks
        return str(content)

    def _resolve_provider_model_id(self, model_id: str, provider_name: str) -> str:
        normalized = (model_id or "").strip()
        if not normalized:
            return normalized
        if provider_name != "routerai":
            return normalized
        if "/" in normalized:
            return normalized
        aliased = ROUTERAI_MODEL_ALIASES.get(normalized)
        if aliased:
            return aliased
        known_model = get_model(normalized)
        provider = str((known_model or {}).get("provider") or "").strip().lower()
        prefix_by_provider = {
            "openai": "openai",
            "google": "google",
            "anthropic": "anthropic",
            "qwen": "qwen",
            "deepseek": "deepseek",
        }
        prefix = prefix_by_provider.get(provider)
        if prefix:
            return f"{prefix}/{normalized}"
        return normalized

    def _image_config_for_size(self, size: str) -> dict:
        normalized = (size or "").strip().lower()
        mapping = {
            "1024x1024": {"aspect_ratio": "1:1", "image_size": "1K"},
            "832x1248": {"aspect_ratio": "2:3", "image_size": "1K"},
            "1248x832": {"aspect_ratio": "3:2", "image_size": "1K"},
            "864x1184": {"aspect_ratio": "3:4", "image_size": "1K"},
            "1184x864": {"aspect_ratio": "4:3", "image_size": "1K"},
            "896x1152": {"aspect_ratio": "4:5", "image_size": "1K"},
            "1152x896": {"aspect_ratio": "5:4", "image_size": "1K"},
            "768x1344": {"aspect_ratio": "9:16", "image_size": "1K"},
            "1344x768": {"aspect_ratio": "16:9", "image_size": "1K"},
            "1536x672": {"aspect_ratio": "21:9", "image_size": "1K"},
        }
        return mapping.get(normalized, {"aspect_ratio": "1:1", "image_size": "1K"})

    def _call_anthropic(self, messages: list[dict], model_id: str, max_tokens: int, api_key: str) -> ModelResponse:
        import httpx  # type: ignore[import]

        base_url = _setting_value("ANTHROPIC_BASE_URL", default="https://api.anthropic.com").rstrip("/")

        system_content: Optional[str] = None
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
            else:
                user_messages.append({
                    "role": msg["role"],
                    "content": self._build_anthropic_content(msg["content"]),
                })

        payload: dict = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": user_messages,
        }
        if system_content:
            payload["system"] = system_content

        response = httpx.post(
            f"{base_url}/v1/messages",
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": _setting_value("ANTHROPIC_VERSION", default="2023-06-01"),
                "content-type": "application/json",
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        for block in data.get("content", []):
            if block.get("type") == "text":
                return ModelResponse(
                    text=block.get("text", ""),
                    provider="anthropic",
                    model_id=model_id,
                    usage=ModelUsage(
                        prompt_tokens=int(usage.get("input_tokens") or 0),
                        completion_tokens=int(usage.get("output_tokens") or 0),
                    ),
                )
        return ModelResponse(text="", provider="anthropic", model_id=model_id)

    def _call_openai_compat(
        self,
        messages: list[dict],
        model_id: str,
        max_tokens: int,
        api_key: str,
        base_url: str,
        provider_name: str,
    ) -> ModelResponse:
        import httpx  # type: ignore[import]

        converted = []
        for msg in messages:
            converted.append({
                "role": msg["role"],
                "content": self._build_openai_content(msg["content"]),
            })

        provider_model_id = self._resolve_provider_model_id(model_id, provider_name)
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json={
                "model": provider_model_id,
                "messages": converted,
                "max_tokens": max_tokens,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}

        if "choices" in data and data["choices"]:
            message = data["choices"][0].get("message") or {}
            return ModelResponse(
                text=message.get("content") or data["choices"][0].get("content") or "",
                provider=provider_name,
                model_id=provider_model_id,
                usage=ModelUsage(
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                ),
            )

        if "content" in data and isinstance(data["content"], list):
            for block in data["content"]:
                if block.get("type") == "text":
                    return ModelResponse(
                        text=block.get("text", ""),
                        provider=provider_name,
                        model_id=provider_model_id,
                    )

        return ModelResponse(text="", provider=provider_name, model_id=provider_model_id)

    def _call_openai_compat_image_generation(
        self,
        *,
        prompt: str,
        model_id: str,
        size: str,
        api_key: str,
        base_url: str,
        provider_name: str,
    ) -> ImageGenerationResponse:
        import httpx  # type: ignore[import]

        provider_model_id = self._resolve_provider_model_id(model_id, provider_name)
        payload = {
            "model": provider_model_id,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
        }
        if provider_model_id.startswith("google/"):
            payload["image_config"] = self._image_config_for_size(size)

        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json={
                **payload,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=180.0,
        )
        response.raise_for_status()
        data = response.json()
        generated_images: list[GeneratedImage] = []
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            for item in message.get("images") or []:
                image_url = ((item or {}).get("image_url") or {}).get("url") or ""
                if not image_url.startswith("data:image/") or ";base64," not in image_url:
                    continue
                header, b64_payload = image_url.split(",", 1)
                media_type = header.split(";", 1)[0].replace("data:", "", 1) or "image/png"
                generated_images.append(
                    GeneratedImage(
                        media_type=media_type,
                        data=b64decode(b64_payload),
                    )
                )
        if not generated_images:
            raise RuntimeError(f"{provider_name} image generation response did not contain image payloads")
        return ImageGenerationResponse(
            provider=provider_name,
            model_id=provider_model_id,
            images=tuple(generated_images),
        )

    def _stream_openai_compat(
        self,
        messages: list[dict],
        model_id: str,
        max_tokens: int,
        api_key: str,
        base_url: str,
        provider_name: str,
    ) -> Generator[StreamChunk, None, None]:
        import json
        import httpx  # type: ignore[import]

        converted = []
        for msg in messages:
            converted.append({
                "role": msg["role"],
                "content": self._build_openai_content(msg["content"]),
            })

        provider_model_id = self._resolve_provider_model_id(model_id, provider_name)
        with httpx.stream(
            "POST",
            f"{base_url.rstrip('/')}/chat/completions",
            json={
                "model": provider_model_id,
                "messages": converted,
                "max_tokens": max_tokens,
                "stream": True,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                data = json.loads(payload)
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content") or ""
                if isinstance(text, list):
                    text = "".join(
                        block.get("text", "")
                        for block in text
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                if text:
                    yield StreamChunk(delta=str(text), provider=provider_name, model_id=provider_model_id)

    def _stream_anthropic(
        self,
        messages: list[dict],
        model_id: str,
        max_tokens: int,
        api_key: str,
    ) -> Generator[StreamChunk, None, None]:
        import json
        import httpx  # type: ignore[import]

        base_url = _setting_value("ANTHROPIC_BASE_URL", default="https://api.anthropic.com").rstrip("/")
        system_content: Optional[str] = None
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
            else:
                user_messages.append({
                    "role": msg["role"],
                    "content": self._build_anthropic_content(msg["content"]),
                })

        payload: dict = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": user_messages,
            "stream": True,
        }
        if system_content:
            payload["system"] = system_content

        with httpx.stream(
            "POST",
            f"{base_url}/v1/messages",
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": _setting_value("ANTHROPIC_VERSION", default="2023-06-01"),
                "content-type": "application/json",
            },
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                data = json.loads(payload)
                delta = ((data.get("delta") or {}).get("text")) or ""
                if delta:
                    yield StreamChunk(delta=str(delta), provider="anthropic", model_id=model_id)
