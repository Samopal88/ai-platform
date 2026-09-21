# Soft Launch Phases - 2026-05-01

This plan translates the broader product vision into the next 20 executable phases on the path to inviting paid users.

## Current stance

- Source of truth: server project at `/opt/ai-workspace/storage/projects/ai-platform`
- MVP core exists and answers `/health`
- Release is still blocked by runtime hardening, production environment setup, provider wiring, billing validation, and launch QA

## Next 20 phases

1. Sync local workspace with the server source of truth.
2. Remove duplicate backend launch paths and converge on one runtime path.
3. Add a repo-owned `systemd` template for `ai-platform.service`.
4. Add a one-command service installation script.
5. Make release readiness report the real service template and deployed unit state.
6. Make readiness fail when multiple `uvicorn` runtime processes are detected.
7. Promote RuAPI to the explicit primary AI gateway configuration path.
8. Keep OpenAI-compatible aliases as placeholders for gateways that reuse that shape.
9. Expand `.env.example` so production-safe defaults are documented before secrets exist.
10. Lock production defaults around `ENVIRONMENT=production` and `AUTO_CREATE_DB_TABLES=false`.
11. Rehearse PostgreSQL as the expected production database path.
12. Validate auth secrets and paid-release gates in readiness output.
13. Wire a stable SMTP configuration template for password reset and release smoke.
14. Validate YooKassa placeholders and release blockers in one place.
15. Re-run provider readiness smoke against the improved readiness contract.
16. Clean runtime/generated artifacts out of commit-ready diffs.
17. Generate a production-safe PostgreSQL rehearsal env from the current runtime shape.
18. Run PostgreSQL rehearsal preflight and close placeholder or secret gaps before touching production.
19. Install the backend under `systemd` and verify single-process runtime behavior.
20. Run browser QA with evidence capture after final UX polish and real secrets are in place.

## Notes

- Real RuAPI, YooKassa, SMTP, and model-provider secrets can be inserted later without reworking the code paths added in this batch.
- The wider product vision still includes vector indexing, deeper memory, and additional productization work after soft launch.
