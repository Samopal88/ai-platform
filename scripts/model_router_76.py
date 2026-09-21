"""
AI Workspace Platform - Model Router.

Provider chain:
  1. RouterAI OpenAI-compatible endpoint (future paid provider)
     ROUTERAI_API_KEY + ROUTERAI_BASE_URL
  2. ClaudeHub OpenAI-compatible endpoint (cheap Claude provider)
     CLAUDEHUB_API_KEY + CLAUDEHUB_BASE_URL
  3. RuAPI/OpenAI-compatible endpoint (current temporary provider)
     OPENAI_API_KEY + OPENAI_BASE_URL
  4. Native Anthropic fallback for claude-* models
     ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


VISION_MODELS = {
    "claude-opus-4.7", "claude-opus-4.6", "claude-opus-4.5",
    "claude-sonnet-4.6", "claude-sonnet-4.5", "claude-haiku-4.5",
    "gpt-4o", "gpt-4-turbo", "gpt-5.4", "gpt-5.2", "gpt-4.1",
    "gemini-3.1-pro-preview", "gemini-2.5-pro",
}


def model_supports_vision(model_id: str) -> bool:
    return model_id in VISION_MODELS or model_id.startswith("claude")


@dataclass(frozen=True)
class OpenAICompatProvider:
    name: str
    key_env: str
    base_url_env: str
    default_base_url: str

    def configured(self) -> bool:
        return bool(os.environ.get(self.key_env, "").strip())

    def key(self) -> str:
        return os.environ.get(self.key_env, "").strip()

    def base_url(self) -> str:
        return (os.environ.get(self.base_url_env, "").strip() or self.default_base_url).rstrip("/")


OPENAI_COMPAT_PROVIDERS = [
    OpenAICompatProvider(
        name="routerai",
        key_env="ROUTERAI_API_KEY",
        base_url_env="ROUTERAI_BASE_URL",
        default_base_url="https://routerai.ru/api/v1",
    ),
    OpenAICompatProvider(
        name="claudehub",
        key_env="CLAUDEHUB_API_KEY",
        base_url_env="CLAUDEHUB_BASE_URL",
        default_base_url="https://api.claudehub.fun/v1",
    ),
    OpenAICompatProvider(
        name="ruapi",
        key_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
    ),
]


class ModelRouter:
    """Routes chat completion requests to the appropriate AI provider."""

    def route(self, messages: list[dict], model_id: str, max_tokens: int = 1024) -> str:
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
                )
            except Exception as exc:
                log.warning(
                    "%s OpenAI-compatible API call failed for model %s (%s): %s",
                    provider.name,
                    model_id,
                    type(exc).__name__,
                    exc,
                )

        anthropic_key = (
            os.environ.get("ANTHROPIC_API_KEY", "").strip()
            or os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
        )
        if anthropic_key and model_id.startswith("claude"):
            try:
                return self._call_anthropic(messages, model_id, max_tokens, anthropic_key)
            except Exception as exc:
                log.warning("Anthropic API call failed for model %s (%s): %s", model_id, type(exc).__name__, exc)

        return "⚠️ Не удалось получить ответ от ИИ. Попробуйте ещё раз или смените модель."

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

    def _call_anthropic(self, messages: list[dict], model_id: str, max_tokens: int, api_key: str) -> str:
        import httpx  # type: ignore[import]

        base_url = (os.environ.get("ANTHROPIC_BASE_URL", "").strip() or "https://api.anthropic.com").rstrip("/")

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
                "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01"),
                "content-type": "application/json",
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
        return ""

    def _call_openai_compat(
        self,
        messages: list[dict],
        model_id: str,
        max_tokens: int,
        api_key: str,
        base_url: str,
    ) -> str:
        import httpx  # type: ignore[import]

        converted = []
        for msg in messages:
            converted.append({
                "role": msg["role"],
                "content": self._build_openai_content(msg["content"]),
            })

        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json={
                "model": model_id,
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

        if "choices" in data and data["choices"]:
            message = data["choices"][0].get("message") or {}
            return message.get("content") or data["choices"][0].get("content") or ""

        if "content" in data and isinstance(data["content"], list):
            for block in data["content"]:
                if block.get("type") == "text":
                    return block.get("text", "")

        return ""
