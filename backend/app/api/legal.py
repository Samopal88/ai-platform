"""Legal pages (Terms and Privacy) for public MVP."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["Legal"])

_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PUBLIC_DOCS_DIR = _PROJECT_ROOT / "docs" / "public"


@router.get("/terms")
async def terms_page():
    fp = _FRONTEND_DIR / "terms.html"
    if fp.exists():
        return FileResponse(fp)
    return JSONResponse(status_code=404, content={"detail": "terms page not found"})


@router.get("/privacy")
async def privacy_page():
    fp = _FRONTEND_DIR / "privacy.html"
    if fp.exists():
        return FileResponse(fp)
    return JSONResponse(status_code=404, content={"detail": "privacy page not found"})


@router.get("/docs-public")
async def public_docs_index():
    fp = _PUBLIC_DOCS_DIR / "README.md"
    if fp.exists():
        return FileResponse(fp, media_type="text/markdown; charset=utf-8")
    return JSONResponse(status_code=404, content={"detail": "docs index not found"})


@router.get("/docs-public/{page}")
async def public_docs_page(page: str):
    safe = page.strip().replace("\\", "/").split("/")[-1]
    if not safe.endswith(".md"):
        safe = f"{safe}.md"
    fp = _PUBLIC_DOCS_DIR / safe
    try:
        fp.resolve().relative_to(_PUBLIC_DOCS_DIR.resolve())
    except ValueError:
        return JSONResponse(status_code=403, content={"detail": "invalid docs path"})
    if fp.exists():
        return FileResponse(fp, media_type="text/markdown; charset=utf-8")
    return JSONResponse(status_code=404, content={"detail": "docs page not found"})
