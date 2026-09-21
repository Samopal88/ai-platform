# Executive Memory Schema v2
## AI Workspace Platform — Manager Persistent State

**Version:** 2.0  
**Storage:** `docs/progress/executive_memory.json`  
**Written by:** `backend/app/services/executive_memory.py`  
**Read by:** `manager_loop.py` at the start of every cycle  
**Updated by:** `manager_loop.py` after every verdict (accepted / blocked / retry_required)

---

## 1. Purpose

The executive memory is the manager's persistent understanding of the product state.  
It is not a log. It is a living model of what has been built, what is broken, and what remains.

The manager reads this at cycle start to answer:
- What product am I building?
- What has been accepted as real and working?
- What was accepted but is actually a stub or false positive?
- What is blocked?
- What must not be touched?
- What phase are we in, and is that phase truly ready?
- How much context budget have we spent?

---

## 2. Key Distinction: Four-Level Completion Model

A file is **not done** just because it exists on disk.

| Level | Meaning |
|---|---|
| `missing` | File does not exist |
| `exists_on_disk` | File exists and is non-empty — no semantic verification |
| `semantically_valid` | File has real implementation (no stub bodies, real logic) |
| `integrated` | File is imported and used by other accepted files (cross-file verified) |
| `product_ready` | Accepted at `verified` confidence with no known issues |

Executive memory tracks each known file in `completion_levels`:

```json
"completion_levels": {
  "backend/app/services/chat_service.py": "semantically_valid",
  "backend/app/api/projects.py": "product_ready",
  "backend/app/services/context_builder.py": "exists_on_disk"
}
```

Phase gates use these levels. Only `semantically_valid` and above count as real foundations.

---

## 3. Full Schema

```json
{
  "schema_version": "2.0",
  "updated_at": "<ISO datetime>",

  "product": {
    "name": "AI Workspace Platform",
    "goal": "Multi-project AI chat platform with REST API and web UI",
    "mvp_definition": "User can create projects, start chats, send messages, get AI responses, upload files",
    "current_phase": "Phase 6 — Chats & Messages API",
    "phase_summary": "Building chat CRUD service and router",
    "authoritative_docs": [
      "docs/VISION_DOCUMENT.md",
      "docs/SYSTEM_ARCHITECTURE.md",
      "docs/DATA_MODEL.md",
      "docs/AGENT_INTERACTION_SPEC.md",
      "docs/IMPLEMENTATION_PLAN.md"
    ]
  },

  "architecture": {
    "decisions": [
      {
        "id": "arch-001",
        "decision": "FastAPI backend, SQLite dev DB, SQLAlchemy ORM",
        "rationale": "Specified in SYSTEM_ARCHITECTURE.md",
        "must_preserve": true
      },
      {
        "id": "arch-002",
        "decision": "All API routers registered in backend/app/main.py",
        "rationale": "Single registration point for router discovery",
        "must_preserve": true
      },
      {
        "id": "arch-003",
        "decision": "File executor writes only to declared safe directories",
        "rationale": "Security boundary prevents system file corruption",
        "must_preserve": true
      }
    ],
    "protected_files": [
      "backend/app/main.py",
      "backend/app/db/session.py",
      "backend/requirements.txt",
      "docs/VISION_DOCUMENT.md",
      "docs/SYSTEM_ARCHITECTURE.md",
      "docs/DATA_MODEL.md"
    ]
  },

  "implemented": {
    "pages": [
      {
        "path": "frontend/chat.html",
        "description": "AI chat UI with project/chat selection",
        "accepted_at": "<ISO datetime>",
        "task_id": "9.1",
        "key_functions": ["loadProjects", "sendMessage", "loadHistory"],
        "confidence": "verified"
      }
    ],
    "api_routers": [
      {
        "path": "backend/app/api/projects.py",
        "description": "Projects CRUD endpoints",
        "routes": ["POST /api/projects", "GET /api/projects", "GET /api/projects/{id}", "PUT /api/projects/{id}", "DELETE /api/projects/{id}"],
        "accepted_at": "<ISO datetime>",
        "task_id": "5.3",
        "confidence": "verified"
      }
    ],
    "services": [
      {
        "path": "backend/app/services/memory_service.py",
        "description": "Memory CRUD and search",
        "key_functions": ["store_memory", "recall_memory", "search_memories"],
        "accepted_at": "<ISO datetime>",
        "task_id": "10.1",
        "confidence": "verified"
      }
    ],
    "schemas": [],
    "migrations": []
  },

  "completion_levels": {
    "backend/app/services/chat_service.py": "semantically_valid",
    "backend/app/api/projects.py": "product_ready",
    "backend/app/services/context_builder.py": "exists_on_disk"
  },

  "false_positives": [
    {
      "task_id": "10.4",
      "file": "backend/app/services/context_builder.py",
      "accepted_at": "<ISO datetime>",
      "detected_at": "<ISO datetime>",
      "reason": "File accepted but contains only def main(): pass stub",
      "detection_method": "post_acceptance_scan",
      "repair_task_id": "10.4-repair",
      "status": "pending_repair"
    }
  ],

  "stubs": [
    {
      "path": "backend/app/services/context_builder.py",
      "function": "main",
      "task_id": "10.4",
      "reason": "Worker produced def main(): pass wrapper instead of real module",
      "repair_priority": "high"
    }
  ],

  "blocked": [
    {
      "task_id": "4.3",
      "title": "Create backend/alembic.ini and backend/alembic/env.py",
      "blocked_at": "<ISO datetime>",
      "retries": 2,
      "reason": "Required files missing after max retries",
      "root_cause_hypothesis": "File executor cannot create files in backend/ root",
      "resolution": "pending"
    }
  ],

  "regressions": [
    {
      "file": "backend/app/api/projects.py",
      "detected_at": "<ISO datetime>",
      "task_that_caused": "6.3",
      "what_was_removed": ["GET /api/projects/{id}", "def get_project"],
      "repair_status": "pending"
    }
  ],

  "product_gaps": [
    {
      "gap_id": "gap-10.4",
      "description": "context_builder.py is a stub — AI chat pipeline broken at context assembly",
      "impact": "POST /api/chats/{id}/complete cannot inject chat history into AI prompt",
      "repair_task": "10.4-repair",
      "priority": "critical"
    }
  ],

  "what_must_not_regress": [
    "backend/app/api/projects.py — 5 CRUD routes",
    "backend/app/api/chats.py — 4 routes for chat/message CRUD",
    "backend/app/api/ai_chat.py — POST /api/chats/{id}/complete",
    "backend/app/api/memory.py — 4 memory endpoints",
    "backend/app/api/files.py — 4 file endpoints",
    "backend/app/main.py — router registrations for all above"
  ],

  "repair_queue_summary": {
    "pending_count": 2,
    "override_count": 1,
    "last_updated": "<ISO datetime>"
  },

  "phase_readiness": {
    "Phase 4": {
      "status": "cleared",
      "blocking_reasons": [],
      "repair_tasks_needed": [],
      "warnings": [],
      "last_checked": "<ISO datetime>"
    },
    "Phase 5": {
      "status": "cleared",
      "blocking_reasons": [],
      "repair_tasks_needed": [],
      "warnings": [],
      "last_checked": "<ISO datetime>"
    },
    "Phase 6": {
      "status": "blocked",
      "blocking_reasons": ["project_service.py is a stub — chat service will fail at import"],
      "repair_tasks_needed": ["5.2-repair"],
      "warnings": [],
      "last_checked": "<ISO datetime>"
    },
    "Phase 7": {
      "status": "not_checked"
    }
  },

  "recent_reference_packs": [
    {
      "task_id": "6.2",
      "level": 2,
      "doc_excerpts_count": 1,
      "interface_refs_count": 2,
      "total_chars": 820,
      "assembled_at": "<ISO datetime>"
    }
  ],

  "context_budget_stats": {
    "total_cycles": 47,
    "total_chars_assembled": 120000,
    "avg_chars_per_cycle": 2553,
    "budget_overruns": 3,
    "overrun_cycles": ["10.2", "9.1", "6.3"],
    "memory_substitutions_used": 23,
    "most_expensive_task_type": "multi-file integration",
    "by_level": {
      "0": { "cycles": 5, "total_chars": 900, "avg_chars": 180 },
      "1": { "cycles": 12, "total_chars": 10680, "avg_chars": 890 },
      "2": { "cycles": 22, "total_chars": 52800, "avg_chars": 2400 },
      "3": { "cycles": 6, "total_chars": 34800, "avg_chars": 5800 },
      "4": { "cycles": 2, "total_chars": 18400, "avg_chars": 9200 }
    }
  },

  "cycle_log": [
    {
      "cycle_at": "<ISO datetime>",
      "task_id": "10.4",
      "verdict": "accepted",
      "files": ["backend/app/services/context_builder.py"],
      "notes": "Accepted — later flagged as stub by false_accept_auditor"
    }
  ]
}
```

