# Task Selection Rules v2
## AI Workspace Platform — Autonomous Manager

**Version:** 2.0  
**Authority:** The manager must follow this selection order every cycle.  
**Enforcement:** `backend/app/services/task_intake.py::choose_next_task()`

---

## Selection Order (Priority Cascade)

The manager does NOT simply pick the next todo item from the roadmap.

Every cycle, selection follows this order:

```
1. P0/P1/P2 repairs from repair_queue        ← override everything
2. Critical product gaps from executive memory ← override roadmap
3. Phase gate check for candidate phase        ← may redirect to repairs
4. Roadmap tasks with explicit file targets    ← normal execution
5. Roadmap tasks without file targets          ← fallback
```

A later step is only reached if the earlier ones produce no candidate.

---

## Step 1 — Repair Queue Override

At cycle start, check:

```python
if has_override_repairs(root):   # any P0, P1, or P2 pending
    repair = next_repair(root)
    return repair_to_task(repair)
```

P0 = emergency (blocking accepted tasks)  
P1 = critical (blocking phase gate)  
P2 = high (stub in accepted file, not yet blocking)  

P3/P4 repairs do NOT override roadmap. They are returned only if
`allow_deferred=True` is passed to `next_repair()`.

---

## Step 2 — Critical Product Gaps

If `executive_memory.product_gaps` contains any entry with `priority == "critical"`,
and no repair task exists for it yet, the manager must:
- Create a repair task for the gap's file
- Queue it at P1
- Select it immediately

This ensures false positives already recorded in memory are acted on even if
the repair queue was not populated by the post-acceptance audit.

---

## Step 3 — Phase Gate

For the first candidate roadmap task, check whether its phase is ready:

```python
gate_result = phase_gate.check(candidate.phase, root)
if gate_result.verdict == "blocked":
    # Prefer deferred repair that fixes the blocking issue
    repair = next_repair(root, allow_deferred=True)
    if repair:
        return repair_to_task(repair)
    # Otherwise return candidate with gate warning injected
    candidate["_phase_gate_blocked"] = True
    candidate["_phase_gate_reasons"] = gate_result.blocking_reasons
```

A `warning` verdict does NOT block. The warning is injected into the brief only.

A `cleared` or unknown-phase verdict proceeds normally.

---

## Step 4 — Roadmap Task Selection

From the remaining todo tasks:
1. Prefer tasks with explicit `**Files:**` targets (deterministic DoD checks)
2. Then tasks without file targets (may produce vague DoD, higher block risk)

Tasks with `status == done` or `status == deferred` are always skipped.

---

## Risk Factors Considered at Selection

Before dispatching, the manager also considers:

| Factor | Effect |
|---|---|
| Task files in repair queue | Warn in brief; consider whether repair should go first |
| Task files are `false_positive` in memory | Must queue repair, do not dispatch original task |
| Task files are `exists_on_disk` only | Flag in brief as unverified dependency |
| Task level ≥ 3 | Phase gate is mandatory before dispatch |
| Task level ≥ 4 | Regression scan scope expands |
| Prerequisite task is blocked in memory | Do not dispatch dependents |

---

## Task Status Detection

Tasks are read from `docs/agent/ROADMAP.md`.  
Status is derived from markers in the heading line or body:

| Marker | Status |
|---|---|
| `[x]`, `[done]`, `[DONE]`, `status: done` | `done` |
| Under `## Deferred` section | `deferred` |
| No marker | `todo` |

A task is marked `[x]` in the roadmap by `manager_loop._mark_roadmap_task_done()`
after a successful acceptance. This prevents re-selection next cycle.

---

## After Selection: What Gets Built

Once a task is selected:

1. `classify_task(task)` → assigns level 0–5
2. `resolve_product_context(task)` → selects relevant product docs
3. `reference_pack.assemble(task, level, root)` → assembles minimum context pack
4. `build_execution_prompt(task, context)` → builds full worker brief with pack injected

The execution prompt is what the file_executor receives. It includes:
- Task objective, target files, must-not-touch list
- Reference pack (doc excerpts, interface refs, prior notes)
- Acceptance criteria and regression risks
- Task level and any phase gate warnings

---

## Token Economy Rule

The manager must not dump entire product docs into the execution prompt.

The reference pack is the only context mechanism:
- Level 0–1: memory summaries + protected list (~180–1,000 chars)
- Level 2: targeted section excerpts + interface signatures (~2,500 chars)
- Level 3: broader excerpts + all integration surface signatures (~5,000 chars)
- Level 4–5: full relevant spec sections, allowed to read full files (~10,000+ chars)

See `docs/agent/CONTEXT_BUDGET_POLICY.md` for the full budget rules.

---

## Repair Task Format

Repair tasks returned by `repair_to_task()` look like normal task dicts:

```python
{
  "id": "9.1-repair-143022",
  "title": "REPAIR: Create real chat UI in frontend/chat.html",
  "phase": "Repair",
  "files": ["frontend/chat.html"],
  "change": "chat.html accepted as static placeholder — no real chat UI",
  "why": "False accept / stub detected in frontend/chat.html",
  "status": "todo",
  "_is_repair": True,
  "_repair_brief": "...(full repair brief from repair_queue entry)...",
  "_repair_entry": {... original repair queue entry ...}
}
```

When `_is_repair` is True, `build_execution_prompt()` uses `_repair_brief` directly
instead of building a fresh brief from scratch.
