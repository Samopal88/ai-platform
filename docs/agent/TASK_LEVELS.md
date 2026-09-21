# Task Level System
## AI Workspace Platform — Autonomous Manager

**Version:** 1.0  
**Authority:** Every task selected by the manager must be assigned a level before execution.  
**Enforcement:** `backend/app/services/task_level_classifier.py`

---

## Purpose

Task levels are not decorative labels. They control:
- how much context the manager assembles
- how strict the acceptance gate is
- whether a phase gate check is required before dispatch
- whether regression scanning must expand scope
- the retry policy
- whether the manager may auto-accept or must do enhanced review

Without levels, the manager treats a one-line patch the same as a cross-system integration task. That wastes tokens on trivial work and under-reviews risky work.

---

## Level Definitions

### Level 0 — Trivial Patch
**What it is:** Single-file, single-change, no logic. Typo fix, adding one line, updating a constant, version bump.

| Property | Value |
|---|---|
| Max target files | 1 |
| Max reference docs | 0 (none needed) |
| Max reference code files | 0 |
| Review strictness | File exists, non-empty, no regression in that file |
| Retry policy | 1 retry max, then block |
| Auto-accept | Yes — if file exists with expected content token |
| Phase gate required | No |
| Regression scan scope | Target file only |

---

### Level 1 — Local Structural Task
**What it is:** Creating or modifying a single file with well-defined structure but no cross-file dependencies. Schema file, config file, simple utility.

| Property | Value |
|---|---|
| Max target files | 2 |
| Max reference docs | 1 (one relevant architecture or data model section) |
| Max reference code files | 1 (one neighboring file for interface reference) |
| Review strictness | File structure correct, no stubs, no placeholder |
| Retry policy | 2 retries, fix brief specifically identifies missing structure |
| Auto-accept | No — must verify key class/function names |
| Phase gate required | No |
| Regression scan scope | Target files only |

---

### Level 2 — Semantic Single-File Implementation
**What it is:** Creating a real service, router, or page that implements declared product behavior. Most roadmap tasks fall here.

| Property | Value |
|---|---|
| Max target files | 3 |
| Max reference docs | 2 (architecture + data model typical) |
| Max reference code files | 2 (interfaces it must call) |
| Review strictness | Structure correct + semantic content correct (no stubs, correct function signatures, real bodies, correct API paths) |
| Retry policy | 2 retries; fix brief must list specific missing elements by name |
| Auto-accept | No — semantic validator must run |
| Phase gate required | If file is in a phase that has preconditions |
| Regression scan scope | Target files + files it imports/is imported by |

---

### Level 3 — Multi-File Integration Task
**What it is:** Task touches 2+ files that must work together — router + service, page + API calls, migration + model. Integration correctness matters.

| Property | Value |
|---|---|
| Max target files | 5 |
| Max reference docs | 3 |
| Max reference code files | 4 (all files in the integration surface) |
| Review strictness | All files individually correct AND cross-file contract honored (imports resolve, function signatures match callers) |
| Retry policy | 2 retries; on first retry manager reads actual file content before rewriting brief |
| Auto-accept | No |
| Phase gate required | Yes — integration tasks assume foundations are real |
| Regression scan scope | All target files + their immediate dependents |

---

### Level 4 — Phase-Critical Product Task
**What it is:** A task that unlocks an entire phase or provides a foundation for multiple downstream tasks. Registering routers in main.py, creating the DB session, wiring up the model router.

| Property | Value |
|---|---|
| Max target files | 3 |
| Max reference docs | 4 (all relevant specs) |
| Max reference code files | 3 (all files that depend on this) |
| Review strictness | Maximum — structure, semantics, integration impact, regression on all dependents |
| Retry policy | 3 retries; if still failing, block and create split repair tasks |
| Auto-accept | No |
| Phase gate required | Yes |
| Regression scan scope | All files in phase that reference this task's outputs |

---

### Level 5 — Architecture / Migration / Foundational Risky Task
**What it is:** Anything that touches the DB schema, auth system, core middleware, or multi-file restructuring. High blast radius. Wrong execution sets back multiple phases.

| Property | Value |
|---|---|
| Max target files | 8 |
| Max reference docs | All relevant authoritative docs |
| Max reference code files | All files in blast radius |
| Review strictness | Maximum + manual confirmation recommended before acceptance |
| Retry policy | 1 retry; on failure, block and escalate to human |
| Auto-accept | Never |
| Phase gate required | Yes — must verify all foundations are real before touching |
| Regression scan scope | Full codebase scan of dependents |

---

## Level Assignment Rules

The classifier assigns levels based on:

1. **File count:** Tasks with >3 target files start at Level 3 minimum
2. **File type combinations:** API + service in same task = Level 3 minimum
3. **Integration keywords:** "register", "wire", "integrate", "connect" = Level 3 minimum
4. **Foundation keywords:** "main.py", "session.py", "migration", "schema" = Level 4 minimum
5. **Risky keywords:** "auth", "alembic", "migrate", "refactor", "restructure" = Level 5 minimum
6. **Change length:** Long change description (>200 chars) = Level 2 minimum
7. **Single small file + tiny change:** Level 0 or 1

