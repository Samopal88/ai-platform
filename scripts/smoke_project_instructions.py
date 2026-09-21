"""
Truthful live verification for project instructions over localhost and public nginx.

This script checks the deployed behavior only. It separates:
- pass: directly observed working behavior
- fail: directly observed broken behavior
- unprovable: required behavior that could not be proven from live outputs
- info: contextual host differences that are useful but not gating
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any


TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
EXPECTED_PROJECT_KEYS = {"id", "name", "description", "instructions", "created_at", "updated_at"}


@dataclass
class Check:
    name: str
    status: str
    route: str
    detail: str
    host: str


@dataclass
class HostAudit:
    host: str
    passes: list[Check] = field(default_factory=list)
    failures: list[Check] = field(default_factory=list)
    unprovable: list[Check] = field(default_factory=list)
    info: list[Check] = field(default_factory=list)

    def record(self, name: str, route: str, detail: str, status: str) -> None:
        item = Check(name=name, status=status, route=route, detail=detail, host=self.host)
        if status == "pass":
            self.passes.append(item)
        elif status == "fail":
            self.failures.append(item)
        elif status == "unprovable":
            self.unprovable.append(item)
        elif status == "info":
            self.info.append(item)
        else:
            raise ValueError(f"Unsupported status: {status}")


def request_json(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with opener.open(request, timeout=60) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def request_json_allow_error(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    try:
        return request_json(method, url, body)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        try:
            parsed = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            parsed = payload
        return exc.code, parsed


def request_status_allow_error(url: str) -> tuple[int, str]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method="GET")
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def audit_host(base_url: str) -> HostAudit:
    base = base_url.rstrip("/")
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    audit = HostAudit(host=base)
    instructions_1 = f"ALPHA instructions {run_id}"
    instructions_2 = f"BETA instructions {run_id}"
    project_a_name = f"instructions-a-{run_id}"
    project_b_name = f"instructions-b-{run_id}"

    try:
        health_status, health_body = request_status_allow_error(f"{base}/health")
        audit.record(
            "Health endpoint observation",
            "/health",
            f"status={health_status} body={health_body[:200]!r}",
            "info",
        )
    except Exception as exc:
        audit.record("Health endpoint observation", "/health", repr(exc), "info")

    try:
        chat_page_status, chat_body = request_status_allow_error(f"{base}/chat")
        audit.record(
            "Chat page reachable",
            "/chat",
            f"status={chat_page_status} body_prefix={chat_body[:120]!r}",
            "pass" if chat_page_status == 200 else "fail",
        )
    except Exception as exc:
        audit.record("Chat page reachable", "/chat", repr(exc), "fail")

    project_a_id = None
    project_b_id = None

    try:
        status, created_a = request_json_allow_error(
            "POST",
            f"{base}/api/projects",
            {
                "name": project_a_name,
                "description": "live project instructions verification A",
                "user_id": TEST_USER_ID,
            },
        )
        detail = f"status={status} payload={created_a!r}"
        if status == 201 and isinstance(created_a, dict):
            project_a_id = created_a.get("id")
            detail = f"status=201 id={project_a_id} keys={sorted(created_a.keys())}"
        audit.record(
            "Create project A",
            "/api/projects",
            detail,
            "pass" if status == 201 and bool(project_a_id) else "fail",
        )
    except Exception as exc:
        audit.record("Create project A", "/api/projects", repr(exc), "fail")

    try:
        status, created_b = request_json_allow_error(
            "POST",
            f"{base}/api/projects",
            {
                "name": project_b_name,
                "description": "live project instructions verification B",
                "user_id": TEST_USER_ID,
            },
        )
        detail = f"status={status} payload={created_b!r}"
        if status == 201 and isinstance(created_b, dict):
            project_b_id = created_b.get("id")
            detail = f"status=201 id={project_b_id} keys={sorted(created_b.keys())}"
        audit.record(
            "Create project B",
            "/api/projects",
            detail,
            "pass" if status == 201 and bool(project_b_id) else "fail",
        )
    except Exception as exc:
        audit.record("Create project B", "/api/projects", repr(exc), "fail")

    if project_a_id:
        try:
            status, updated = request_json_allow_error(
                "PUT",
                f"{base}/api/projects/{project_a_id}",
                {"instructions": instructions_1},
            )
            ok = (
                status == 200
                and isinstance(updated, dict)
                and set(updated.keys()) == EXPECTED_PROJECT_KEYS
                and updated.get("instructions") == instructions_1
            )
            detail = (
                f"status={status} keys={sorted(updated.keys()) if isinstance(updated, dict) else type(updated).__name__} "
                f"instructions={updated.get('instructions') if isinstance(updated, dict) else None!r}"
            )
            audit.record("Set instructions for project A", f"/api/projects/{project_a_id}", detail, "pass" if ok else "fail")
        except Exception as exc:
            audit.record("Set instructions for project A", f"/api/projects/{project_a_id}", repr(exc), "fail")

    if project_a_id:
        try:
            status, fetched = request_json_allow_error("GET", f"{base}/api/projects/{project_a_id}")
            ok = (
                status == 200
                and isinstance(fetched, dict)
                and set(fetched.keys()) == EXPECTED_PROJECT_KEYS
                and fetched.get("instructions") == instructions_1
            )
            detail = (
                f"status={status} keys={sorted(fetched.keys()) if isinstance(fetched, dict) else type(fetched).__name__} "
                f"instructions={fetched.get('instructions') if isinstance(fetched, dict) else None!r}"
            )
            audit.record("GET project A returns set instructions", f"/api/projects/{project_a_id}", detail, "pass" if ok else "fail")
        except Exception as exc:
            audit.record("GET project A returns set instructions", f"/api/projects/{project_a_id}", repr(exc), "fail")

    if project_a_id and project_b_id:
        try:
            status_a, first = request_json_allow_error("GET", f"{base}/api/projects/{project_a_id}")
            status_b, second = request_json_allow_error("GET", f"{base}/api/projects/{project_b_id}")
            ok = (
                status_a == 200
                and status_b == 200
                and isinstance(first, dict)
                and isinstance(second, dict)
                and first.get("instructions") == instructions_1
                and second.get("instructions") in (None, "")
                and first.get("instructions") != second.get("instructions")
            )
            detail = (
                f"status_a={status_a} status_b={status_b} "
                f"first={first.get('instructions') if isinstance(first, dict) else None!r} "
                f"second={second.get('instructions') if isinstance(second, dict) else None!r}"
            )
            audit.record("Project B does not inherit A instructions", "/api/projects/{id}", detail, "pass" if ok else "fail")
        except Exception as exc:
            audit.record("Project B does not inherit A instructions", "/api/projects/{id}", repr(exc), "fail")

    if project_a_id:
        try:
            status, updated = request_json_allow_error(
                "PUT",
                f"{base}/api/projects/{project_a_id}",
                {"instructions": instructions_2},
            )
            ok = (
                status == 200
                and isinstance(updated, dict)
                and set(updated.keys()) == EXPECTED_PROJECT_KEYS
                and updated.get("instructions") == instructions_2
            )
            detail = (
                f"status={status} keys={sorted(updated.keys()) if isinstance(updated, dict) else type(updated).__name__} "
                f"instructions={updated.get('instructions') if isinstance(updated, dict) else None!r}"
            )
            audit.record("Update project A instructions", f"/api/projects/{project_a_id}", detail, "pass" if ok else "fail")
        except Exception as exc:
            audit.record("Update project A instructions", f"/api/projects/{project_a_id}", repr(exc), "fail")

        try:
            status, refetched = request_json_allow_error("GET", f"{base}/api/projects/{project_a_id}")
            ok = status == 200 and isinstance(refetched, dict) and refetched.get("instructions") == instructions_2
            detail = f"status={status} instructions={refetched.get('instructions') if isinstance(refetched, dict) else None!r}"
            audit.record("Re-fetch project A returns updated instructions", f"/api/projects/{project_a_id}", detail, "pass" if ok else "fail")
        except Exception as exc:
            audit.record("Re-fetch project A returns updated instructions", f"/api/projects/{project_a_id}", repr(exc), "fail")

        try:
            status, second_refetch = request_json_allow_error("GET", f"{base}/api/projects/{project_a_id}")
            ok = status == 200 and isinstance(second_refetch, dict) and second_refetch.get("instructions") == instructions_2
            detail = f"status={status} instructions={second_refetch.get('instructions') if isinstance(second_refetch, dict) else None!r}"
            audit.record("Second fetch still returns updated instructions", f"/api/projects/{project_a_id}", detail, "pass" if ok else "fail")
        except Exception as exc:
            audit.record("Second fetch still returns updated instructions", f"/api/projects/{project_a_id}", repr(exc), "fail")

    if project_a_id and project_b_id:
        try:
            status, chat = request_json_allow_error(
                "POST",
                f"{base}/api/projects/{project_a_id}/chats",
                {
                    "title": f"instructions-chat-{run_id}",
                    "model": "claude-sonnet-4-20250514",
                },
            )
            if status != 201 or not isinstance(chat, dict):
                raise AssertionError(f"chat create status={status} payload={chat}")
            chat_id = chat["id"]

            status, _ = request_json_allow_error(
                "POST",
                f"{base}/api/chats/{chat_id}/messages",
                {"role": "user", "content": "Say hello."},
            )
            if status != 201:
                raise AssertionError(f"message create status={status}")

            status, completion = request_json_allow_error(
                "POST",
                f"{base}/api/chats/{chat_id}/complete",
                {},
            )
            if status != 201 or not isinstance(completion, dict):
                raise AssertionError(f"complete status={status} payload={completion}")

            content_a = completion.get("content")

            status, chat_b = request_json_allow_error(
                "POST",
                f"{base}/api/projects/{project_b_id}/chats",
                {
                    "title": f"instructions-chat-b-{run_id}",
                    "model": "claude-sonnet-4-20250514",
                },
            )
            if status != 201 or not isinstance(chat_b, dict):
                raise AssertionError(f"chat B create status={status} payload={chat_b}")
            chat_b_id = chat_b["id"]

            status, _ = request_json_allow_error(
                "POST",
                f"{base}/api/chats/{chat_b_id}/messages",
                {"role": "user", "content": "Say hello."},
            )
            if status != 201:
                raise AssertionError(f"message B create status={status}")

            status, completion_b = request_json_allow_error(
                "POST",
                f"{base}/api/chats/{chat_b_id}/complete",
                {},
            )
            if status != 201 or not isinstance(completion_b, dict):
                raise AssertionError(f"complete B status={status} payload={completion_b}")

            content_b = completion_b.get("content")
            if isinstance(content_a, str) and instructions_2 in content_a:
                audit.record(
                    "Completion path observably uses project instructions",
                    f"/api/chats/{chat_id}/complete",
                    f"status=201 content={content_a!r}",
                    "pass",
                )
            else:
                audit.record(
                    "Completion path observably uses project instructions",
                    f"/api/chats/{chat_id}/complete",
                    (
                        "status_a=201 status_b=201 "
                        f"content_a={content_a!r} content_b={content_b!r}; "
                        "instructions usage in live completion path is not provable from current observable outputs"
                    ),
                    "unprovable",
                )
        except Exception as exc:
            audit.record(
                "Completion path observably uses project instructions",
                "/api/chats/{chat_id}/complete",
                repr(exc),
                "unprovable",
            )

    audit.record(
        "Browser refresh behavior through UI",
        "/chat",
        "Not proven in this smoke run. The live verification used API-backed persistence checks only; no browser-visible instructions state was exercised end-to-end.",
        "unprovable",
    )

    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--localhost-url", default="http://127.0.0.1:8000")
    parser.add_argument("--public-url", default="http://203.0.113.10")
    args = parser.parse_args()

    localhost_audit = audit_host(args.localhost_url)
    public_audit = audit_host(args.public_url)

    report = {
        "localhost": {
            "info": [check.__dict__ for check in localhost_audit.info],
            "passes": [check.__dict__ for check in localhost_audit.passes],
            "failures": [check.__dict__ for check in localhost_audit.failures],
            "unprovable": [check.__dict__ for check in localhost_audit.unprovable],
        },
        "public_nginx": {
            "info": [check.__dict__ for check in public_audit.info],
            "passes": [check.__dict__ for check in public_audit.passes],
            "failures": [check.__dict__ for check in public_audit.failures],
            "unprovable": [check.__dict__ for check in public_audit.unprovable],
        },
    }
    print(json.dumps(report, indent=2))
    return 0 if not localhost_audit.failures and not public_audit.failures and not localhost_audit.unprovable and not public_audit.unprovable else 1


if __name__ == "__main__":
    raise SystemExit(main())
