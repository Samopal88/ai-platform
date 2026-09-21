# AI Workspace Platform — Agent Workflow

## Golden Rule

**Never read the entire project.** Use the system map to find the one or two
files relevant to the current task, then read only those.

Lookup order:
1. `docs/agent/SYSTEM_MAP.md` — find which file handles your concern
2. Read that specific file
3. Make the change
4. Verify on disk

---

## Task Execution Pipeline

```
User task prompt
      │
      ▼
1. INTAKE
   Read:
   - docs/agent/PROJECT_BRIEF.md (once per session)
   - docs/progress/CURRENT_STATUS.md (current state)

   If task affects product behaviour, also read the relevant section of:
   - docs/VISION_DOCUMENT.md
   - docs/SYSTEM_ARCHITECTURE.md
   - docs/DATA_MODEL.md
   - docs/AGENT_INTERACTION_SPEC.md

   Do NOT scan all of backend/ or services/

      │
      ▼
2. PLAN
   Identify target files from task description
   Check SYSTEM_MAP.md for correct service / path
   Confirm paths are in SAFE_DIRS (see PROJECT_BRIEF.md)
   Create a short list of steps (3–5 max for typical tasks)

      │
      ▼
3. EXECUTE STEP
   Read only the file(s) you need to change
   Make the change (create / modify / patch)
   Confirm the file exists on disk after write
   Record in files_changed

      │
      ▼
4. REVIEW STEP
   Check: does the file exist?
   Check: does it contain expected content?
   Check: no error markers in output?
   If review passes → go to next step
   If review fails  → create a clean fix prompt (no review text in payload)

      │
      ▼
5. RETRY (if needed)
   Execute the ORIGINAL task description again, not the review markdown
   Self-fix logic is internal; do not inject "## Self-Correction" into file content
   Max 2 retries before marking blocked

      │
      ▼
6. MARK COMPLETE
   Verify all required_files exist on disk
   Update docs/progress/CURRENT_STATUS.md
   Clear active_task in orchestrator_state.json
   Return files_changed list

      │
      ▼
7. NEXT STEP (manager mode)
   Only proceed if current step review passed
   Manager decides order — do not skip steps
```

---

## Reading Files — Economy Rules

| Situation | What to read |
|---|---|
| "What does the platform do?" | `docs/agent/PROJECT_BRIEF.md` only |
| "Where is X implemented?" | `docs/agent/SYSTEM_MAP.md` only |
| "Fix a bug in file_executor" | Read `services/file_executor.py` only |
| "Add endpoint" | Read `api/jobs.py` only |
| "Current status?" | Read `docs/progress/CURRENT_STATUS.md` only |
| "Job state for job X?" | Read `storage/jobs/X.json` only |
| "All services overview" | `docs/agent/SYSTEM_MAP.md` — do not open each service file |

Never do: `find . -name "*.py"` or read all services to understand one thing.

---

## Writing Files — Rules

1. **Always write to SAFE_DIRS** (see PROJECT_BRIEF.md § Safe Write Directories)
2. **Normalize paths** — no `../` traversal, must stay inside PROJECT_ROOT
3. **One file per step** — do not batch unrelated writes into one step
4. **Content must reflect the task** — do not include review/fix markdown in file content
5. **Confirm existence** — after write, check `Path(target).exists()` before marking step done

### Content generation rules

- `.py` files: proper module docstring + real logic, not just `print("done")`
- `.js/.ts` files: proper exports/imports for the project's style
- `.md` files: structured markdown, no placeholder text
- `.json` files: valid JSON, no trailing commas
- Never write into a file: `## Self-Correction`, `## REQUIRED FIXES`, retry counts

---

## State Update Protocol

After any file change:

```python
# Minimum required updates:
job_queue.update_job(job_id, files_changed=[changed_file])
# Optional but preferred:
project_state.on_job_progress(job_id, f"Created {changed_file}")
# On completion:
project_state.on_job_finish(job_id, success=True, files=files_changed)
# CURRENT_STATUS.md auto-syncs via status_updater.sync_status_file()
```

Do NOT manually edit `CURRENT_STATUS.md` — let `status_updater.py` handle it.

---

## Definition of Done Checklist

Before marking a task complete, verify:

- [ ] Every file listed in `dod.required_files` exists on disk
- [ ] Every pattern in `dod.required_patterns` matches in the file
- [ ] `orchestrator_state.json` → `status: completed`, `current_task: null`
- [ ] `job.json` → `status: finished`, `files_changed` is non-empty (if files were expected)
- [ ] No `error` field in job record
- [ ] `CURRENT_STATUS.md` reflects completed task

---

## Anti-Patterns to Avoid

| Anti-pattern | Correct approach |
|---|---|
| Passing review markdown as task payload | Always pass `original_task` to executor |
| `"Job completed successfully (simulated)"` | Only return success when files actually changed |
| Reading all `.py` files to understand one function | Use SYSTEM_MAP to find the right file |
| Creating files outside SAFE_DIRS | Fallback to `sandbox/<filename>` |
| Marking complete without verifying file exists | Check `Path(f).exists()` explicitly |
| Writing `## Self-Correction Attempt 2` into file content | Self-fix is internal; never inject into payload |
| Scanning `storage/jobs/` to find active job | Use `/api/active-job` endpoint |

---

## Common Task Patterns

### Create a new file
```
Task: "create frontend/Button.js with a button component"
→ Analyze: target = frontend/Button.js (in SAFE_DIRS ✓)
→ Generate content appropriate for .js
→ file_executor.create_file("frontend/Button.js", content)
→ Verify exists
→ Done: files_changed = ["frontend/Button.js"]
```

### Modify existing file
```
Task: "add /api/health endpoint to backend/app/api/jobs.py"
→ Read backend/app/api/jobs.py (only this file)
→ Identify insertion point
→ file_executor.patch_file(path, find=..., replace=...)
→ Verify pattern present
→ Done
```

### Add test
```
Task: "add unit tests for file_executor to tests/test_file_executor.py"
→ Target: tests/test_file_executor.py (in SAFE_DIRS ✓)
→ Read file_executor.py public API (only)
→ Write test file
→ Done
```

### Update docs
```
Task: "update docs/README.md with API documentation"
→ Target: docs/README.md (in SAFE_DIRS ✓)
→ Read current README (if exists)
→ Append/replace relevant section
→ Done
```