When in doubt, assign one level higher, not lower.

---

## Level Enforcement Matrix

| Decision Point | L0 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|
| Context budget (docs) | 0 | 1 | 2 | 3 | 4 | all |
| Context budget (code) | 0 | 1 | 2 | 4 | 3 | all |
| Phase gate check | ✗ | ✗ | conditional | ✓ | ✓ | ✓ |
| Semantic validator | ✗ | partial | ✓ | ✓ | ✓ | ✓ |
| Regression scan | target | target | target+deps | extended | all refs | full |
| False-accept audit | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ |
| Max retries | 1 | 2 | 2 | 2 | 3 | 1 |
| Escalate on block | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |

---

## Worked Examples

### Example A — Level 0: Add health-check version field

**Task:** Add `VERSION = "0.1.0"` to `backend/app/config.py`

**Classification:**
- 1 target file
- No integration keywords
- Trivial single-constant change
- **Level 0 — Trivial Patch**

**Reference pack:**
```
product_goal_summary: (3 lines from memory, free)
protected_paths: 6 entries
Total: ~180 chars
```

No doc excerpts. No interface refs. No phase gate.

**Acceptance mode:** Auto-accept if file exists and contains `VERSION`.  
**Retry policy:** 1 retry, then block.

---

### Example B — Level 3: Create chats API router + service together

**Task 6.3:** Create `backend/app/api/chats.py` and call `backend/app/services/chat_service.py`

**Classification:**
- 2 target files
- API + service in same task → Level 3
- Integration keyword "create router that calls service" → Level 3 confirmed
- **Level 3 — Multi-File Integration**

**Reference pack:**
```
product_goal_summary: 3 lines
doc_excerpts:
  [From DATA_MODEL.md — Chat section, 14 lines]
  [From SYSTEM_ARCHITECTURE.md — API section, 12 lines]
  [From VISION_DOCUMENT.md — UX/chat section, 10 lines]
interface_refs:
  # From: backend/app/services/chat_service.py (signatures only)
  # From: backend/app/db/session.py (get_db signature)
  # From: backend/app/api/projects.py (APIRouter pattern)
  # From: backend/app/models/chat.py (class Chat)
architecture_decisions: 3 must_preserve entries
protected_paths: 6 entries
Total: ~4,200 chars
```

**Phase gate:** Phase 6 checked — `project_service.py` must be `semantically_valid`.  
**Regression scope:** All files importing `chats.py` or `chat_service.py`.  
**Auto-accept:** No. Semantic validator runs + false-accept audit.

---

### Example C — False-accepted frontend task becomes a repair

**Scenario:** Task `9.1 — Create frontend/chat.html` was accepted.  
Post-acceptance audit finds: page title is "Generated Content", no JavaScript functions, static HTML only.

**How it enters the repair queue:**
```python
# false_accept_auditor detects:
AuditFinding(
    finding="wrong_page_content",
    rel_path="frontend/chat.html",
    task_id="9.1",
    severity="high",
    detail="chat.html title='Generated Content'; no JS functions found",
    repair_action="Rewrite as real chat UI with sendMessage, loadHistory, loadProjects JS"
)

# repair_queue.queue_from_finding() adds:
{
  "repair_id": "9.1-repair-143022",
  "file": "frontend/chat.html",
  "priority": "P2",
  "reason": "chat.html accepted as static placeholder — no real chat UI",
  "status": "pending"
}
```

**Why it overrides roadmap order:**
- P2 repair → qualifies as `PRIORITY_THRESHOLD_OVERRIDE`
- `has_override_repairs(root)` returns True at next cycle start
- `choose_next_task()` returns the repair before any roadmap item
- Repair brief explicitly forbids "Generated Content" and requires JS functions

**executive_memory update:**
- `false_positives[9.1].status = "pending_repair"`
- `completion_levels["frontend/chat.html"] = "exists_on_disk"` (downgraded from `semantically_valid`)
- `phase_readiness["Phase 10"].status = "blocked"` (chat.html is its gate condition)

---

### Example D — Later roadmap task refused because earlier phase is not ready

**Scenario:** Manager selects task `7.1 — Create AI chat endpoint` (Phase 7).  
Phase gate check for Phase 7 runs.

**Gate check result:**
```python
PhaseGateResult(
    phase="Phase 7",
    verdict="blocked",
    blocking_reasons=[
        "backend/app/api/chats.py is a stub — chat endpoints not real",
        "backend/app/services/chat_service.py is in repair queue as false positive"
    ],
    repair_tasks_needed=["6.3-repair", "6.2-repair"],
)
```

**Manager action:**
1. Does NOT dispatch task 7.1
2. Checks repair queue for `6.3-repair` or `6.2-repair`
3. If found, selects that repair task instead
4. If not found, creates repair tasks via `repair_queue.add_repair()` for both files
5. Logs the block to `executive_memory.phase_readiness["Phase 7"]`
6. Next cycle: repair runs first; if it succeeds, Phase 7 gate re-checks and clears

**Result:** No fake progress. Phase 7 advancement is gated on Phase 6 being real.
