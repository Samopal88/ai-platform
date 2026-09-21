"""Media generation and speech recognition endpoints."""
from __future__ import annotations

from base64 import b64encode

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.limits_service import ensure_token_available
from app.services.model_router import ModelRouter
from app.services.usage_service import record_usage

router = APIRouter(prefix="/api/media", tags=["Media"])
_model_router = ModelRouter()


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model: str = "openai-image"
    size: str = "1024x1024"


@router.post("/images")
def generate_image(
    data: ImageGenerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_token_available(db=db, user=current_user, token_delta=1000)
    if not any(
        (
            settings.ROUTERAI_API_KEY,
            settings.RUAPI_API_KEY and settings.RUAPI_BASE_URL,
            settings.OPENAI_API_KEY and settings.OPENAI_BASE_URL,
            settings.CLAUDEHUB_API_KEY,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image generation provider is not configured",
        )

    try:
        result = _model_router.generate_image(
            prompt=data.prompt,
            model_id=data.model,
            size=data.size,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        record_usage(
            db,
            user=current_user,
            operation="image_generation",
            provider=result.provider,
            model=result.model_id,
            units_images=len(result.images),
        )
    except Exception:
        pass

    return {
        "provider": result.provider,
        "model": result.model_id,
        "size": data.size,
        "images": [
            {
                "media_type": image.media_type,
                "b64_json": b64encode(image.data).decode("ascii"),
            }
            for image in result.images
        ],
    }


@router.post("/speech-to-text")
async def speech_to_text(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Phase 9.1 – Speech-to-text via OpenAI Whisper-compatible endpoint.

    Accepts audio file and returns transcript.
    Requires OPENAI_API_KEY (or a RouterAI/RuAPI key with a Whisper-compatible endpoint).
    Usage is accounted as token_delta=1000 placeholder until actual token counts are available.
    """
    ensure_token_available(db=db, user=current_user, token_delta=1000)

    # Check for any configured provider that supports Whisper
    whisper_key = (
        settings.OPENAI_API_KEY
        or settings.ROUTERAI_API_KEY
        or settings.RUAPI_API_KEY
    )
    whisper_base = (
        ""  # OpenAI default
        if settings.OPENAI_API_KEY
        else (
            settings.ROUTERAI_BASE_URL or settings.RUAPI_BASE_URL or ""
        )
    )

    if not whisper_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech recognition provider is not configured. Set OPENAI_API_KEY, ROUTERAI_API_KEY, or RUAPI_API_KEY.",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"

    try:
        import httpx

        url_base = whisper_base.rstrip("/") if whisper_base else "https://api.openai.com/v1"
        url = f"{url_base}/audio/transcriptions"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {whisper_key}"},
                files={"file": (filename, audio_bytes, content_type)},
                data={"model": "whisper-1"},
            )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Speech recognition provider returned {resp.status_code}: {resp.text[:200]}",
            )

        result = resp.json()
        transcript = result.get("text", "")

        try:
            record_usage(
                db,
                user=current_user,
                operation="speech_to_text",
                provider="whisper",
                model="whisper-1",
                tokens_input=max(1, len(audio_bytes) // 1000),
            )
        except Exception:
            pass

        return {"transcript": transcript, "filename": filename}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Speech recognition failed: {exc}",
        ) from exc
