#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="${PROJECT_ROOT}/deploy/systemd/searxng.service"
UNIT_DST="/etc/systemd/system/searxng.service"

if [[ ! -f "${UNIT_SRC}" ]]; then
  echo "Unit source not found: ${UNIT_SRC}" >&2
  exit 1
fi

echo "Installing ${UNIT_DST} from ${UNIT_SRC}"
install -m 0644 "${UNIT_SRC}" "${UNIT_DST}"

echo "Reloading systemd"
systemctl daemon-reload

echo "Enabling and starting searxng.service"
systemctl enable --now searxng.service

echo "Status:"
systemctl --no-pager --full status searxng.service
