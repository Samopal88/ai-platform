from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
REHEARSAL_ENV_FILE = Path(
    os.environ.get(
        "POSTGRES_REHEARSAL_ENV_FILE",
        str(BACKEND_DIR / ".env.postgres.rehearsal"),
    )
)

REQUIRED_KEYS = [
    "ENVIRONMENT",
    "AUTO_CREATE_DB_TABLES",
    "DATABASE_URL",
    "AUTH_TOKEN_SECRET",
    "SECRET_KEY",
]

RECOMMENDED_KEYS = [
    "PUBLIC_BASE_URL",
    "RUAPI_API_KEY",
    "RUAPI_BASE_URL",
    "SMTP_HOST",
    "SMTP_FROM_EMAIL",
    "YOOKASSA_SHOP_ID",
    "YOOKASSA_SECRET_KEY",
]

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


def is_placeholder(value: str) -> bool:
    lower = value.strip().lower()
    if not lower:
        return True
    return any(marker in lower for marker in PLACEHOLDER_MARKERS)


def build_result() -> dict:
    values = parse_env_file(REHEARSAL_ENV_FILE)
    database_url = values.get("DATABASE_URL", "")
    env_name = values.get("ENVIRONMENT", "")
    auto_create = values.get("AUTO_CREATE_DB_TABLES", "")

    missing_required = [key for key in REQUIRED_KEYS if not values.get(key, "").strip()]
    placeholder_required = [
        key for key in REQUIRED_KEYS if values.get(key, "").strip() and is_placeholder(values[key])
    ]
    recommended_missing = [key for key in RECOMMENDED_KEYS if not values.get(key, "").strip()]

    checks = {
        "env_file_present": REHEARSAL_ENV_FILE.exists(),
        "environment_production": env_name.lower() in {"production", "prod"},
        "auto_create_db_tables_disabled": auto_create.lower() == "false",
        "database_url_is_postgres": database_url.startswith("postgresql://")
        or database_url.startswith("postgresql+psycopg://"),
        "database_name_is_rehearsal_like": "_rehearsal" in database_url,
        "required_present": not missing_required,
        "required_placeholders_cleared": not placeholder_required,
    }

    next_commands = [
        "cd /opt/ai-workspace/storage/projects/ai-platform",
        "python3 scripts/prepare_postgres_rehearsal_env.py",
        "edit backend/.env.postgres.rehearsal with real PostgreSQL credentials and non-placeholder secrets",
        "python3 scripts/postgres_rehearsal_check.py",
        "bash scripts/postgres_rehearsal_runner.sh",
    ]

    return {
        "ok": all(checks.values()),
        "rehearsal_env_file_present": REHEARSAL_ENV_FILE.exists(),
        "rehearsal_env_file": str(REHEARSAL_ENV_FILE),
        "checks": checks,
        "missing_required": missing_required,
        "placeholder_required": placeholder_required,
        "recommended_missing": recommended_missing,
        "database_url_family": (
            "postgresql"
            if checks["database_url_is_postgres"]
            else "not-postgresql-or-empty"
        ),
        "next_commands": next_commands,
    }


result = build_result()
print(json.dumps(result, ensure_ascii=False, indent=2))

if not result["ok"]:
    raise SystemExit(0)
