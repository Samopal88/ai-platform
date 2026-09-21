"""AI model catalog endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.model_catalog import get_model, list_models
from app.services.model_router import ModelRouter

router = APIRouter(prefix="/api/models", tags=["Models"])
_model_router = ModelRouter()


@router.get("")
def models():
    return {
        "models": list_models(),
        "gateway": {
            "preferred_family": "ruapi_openai_compatible",
        },
    }


@router.get("/{model_id}")
def model(model_id: str):
    item = get_model(model_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return {
        **item,
        "preferred_provider": _model_router.preferred_provider_name(model_id),
    }
