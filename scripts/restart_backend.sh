#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/ai-workspace/storage/projects/ai-platform"
BACKEND_DIR="$ROOT/backend"
LOG_FILE="/opt/ai-workspace/logs/ai-platform.log"
ENV_FILE="${BACKEND_ENV_FILE:-$BACKEND_DIR/.env}"

mkdir -p /opt/ai-workspace/logs

cd "$BACKEND_DIR"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

HOST="${BACKEND_HOST:-0.0.0.0}"
PORT="${BACKEND_PORT:-8000}"
PATTERN="uvicorn app.main:app --host $HOST --port $PORT"
START_CMD=(/opt/ai-workspace/.venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT")

pkill -f "$PATTERN" || true

for _ in $(seq 1 30); do
  if ! pgrep -f "$PATTERN" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

for _ in $(seq 1 30); do
  if ! ss -ltn "( sport = :$PORT )" | grep -q ":$PORT"; then
    break
  fi
  sleep 1
done

nohup "${START_CMD[@]}" >>"$LOG_FILE" 2>&1 &

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    curl -fsS "http://127.0.0.1:$PORT/health"
    exit 0
  fi
  sleep 1
done

echo "Backend did not become healthy after restart" >&2
tail -n 40 "$LOG_FILE" >&2 || true
exit 1
