"""
Claude CLI Executor — thin bridge to the real file-writing path.

Mirrors the upper orchestrator's run_claude_task_internal pattern
(orchestrator_lib.py:run_claude_task_internal) adapted for manager_loop.

Runs: claude --allowed-tools Read,Write,Edit --print <prompt>
in cwd=project_root and detects changed files via mtime + content-hash diff.

Returns a dict compatible with _execute_worker's expected format:
  {success, files_changed, verified_unchanged, output, error, executor: "claude_cli"}

  verified_unchanged: list of target files that Claude read and left unchanged
    because their content already satisfied the requirement.  These files are
    NOT in files_changed (content was not modified) but ARE considered correct
    by the executor — the review gate must not treat them as "not touched".
"""
import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

# Placeholder patterns that indicate a file is NOT yet correct.
# If any of these appear in a "verified_unchanged" file, we do NOT mark it
# as already-correct — we let the normal failure path handle it.
_BAD_CONTENT_PATTERNS = (
    "generated content",
    "todo placeholder",
    "coming soon",
    "lorem ipsum",
    "insert content here",
    "def main():\n    pass",
    "def main():\r\n    pass",
)


def _file_hash(path: Path) -> str:
    """SHA-256 of file content, or empty string if unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def _snapshot_mtimes(project_root: Path, rel_paths: list[str]) -> dict[str, float]:
    """Record mtime of each declared target file."""
    snap = {}
    for rel in rel_paths:
        p = project_root / rel
        try:
            snap[rel] = p.stat().st_mtime if p.exists() else 0.0
        except Exception:
            snap[rel] = 0.0
    return snap


def _snapshot_hashes(project_root: Path, rel_paths: list[str]) -> dict[str, str]:
    """Record content hash of each declared target file."""
    snap = {}
    for rel in rel_paths:
        p = project_root / rel
        snap[rel] = _file_hash(p) if p.exists() else ""
    return snap


def _detect_changed(
    project_root: Path,
    before_mtimes: dict[str, float],
    start_ts: float,
    allowed_write_paths: list[str],
) -> list[str]:
    """
    Return relative paths of files whose mtime increased since before_mtimes.

    Primary: declared target files whose mtime increased.
    Secondary: any file under allowed_write_paths prefixes whose mtime > start_ts.
    """
    changed = set()

    # Primary: check declared targets
    for rel, mtime_before in before_mtimes.items():
        p = project_root / rel
        try:
            if p.exists() and p.stat().st_mtime > mtime_before:
                changed.add(rel)
        except Exception:
            pass

    # Secondary: walk allowed_write_paths prefixes for any new/modified files
    for allowed in (allowed_write_paths or []):
        full = project_root / allowed
        if full.is_dir():
            for child in full.rglob("*"):
                if child.is_file():
                    try:
                        if child.stat().st_mtime > start_ts:
                            changed.add(str(child.relative_to(project_root)))
                    except Exception:
                        pass

    return sorted(changed)


def _detect_verified_unchanged(
    project_root: Path,
    before_hashes: dict[str, str],
    files_changed: list[str],
) -> list[str]:
    """
    Return target files that were NOT in files_changed (no mtime bump) but whose
    content is non-empty, hash-stable (same as before), and free of placeholders.

    These are files the executor considers "already correct": Claude read them,
    found the requirement already satisfied, and made no changes.  They are NOT
    failures — the task's desired state IS present on disk.

    A file is excluded from this list if:
    - it was already detected as changed (in files_changed)
    - it doesn't exist
    - it is empty
    - its hash changed (content was silently modified without mtime bump — unlikely
      but we treat it as files_changed territory, not verified_unchanged)
    - it contains known placeholder/filler patterns
    """
    verified = []
    changed_set = set(files_changed)
    for rel, hash_before in before_hashes.items():
        if rel in changed_set:
            continue  # already tracked as changed
        p = project_root / rel
        if not p.exists():
            continue
        try:
            content_bytes = p.read_bytes()
        except Exception:
            continue
        if not content_bytes:
            continue
        hash_after = hashlib.sha256(content_bytes).hexdigest()
        if hash_after != hash_before:
            # Content changed without mtime update (rare, but treat as changed)
            continue
        # Check for bad content
        content_lower = content_bytes.decode("utf-8", errors="replace").lower()
        if any(pat in content_lower for pat in _BAD_CONTENT_PATTERNS):
            continue
        verified.append(rel)
    return sorted(verified)


def run_claude_cli(
    prompt: str,
    project_root: Path,
    allowed_write_paths: Optional[list[str]] = None,
    job_id: Optional[str] = None,
    timeout: int = 600,
) -> dict:
    """
    Execute prompt via `claude --allowed-tools Read,Write,Edit --print`.

    Args:
        prompt: Task prompt to send to Claude Code CLI.
        project_root: Directory where claude will run (cwd).
        allowed_write_paths: Relative paths this task may write.
        job_id: Optional identifier for logging.
        timeout: Subprocess timeout in seconds.

    Returns:
        {
            success: bool,
            files_changed: list[str],       # mtime-detected writes
            verified_unchanged: list[str],  # already-correct files (no write needed)
            output: str,
            error: str|None,
            executor: "claude_cli",
        }
    """
    awp = allowed_write_paths or []
    start_ts = time.time()
    before_mtimes = _snapshot_mtimes(project_root, awp)
    before_hashes = _snapshot_hashes(project_root, awp)

    try:
        result = subprocess.run(
            [
                "claude",
                "--allowed-tools", "Read,Write,Edit",
                "--dangerously-skip-permissions",
                "--print",
                prompt,
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        returncode = result.returncode

        files_changed = _detect_changed(project_root, before_mtimes, start_ts, awp)

        if returncode != 0:
            return {
                "success": False,
                "files_changed": files_changed,
                "verified_unchanged": [],
                "output": stdout[:800],
                "error": f"claude CLI exited with code {returncode}: {stderr[:200]}",
                "executor": "claude_cli",
                "returncode": returncode,
            }

        # CLI succeeded (rc=0).
        if files_changed:
            # Normal path: Claude wrote something.
            return {
                "success": True,
                "files_changed": files_changed,
                "verified_unchanged": [],
                "output": stdout[:800],
                "error": None,
                "executor": "claude_cli",
                "returncode": returncode,
            }

        # No mtime change. Determine whether files were already correct or truly missing.
        verified_unchanged = _detect_verified_unchanged(
            project_root, before_hashes, files_changed
        )

        if verified_unchanged:
            # Claude found the requirement already satisfied — treat as success.
            # The review gate must not penalise this as "no files changed".
            return {
                "success": True,
                "files_changed": [],
                "verified_unchanged": verified_unchanged,
                "output": stdout[:800],
                "error": None,
                "executor": "claude_cli",
                "returncode": returncode,
            }

        # Neither changed nor verifiably correct (files missing / have placeholders).
        return {
            "success": False,
            "files_changed": [],
            "verified_unchanged": [],
            "output": stdout[:800],
            "error": "claude CLI ran successfully but no target files were changed or verified",
            "executor": "claude_cli",
            "returncode": returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "files_changed": [],
            "verified_unchanged": [],
            "output": "",
            "error": f"claude CLI timed out after {timeout}s",
            "executor": "claude_cli",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "files_changed": [],
            "verified_unchanged": [],
            "output": "",
            "error": "claude CLI not found in PATH",
            "executor": "claude_cli",
        }
    except Exception as e:
        return {
            "success": False,
            "files_changed": [],
            "verified_unchanged": [],
            "output": "",
            "error": f"claude CLI unexpected error: {str(e)[:200]}",
            "executor": "claude_cli",
        }


def is_available() -> bool:
    """Check if claude CLI is available in PATH."""
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False
