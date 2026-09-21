# Task Examples

Concrete example prompts that the platform handles correctly end-to-end.
Use these to verify the pipeline or as templates for new tasks.

---

## Example 1

**Task:** `create sandbox/counter.py with a Counter class`
**Expected files_changed:** `["sandbox/counter.py"]`
**DoD:** `sandbox/counter.py` exists
**Notes:** `Counter` is extracted as entity name by `_generate_file_content`.

---

## Example 2

**Task:** `create tests/test_utils.py with smoke tests for the utils module`
**Expected files_changed:** `["tests/test_utils.py"]`
**DoD:** `tests/test_utils.py` exists
**Notes:** `tests/` prefix is in SAFE_DIRS; file is created without LLM.

---

## Example 3

**Task:** `create frontend/components/Button.js with a button component`
**Expected files_changed:** `["frontend/components/Button.js"]`
**DoD:** `frontend/components/Button.js` exists
**Notes:** "component" keyword triggers React functional component template.

---

## Example 4

**Task:** `create docs/progress/SPRINT_NOTES.md with sprint summary`
**Expected files_changed:** `["docs/progress/SPRINT_NOTES.md"]`
**DoD:** `docs/progress/SPRINT_NOTES.md` exists
**Notes:** `docs/` prefix is in SAFE_DIRS; markdown template used.

---

## Example 5

**Task:** `create backend/app/services/cache.py with a Cache class`
**Expected files_changed:** `["backend/app/services/cache.py"]`
**DoD:** `backend/app/services/cache.py` exists
**Notes:** `backend/app/services/` is in SAFE_DIRS.

---

## Example 6

**Task:** `create sandbox/config.yaml with default configuration`
**Expected files_changed:** `["sandbox/config.yaml"]`
**DoD:** `sandbox/config.yaml` exists
**Notes:** YAML template used; `# task:` comment + `generated:` field.

---

## Example 7

**Task:** `add get_count function to sandbox/counter.py`
**Expected files_changed:** `["sandbox/counter.py"]` (modified)
**DoD:** `sandbox/counter.py` exists; pattern `def get_count` found
**Notes:** `_generate_modification` detects "add function" intent, appends stub.

---

## Example 8

**Task:** `create frontend/utils/api.js with fetch helper functions`
**Expected files_changed:** `["frontend/utils/api.js"]`
**DoD:** `frontend/utils/api.js` exists
**Notes:** "function" keyword triggers named-function JS template.

---

## Example 9

**Task:** `create backend/app/api/metrics.py with a metrics endpoint`
**Expected files_changed:** `["backend/app/api/metrics.py"]`
**DoD:** `backend/app/api/metrics.py` exists
**Notes:** `backend/app/api/` is in SAFE_DIRS.

---

## Example 10

**Task:** `create scripts/cleanup.py with a cleanup utility`
**Expected files_changed:** `["scripts/cleanup.py"]`
**DoD:** `scripts/cleanup.py` exists
**Notes:** `scripts/` is in SAFE_DIRS; "cleanup" extracted as function name.

---

## Anti-patterns (tasks that will likely be blocked or produce wrong output)

| Bad prompt | Problem | Fix |
|---|---|---|
| `create main.py` | `main.py` at root is not in SAFE_DIRS | Use `sandbox/main.py` |
| `update the auth module` | No file path → DoD has no required_files | Add explicit path: `update backend/app/services/auth.py` |
| `create a utility` | No extension → file type unknown | Add filename: `create sandbox/utility.py` |
| `fix the bug in login` | No concrete file or change | Specify: `update backend/app/api/auth.py to fix login validation` |
