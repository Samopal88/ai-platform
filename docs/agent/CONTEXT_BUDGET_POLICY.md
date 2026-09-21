# Context Budget Policy
## AI Workspace Platform — Autonomous Manager

**Version:** 1.0  
**Authority:** Context assembly for every task must comply with this budget.  
**Enforcement:** `reference_pack.py` respects these limits; violations are logged in `executive_memory.context_budget_stats`.

---

## Problem Statement

Uncontrolled context reading has two failure modes:
1. **Over-reading:** Manager reads entire docs and codebases for a trivial patch → token waste, slow cycles, no precision improvement
2. **Under-specifying:** Manager sends vague brief with no references → worker produces stubs → false accepts → repair cycles

The goal is targeted reading — exactly the context needed for this task, assembled from the cheapest source available.

---

## Source Hierarchy (Cheapest to Most Expensive)

The manager must always prefer the cheapest source that accurately answers the question.

| Priority | Source | Cost | When to Use |
|---|---|---|---|
| 1 | Executive memory summary (key_functions list) | Near-zero | When file was accepted at `verified` confidence and task only calls it |
| 2 | Signature-only excerpt (def lines + docstring first line) | Minimal | When task must match an interface |
| 3 | Section excerpt from authoritative doc (≤20 lines) | Low | When task creates a resource defined in the doc |
| 4 | Full read of a single small file (<60 lines) | Medium | When task modifies the file |
| 5 | Full read of a large file (>60 lines) | High | Only for Level 4+ or when the file is the task target |
| 6 | Multiple large files full read | Very high | Only for Level 5 or phase-gate validation |

**Never escalate to a more expensive source without first exhausting cheaper ones.**

---

## Budget Tables

### Per Task Level

| Level | Max total context (chars) | Max doc excerpts | Max full file reads | Notes |
|---|---|---|---|---|
| 0 | 300 | 0 | 0 | Memory summary only + protected list |
| 1 | 1,500 | 1 excerpt | 1 small file | One architecture section + one interface ref |
| 2 | 4,000 | 2 excerpts | 1 full file | Data model section + one interface file |
| 3 | 8,000 | 3 excerpts | 2 full files | Architecture + data model + 2 integration targets |
| 4 | 16,000 | 4 excerpts | 3 full files | All relevant specs + full target reading |
| 5 | no cap | no cap | no cap | Full context justified |

### Per Doc Category

| Doc | When to include | Max excerpt size |
|---|---|---|
| `VISION_DOCUMENT.md` | Frontend tasks only | 30 lines (UX section) |
| `SYSTEM_ARCHITECTURE.md` | API, routing, service tasks | 25 lines (relevant section) |
| `DATA_MODEL.md` | Schema, model, CRUD tasks | 20 lines (entity definition) |
| `AGENT_INTERACTION_SPEC.md` | Agent/executor tasks only | 20 lines |
| `IMPLEMENTATION_PLAN.md` | Phase gate check only | 10 lines (phase section) |

---

## When Memory Substitutes for File Read

The manager uses the executive memory entry instead of reading a file when:

| Condition | Allowed |
|---|---|
| File is `verified` + task only calls it (not modifies it) | ✓ Use key_functions list |
| File is `structural` + task only calls it | ✓ Use key_functions but note uncertainty |
| File is `file_only` | ✗ Must re-read — we don't know what's in it |
| File is `false_positive` | ✗ Must re-read — previous content was wrong |
| File is in repair queue | ✗ Must re-read — content may have changed |
| Task is Level 4+ | ✗ Must always read directly for this level |

---

## Refresh Rules

The manager must refresh from source (re-read the actual file or doc) when:
- The file has been modified since the memory entry was written (`mtime > memory.updated_at`)
- The executive memory entry shows `false_positive` or `repair_queue` status
- The task is a repair task (always read the file being repaired)
- No memory entry exists for the file

The manager must NOT refresh:
- Stable architecture docs that haven't changed in multiple phases (cache the section excerpt)
- Files accepted at `verified` confidence that are not the current task target

---

## Usage Tracking

After every cycle, record in `executive_memory.context_budget_stats`:

```json
"context_budget_stats": {
  "total_cycles": 47,
  "total_chars_assembled": 120000,
  "avg_chars_per_cycle": 2553,
  "budget_overruns": 3,
  "overrun_cycles": ["10.2", "9.1", "6.3"],
  "most_expensive_task_type": "multi-file integration",
  "memory_substitutions_used": 23,
  "by_level": {
    "0": { "cycles": 5, "avg_chars": 180 },
    "1": { "cycles": 12, "avg_chars": 890 },
    "2": { "cycles": 22, "avg_chars": 2400 },
    "3": { "cycles": 6, "avg_chars": 5800 },
    "4": { "cycles": 2, "avg_chars": 9200 }
  }
}
```

This allows the manager to identify which task types consistently exceed budget and adjust their level assignments or extract frequently-needed sections into the level's default reference set.

---

## Discipline Rules

1. **Never dump entire docs.** Always select sections by keyword.
2. **Never read a file you don't need.** If the task doesn't touch it, don't read it.
3. **Never re-read docs that haven't changed.** Cache section excerpts across cycles in the same phase.
4. **Never increase context because the worker produced a bad result.** Fix the brief instead.
5. **Use memory summaries as the first-pass interface reference.** Only open the file if the summary is insufficient.
6. **One doc re-read per repair.** Repair tasks read the target file once, not the entire project.
