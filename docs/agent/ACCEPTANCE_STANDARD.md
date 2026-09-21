# Acceptance Standard
## AI Workspace Platform — Task Review and Acceptance Gate

**Version:** 1.0  
**Authority:** This document defines what "accepted" means. A task must satisfy ALL applicable criteria to be accepted.  
**Enforcement:** manager_loop._review_result() and semantic_validator.py enforce these rules programmatically. This document is the human-readable specification.

---

## 1. Core Principle

**Acceptance is evidence-based, not optimistic.**

The manager must not accept because:
- The file exists (necessary but not sufficient)
- The worker reported success (worker self-reports are unreliable)
- No error was thrown (absence of error ≠ presence of correctness)
- The task looks plausible (plausible ≠ complete)

The manager must accept because:
- The file exists AND contains the required functions/classes/routes
- The required functions have real bodies, not `pass`
- The file does not contain placeholder text
- The file does not regress previously accepted structure
- The file is the right kind of content for its declared purpose

---

## 2. Universal Gates (All Task Types)

These checks apply to every accepted file regardless of type.

| Check | Pass Condition | Fail → Verdict |
|---|---|---|
| Worker success | worker_result.success == True | → retry_required |
| Target file exists | File on disk, size > 0 | → retry_required |
| Target file was changed | File path in files_changed | → retry_required |
| No placeholder content | No "Generated Content", "Lorem ipsum", "TODO Placeholder", "Insert content here", "Coming soon" | → retry_required |
| Correct file was changed | files_changed intersects task.files (not just any file) | → retry_required |

**Critical false-accept pattern to detect:** Worker changes `docs/system_architecture.md` but not `backend/app/main.py` when the task required `backend/app/main.py`. The file_changed count is > 0 but the required target was not touched. This must fail.

---

## 3. Python Service Files (`backend/app/services/*.py`)

| Check | Pass Condition |
|---|---|
| Not a stub | No function body consisting only of `pass` for required functions |
| Real implementation | Key functions contain at least 5 lines of non-comment logic |
| No placeholder docstring body | Docstring body is not the task description copy-pasted |
| Correct imports | Required external modules are imported (not commented out) |
| No `main()` wrapper masking as service | File is not a `def main(): ... if __name__ == "__main__": main()` script |

**Stub signature detection:** Any file matching the pattern below is a stub, not a service:
```python
def some_function(...):
    """<task description copied here>"""
    pass
```

---

## 4. Python API Files (`backend/app/api/*.py`)

| Check | Pass Condition |
|---|---|
| Has APIRouter | `router = APIRouter(...)` present |
| Has at least 1 route decorator | `@router.get`, `@router.post`, `@router.put`, or `@router.delete` |
| Route functions are non-empty | No route handler body consisting only of `pass` |
| Correct route paths | Route paths match expected API contract (from SYSTEM_ARCHITECTURE.md) |
| No registration in same file | Router is not self-registered (registration belongs in main.py) |

---

## 5. Frontend HTML Files (`frontend/*.html`)

### 5a. Structural

| Check | Pass Condition |
|---|---|
| Has `<title>` | Title tag present and non-empty |
| Title matches purpose | Title is not "Generated Content", "AI Workspace Dashboard" for chat.html, etc. |
| Has `<body>` content | Body is not empty or has only one line |
| Has at least one interactive element | `<input>`, `<button>`, `<textarea>`, or `<select>` |
| Has at least one JS function | `function` keyword or arrow function present in `<script>` |

### 5b. Page Identity (cross-page overwrite detection)

| Page File | Must Contain | Must Not Contain |
|---|---|---|
| `chat.html` | chat/message/send/input UI elements | dashboard/manager/orchestrator as primary content |
| `dashboard.html` | manager/status/task/loop UI elements | chat message input as primary content |

### 5c. API Integration

| Check | Pass Condition |
|---|---|
| Chat UI calls chat APIs | `/api/chats` or `/api/projects` referenced in JS |
| Dashboard calls management APIs | `/api/active-job`, `/api/job-status`, or `/api/health` referenced |
| No hardcoded mock data | No `const messages = [...]` hardcoded mock arrays as primary data source |

---

## 6. Configuration Files

| File Type | Pass Condition |
|---|---|
| `requirements.txt` | Contains actual package names with versions or version constraints |
| `.env.example` | Contains at least one `KEY=` line with comment |
| `alembic.ini` | Contains `[alembic]` section and `script_location` |
| `*.json` schema/config | Valid JSON, keys match expected schema |

---

## 7. Regression Gate

For any file that was previously accepted (has a snapshot in `docs/progress/file_snapshots/`):

| Check | Pass Condition |
|---|---|
| Route count did not decrease | New route count ≥ previous route count |
| Key function names preserved | Previously accepted `def:X` tokens still present |
| Key HTML element ids preserved | Major id= values not mass-deleted (>5 removals = warning) |

A regression in a previously accepted file from a different task is grounds for `retry_required` on the new task, with a repair task created.

---

## 8. Example: Bad Acceptance (Pre-Executive Standard)

**Task:** 10.4 — Create context_builder.py  
**Files changed:** `docs/task_prompt_templates.md`, `docs/vision_document.md`, `backend/app/services/context_builder.py`  
**Review result:** `accepted` — "All checks passed. 3 file(s) changed."

**Why this is a false acceptance:**
- `context_builder.py` was created with content:
  ```python
  def main():
      """Task 10.4: Create backend/app/services/context_builder.py ..."""
      pass
  ```
- File exists: ✓ (passed)
- File non-empty: ✓ (passed — has a function)
- Semantic check: NOT RUN because `context_builder` has no rules in `_PYTHON_API_REQUIRED`
- Result: A completely non-functional stub was accepted as complete

**Failure modes exposed:**
1. Semantic validator only covers `backend/app/api/` files, not `backend/app/services/`
2. No check for `pass`-only function bodies in services
3. No check that `files_changed` contains the task's declared `files` (docs were changed instead)

---

## 9. Example: Correct Acceptance Report

**Task:** 6.3 — Create backend/app/api/chats.py  
**Acceptance report:**
```
worker_success: OK
file_exists(backend/app/api/chats.py): OK
files_changed: 2 [backend/app/api/chats.py confirmed in changed list]
python_no_stub(chats): OK — no placeholder patterns
python_has_router(chats): OK — APIRouter present
python_routes(chats): OK — 4 routes found
route_paths(chats): OK — /api/projects/{project_id}/chats, /api/chats/{chat_id}/messages confirmed
regression(chats): no snapshot yet, skipped
semantic_validator: PASSED
```
**Verdict: accepted**

---

## 10. Escalation Triggers

If the review reveals any of the following, escalate rather than retry:

| Condition | Action |
|---|---|
| Worker changed only docs, not code files (3rd time) | BLOCK + create repair task targeting the docs files for cleanup |
| File exists but is a `def main(): pass` wrapper (2nd time) | BLOCK + rewrite brief with explicit stub-forbidden instruction |
| Previously accepted file was overwritten with wrong content | BLOCK + create regression repair task before continuing |
| Task acceptance would contradict product architecture docs | BLOCK + escalate to human |
| All roadmap tasks are marked done but product visibly broken | Trigger retroactive audit via false_accept_auditor |
