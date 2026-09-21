#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "AI Platform is not installed. Run: bash scripts/install.sh" >&2
  exit 1
fi

exec "$VENV_PYTHON" "$PROJECT_DIR/scripts/ai_platform.py" service-install
