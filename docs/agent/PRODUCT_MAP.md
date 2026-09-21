# Product Map

## Purpose

Index of product-level documentation.
Use this file to decide which product doc to read before implementing a feature.

---

## Files

### VISION_DOCUMENT.md
High-level platform purpose and user value.

### SYSTEM_ARCHITECTURE.md
Component structure and responsibilities.

### DATA_MODEL.md
Core entities and relationships.

### AGENT_INTERACTION_SPEC.md
How AI agents interact with tasks and system state.

### IMPLEMENTATION_PLAN.md
Execution phases and milestones.

### TASK_PROMPT_TEMPLATES.md
Templates for task generation.

---

## Reading Strategy

Do NOT read all files every time.

Use this table to decide which doc is relevant:

| Task type | Read |
|-----------|------|
| API change | `SYSTEM_ARCHITECTURE.md` |
| DB / schema change | `DATA_MODEL.md` |
| Agent logic / executor behaviour | `AGENT_INTERACTION_SPEC.md` |
| UX behaviour / user-facing feature | `VISION_DOCUMENT.md` |
| Planning / phasing | `IMPLEMENTATION_PLAN.md` |
| Prompt design / task templates | `TASK_PROMPT_TEMPLATES.md` |

Read only the section relevant to your change, not the entire document.

---

## Authority Rule

These files define **what** the platform must do.
Execution-layer files (`SYSTEM_MAP.md`, `WORKFLOW.md`, `ROADMAP.md`) define **how** it is implemented.

If there is a conflict, the product docs win.
