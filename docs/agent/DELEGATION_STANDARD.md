# Delegation Standard
## AI Workspace Platform — Worker Task Brief Format

**Version:** 1.0  
**Authority:** All task prompts sent to the worker (file_executor / claude_executor) MUST conform to this standard.  
**Enforcement:** manager_loop and task_intake are responsible for producing compliant briefs. Vague prompts must be rejected before dispatch.

---

## 1. Purpose

A worker task brief is not a description of what to do.  
It is a complete engineering contract that enables the worker to produce correct output on the first attempt.

A brief is complete when a skilled engineer reading it could implement the task without asking any questions.

---

## 2. Mandatory Sections

Every worker task prompt MUST contain all of these sections. Absence of any section is a malformed brief.

```
TASK BRIEF
==========

## Objective
[One sentence: what must be created or changed, stated as an outcome, not an activity]

## Product Reason
[Why this matters to the working product. What breaks or is incomplete without it.]

## Target Files
[Exact relative paths. One per line. No wildcards.]

## Must Not Touch
[Files that must not be modified. Especially: main.py, __init__.py, .env, vision docs]

## Required References
[Docs the worker must read before implementing. Exact paths.]

## Implementation Requirements
[Specific functions, classes, routes, fields, behaviors that must be present.
NOT "implement a chat service" — instead:
  - class ChatService with methods: create_chat(db, project_id, title), get_messages(db, chat_id)
  - all methods must take db: Session as first argument
  - imports: from app.models.chat import Chat, Message
  - no stubs, no pass bodies]

## Non-Goals
[What is explicitly out of scope. Prevents scope creep and side-effects.]

## Acceptance Criteria
[Verifiable, file-level checks the manager will run after execution:
  - File exists and is non-empty
  - Contains class/function X
  - Function X has parameters (db, project_id)
  - No placeholder text
  - No pass-only function bodies for required functions]

## Regression Risks
[Previously accepted files that this task might affect. List them explicitly.]

## Expected Output Quality
[Code | Document | Configuration | Test | Schema]
[Production-quality / prototype / documentation-only]
```

---

## 3. Prohibited Brief Patterns

These patterns in a task brief indicate it is malformed and must be rewritten before dispatch:

| Pattern | Why Prohibited |
|---|---|
| `"Create file X"` with no implementation requirements | Worker produces a stub |
| `"Implement Y"` with no function signatures | Worker guesses the interface |
| No `Must Not Touch` section | Worker may overwrite main.py or vision docs |
| No `Acceptance Criteria` | Manager cannot verify against stated contract |
| No `Product Reason` | Worker has no basis to make implementation decisions |
| References to docs that don't exist | Worker gets no context; produces generic output |
| `"See change description"` in files section | Files must be explicit |

---

## 4. Example: Bad Brief (Pre-Executive Standard)

```
Task 10.4: Create `backend/app/services/context_builder.py
Files: backend/app/services/context_builder.py
Change: `build_context(project_id, chat_id, query: str) -> str`. Collects: last 10 messages fr
Why: AI complete endpoint needs a context builder that combines history + memory + project info
Product context: docs/VISION_DOCUMENT.md, docs/TASK_PROMPT_TEMPLATES.md
```

**Problems:**
- Change description is truncated at 300 chars — critical spec is missing
- No function signature details
- No import requirements
- No `Must Not Touch`
- No `Acceptance Criteria`
- No `Regression Risks`
- No `Non-Goals`
- Result: worker produced `def main(): pass` — accepted as success

---

## 5. Example: Correct Executive-Standard Brief

```
TASK BRIEF
==========

## Objective
Create backend/app/services/context_builder.py with a functional build_context()
that assembles a prompt-ready context string from chat history, project memory, and project metadata.

## Product Reason
The POST /api/chats/{chat_id}/complete endpoint (ai_chat.py) needs a context assembler
to produce meaningful AI responses. Without it, all AI responses are context-free.
This is the final missing piece before the chat-to-AI pipeline works end-to-end.

## Target Files
backend/app/services/context_builder.py

## Must Not Touch
backend/app/main.py
backend/app/api/ai_chat.py
backend/app/services/memory_service.py
docs/VISION_DOCUMENT.md
docs/SYSTEM_ARCHITECTURE.md

## Required References
docs/SYSTEM_ARCHITECTURE.md — section: AI Chat flow, context injection
docs/DATA_MODEL.md — Chat and Message schema
backend/app/services/memory_service.py — existing recall_memory() and search_memories() signatures
backend/app/services/chat_service.py — existing get_messages() signature

## Implementation Requirements
- Module: backend/app/services/context_builder.py
- Function: build_context(project_id: str, chat_id: str, query: str) -> str
- Must import and call: memory_service.search_memories(project_id, query) — top 3 results
- Must import and call: chat_service.get_messages(db, chat_id) — last 10 messages
- Must format output as: system prompt block including project name, relevant memories, message history
- Must handle empty memory / empty history gracefully (no exceptions)
- All DB interactions must accept a db: Session parameter (pass None for now with fallback)
- No placeholder text. No stub pass bodies. No TODO comments.

## Non-Goals
- Do not implement vector search or embedding-based retrieval
- Do not modify chat_service.py or memory_service.py
- Do not add API endpoints
- Do not create tests in this task

## Acceptance Criteria
- File backend/app/services/context_builder.py exists and is >30 lines
- Contains: def build_context(project_id
- Contains: search_memories or recall_memory (memory integration present)
- Contains: get_messages (chat history integration present)
- No line: pass (no stub function bodies)
- No text: "Generated Content", "TODO", "placeholder"

## Regression Risks
- backend/app/services/memory_service.py — do not overwrite
- backend/app/services/chat_service.py — do not overwrite

## Expected Output Quality
Production-quality service module. Will be called by the AI chat endpoint in production.
```

---

## 6. Brief Validation Checklist (Manager Must Run Before Dispatch)

Before sending any brief to the worker, the manager must confirm:

- [ ] All 8 mandatory sections are present
- [ ] Target files list is explicit (no `see change description`)
- [ ] Implementation requirements include at least one function/class name with signature
- [ ] Acceptance criteria are verifiable without running the code
- [ ] Must Not Touch includes main.py, __init__.py, .env files
- [ ] References point to files that actually exist on disk
- [ ] Non-Goals prevent the most likely scope creep for this task type

If any item is unchecked, the brief must be rewritten, not dispatched.
