from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ai_platform_installer", ROOT / "scripts" / "ai_platform.py"
)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_default_config_generates_separate_secrets():
    values = installer.default_config({})
    assert len(values["SECRET_KEY"]) >= 32
    assert len(values["AUTH_TOKEN_SECRET"]) >= 32
    assert values["SECRET_KEY"] != values["AUTH_TOKEN_SECRET"]
    assert values["PROJECT_ROOT"] == str(ROOT)


def test_write_and_read_env_round_trip(tmp_path):
    target = tmp_path / ".env"
    expected = {
        "ENVIRONMENT": "development",
        "SECRET_KEY": "a" * 48,
        "AUTH_TOKEN_SECRET": "b" * 48,
        "SMTP_FROM_NAME": "AI Platform",
        "OPENAI_API_KEY": "value-with-#-and spaces",
    }
    installer.write_env(expected, target)
    assert installer.read_env(target) == expected


def test_parser_accepts_noninteractive_setup():
    args = installer.build_parser().parse_args(
        ["setup", "--yes", "--skip-install", "--provider", "none"]
    )
    assert args.command == "setup"
    assert args.yes is True
    assert args.skip_install is True


def test_systemd_unit_uses_current_project_paths():
    unit = installer.systemd_unit()
    assert str(ROOT / "backend") in unit
    assert str(ROOT / "scripts" / "ai_platform.py") in unit
    assert "/opt/ai-workspace" not in unit
