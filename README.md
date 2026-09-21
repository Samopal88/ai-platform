# AI Platform

[![CI](https://github.com/Samopal88/ai-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Samopal88/ai-platform/actions/workflows/ci.yml)

Self-hosted AI workspace with projects, chats, files, memory, multiple model
providers, media tools, and an autonomous task runner. The backend is built on
FastAPI; the web interface is served by the same application.

> The project is at MVP / product-hardening stage. Local development with
> SQLite works out of the box. Payments, outbound email, external search and
> production AI calls require their own credentials and additional deployment
> configuration.

## What is included

- projects, persistent chats, file uploads and project instructions;
- AI chat with OpenAI-compatible, Anthropic, RouterAI, RuAPI and ClaudeHub routes;
- model catalog and plan/tier access controls;
- project memory, summaries, indexing and context assembly;
- file-edit previews, image generation, speech-to-text and web-search surfaces;
- authentication, usage accounting and optional YooKassa/SMTP integrations;
- an operator dashboard and autonomous job runner;
- a cross-platform setup wizard and Linux user-service installer.

## Quick start

Requirements: Git and Python 3.11 or newer.

### Linux / macOS

```bash
git clone https://github.com/Samopal88/ai-platform.git
cd ai-platform
bash scripts/install.sh
.venv/bin/python scripts/ai_platform.py run
```

### Windows PowerShell

```powershell
git clone https://github.com/Samopal88/ai-platform.git
cd ai-platform
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
.venv\Scripts\python.exe scripts\ai_platform.py run
```

The installer creates an isolated `.venv`, installs dependencies, generates
strong local secrets, and writes the private configuration to `backend/.env`.
It also asks which AI provider to configure. Provider credentials are optional,
so the UI and local features can be started without an API key.

Open after startup:

- chat: <http://127.0.0.1:8000/chat>
- dashboard: <http://127.0.0.1:8000/dashboard>
- API docs: <http://127.0.0.1:8000/docs>
- health check: <http://127.0.0.1:8000/health>

## Installer commands

| Command | Purpose |
|---|---|
| `python scripts/ai_platform.py setup` | Interactive installation or configuration update |
| `python scripts/ai_platform.py check` | Validate secrets, virtualenv and backend imports |
| `python scripts/ai_platform.py run` | Start the application |
| `python scripts/ai_platform.py run --reload` | Start a development server with auto-reload |
| `python scripts/ai_platform.py status` | Query the running health endpoint |
| `python scripts/ai_platform.py service-install` | Install and start a Linux systemd user service |

For unattended development setup, use:

```bash
python3 scripts/ai_platform.py setup --yes --provider none
```

## Configuration

Runtime settings live in `backend/.env`; a documented template is provided as
[`backend/.env.example`](backend/.env.example). Never commit the real `.env`.

Only one provider key is needed for the corresponding models:

| Provider | Required setting | Optional/custom endpoint |
|---|---|---|
| OpenAI-compatible | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| RouterAI | `ROUTERAI_API_KEY` | `ROUTERAI_BASE_URL` |
| RuAPI | `RUAPI_API_KEY` | `RUAPI_BASE_URL` |
| ClaudeHub | `CLAUDEHUB_API_KEY` | `CLAUDEHUB_BASE_URL` |
| Anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| Google/Gemini | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | — |

This project does not use a Telegram/channel ID. Its main configuration is the
AI provider, database, public URL and optional billing/email services.

See the full [installation and configuration guide](docs/INSTALLATION.md), the
[Russian guide](docs/README.ru.md), and the [public feature documentation](docs/public/README.md).

## Architecture

```text
Browser UI  ->  FastAPI routes  ->  services/model router
                                  |-> SQLite or PostgreSQL
                                  |-> Redis (optional runtime integration)
                                  |-> AI/media/search providers
```

The default development database is `backend/ai_workspace.db`. Production
deployments should use PostgreSQL, HTTPS, restricted CORS, rotated secrets and
external service credentials; see [production checklist](docs/implementation/PRODUCTION_ENV_CHECKLIST.md).

## Development

```bash
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt pytest
.venv/bin/python -m pytest -q
```

Implementation notes and current limitations are tracked in
[`docs/implementation/CURRENT_EXECUTION_STATUS.md`](docs/implementation/CURRENT_EXECUTION_STATUS.md)
and [`docs/public/release-readiness.md`](docs/public/release-readiness.md).
