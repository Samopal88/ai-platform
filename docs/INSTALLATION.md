# Installation and configuration

This guide covers a local installation, configuration changes, background
startup on Linux, and the minimum production checklist.

## 1. Requirements

- Python 3.11 or newer;
- Git;
- internet access while Python packages are installed;
- an AI-provider key only if real model calls are needed.

The default SQLite setup does not require PostgreSQL or Redis. Some integrations
can report a degraded state until their external service is configured.

## 2. Guided installation

Linux/macOS:

```bash
git clone https://github.com/Samopal88/ai-platform.git
cd ai-platform
bash scripts/install.sh
```

Windows PowerShell:

```powershell
git clone https://github.com/Samopal88/ai-platform.git
cd ai-platform
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
```

The installer is safe to run again. Existing values and secrets are retained
when the configuration is updated. Pass `--force` to skip the overwrite prompt,
or `--yes` for non-interactive defaults:

```bash
python3 scripts/ai_platform.py setup --yes --force --provider none
```

Do not pass API keys on the command line. Use the interactive masked prompt or
edit `backend/.env` after setup.

## 3. Start and validate

Linux/macOS:

```bash
.venv/bin/python scripts/ai_platform.py check
.venv/bin/python scripts/ai_platform.py run
```

Windows:

```powershell
.venv\Scripts\python.exe scripts\ai_platform.py check
.venv\Scripts\python.exe scripts\ai_platform.py run
```

The default URLs are:

| Surface | URL |
|---|---|
| Chat | `http://127.0.0.1:8000/chat` |
| Dashboard | `http://127.0.0.1:8000/dashboard` |
| OpenAPI | `http://127.0.0.1:8000/docs` |
| Health | `http://127.0.0.1:8000/health` |

## 4. Core settings

The generated `backend/.env` is private and ignored by Git. The complete public
template is `backend/.env.example`.

| Setting | Development default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `development` | Enables development-safe database bootstrap |
| `BACKEND_HOST` | `127.0.0.1` | Bind address; use `0.0.0.0` only behind a firewall/proxy |
| `BACKEND_PORT` | `8000` | HTTP port |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | Browser-facing application URL |
| `DATABASE_URL` | `sqlite:///./ai_workspace.db` | SQLAlchemy connection URL |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis endpoint for supported runtime functions |
| `SECRET_KEY` | generated | General application secret |
| `AUTH_TOKEN_SECRET` | generated | Authentication-token signing secret |
| `AUTO_CREATE_DB_TABLES` | `true` | Creates missing tables outside production |

Use different random values for both secrets. The installer does this
automatically and applies mode `0600` to `.env` on POSIX systems.

## 5. AI providers

Configure only providers you intend to use. OpenAI-compatible gateways usually
require both their key and their documented base URL.

```dotenv
OPENAI_API_KEY="..."
OPENAI_BASE_URL="https://api.openai.com/v1"

ANTHROPIC_API_KEY="..."
ANTHROPIC_BASE_URL=""

ROUTERAI_API_KEY="..."
ROUTERAI_BASE_URL="https://provider.example/v1"

RUAPI_API_KEY="..."
RUAPI_BASE_URL="https://provider.example/v1"

CLAUDEHUB_API_KEY="..."
CLAUDEHUB_BASE_URL="https://provider.example/v1"

GOOGLE_API_KEY="..."
GEMINI_API_KEY="..."
```

Base URLs for third-party gateways deliberately have no guessed defaults. Copy
the exact endpoint from the provider's current documentation.

## 6. Database

SQLite is appropriate for a single local process. Its file is created at
`backend/ai_workspace.db` and is ignored by Git.

For PostgreSQL, install/provision the database first and use a psycopg URL:

```dotenv
ENVIRONMENT="production"
DATABASE_URL="postgresql+psycopg://ai_platform:password@127.0.0.1:5432/ai_platform"
AUTO_CREATE_DB_TABLES="false"
```

Run migrations and rehearse a rollback before switching live data. The project
contains additional notes in `docs/implementation/POSTGRES_DEPLOYMENT_PATH.md`
and `docs/implementation/POSTGRES_REHEARSAL.md`.

## 7. Optional SMTP and billing

Password-reset email:

```dotenv
SMTP_HOST="smtp.example.com"
SMTP_PORT="587"
SMTP_USERNAME="user"
SMTP_PASSWORD="password"
SMTP_FROM_EMAIL="noreply@example.com"
SMTP_FROM_NAME="AI Platform"
SMTP_USE_TLS="true"
```

YooKassa:

```dotenv
YOOKASSA_SHOP_ID="..."
YOOKASSA_SECRET_KEY="..."
YOOKASSA_RETURN_URL="https://ai.example.com/billing/return"
YOOKASSA_WEBHOOK_SECRET="..."
```

Use sandbox credentials first. Payment UI and routes being present does not by
itself certify a production payment flow.

## 8. Linux background service

After a successful setup and check:

```bash
.venv/bin/python scripts/ai_platform.py service-install
systemctl --user status ai-platform.service
journalctl --user -u ai-platform.service -f
```

This installs `~/.config/systemd/user/ai-platform.service` for the current user;
it does not require sudo. To keep it running after logout, an administrator may
enable lingering for that account:

```bash
sudo loginctl enable-linger "$USER"
```

## 9. Production minimum

Before exposing the application publicly:

1. use PostgreSQL and tested migrations;
2. place the backend behind an HTTPS reverse proxy;
3. restrict CORS instead of allowing every origin;
4. bind the application only to the intended interface;
5. rotate all secrets and keep them outside the repository;
6. configure backups, logs, monitoring and rate limits;
7. validate email, payment, search and media integrations separately;
8. run `python -m pytest -q` and the release smoke checks;
9. review `docs/implementation/PRODUCTION_ENV_CHECKLIST.md` and
   `docs/public/release-readiness.md`.

The included installer targets a reproducible local/self-hosted setup. It does
not automatically configure DNS, TLS, a firewall or a production database.

## Troubleshooting

`Python 3.11 or newer is required`
: Install a supported Python release, then rerun the setup script.

`AI Platform is not configured`
: Run `python scripts/ai_platform.py setup` from the repository root.

Health check reports Redis unavailable
: Install/start Redis and update `REDIS_URL`, or ignore it for flows that do not
  require Redis during local development.

Provider requests fail
: Check the matching API key and base URL, restart the app, and avoid mixing a
  key from one gateway with another gateway's URL.

Port 8000 is busy
: Rerun setup with another port, for example
  `python scripts/ai_platform.py setup --yes --force --port 8080`.
