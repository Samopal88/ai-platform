#!/usr/bin/env python3
"""
MVP Smoke Test — AI Workspace Platform
Runs end-to-end against http://localhost:8000

Steps:
  1. Create a project
  2. Create a chat in that project
  3. Add a user message to the chat
  4. Call /complete to get an AI response
  5. Verify /messages returns both messages
  6. Verify /api/projects list includes the project
  7. Print PASS or FAIL with details
"""
import sys
import uuid
import requests

BASE = "http://localhost:8000"

FAKE_USER_ID = str(uuid.uuid4())

errors = []


def check(label: str, condition: bool, detail: str = ""):
    if not condition:
        msg = f"FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        errors.append(msg)
        print(msg)
    else:
        print(f"  OK: {label}")


# ---------------------------------------------------------------------------
# 1. Create project
# ---------------------------------------------------------------------------
print("\n--- Step 1: Create project ---")
r = requests.post(f"{BASE}/api/projects", json={
    "name": "Smoke Test Project",
    "description": "created by smoke_mvp.py",
    "user_id": FAKE_USER_ID,
})
check("POST /api/projects status 201", r.status_code == 201, f"got {r.status_code}: {r.text[:200]}")
project_id = None
if r.status_code == 201:
    project_id = r.json().get("id")
    check("project has UUID id", bool(project_id))

if not project_id:
    print("\nCannot continue without a project. MVP smoke test FAILED.\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Create chat
# ---------------------------------------------------------------------------
print("\n--- Step 2: Create chat ---")
r = requests.post(f"{BASE}/api/projects/{project_id}/chats", json={
    "title": "Smoke Chat",
    "model": "claude-haiku-4-5-20251001",
})
check("POST /api/projects/{id}/chats status 201", r.status_code == 201, f"got {r.status_code}: {r.text[:200]}")
chat_id = None
if r.status_code == 201:
    chat_id = r.json().get("id")
    check("chat has UUID id", bool(chat_id))

if not chat_id:
    print("\nCannot continue without a chat. MVP smoke test FAILED.\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Add user message
# ---------------------------------------------------------------------------
print("\n--- Step 3: Add user message ---")
r = requests.post(f"{BASE}/api/chats/{chat_id}/messages", json={
    "role": "user",
    "content": "Hello, this is the smoke test. Reply with one word: OK",
})
check("POST /api/chats/{id}/messages status 201", r.status_code == 201, f"got {r.status_code}: {r.text[:200]}")
msg_id = None
if r.status_code == 201:
    msg_id = r.json().get("id")
    check("message has UUID id", bool(msg_id))

# ---------------------------------------------------------------------------
# 4. Call complete
# ---------------------------------------------------------------------------
print("\n--- Step 4: Call /complete ---")
r = requests.post(f"{BASE}/api/chats/{chat_id}/complete")
check("POST /api/chats/{id}/complete status 201", r.status_code == 201, f"got {r.status_code}: {r.text[:200]}")
assistant_reply = None
if r.status_code == 201:
    body = r.json()
    assistant_reply = body.get("content")
    check("assistant reply is non-empty string", bool(assistant_reply and isinstance(assistant_reply, str)))
    check("role is assistant", body.get("role") == "assistant")
    print(f"  Assistant replied: {assistant_reply[:100]}")

# ---------------------------------------------------------------------------
# 5. Verify messages list
# ---------------------------------------------------------------------------
print("\n--- Step 5: Verify messages list ---")
r = requests.get(f"{BASE}/api/chats/{chat_id}/messages")
check("GET /api/chats/{id}/messages status 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 200:
    messages = r.json()
    check("at least 2 messages (user + assistant)", len(messages) >= 2, f"got {len(messages)}")
    roles = [m.get("role") for m in messages]
    check("has user message", "user" in roles)
    check("has assistant message", "assistant" in roles)

# ---------------------------------------------------------------------------
# 6. Verify project list
# ---------------------------------------------------------------------------
print("\n--- Step 6: Verify project list ---")
r = requests.get(f"{BASE}/api/projects")
check("GET /api/projects status 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 200:
    projects = r.json()
    ids = [p.get("id") for p in projects]
    check("created project appears in list", project_id in ids)

# ---------------------------------------------------------------------------
# 7. Verify chat list
# ---------------------------------------------------------------------------
print("\n--- Step 7: Verify chat list ---")
r = requests.get(f"{BASE}/api/projects/{project_id}/chats")
check("GET /api/projects/{id}/chats status 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
if r.status_code == 200:
    chats = r.json()
    ids = [c.get("id") for c in chats]
    check("created chat appears in list", chat_id in ids)

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
print()
if errors:
    print(f"MVP smoke test FAILED ({len(errors)} error(s)):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("MVP smoke test PASSED")
    sys.exit(0)
