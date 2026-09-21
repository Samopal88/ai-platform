#!/usr/bin/env python3
"""
Compact SearxNG health check.

Exit codes:
  0 - healthy
  1 - unhealthy / timeout / request error
"""
from __future__ import annotations

import os
import sys
import time

import requests


def main() -> int:
    base_url = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")
    timeout = float(os.environ.get("SEARXNG_HEALTH_TIMEOUT", "0.8"))
    url = f"{base_url}/"
    started = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if 200 <= resp.status_code < 500:
            print(f"OK searxng status={resp.status_code} latency_ms={elapsed_ms} url={base_url}")
            return 0
        print(f"DOWN searxng status={resp.status_code} latency_ms={elapsed_ms} url={base_url}")
        return 1
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        print(f"DOWN searxng error={type(exc).__name__} latency_ms={elapsed_ms} url={base_url}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
