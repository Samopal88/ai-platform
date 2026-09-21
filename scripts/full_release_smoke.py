from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


CHECKS = [
    {
        "name": "compile_smoke_scripts",
        "cmd": [
            sys.executable,
            "-m",
            "py_compile",
            "scripts/auth_account_smoke.py",
            "scripts/release_surface_smoke.py",
            "scripts/negative_limit_smoke.py",
            "scripts/storage_accounting_smoke.py",
            "scripts/postgres_rehearsal_check.py",
        ],
    },
    {
        "name": "launch_assets_present",
        "cmd": [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "root = Path.cwd(); "
                "required = ["
                "'deploy/systemd/ai-platform.service', "
                "'scripts/install_ai_platform_service.sh', "
                "'docs/ops/SOFT_LAUNCH_PHASES_2026-05-01.md'"
                "]; "
                "missing = [item for item in required if not (root / item).exists()]; "
                "print({'ok': not missing, 'missing': missing}); "
                "raise SystemExit(0 if not missing else 1)"
            ),
        ],
    },
    {
        "name": "production_env_audit",
        "cmd": [sys.executable, "scripts/production_env_audit.py"],
    },
    {
        "name": "runtime_git_audit",
        "cmd": [sys.executable, "scripts/runtime_git_audit.py"],
    },
    {
        "name": "release_gate_report",
        "cmd": [sys.executable, "scripts/release_gate_report.py"],
    },
    {
        "name": "auth_account",
        "cmd": [sys.executable, "scripts/auth_account_smoke.py"],
    },
    {
        "name": "password_reset",
        "cmd": [sys.executable, "scripts/password_reset_smoke.py"],
    },
    {
        "name": "release_surface",
        "cmd": [sys.executable, "scripts/release_surface_smoke.py"],
    },
    {
        "name": "provider_readiness",
        "cmd": [sys.executable, "scripts/provider_readiness_smoke.py"],
    },
    {
        "name": "model_catalog",
        "cmd": [sys.executable, "scripts/model_catalog_smoke.py"],
    },
    {
        "name": "negative_limits",
        "cmd": [sys.executable, "scripts/negative_limit_smoke.py"],
    },
    {
        "name": "storage_accounting",
        "cmd": [sys.executable, "scripts/storage_accounting_smoke.py"],
    },
    {
        "name": "postgres_rehearsal_preflight",
        "cmd": [sys.executable, "scripts/postgres_rehearsal_check.py"],
        "allow_not_ready": True,
    },
]


def parse_json_output(output: str):
    output = output.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output[-2000:]


def run_check(check: dict) -> dict:
    started = time.monotonic()
    completed = subprocess.run(
        check["cmd"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload = parse_json_output(stdout)
    ok = completed.returncode == 0
    if check.get("allow_not_ready") and isinstance(payload, dict):
        ok = completed.returncode == 0

    return {
        "name": check["name"],
        "ok": ok,
        "returncode": completed.returncode,
        "duration_ms": duration_ms,
        "payload": payload,
        "stderr": stderr[-2000:] if stderr else "",
    }


results = [run_check(check) for check in CHECKS]
failed = [item for item in results if not item["ok"]]

print(json.dumps({
    "ok": not failed,
    "root": str(ROOT),
    "checks": results,
}, ensure_ascii=False, indent=2))

if failed:
    raise SystemExit(1)
