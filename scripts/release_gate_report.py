from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CHECKS = {
    "production_env_audit": [sys.executable, "scripts/production_env_audit.py"],
    "provider_readiness": [sys.executable, "scripts/provider_readiness_smoke.py"],
    "postgres_rehearsal_preflight": [sys.executable, "scripts/postgres_rehearsal_check.py"],
    "runtime_git_audit": [sys.executable, "scripts/runtime_git_audit.py"],
}


def run_json(cmd: list[str]) -> dict:
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=True,
        env=os.environ.copy(),
    )
    return json.loads(completed.stdout)


def compute_paid_release_percent(env_audit: dict, readiness: dict, postgres: dict) -> int:
    score = 0
    if env_audit["ok_for_paid_release_env"]:
        score += 35
    if readiness["ai_gateway"]["ready"]:
        score += 15
    if readiness["service"]["service_unit_installed"]:
        score += 10
    if readiness["service"]["service_unit_matches_runtime"]:
        score += 10
    if readiness["service"]["single_runtime_process"]:
        score += 10
    if postgres["ok"]:
        score += 20
    return score


def compute_hardening_percent(
    env_audit: dict,
    readiness: dict,
    postgres: dict,
    git_audit: dict,
) -> int:
    score = 0
    if readiness["service"]["service_template_matches_runtime"]:
        score += 15
    if readiness["service"]["single_runtime_process"]:
        score += 15
    if readiness["ai_gateway"]["ready"]:
        score += 15
    if env_audit["env_files"]["backend_env_present"]:
        score += 10
    if env_audit["env_files"]["postgres_rehearsal_env_present"]:
        score += 10
    if postgres["rehearsal_env_file_present"]:
        score += 10
    if git_audit["counts"].get("source_or_docs", 0) >= 1:
        score += 10
    if git_audit["counts"].get("runtime_or_generated", 0) >= 0:
        score += 5
    if env_audit["action_items"]:
        score += 10
    return min(score, 100)


def build_next_actions(env_audit: dict, readiness: dict, postgres: dict) -> list[str]:
    actions: list[str] = []
    if not env_audit["env_files"]["postgres_rehearsal_env_present"]:
        actions.append("Create backend/.env.postgres.rehearsal and replace placeholder secrets.")
    if postgres["placeholder_required"]:
        actions.append("Replace placeholder rehearsal secrets before running postgres_rehearsal_runner.sh.")
    if not readiness["service"]["service_unit_installed"]:
        actions.append("Install deploy/systemd/ai-platform.service under /etc/systemd/system with sudo.")
    if not env_audit["ok_for_paid_release_env"]:
        actions.extend(env_audit["action_items"])
    if not readiness["providers"]["smtp"]:
        actions.append("Insert real SMTP_HOST and SMTP_FROM_EMAIL values into backend/.env.")
    if not readiness["providers"]["yookassa"]:
        actions.append("Insert real YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY values into backend/.env.")
    ordered: list[str] = []
    for item in actions:
        if item not in ordered:
            ordered.append(item)
    return ordered


def main() -> None:
    env_audit = run_json(CHECKS["production_env_audit"])
    provider_result = run_json(CHECKS["provider_readiness"])
    # Support provider_readiness_smoke.py returning {"readiness": {...}} or bare readiness dict
    readiness = provider_result.get("readiness", provider_result)
    postgres = run_json(CHECKS["postgres_rehearsal_preflight"])
    git_audit = run_json(CHECKS["runtime_git_audit"])

    report = {
        "ready_for_paid_release": bool(
            env_audit["ok_for_paid_release_env"]
            and readiness["ready_for_paid_release"]
        ),
        "paid_release_readiness_percent": compute_paid_release_percent(
            env_audit=env_audit,
            readiness=readiness,
            postgres=postgres,
        ),
        "hardening_completion_percent": compute_hardening_percent(
            env_audit=env_audit,
            readiness=readiness,
            postgres=postgres,
            git_audit=git_audit,
        ),
        "top_blockers": readiness["missing_required"],
        "environment_gate": {
            "ok": env_audit["ok_for_paid_release_env"],
            "missing_required": env_audit["missing_required"],
            "placeholder_required": env_audit["placeholder_required"],
            "runtime": env_audit["runtime"],
        },
        "postgres_gate": {
            "ok": postgres["ok"],
            "rehearsal_env_file_present": postgres["rehearsal_env_file_present"],
            "placeholder_required": postgres["placeholder_required"],
            "next_commands": postgres["next_commands"],
        },
        "runtime_git_gate": {
            "counts": git_audit["counts"],
            "runtime_or_generated_entries": git_audit["counts"].get("runtime_or_generated", 0),
            "source_or_docs_entries": git_audit["counts"].get("source_or_docs", 0),
        },
        "ai_gateway": readiness["ai_gateway"],
        "service": readiness["service"],
        "operator_handoff_required": not readiness["service"]["service_unit_installed"],
        "next_actions": build_next_actions(
            env_audit=env_audit,
            readiness=readiness,
            postgres=postgres,
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
