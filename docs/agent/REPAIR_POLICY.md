# Repair Policy
## AI Workspace Platform — Autonomous Manager

**Version:** 1.0  
**Authority:** When a repair task exists, it overrides roadmap order.  
**Enforcement:** `backend/app/services/repair_queue.py` + `manager_loop.py` task selection

---

## Core Principle

Expanding a broken system makes it more broken.  
Adding Phase 7 tasks on top of a stub Phase 5 service creates a house of cards that collapses later in ways that are hard to trace.

The manager must always ask: **"Is my foundation solid enough to build on?"**  
If the answer is no, the next task is a repair, not a roadmap advancement.

---

## What Triggers a Repair Task

A repair task is created when any of the following are detected:

| Source | Detection Method | Severity |
|---|---|---|
| `false_accept_auditor` finds a stub | Post-acceptance scan of service/API files | critical or high |
| `semantic_validator` finds wrong-page content in HTML | During acceptance review | high |
| `doc_only_guard` fires 2+ times for same task | During acceptance review | high |
| Regression scan detects removed routes or functions | During acceptance review | critical |
| Phase gate finds a `false_positive` in gate condition | During task selection | critical |
| Manager receives 3 consecutive `retry_required` on same file | During cycle | high |

---

## Repair Task Format

Repair tasks follow the same executive brief format as regular tasks, with added sections:

```
REPAIR TASK BRIEF
=================

## Repair Reason
[What was wrong. Specific: 'context_builder.py accepted as def main(): pass stub on 2026-04-18']

## Original Task
[task_id] — [original title]

## What Must Be Replaced
[Exact file path + what was wrong with the current content]

## Target Files
[Same files as original task — and ONLY those]

## Known Bad Pattern to Avoid
[Exactly what the worker must not produce again]
  - Do not produce: def main(): pass
  - Do not produce: script wrapper with if __name__ == '__main__'
  - Do not change: docs/ files

## Correct Implementation Requirements
[Full executive brief implementation requirements, same format as DELEGATION_STANDARD.md]

## Acceptance Criteria
[Same as or stricter than original task acceptance criteria]
```

---

## Repair Queue Priority Tiers

| Priority | When Used | Examples |
|---|---|---|
| P0 — Emergency | A previously accepted file is now blocking another accepted task from working | Stub context_builder.py when ai_chat endpoint has been accepted and depends on it |
| P1 — Critical | A phase gate condition is failing due to a false positive | Stub project_service.py blocking Phase 6 advancement |
| P2 — High | Accepted file is a stub but no downstream tasks depend on it yet | Stub memory_service.py before Phase 10 tasks start |
| P3 — Medium | Regression detected — a previously accepted function was removed | Route removed from projects.py in a later edit |
| P4 — Low | Minor quality issue: missing docstring, placeholder comment | Non-blocking cosmetic issue |

---

## Repair Queue Processing

### When to process before roadmap task:

The manager checks the repair queue FIRST, before selecting from the roadmap.  
If any repair task with priority P0, P1, or P2 exists, it is dispatched instead of the roadmap task.

P3 and P4 repairs may be deferred until the current phase is complete.

### Exception — repair may be deferred if:

- The repair affects a file in a phase not yet reached (e.g., Phase 9 has a stub but manager is on Phase 5)
- The repair has priority P3/P4 AND the next roadmap task does not depend on it
- The repair was already attempted once and blocked (escalate, do not loop)

---

## Repair Queue Entry Schema

```json
{
  "repair_id": "10.4-repair",
  "original_task_id": "10.4",
  "original_task_title": "Create context_builder.py",
  "file": "backend/app/services/context_builder.py",
  "priority": "P1",
  "reason": "Accepted as def main(): pass stub",
  "detection_source": "false_accept_auditor",
  "detected_at": "2026-04-18T...",
  "repair_brief": "...",
  "attempts": 0,
  "max_attempts": 2,
  "status": "pending",
  "blocking_tasks": ["any task that imports context_builder"]
}
```

---

## Repair Escalation Rules

| Condition | Action |
|---|---|
| Repair fails max_attempts | Mark as `blocked`, add to escalation log, do NOT re-queue |
| Repair of same file fails twice | Decompose: split into 2 smaller repair tasks |
| Repair causes regression in another accepted file | Immediately queue a regression repair, escalate both |
| Phase 4+ file refuses to repair | Escalate to human — foundational issue |

---

## Example: Repair Queue Override

Roadmap next task: `10.4` (already done, but was a false positive)  
Repair queue: `10.4-repair` at priority P1

**Manager action:**  
Skip roadmap item (already marked [x]).  
Select `10.4-repair` from repair queue.  
Dispatch with repair brief.  
On acceptance: mark `executive_memory.false_positives[10.4]` status = `repaired`.  
Remove from repair queue.  
Resume normal roadmap selection.
