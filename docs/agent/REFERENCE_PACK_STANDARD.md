# Reference Pack Standard
## AI Workspace Platform — Autonomous Manager Context Assembly

**Version:** 1.0  
**Authority:** Every task dispatch must be preceded by a reference pack assembly step.  
**Enforcement:** `backend/app/services/reference_pack.py`

---

## Purpose

A reference pack is the minimum, task-specific context bundle assembled before writing a worker brief.

The manager must not re-read the entire project for every task.  
The manager must not skip context and produce vague briefs.  
The manager must assemble exactly what is needed — no more, no less.

A reference pack is selected, not generated. It is assembled from known sources using explicit rules.

---

## Contents of a Reference Pack

A reference pack contains:

| Slot | Content | When Included |
|---|---|---|
| `product_goal_summary` | 3-line product goal + MVP definition | Always (from executive memory) |
| `phase_context` | Current phase name + 1-line summary | Always |
| `doc_excerpts` | Key sections from architecture/data model docs | When task touches APIs, schemas, or data |
| `interface_refs` | Function signatures from files the task must call | When task creates a service that uses another |
| `prior_acceptance_notes` | Any false-accept or stub notes for this file | When file was previously accepted |
| `protected_paths` | Files that must not be touched | Always |
| `architecture_decisions` | Relevant ADRs from executive memory | For Level 3+ |

---

## Pack Size by Task Level

| Level | Max doc excerpts (chars) | Max code interface refs (chars) | Total pack target |
|---|---|---|---|
| 0 | 0 | 0 | < 200 chars |
| 1 | 500 | 300 | < 1,000 chars |
| 2 | 1,500 | 600 | < 2,500 chars |
| 3 | 3,000 | 1,200 | < 5,000 chars |
| 4 | 6,000 | 2,000 | < 10,000 chars |
| 5 | unlimited | unlimited | no cap |

These are soft targets. The manager must always prefer summaries from memory over full re-reads when the summary accurately describes the content.

---

## Doc Excerpt Selection Rules

For each candidate doc, include:
- **Only sections whose headings match task keywords**
- A max of 20 lines per included section
- Skip sections unrelated to the task's file types or keywords

Never include:
- Entire files when a section excerpt would serve
- Historical change logs, appendices, or deferred sections
- Docs that apply to phases 5+ away from the current task

---

## Code Interface Reference Rules

For each code file the task must call or extend:
- Include only the function/class signatures (def lines + docstring first line only)
- Do not include function bodies
- Format as: `# From: <path>\n<signature>\n  # <docstring first line>`

Example:
```python
# From: backend/app/services/memory_service.py
def recall_memory(project_id: str, key: str) -> Optional[str]:
  # Returns stored value or None if not found

def search_memories(project_id: str, query: str) -> list[dict]:
  # Returns top matching memory entries (substring match)
```

This gives the worker the contract without the full implementation (~5 lines vs 60).

---

## Substitution Rules (When Memory Can Replace File Read)

The manager may use a memory summary instead of reading a file when:
- The file was accepted at confidence level `verified` in executive memory
- The memory entry lists `key_functions` matching what the task needs
- The file has not been touched since the memory entry was written

The manager must re-read the file when:
- The memory entry is `file_only` or `false_positive`
- The task is modifying (not just calling) the file
- The task is Level 4+ and the file is in the integration surface
- There is a repair_queue entry for this file

---

## Pack Storage

Reference packs are ephemeral — they are not stored permanently.  
The pack assembly decisions (which docs/files were selected, total chars) are recorded in `executive_memory.recent_reference_packs` as a ring buffer of last 20.

This allows the manager to learn: if a task type repeatedly needs the same reference, promote it to the level's default reference set.

---

## Example: Level 2 Task — Create chat_service.py

**Task:** Create `backend/app/services/chat_service.py` with CRUD functions for chats and messages.

**Pack assembled:**
```
product_goal_summary:
  "Multi-project AI chat platform. MVP: create projects, chats, send messages, get AI."
  Current phase: Phase 6 — Chats & Messages API

doc_excerpts:
  [From DATA_MODEL.md — Chat section, 18 lines]
  Chat: id, project_id, title, created_at
  Message: id, chat_id, role, content, created_at

interface_refs:
  # From: backend/app/models/chat.py
  class Chat(Base): ...
  class Message(Base): ...
  # From: backend/app/db/session.py
  def get_db() -> Session: ...

prior_acceptance_notes: (none — file not previously attempted)

protected_paths:
  backend/app/main.py, backend/app/db/session.py, docs/VISION_DOCUMENT.md

Total pack: ~800 chars
```

---

## Example: Level 0 Task — Add one-line health check field

**Pack assembled:**
```
product_goal_summary: (3 lines)
protected_paths: (2 lines)
Total pack: ~180 chars
```

No doc excerpts. No interface refs. Worker gets the brief and the protected list.
