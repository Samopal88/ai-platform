# Phase Gates
## AI Workspace Platform — Autonomous Manager

**Version:** 1.0  
**Authority:** The manager must check phase readiness before executing tasks in a new phase.  
**Enforcement:** `backend/app/services/phase_gate.py`

---

## Purpose

The manager must not blindly advance through roadmap phases.  
Each phase builds on foundations from prior phases. If those foundations are stubs or false positives, advancing is fake progress that generates technical debt and makes later tasks fail mysteriously.

Phase gates are checked at task selection time, not at acceptance time.

---

## Gate Check Trigger

A phase gate check fires when:
- The next roadmap task belongs to a phase the manager has not yet validated
- Executive memory reports `phase_readiness[phase_name].status != "cleared"`
- A repair task queue entry exists for a file that is a declared foundation for the next phase

---

## Phase Definitions and Their Preconditions

### Phase 4 — Database Layer
**Gate: may proceed if:**
- `backend/app/db/session.py` exists AND is semantically valid (real engine + SessionLocal + get_db())
- `backend/requirements.txt` has sqlalchemy uncommented
- No critical gap in executive memory blocking DB setup

**Forbidden unresolved gaps:**
- Missing or stub `session.py`
- SQLAlchemy commented out in requirements

---

### Phase 5 — Projects API
**Gate: may proceed if:**
- Phase 4 cleared
- `backend/app/db/session.py` is `integrated` (not just `file_only`)
- `backend/app/models/project.py` exists and has `class Project`

**Forbidden:**
- Stub DB session
- Missing Project model

---

### Phase 6 — Chats & Messages API
**Gate: may proceed if:**
- Phase 5 cleared
- `backend/app/api/projects.py` is `semantically_valid` with at least 3 routes
- `backend/app/services/project_service.py` is `semantically_valid` (not stub)
- Projects router registered in `backend/app/main.py`

**Forbidden:**
- Projects API is a stub
- Projects router not in main.py

---

### Phase 7 — AI Chat Service
**Gate: may proceed if:**
- Phase 6 cleared
- `backend/app/api/chats.py` is `semantically_valid` with at least 2 routes
- `backend/app/services/chat_service.py` is `semantically_valid`

**Forbidden:**
- Stub chat service
- Missing message endpoints

---

### Phase 8 — Files API
**Gate: may proceed if:**
- Phase 7 cleared
- `backend/app/api/ai_chat.py` is `semantically_valid`

**Forbidden:**
- AI chat endpoint is a stub (routes registered but return `pass` or empty)

---

### Phase 9 — Chat UI Integration
**Gate: may proceed if:**
- Phase 8 cleared
- All 4 backend APIs (projects, chats, ai_chat, files) are `semantically_valid`
- None of them are in the repair queue

**Forbidden:**
- Advancing to UI if core API is still fake
- Any critical product_gap for backend APIs unresolved

---

### Phase 10 — Memory & Context
**Gate: may proceed if:**
- Phase 9 cleared
- `frontend/chat.html` is `semantically_valid` (real chat UI, real API calls)
- Not in repair queue as `false_positive`

**Forbidden:**
- Advancing to memory features if chat UI is a static placeholder
- Advancing if chat.html contains wrong-page content

---

## Gate Verdict Types

| Verdict | Meaning | Manager Action |
|---|---|---|
| `cleared` | All conditions met | Proceed with task |
| `warning` | Optional conditions not met | Proceed but inject warning note in brief |
| `blocked` | Required condition not met | Select repair task first, do not dispatch roadmap task |
| `escalate` | Foundation is fundamentally broken and no repair task can fix it | Block + log to executive memory + surface to human |

---

## Gate Check Output

```python
PhaseGateResult(
    phase="Phase 6",
    verdict="blocked",
    blocking_reasons=["project_service.py is a stub — chat service will fail at import"],
    warnings=[],
    repair_tasks_needed=["5.2-repair"],
)
```

---

## Example: Gate Block

Manager is about to execute task `6.2 — Create chat_service.py`.  
Phase gate for Phase 6 checks:
- `backend/app/api/projects.py` → found in executive memory as `semantically_valid` ✓
- `backend/app/services/project_service.py` → found in executive memory as `false_positive` (stub)

Gate verdict: `blocked`  
Blocking reason: `project_service.py is in repair queue (stub) — chat_service.py will import it; building on broken foundation`  
Manager action: Select `5.2-repair` from repair queue before proceeding to task 6.2.

---

## Gate State Persistence

Phase gate results are stored in `executive_memory.phase_readiness`:

```json
"phase_readiness": {
  "Phase 5": { "status": "cleared", "cleared_at": "2026-04-18T..." },
  "Phase 6": { "status": "blocked", "blocking_reasons": ["..."], "last_checked": "..." },
  "Phase 7": { "status": "not_checked" }
}
```

A cleared phase does not need to be re-checked unless a regression or repair task touches a file that was its gate condition.
