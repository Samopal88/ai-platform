"""
Smoke verification for project-scoped file handling.

Exercises the full file API on both localhost and the public nginx endpoint:
  POST   /api/projects                                  — create project
  POST   /api/projects/{project_id}/files               — upload
  GET    /api/projects/{project_id}/files               — list + persistence
  GET    /api/projects/{project_id}/files/{id}/download — download
  DELETE /api/projects/{project_id}/files/{id}          — delete

Usage:
  python scripts/smoke_project_files.py
  python scripts/smoke_project_files.py --localhost-url http://127.0.0.1:8000 \\
                                         --public-url    http://203.0.113.10
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any


TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
FILE_KEYS = {"id", "project_id", "filename", "size", "mime_type", "created_at"}
FILE_LIST_KEYS = {"files", "total"}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request_json(method: str, url: str, body: dict | None = None) -> tuple[int, Any]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with _opener().open(req, timeout=60) as r:
            raw = r.read()
            return r.status, json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = raw.decode("utf-8", errors="replace")
        return exc.code, payload


def request_raw(method: str, url: str) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method=method)
    try:
        with _opener().open(req, timeout=60) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), {k.lower(): v for k, v in exc.headers.items()}


def upload_file(base_url: str, project_id: str, filename: str, content: bytes) -> tuple[int, Any]:
    with tempfile.NamedTemporaryFile(prefix="smoke-upload-", suffix=".txt", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            [
                "curl", "--silent", "--show-error",
                "--write-out", "\n%{http_code}",
                "-X", "POST",
                f"{base_url}/api/projects/{project_id}/files",
                "-F", f"file=@{tmp_path};filename={filename};type=text/plain",
            ],
            check=False, capture_output=True, text=True,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if result.returncode != 0:
        raise RuntimeError(f"curl upload failed: {result.stderr.strip()}")

    body, code_str = result.stdout.rsplit("\n", 1)
    return int(code_str), json.loads(body)


# ---------------------------------------------------------------------------
# Audit tracking
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    ok: bool
    endpoint: str
    detail: str


@dataclass
class HostAudit:
    base_url: str
    passes: list[Check] = field(default_factory=list)
    failures: list[Check] = field(default_factory=list)

    def record(self, name: str, endpoint: str, detail: str, ok: bool) -> None:
        (self.passes if ok else self.failures).append(
            Check(name=name, ok=ok, endpoint=endpoint, detail=detail)
        )

    def pass_(self, name: str, endpoint: str, detail: str = "") -> None:
        self.record(name, endpoint, detail, True)

    def fail(self, name: str, endpoint: str, detail: str = "") -> None:
        self.record(name, endpoint, detail, False)


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def assert_uuid(value: str, context: str = "") -> None:
    parsed = uuid.UUID(str(value))
    if str(parsed) != str(value):
        raise AssertionError(f"{context}: not a canonical UUID: {value!r}")


def assert_keys(payload: dict, expected: set[str], context: str = "") -> None:
    if set(payload.keys()) != expected:
        raise AssertionError(
            f"{context}: expected keys {sorted(expected)}, got {sorted(payload.keys())}"
        )


def assert_file_payload(payload: dict, project_id: str, filename: str, size: int) -> str:
    assert_keys(payload, FILE_KEYS, "upload response")
    assert_uuid(payload["id"], "file.id")
    assert_uuid(payload["project_id"], "file.project_id")
    if payload["project_id"] != project_id:
        raise AssertionError(f"project_id mismatch: expected {project_id}, got {payload['project_id']}")
    if payload["filename"] != filename:
        raise AssertionError(f"filename mismatch: expected {filename!r}, got {payload['filename']!r}")
    if payload["size"] != size:
        raise AssertionError(f"size mismatch: expected {size}, got {payload['size']}")
    return payload["id"]


def assert_file_list(payload: dict, expected_ids: list[str], context: str = "") -> None:
    assert_keys(payload, FILE_LIST_KEYS, context or "file list")
    if payload["total"] != len(expected_ids):
        raise AssertionError(f"{context}: total={payload['total']}, expected {len(expected_ids)}")
    actual_ids = [f["id"] for f in payload["files"]]
    if actual_ids != expected_ids:
        raise AssertionError(f"{context}: file ids {actual_ids} != expected {expected_ids}")
    for item in payload["files"]:
        assert_keys(item, FILE_KEYS, f"{context}/item")
        assert_uuid(item["id"], "list item id")
        assert_uuid(item["project_id"], "list item project_id")


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

def create_project(base: str, name: str) -> str:
    status, payload = request_json(
        "POST", f"{base}/api/projects",
        {"name": name, "description": "smoke file verification", "user_id": TEST_USER_ID},
    )
    if status != 201:
        raise AssertionError(f"POST /api/projects returned {status}: {payload}")
    return payload["id"]


def run_host_flow(base_url: str, run_id: str) -> HostAudit:
    audit = HostAudit(base_url=base_url.rstrip("/"))
    base = audit.base_url
    upload_name = f"smoke-{run_id}.txt"
    upload_content = f"smoke file payload {run_id}".encode("utf-8")

    pa: str | None = None
    pb: str | None = None

    try:
        # ── Create two projects ────────────────────────────────────────────
        pa = create_project(base, f"smoke-a-{run_id}")
        audit.pass_("Create Project A", "/api/projects", f"id={pa}")

        pb = create_project(base, f"smoke-b-{run_id}")
        audit.pass_("Create Project B", "/api/projects", f"id={pb}")

        # ── Upload ────────────────────────────────────────────────────────
        status, upload_payload = upload_file(base, pa, upload_name, upload_content)
        if status != 201:
            raise AssertionError(f"POST .../files returned {status}: {upload_payload}")
        file_id = assert_file_payload(upload_payload, pa, upload_name, len(upload_content))
        audit.pass_("Upload file into Project A", f"/api/projects/{pa}/files", f"file_id={file_id}")

        # ── List ─────────────────────────────────────────────────────────
        status, list1 = request_json("GET", f"{base}/api/projects/{pa}/files")
        if status != 200:
            raise AssertionError(f"GET .../files returned {status}: {list1}")
        assert_file_list(list1, [file_id], "first list")
        audit.pass_("List Project A files", f"/api/projects/{pa}/files", f"total={list1['total']}")

        # ── Persistence (second fetch) ────────────────────────────────────
        status, list2 = request_json("GET", f"{base}/api/projects/{pa}/files")
        if status != 200:
            raise AssertionError(f"second GET .../files returned {status}: {list2}")
        assert_file_list(list2, [file_id], "second list")
        audit.pass_("Persistence: second fetch same data", f"/api/projects/{pa}/files", f"total={list2['total']}")

        # ── Cross-project isolation (before delete) ────────────────────────
        status, b_list = request_json("GET", f"{base}/api/projects/{pb}/files")
        if status != 200:
            raise AssertionError(f"GET project B files returned {status}: {b_list}")
        assert_file_list(b_list, [], "project B before delete")
        audit.pass_("Cross-project isolation (before delete)", f"/api/projects/{pb}/files", "Project B empty")

        # ── Download ─────────────────────────────────────────────────────
        dl_url = f"{base}/api/projects/{pa}/files/{file_id}/download"
        dl_status, dl_body, dl_headers = request_raw("GET", dl_url)

        if dl_status == 200:
            ok = True
            problems: list[str] = []

            if dl_body != upload_content:
                ok = False
                problems.append(f"body mismatch: got {dl_body!r}, expected {upload_content!r}")

            cd = dl_headers.get("content-disposition", "")
            if "attachment" not in cd.lower():
                ok = False
                problems.append(f"missing attachment disposition: {cd!r}")

            ct = dl_headers.get("content-type", "")
            if "text/plain" not in ct:
                ok = False
                problems.append(f"unexpected content-type: {ct!r}")

            detail = "status=200, content correct, headers OK" if ok else "; ".join(problems)
            audit.record("Download file", dl_url, detail, ok)
        else:
            audit.fail("Download file", dl_url, f"status={dl_status} body={dl_body[:200]!r}")

        # ── Wrong-project download returns 404 ────────────────────────────
        wrong_dl_status, _, _ = request_raw(
            "GET", f"{base}/api/projects/{pb}/files/{file_id}/download"
        )
        if wrong_dl_status == 404:
            audit.pass_("Download scoping (wrong project → 404)", f"/api/projects/{pb}/files/{file_id}/download")
        else:
            audit.fail("Download scoping (wrong project → 404)", f"/api/projects/{pb}/files/{file_id}/download",
                       f"expected 404, got {wrong_dl_status}")

        # ── Delete ────────────────────────────────────────────────────────
        del_status, _, _ = request_raw("DELETE", f"{base}/api/projects/{pa}/files/{file_id}")
        if del_status == 204:
            audit.pass_("Delete file", f"/api/projects/{pa}/files/{file_id}", "status=204")
        else:
            raise AssertionError(f"DELETE returned {del_status}")

        # ── List after delete ─────────────────────────────────────────────
        status, list3 = request_json("GET", f"{base}/api/projects/{pa}/files")
        if status != 200:
            raise AssertionError(f"list after delete returned {status}: {list3}")
        assert_file_list(list3, [], "list after delete")
        audit.pass_("List after delete: Project A empty", f"/api/projects/{pa}/files", "total=0")

        # ── Download after delete → 404 ───────────────────────────────────
        post_del_dl_status, _, _ = request_raw("GET", dl_url)
        if post_del_dl_status == 404:
            audit.pass_("Download deleted file → 404", dl_url)
        else:
            audit.fail("Download deleted file → 404", dl_url,
                       f"expected 404, got {post_del_dl_status}")

        # ── Cross-project isolation (after delete) ────────────────────────
        status, b_list2 = request_json("GET", f"{base}/api/projects/{pb}/files")
        if status != 200:
            raise AssertionError(f"project B list after A delete returned {status}: {b_list2}")
        assert_file_list(b_list2, [], "project B after A delete")
        audit.pass_("Cross-project isolation (after delete)", f"/api/projects/{pb}/files", "Project B still empty")

        # ── Download route in OpenAPI spec ────────────────────────────────
        spec_status, spec_payload = request_json("GET", f"{base}/api/openapi.json")
        if spec_status == 200 and isinstance(spec_payload, dict):
            paths = set(spec_payload.get("paths", {}).keys())
            dl_path = "/api/projects/{project_id}/files/{file_id}/download"
            if dl_path in paths:
                audit.pass_("Download route in OpenAPI spec", dl_path)
            else:
                audit.fail("Download route in OpenAPI spec", dl_path,
                            f"not found in spec paths; file paths={sorted(p for p in paths if 'file' in p)}")
        else:
            audit.fail("OpenAPI spec reachable", f"{base}/api/openapi.json",
                       f"status={spec_status}")

    except Exception as exc:
        audit.fail("Host flow aborted", base, str(exc))

    finally:
        for pid in filter(None, [pa, pb]):
            try:
                request_raw("DELETE", f"{base}/api/projects/{pid}")
            except Exception:
                pass

    return audit


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(audit: HostAudit, label: str) -> None:
    total = len(audit.passes) + len(audit.failures)
    print(f"\n{'='*60}")
    print(f" {label}: {audit.base_url}")
    print(f" {len(audit.passes)}/{total} checks passed")
    print(f"{'='*60}")

    if audit.passes:
        print("  PASS:")
        for c in audit.passes:
            print(f"    [OK] {c.name}")
            if c.detail:
                print(f"         {c.detail}")

    if audit.failures:
        print("  FAIL:")
        for c in audit.failures:
            print(f"    [FAIL] {c.name}")
            print(f"           endpoint: {c.endpoint}")
            if c.detail:
                print(f"           detail:   {c.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for project file API")
    parser.add_argument("--localhost-url", default="http://127.0.0.1:8000")
    parser.add_argument("--public-url", default="http://203.0.113.10")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:10]
    local_audit = run_host_flow(args.localhost_url, f"local-{run_id}")
    public_audit = run_host_flow(args.public_url, f"public-{run_id}")

    if args.json:
        report = {
            "run_id": run_id,
            "localhost": {
                "base_url": local_audit.base_url,
                "passed": len(local_audit.passes),
                "failed": len(local_audit.failures),
                "passes": [c.__dict__ for c in local_audit.passes],
                "failures": [c.__dict__ for c in local_audit.failures],
            },
            "public": {
                "base_url": public_audit.base_url,
                "passed": len(public_audit.passes),
                "failed": len(public_audit.failures),
                "passes": [c.__dict__ for c in public_audit.passes],
                "failures": [c.__dict__ for c in public_audit.failures],
            },
        }
        print(json.dumps(report, indent=2))
    else:
        print_report(local_audit, "LOCALHOST")
        print_report(public_audit, "PUBLIC (nginx)")

    all_ok = not local_audit.failures and not public_audit.failures
    print(f"\n{'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
