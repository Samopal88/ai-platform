# SearxNG Operations

## Overview
This project uses SearxNG as the first web-search provider in `WEB_SEARCH_PROVIDER=auto`.

Provider chain in auto mode:
1. `searxng`
2. `yandex_xml`
3. `serpapi`
4. `serper`

If SearxNG is unhealthy, backend skips it quickly and falls through to `yandex_xml` without waiting for full search timeout on every request.

## Systemd service

Unit template in repo:
- `deploy/systemd/searxng.service`

Runtime unit location:
- `/etc/systemd/system/searxng.service`

Install and start:
```bash
sudo /opt/ai-workspace/storage/projects/ai-platform/scripts/install_searxng_service.sh
```

Manual commands:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now searxng.service
sudo systemctl status searxng.service
```

## Logs and restart

Service logs:
```bash
sudo journalctl -u searxng.service -f
```

Restart service:
```bash
sudo systemctl restart searxng.service
```

Stop service:
```bash
sudo systemctl stop searxng.service
```

## Health check

Script:
- `scripts/check_searxng.py`

Run:
```bash
/opt/ai-workspace/storage/projects/ai-platform/scripts/check_searxng.py
```

Environment overrides:
- `SEARXNG_URL` (default: `http://127.0.0.1:8080`)
- `SEARXNG_HEALTH_TIMEOUT` (default: `0.8`)

Exit codes:
- `0` healthy
- non-zero unhealthy

## Fast fallback behavior

Backend file:
- `backend/app/services/web_search_service.py`

Key behavior:
- quick health probe for SearxNG with short timeout
- cached state to avoid repeated slow failures
- down state TTL prevents wasting ~5s provider timeout per request while SearxNG is unavailable

Tunable env vars:
- `SEARXNG_HEALTH_TIMEOUT` (default `0.6`)
- `SEARXNG_HEALTH_TTL_UP` (default `30`)
- `SEARXNG_HEALTH_TTL_DOWN` (default `10`)
