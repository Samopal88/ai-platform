"""
Regression tests for Supervisor.infer_dod_from_task().
Run from PROJECT_ROOT/backend:
    python -m pytest ../tests/test_supervisor.py -v
No network or LLM calls required.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.supervisor import Supervisor


def make_supervisor(tmp_path: Path) -> Supervisor:
    return Supervisor(project_root=tmp_path)


# ---------------------------------------------------------------------------
# expected_outputs must always be empty
# ---------------------------------------------------------------------------

def test_expected_outputs_always_empty(tmp_path):
    sup = make_supervisor(tmp_path)
    dod = sup.infer_dod_from_task("create sandbox/hello.py with hello world")
    assert dod.expected_outputs == [], "expected_outputs must be empty to avoid false BLOCKED"


def test_expected_outputs_empty_for_route_task(tmp_path):
    sup = make_supervisor(tmp_path)
    dod = sup.infer_dod_from_task("add GET /api/status route to backend/app/api/jobs.py")
    assert dod.expected_outputs == []


# ---------------------------------------------------------------------------
# required_files inference
# ---------------------------------------------------------------------------

def test_infers_quoted_path(tmp_path):
    sup = make_supervisor(tmp_path)
    dod = sup.infer_dod_from_task('create file `sandbox/utils.py` with helper functions')
    assert any("sandbox/utils.py" in f for f in dod.required_files), \
        f"expected sandbox/utils.py in {dod.required_files}"


def test_infers_tests_path(tmp_path):
    sup = make_supervisor(tmp_path)
    dod = sup.infer_dod_from_task("create tests/test_jobs.py with smoke tests")
    assert any("test_jobs.py" in f for f in dod.required_files), \
        f"expected test_jobs.py in {dod.required_files}"


def test_infers_frontend_path(tmp_path):
    sup = make_supervisor(tmp_path)
    dod = sup.infer_dod_from_task("add frontend/components/Button.js with a button component")
    assert any("Button.js" in f for f in dod.required_files), \
        f"expected Button.js in {dod.required_files}"


# ---------------------------------------------------------------------------
# No pollution in task_id or description
# ---------------------------------------------------------------------------

def test_no_pollution_in_description(tmp_path):
    sup = make_supervisor(tmp_path)
    polluted = (
        "## Self-Correction Attempt 2\n"
        "### Original Task\ncreate sandbox/clean.py\n"
        "### Required Fixes\nsome fix"
    )
    dod = sup.infer_dod_from_task(polluted)
    for marker in ("## Self-Correction", "## REQUIRED FIXES", "Attempt 2 to fix"):
        assert marker not in dod.description, f"Pollution marker found in description: {marker}"
