#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/ai-workspace/storage/projects/ai-platform"
BACKEND_DIR="$ROOT/backend"
REHEARSAL_ENV_FILE="${POSTGRES_REHEARSAL_ENV_FILE:-$BACKEND_DIR/.env.postgres.rehearsal}"
PYTHON_BIN="${PYTHON_BIN:-/opt/ai-workspace/.venv/bin/python}"

if [[ ! -f "$REHEARSAL_ENV_FILE" ]]; then
  echo "Missing rehearsal env file: $REHEARSAL_ENV_FILE" >&2
  echo "Copy backend/.env.postgres.rehearsal.example to backend/.env.postgres.rehearsal and fill placeholders." >&2
  exit 1
fi

cd "$ROOT"
$PYTHON_BIN scripts/postgres_rehearsal_check.py >/tmp/postgres_rehearsal_check.json
cat /tmp/postgres_rehearsal_check.json

set -a
# shellcheck disable=SC1090
source "$REHEARSAL_ENV_FILE"
set +a

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required in $REHEARSAL_ENV_FILE" >&2
  exit 1
fi

if [[ "$DATABASE_URL" != postgresql://* && "$DATABASE_URL" != postgresql+psycopg://* ]]; then
  echo "DATABASE_URL must point to PostgreSQL for the rehearsal" >&2
  exit 1
fi

if [[ "${ENVIRONMENT:-}" != "production" && "${ENVIRONMENT:-}" != "prod" ]]; then
  echo "ENVIRONMENT must be production/prod in the rehearsal env" >&2
  exit 1
fi

if [[ "${AUTO_CREATE_DB_TABLES:-}" != "false" ]]; then
  echo "AUTO_CREATE_DB_TABLES must be false in the rehearsal env" >&2
  exit 1
fi

cd "$ROOT"
BACKEND_ENV_FILE="$REHEARSAL_ENV_FILE" $PYTHON_BIN scripts/production_env_audit.py

cd "$BACKEND_DIR"
$PYTHON_BIN -m alembic upgrade head
$PYTHON_BIN -m compileall -q app

cd "$ROOT"
BACKEND_ENV_FILE="$REHEARSAL_ENV_FILE" bash scripts/restart_backend.sh
SMOKE_BASE_URL="http://127.0.0.1:${BACKEND_PORT:-8000}" $PYTHON_BIN scripts/auth_account_smoke.py
SMOKE_BASE_URL="http://127.0.0.1:${BACKEND_PORT:-8000}" $PYTHON_BIN scripts/release_surface_smoke.py
SMOKE_BASE_URL="http://127.0.0.1:${BACKEND_PORT:-8000}" $PYTHON_BIN scripts/negative_limit_smoke.py
SMOKE_BASE_URL="http://127.0.0.1:${BACKEND_PORT:-8000}" $PYTHON_BIN scripts/storage_accounting_smoke.py
SMOKE_BASE_URL="http://127.0.0.1:${BACKEND_PORT:-8000}" $PYTHON_BIN scripts/provider_readiness_smoke.py
BACKEND_ENV_FILE="$REHEARSAL_ENV_FILE" $PYTHON_BIN scripts/release_gate_report.py