---

## 4. Confidence vs Completion Level

These are related but distinct:

| confidence (in `implemented.*`) | completion_level |
|---|---|
| `verified` | `product_ready` |
| `structural` | `semantically_valid` |
| `file_only` | `exists_on_disk` |
| `false_positive` | `exists_on_disk` (or demoted from higher) |

When a false positive is detected, the `completion_levels` entry is **downgraded** to `exists_on_disk`. A successful repair upgrades it back to `semantically_valid` or higher.

---

## 5. Update Protocol

After each cycle, the manager must:

1. **On `accepted`:** Add to `implemented.*`, set `completion_levels[path] = semantically_valid`, remove from `stubs` and `false_positives` if previously there
2. **On `blocked`:** Add to `blocked[]` with `root_cause_hypothesis`; set `completion_levels[path] = exists_on_disk`
3. **On `retry_required`:** Update `cycle_log`, do not change `implemented` state
4. **On false-accept detected (post-acceptance):** Move from `implemented` to `false_positives`, demote `completion_levels`, create `product_gaps` entry, queue repair
5. **On repair accepted:** Set `false_positives[*].status = "repaired"`, upgrade `completion_levels`, remove from `stubs`, resolve `product_gaps` entry
6. **Always:** Update `product.current_phase`, `product.phase_summary`, `repair_queue_summary`, `updated_at`

---

## 6. Reading Protocol

At cycle start, the manager must:

1. Load executive memory
2. Check `repair_queue_summary.override_count` — if > 0, repair queue will override roadmap (task_intake handles this)
3. Check `false_positives` with `status == "pending_repair"` — these create repair priorities
4. Check `product_gaps` with `priority == "critical"` — these override roadmap sequence
5. Check `phase_readiness` for the next roadmap task's phase — if `blocked`, defer to repair first
6. Only then proceed with normal roadmap selection

---

## 7. Storage Location and Backup

- **Primary:** `docs/progress/executive_memory.json`
- **Backup on each write:** `docs/progress/executive_memory.json.bak`
- **Format:** JSON, indented 2 spaces, UTF-8
- **Growth management:** `cycle_log` is a ring buffer of last 50 entries; `recent_reference_packs` is last 20; all other sections grow until explicitly resolved
- **Never:** Truncate `implemented`, `false_positives`, `product_gaps`, or `completion_levels` automatically
