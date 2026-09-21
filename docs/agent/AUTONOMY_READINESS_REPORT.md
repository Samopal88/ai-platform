# Autonomy Readiness Report
## AI Workspace Platform — Can the Manager Be Trusted?

**Date:** 2026-04-19

---

## Current Readiness Level

**LIMITED SUPERVISED EXECUTION**

The manager can be trusted to execute individual recovery tasks with human review after
each cycle. It must NOT be run in auto-mode until the semantic validator fix is proven
to hold across multiple recovery tasks.

---

## What Works

| Component | Status |
|---|---|
| Task selection (roadmap + repair queue priority) | Works correctly |
| Execution prompt generation | Works (bug fixed this session) |
| Doc-only change detection | Works |
| Worker result review | Works |
| Retry loop | Works |
| State persistence across restarts | Works |
| Human status endpoint | Works |
| False-accept detection for multi-function stubs | Works |

## What Was Just Fixed (This Session)

1. **`_build_must_not_touch`**: target files no longer appear in Must Not Touch
2. **`reference_pack.py` protected_paths**: same fix
3. **Reference docs labelled read-only** in the prompt
4. **Stale manager_state.json current_step** replaced with corrected brief
5. **Semantic validator single-function stub gap**: `>= 2` guard removed — now ANY file
   where all functions are pass-only stubs is rejected

## Remaining Failure Modes

### 1. Worker still writes to docs (mitigated, not eliminated)
The prompt now has explicit read-only guards. But the underlying file_executor does
keyword matching to determine writable files and has historically matched doc paths.
The guards in the brief are instructions to the LLM — they reduce the risk but do not
guarantee the worker won't ignore them. **Risk: medium. Mitigation: doc-only guard in review.**

### 2. Worker creates file in wrong path
The worker could create `requirements.txt` instead of `backend/requirements.txt`.
The file-existence check would fail and trigger a retry, but this wastes a cycle.
**Risk: low. Impact: one extra retry.**

### 3. Semantic validator false-negative on novel stub patterns
The stub detection covers `def func(): pass` and `def func(): """doc""" pass`.
A worker could write `def func(): return None` or `def func(): ...` and pass.
**Risk: low-medium. Impact: another false accept.**

### 4. Phase gate not verifying runtime
Phase gate checks file existence and content patterns. It cannot verify that the app
actually starts. After R1–R12 are "done", the manager may accept the state without
confirming that `uvicorn` actually runs.
**Risk: medium. Mitigation: R13 smoke test is in the roadmap.**

### 5. User auth constraint in Project model
`Project.user_id` is `NOT NULL` with FK to `users`. Without a seeded user or auth
bypass, every `POST /api/projects` will fail at DB level even after all stubs are
replaced. This is not in R1–R13. **Risk: high. Blocks MVP end-to-end.**

---

## Safety Classification

| Scenario | Safety |
|---|---|
| Single cycle, human reviews result | SAFE |
| Run Auto for R1 only | SAFE (doc-only guard will catch failures) |
| Run Auto for R1–R5 | BORDERLINE — requires post-run human verification |
| Run Auto for all 13 recovery tasks | UNSAFE until semantic validator is proven |
| Run Auto on the original roadmap | UNSAFE — original roadmap tasks are already falsely marked done |

---

## Before Auto-Run Is Safe

1. ✅ Must Not Touch bug fixed
2. ✅ Single-function stub detection fixed  
3. ✅ Stale state brief updated
4. ⬜ R1 must succeed and produce a real requirements.txt (verify manually)
5. ⬜ R2 must produce a real get_db() (verify: `grep create_engine backend/app/db/session.py`)
6. ⬜ Run one full R1→R2→R3 sequence under supervision before enabling auto-run
7. ⬜ After R12, run `python3 sandbox/smoke_mvp.py` before declaring any task as truly done

---

## Recommendation

Run cycles one at a time. After R1 succeeds, manually verify:
```bash
grep "^sqlalchemy" backend/requirements.txt
```
Then proceed to R2, verify, etc. Do not run auto-mode until R3 (startup DB init) is
confirmed working with a live server start. The cost of one false accept is a full set
of stub re-implementations — the cost of manual verification is one grep command per task.
