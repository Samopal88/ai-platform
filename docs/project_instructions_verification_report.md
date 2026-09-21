# Project Instructions Verification Report

Date: 2026-04-20

This report is live-deployment verification only. It does not draw conclusions from a temporary test server or from source inspection.

## Automated artifact used

- Smoke script: `/opt/ai-workspace/storage/projects/ai-platform/scripts/smoke_project_instructions.py`

## Commands run

- `python3 /opt/ai-workspace/storage/projects/ai-platform/scripts/smoke_project_instructions.py`
- `curl -i http://127.0.0.1:8000/health`
- `curl -i http://203.0.113.10/health`

## Localhost live: `http://127.0.0.1:8000`

### Pass

- `GET /chat` returned `200`
- `POST /api/projects` created project A and project B with `201`
- `PUT /api/projects/{project_a_id}` set instructions for project A and response included `instructions`
- `GET /api/projects/{project_a_id}` returned the set instructions
- `GET /api/projects/{project_b_id}` returned `instructions=null`, so project B did not inherit project A instructions
- `PUT /api/projects/{project_a_id}` updated instructions to a new value
- Two subsequent `GET /api/projects/{project_a_id}` requests both returned the updated value
- `GET /health` returned `200 OK`

### Unprovable

- `POST /api/chats/{chat_id}/complete` returned `201`, but the content for project A and project B was identical:
  - `'[MVP stub — no API key configured] You said: Say hello.'`
  - Result: `instructions usage in live completion path is not provable from current observable outputs`
- Browser refresh behavior through the live UI was not proven in this run. Persistence was verified through repeated API fetches only.

## Public nginx: `http://203.0.113.10`

### Pass

- `GET /chat` returned `200`
- `POST /api/projects` created project A and project B with `201`
- `PUT /api/projects/{project_a_id}` set instructions for project A and response included `instructions`
- `GET /api/projects/{project_a_id}` returned the set instructions
- `GET /api/projects/{project_b_id}` returned `instructions=null`, so project B did not inherit project A instructions
- `PUT /api/projects/{project_a_id}` updated instructions to a new value
- Two subsequent `GET /api/projects/{project_a_id}` requests both returned the updated value

### Blocked / different

- `GET /health` returned `401 Unauthorized`
- `/chat` and `/api/...` routes remained reachable despite the `/health` block

### Unprovable

- `POST /api/chats/{chat_id}/complete` returned `201`, but the content for project A and project B was identical:
  - `'[MVP stub — no API key configured] You said: Say hello.'`
  - Result: `instructions usage in live completion path is not provable from current observable outputs`
- Browser refresh behavior through the live UI was not proven in this run. Persistence was verified through repeated API fetches only.

## Bottom line

As observed on 2026-04-20, live localhost and live public nginx both pass the required project read/write and persistence checks for project instructions.

Completion-path integration is not proven on either live host. The current observable completion output is the same stub response for different project instructions, so the truthful conclusion is:

`instructions usage in live completion path is not provable from current observable outputs`
