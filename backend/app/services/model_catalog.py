"""Supported AI model catalog and capability flags."""
from __future__ import annotations


MODEL_CATALOG: list[dict] = [
    {
        "id": "claude-haiku-4.5",
        "provider": "anthropic",
        "label": "Claude Haiku 4.5",
        "short_label": "Haiku 4.5",
        "description": "Быстрая и экономичная модель Claude для коротких задач, чатов и быстрых правок.",
        "capabilities": ["text", "vision", "streaming"],
        "badges": ["Быстрая", "Картинки"],
        "tier": "free",
    },
    {
        "id": "gpt-4.1",
        "provider": "openai",
        "label": "GPT-4.1",
        "short_label": "GPT-4.1",
        "description": "Недорогая и надежная модель OpenAI для текста, кода, изображений и повседневных задач.",
        "capabilities": ["text", "vision", "streaming"],
        "badges": ["Экономичная", "Картинки"],
        "tier": "free",
    },
    {
        "id": "gpt-5.2",
        "provider": "openai",
        "label": "GPT-5.2",
        "short_label": "GPT-5.2",
        "description": "Сильная универсальная модель OpenAI для ежедневной работы, анализа и аккуратных ответов.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Картинки"],
        "tier": "starter",
    },
    {
        "id": "claude-opus-4.7",
        "provider": "anthropic",
        "label": "Claude Opus 4.7",
        "short_label": "Opus 4.7",
        "description": "Новейшая флагманская модель Claude для самых сложных задач, архитектуры, кода и глубокого анализа.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["NEW", "Рассуждения", "Файлы"],
        "tier": "pro",
    },
    {
        "id": "gpt-5.4",
        "provider": "openai",
        "label": "GPT-5.4",
        "short_label": "GPT-5.4",
        "description": "Флагманская модель OpenAI для сложных задач, кода, документов, анализа и рассуждений.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Картинки", "Файлы"],
        "tier": "pro",
    },
    {
        "id": "gpt-4o",
        "provider": "openai",
        "label": "GPT-4o",
        "short_label": "GPT-4o",
        "description": "Мультимодальная модель OpenAI для быстрых диалогов, изображений и голосовых сценариев.",
        "capabilities": ["text", "vision", "streaming", "audio"],
        "badges": ["Картинки", "Аудио"],
        "tier": "starter",
    },
    {
        "id": "claude-opus-4.6",
        "provider": "anthropic",
        "label": "Claude Opus 4.6",
        "short_label": "Opus 4.6",
        "description": "Самая продвинутая модель Claude для глубокого анализа, архитектуры и сложных документов.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Файлы"],
        "tier": "pro",
    },
    {
        "id": "claude-opus-4.5",
        "provider": "anthropic",
        "label": "Claude Opus 4.5",
        "short_label": "Opus 4.5",
        "description": "Мощная модель Claude для сложных рассуждений, документов и задач с большим контекстом.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Файлы"],
        "tier": "pro",
    },
    {
        "id": "claude-sonnet-4.6",
        "provider": "anthropic",
        "label": "Claude Sonnet 4.6",
        "short_label": "Sonnet 4.6",
        "description": "Сильный баланс качества и скорости: код, тексты, длинные файлы и проектная работа.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Файлы"],
        "tier": "starter",
    },
    {
        "id": "claude-sonnet-4.5",
        "provider": "anthropic",
        "label": "Claude Sonnet 4.5",
        "short_label": "Sonnet 4.5",
        "description": "Надежная модель Claude для кода, текстов, анализа файлов и ежедневной проектной работы.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Файлы"],
        "tier": "starter",
    },
    {
        "id": "gemini-3.1-pro-preview",
        "provider": "google",
        "label": "Gemini 3.1 Pro Preview",
        "short_label": "Gemini 3.1 Pro",
        "description": "Экспериментальная модель Google с большим контекстом для анализа, рассуждений и сложных задач.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Preview", "Рассуждения", "Картинки"],
        "tier": "pro",
    },
    {
        "id": "gemini-2.5-pro",
        "provider": "google",
        "label": "Gemini 2.5 Pro",
        "short_label": "Gemini 2.5",
        "description": "Сильная модель Google для анализа, изображений, больших документов и сложных запросов.",
        "capabilities": ["text", "vision", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Картинки"],
        "tier": "starter",
    },
    {
        "id": "deepseek-chat",
        "provider": "deepseek",
        "label": "DeepSeek Chat",
        "short_label": "DeepSeek",
        "description": "Экономичная модель для текстов, кода, идей и быстрых рабочих ответов.",
        "capabilities": ["text", "streaming"],
        "badges": ["Быстрая", "Код"],
        "tier": "starter",
    },
    {
        "id": "deepseek-reasoner",
        "provider": "deepseek",
        "label": "DeepSeek Reasoner",
        "short_label": "DeepSeek R1",
        "description": "Модель с акцентом на пошаговые рассуждения, математику, код и сложную логику.",
        "capabilities": ["text", "streaming", "file_reasoning"],
        "badges": ["Рассуждения", "Код"],
        "tier": "pro",
    },
    {
        "id": "grok-4",
        "provider": "xai",
        "label": "Grok 4",
        "short_label": "Grok 4",
        "description": "Модель xAI для быстрых ответов, анализа и свежего разговорного стиля.",
        "capabilities": ["text", "streaming"],
        "badges": ["Быстрая"],
        "tier": "pro",
    },
    {
        "id": "qwen3-max",
        "provider": "qwen",
        "label": "Qwen3 Max",
        "short_label": "Qwen Max",
        "description": "Мощная модель Qwen для кода, документов, рассуждений и многоязычных задач.",
        "capabilities": ["text", "streaming", "file_reasoning"],
        "badges": ["Код", "Файлы"],
        "tier": "starter",
    },
]


def list_models() -> list[dict]:
    return MODEL_CATALOG


def get_model(model_id: str) -> dict | None:
    for model in MODEL_CATALOG:
        if model["id"] == model_id:
            return model
    return None


def model_has_capability(model_id: str, capability: str) -> bool:
    model = get_model(model_id)
    return bool(model and capability in model.get("capabilities", []))


# Plan tier ordering: a plan can access models at its tier and below.
_TIER_ORDER: dict[str, int] = {
    "free": 0,
    "starter": 1,
    "medium": 2,
    "pro": 3,
}

# Subscription plan → effective model tier (medium plan gets same access as pro for simplicity)
_PLAN_TIER: dict[str, str] = {
    "free": "free",
    "starter": "starter",
    "starter_490": "starter",
    "medium": "pro",  # medium plan gets pro-tier models
    "pro": "pro",
}


def model_allowed_for_plan(model_id: str, plan_type: str) -> bool:
    """Return True if `plan_type` subscription allows access to `model_id`."""
    model = get_model(model_id)
    if model is None:
        # Unknown model — allow so existing logic remains unblocked
        return True
    model_tier = model.get("tier", "free")
    user_tier = _PLAN_TIER.get(plan_type or "free", "free")
    return _TIER_ORDER.get(user_tier, 0) >= _TIER_ORDER.get(model_tier, 0)
