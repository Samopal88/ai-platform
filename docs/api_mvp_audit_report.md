**API Audit**
Date: 2026-04-19

Passes:
- `GET /api/projects` returned `200` on the public host and localhost, with list items matching the observed project schema and UUID-shaped `id` values.
- `POST /api/projects` returned `201` on the public host with project id `451e8719-c70c-466b-aafc-0abb830f55e1`.
- `POST /api/projects/{project_id}/chats` returned `201` on the public host with chat id `60bb943c-0754-4813-9f4e-461edf90851f`.
- `GET /api/projects/{project_id}/chats` returned `200` on the public host and included the created chat.
- `POST /api/chats/{chat_id}/messages` returned `201` on the public host with message id `2c0bbf57-618f-401f-b229-1c450d500ddd`.
- `GET /api/chats/{chat_id}/messages` returned `200` on the public host and preserved message order.
- `POST /api/chats/{chat_id}/complete` returned `201` on the public host with assistant message id `119a02aa-752a-452c-90ca-85e39068d748`.
- Response schema consistency checks passed for project, chat, and message payloads in the automated pytest layer and in the public smoke run.
- UUID-shape checks passed for all created project, chat, and message ids.
- Refresh persistence scenario was reproducible: after re-reading projects, chats, and messages, the created project, chat, and both message ids were still present.
- Public nginx path worked through `http://203.0.113.10/chat` and `http://203.0.113.10/api/...`, and the created project was also visible through `http://127.0.0.1:8000/api/projects`.

Fails:
- None observed.

Automated runs:
- `python3 -m pytest /opt/ai-workspace/storage/projects/ai-platform/tests/test_mvp_api.py -v` -> `1 passed`
- `python3 /opt/ai-workspace/storage/projects/ai-platform/scripts/smoke_mvp_api.py` -> no failures

Notes:
- The pytest run emitted deprecation warnings from SQLAlchemy/base model code, but the test itself passed.
- The pytest fixture injects a temporary `multipart` stub into `PYTHONPATH` only for the spawned test server process so the app can import its file-upload route in this environment without changing backend behavior.
