# Release Gate Report

This is the compact report command for the current launch status.

## Run

```bash
cd /opt/ai-workspace/storage/projects/ai-platform
python3 scripts/release_gate_report.py
```

## What it combines

- production environment audit
- readiness endpoint smoke
- PostgreSQL rehearsal preflight
- runtime git audit

## Key fields

- `ready_for_paid_release`: strict go/no-go flag
- `paid_release_readiness_percent`: live gate completion against the current runtime and secrets
- `hardening_completion_percent`: how much of the production hardening scaffolding is already in place
- `top_blockers`: compact list of remaining launch blockers
- `next_actions`: ordered handoff list for the next operator pass

## Why this exists

The raw smoke suite is useful, but its output is intentionally detailed.  
`release_gate_report.py` gives a shorter launch-control summary that is easier to check before each paid beta milestone.
