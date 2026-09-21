from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
ENV_FILE = Path(os.environ.get("BACKEND_ENV_FILE", str(BACKEND_DIR / ".env")))
POSTGRES_REHEARSAL_ENV = Path(
    os.environ.get(
        "POSTGRES_REHEARSAL_ENV_FILE",
        str(BACKEND_DIR / ".env.postgres.rehearsal"),
    )
)

REQUIRED_FOR_PAID_RELEASE = {
    "auth": ["AUTH_TOKEN_SECRET"],
    "database": ["DATABASE_URL"],
    "billing": ["YOOKASSA_SHOP_ID", "YOOKASSA_SECRET_KEY"],
    "smtp": ["SMTP_HOST", "SMTP_FROM_EMAIL"],
}

RECOMMENDED = {
    "runtime": ["ENVIRONMENT", "AUTO_CREATE_DB_TABLES", "PUBLIC_BASE_URL"],
    "ai_gateway": ["RUAPI_API_KEY", "RUAPI_BASE_URL"],
    "search": ["WEB_SEARCH_ENABLED", "WEB_SEARCH_PROVIDER"],
}

PLACEHOLDER_MARKERS = (
    "replace-with",
    "changeme",
    "example",
    "your-",
    "<",
    ">",
)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def effective_value(name: str, file_values: dict[str, str]) -> str:
    env_value = os.environ.get(name)
    if env_value is not None and env_value.strip():
        return env_value.strip()
    return file_values.get(name, "").strip()


def has_value(name: str, file_values: dict[str, str]) -> bool:
    return bool(effective_value(name, file_values))


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def category_report(groups: dict[str, list[str]], file_values: dict[str, str]) -> dict[str, dict[str, bool]]:
    return {
        group: {name: has_value(name, file_values) for name in names}
        for group, names in groups.items()
    }


def build_action_items(
    missing_required: list[str],
    placeholder_required: list[str],
    env_name: str,
    auto_create: str,
    database_url: str,
    rehearsal_present: bool,
) -> list[str]:
    items: list[str] = []
    if missing_required:
        items.append("Populate the missing required keys in backend/.env before paid release.")
    if placeholder_required:
        items.append("Replace placeholder secret values in backend/.env with real production secrets.")
    if not rehearsal_present:
        items.append("Create backend/.env.postgres.rehearsal and prepare a PostgreSQL rehearsal run.")
    if env_name.lower() not in {"production", "prod"}:
        items.append("Set ENVIRONMENT=production in the active backend env file.")
    if auto_create.lower() != "false":
        items.append("Set AUTO_CREATE_DB_TABLES=false for production-safe runtime behavior.")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        items.append("Move DATABASE_URL to PostgreSQL before paid release.")
    if not items:
        items.append("Environment gate is fully configured for paid release.")
    return items


def load_report() -> dict:
    active_values = parse_env_file(ENV_FILE)
    rehearsal_values = parse_env_file(POSTGRES_REHEARSAL_ENV)

    required = category_report(REQUIRED_FOR_PAID_RELEASE, active_values)
    recommended = category_report(RECOMMENDED, active_values)

    database_url = effective_value("DATABASE_URL", active_values)
    env_name = effective_value("ENVIRONMENT", active_values)
    auto_create = effective_value("AUTO_CREATE_DB_TABLES", active_values)

    missing_required = [
        name
        for values in required.values()
        for name, configured in values.items()
        if not configured
    ]
    placeholder_required = [
        name
        for names in REQUIRED_FOR_PAID_RELEASE.values()
        for name in names
        if has_value(name, active_values) and is_placeholder(effective_value(name, active_values))
    ]

    rehearsal_missing = [
        name
        for name in ("DATABASE_URL", "AUTH_TOKEN_SECRET", "SECRET_KEY")
        if not rehearsal_values.get(name, "").strip()
    ]

    ok_for_paid_release_env = (
        not missing_required
        and not placeholder_required
        and env_name.lower() in {"production", "prod"}
        and auto_create.lower() == "false"
        and database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    )

    report = {
        "ok_for_paid_release_env": ok_for_paid_release_env,
        "env_files": {
            "backend_env_present": ENV_FILE.exists(),
            "backend_env_file": str(ENV_FILE),
            "postgres_rehearsal_env_present": POSTGRES_REHEARSAL_ENV.exists(),
            "postgres_rehearsal_env_file": str(POSTGRES_REHEARSAL_ENV),
        },
        "required_for_paid_release": required,
        "recommended": recommended,
        "runtime": {
            "environment": env_name or None,
            "auto_create_db_tables": auto_create or None,
            "database_url_family": (
                "postgresql"
                if database_url.startswith(("postgresql://", "postgresql+psycopg://"))
                else ("sqlite" if database_url.startswith("sqlite") else "missing_or_other")
            ),
        },
        "rehearsal": {
            "env_present": POSTGRES_REHEARSAL_ENV.exists(),
            "missing_core_values": rehearsal_missing,
        },
        "missing_required": missing_required,
        "placeholder_required": placeholder_required,
        "action_items": build_action_items(
            missing_required=missing_required,
            placeholder_required=placeholder_required,
            env_name=env_name,
            auto_create=auto_create,
            database_url=database_url,
            rehearsal_present=POSTGRES_REHEARSAL_ENV.exists(),
        ),
        "notes": [
            "Paid release requires real secrets in backend/.env, not just .env.example placeholders.",
            "RuAPI is the preferred AI gateway path when RUAPI_API_KEY and RUAPI_BASE_URL are set.",
            "PostgreSQL rehearsal can use backend/.env.postgres.rehearsal before touching the primary runtime .env.",
        ],
    }
    return report


if __name__ == "__main__":
    print(json.dumps(load_report(), ensure_ascii=False, indent=2))
