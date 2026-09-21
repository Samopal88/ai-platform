# Release Smoke Checks

Run these before calling the demo build stable.

## Server Command

```bash
/opt/ai-workspace/.venv/bin/python /tmp/test_release_surface_smoke.py
/opt/ai-workspace/.venv/bin/python /tmp/test_auth_account_surfaces.py
curl -fsS http://127.0.0.1:8000/health
```

## Covered Surfaces

- `/chat` current frontend build marker.
- Account UI: forgot-password placeholder and guest/account note.
- Media controls: image generation and speech-to-text entrypoints.
- Documentation: getting started, models, image generation, speech-to-text, release readiness.
- API: models, plans, billing summary.
- Media disabled fallback returns `503` without breaking the product.
- Auth: guest, register, login, billing summary for authenticated user.

## Not Covered Yet

- Visual browser QA.
- Real provider completions with live keys.
- YooKassa live checkout.
- PostgreSQL production migration.
