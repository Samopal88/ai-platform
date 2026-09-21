"""Operational readiness diagnostics for release preparation."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.auth_deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/api/system", tags=["System"])


def _configured(*names: str) -> bool:
    return all(bool((os.environ.get(name, "").strip() or str(getattr(settings, name, "") or "").strip())) for name in names)


def _any_configured(*names: str) -> bool:
    return any(bool((os.environ.get(name, "").strip() or str(getattr(settings, name, "") or "").strip())) for name in names)


def _runtime_process_count() -> int:
    proc_root = Path("/proc")
    if not proc_root.exists():
        return 0

    count = 0
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        argv = [part.decode("utf-8", "ignore") for part in raw.split(b"\x00") if part]
        # Only count actual uvicorn workers, not shell commands that happen to grep for "uvicorn"
        if "uvicorn" in argv and "app.main:app" in argv and (
            any("python" in a or ".venv" in a for a in argv[:3])
        ):
            count += 1
    return count


def _service_file_contains(path: Path, expected_exec: str) -> bool:
    if not path.exists():
        return False
    try:
        return expected_exec in path.read_text(encoding="utf-8")
    except OSError:
        return False


@router.get("/readiness")
def system_readiness(current_user: User = Depends(get_current_user)):
    auth_secret_configured = bool(
        (getattr(settings, "AUTH_TOKEN_SECRET", "") or getattr(settings, "SECRET_KEY", "")).strip()
    )
    smtp_ready = _configured("SMTP_HOST", "SMTP_FROM_EMAIL")
    postgres_mode = settings.DATABASE_URL.startswith("postgresql+psycopg") or settings.DATABASE_URL.startswith("postgresql://")
    project_root = Path(__file__).resolve().parents[3]
    template_service_unit_path = project_root / "deploy" / "systemd" / settings.SYSTEMD_UNIT_NAME
    deployed_service_unit_path = Path("/etc/systemd/system") / settings.SYSTEMD_UNIT_NAME
    expected_exec = (
        f"ExecStart=/opt/ai-workspace/.venv/bin/python -m uvicorn app.main:app "
        f"--host {settings.BACKEND_HOST} --port {settings.BACKEND_PORT}"
    )
    service_template_matches_runtime = _service_file_contains(template_service_unit_path, expected_exec)
    service_unit_installed = deployed_service_unit_path.exists()
    service_unit_matches_runtime = _service_file_contains(deployed_service_unit_path, expected_exec)
    runtime_process_count = _runtime_process_count()
    single_runtime_process = runtime_process_count <= 1

    providers = {
        "routerai": _configured("ROUTERAI_API_KEY"),
        "claudehub": _configured("CLAUDEHUB_API_KEY"),
        "ruapi_openai_compatible": (
            _configured("RUAPI_API_KEY", "RUAPI_BASE_URL")
            or _configured("OPENAI_API_KEY", "OPENAI_BASE_URL")
        ),
        "ruapi_explicit": _configured("RUAPI_API_KEY", "RUAPI_BASE_URL"),
        "openai_direct_or_compatible": _configured("OPENAI_API_KEY"),
        "anthropic_native": _configured("ANTHROPIC_API_KEY") or _configured("ANTHROPIC_AUTH_TOKEN"),
        "anthropic_proxy_base": _configured("ANTHROPIC_BASE_URL"),
        "google_direct": _configured("GOOGLE_API_KEY") or _configured("GEMINI_API_KEY"),
        "yookassa": bool(settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY),
        "smtp": smtp_ready,
        "web_search": bool(
            str(os.environ.get("WEB_SEARCH_ENABLED", "") or getattr(settings, "WEB_SEARCH_ENABLED", "")).lower() in {"1", "true", "yes", "on"}
            and (os.environ.get("WEB_SEARCH_PROVIDER") or str(getattr(settings, "WEB_SEARCH_PROVIDER", "") or ""))
        ),
    }
    ai_gateway_ready = (
        providers["routerai"]
        or providers["claudehub"]
        or providers["ruapi_openai_compatible"]
        or providers["openai_direct_or_compatible"]
        or providers["anthropic_native"]
    )
    missing_required = []
    if not ai_gateway_ready:
        missing_required.append("ai_gateway")
    if not providers["yookassa"]:
        missing_required.append("yookassa")
    if not providers["smtp"]:
        missing_required.append("smtp")
    if not postgres_mode:
        missing_required.append("postgresql")
    if settings.ENVIRONMENT.lower() in {"production", "prod"} and settings.AUTO_CREATE_DB_TABLES:
        missing_required.append("auto_create_db_tables_disabled")
    if settings.ENVIRONMENT.lower() in {"production", "prod"} and not auth_secret_configured:
        missing_required.append("auth_secret")
    if not service_template_matches_runtime:
        missing_required.append("service_template_execstart")
    if not service_unit_installed:
        missing_required.append("service_unit_installed")
    if not service_unit_matches_runtime:
        missing_required.append("service_unit_execstart")
    if not single_runtime_process:
        missing_required.append("single_runtime_process")

    return {
        "ready_for_paid_release": not missing_required,
        "missing_required": missing_required,
        "providers": providers,
        "ai_gateway": {
            "ready": ai_gateway_ready,
            "primary": (
                "routerai"
                if providers["routerai"]
                else (
                    "ruapi"
                    if providers["ruapi_openai_compatible"]
                    else (
                        "claudehub"
                        if providers["claudehub"]
                        else ("anthropic" if providers["anthropic_native"] else "openai")
                    )
                )
            ),
            "temporary_provider_in_use": bool(providers["ruapi_openai_compatible"] and not providers["routerai"] and not providers["claudehub"]),
        },
        "auth": {
            "secret_configured": auth_secret_configured,
            "password_reset_backend_present": True,
        },
        "smtp": {
            "configured": smtp_ready,
            "host_present": _any_configured("SMTP_HOST"),
            "from_email_present": _any_configured("SMTP_FROM_EMAIL"),
        },
        "database": {
            "postgres_mode": postgres_mode,
            "database_url_family": "postgresql" if postgres_mode else "non-postgresql",
        },
        "service": {
            "service_template_path": str(template_service_unit_path),
            "service_template_matches_runtime": service_template_matches_runtime,
            "service_unit_path": str(deployed_service_unit_path),
            "service_unit_installed": service_unit_installed,
            "service_unit_matches_runtime": service_unit_matches_runtime,
            "runtime_process_count": runtime_process_count,
            "single_runtime_process": single_runtime_process,
        },
        "environment": settings.ENVIRONMENT,
        "auto_create_db_tables": settings.AUTO_CREATE_DB_TABLES,
    }
