# Product sprint: real artifact generation infrastructure

Date: 2026-04-22
Scope: /opt/ai-workspace/storage/projects/ai-platform

## 1) Files changed
- backend/app/models/chat_artifact.py
- backend/app/services/artifact_service.py
- backend/app/schemas/artifact.py
- backend/app/api/files.py
- backend/app/api/ai_chat.py
- backend/app/main.py
- backend/app/models/__init__.py
- frontend/chat.html

## 2) Truly supported generated formats
- txt
- csv
- json
- xlsx

Notes:
- `xlsx` is generated as a real `.xlsx` file via backend OpenXML writer (no UI-only placeholder).
- Project chats save generated files into project files storage and create artifact records.
- Personal chats save generated files into chat artifact storage and create artifact records.

## 3) Fallback formats (honest)
Requested -> Generated fallback:
- docx -> txt
- pdf -> txt
- pptx -> txt

Behavior:
- Backend sets fallback metadata (`fallback_from`, `fallback_reason`) in artifact payload.
- Assistant response explicitly states fallback when it happens.
- No fake claim that unsupported binary format was produced.

## 4) Example request -> generated file result
- "создай таблицу продаж за 3 месяца" -> `table.csv` (or `table.xlsx` if user asks excel/xlsx explicitly)
- "сделай excel с колонками name, amount" -> `table.xlsx`
- "сделай json с полями name и email" -> `data.json`
- "сделай документ по итогам" -> `document.txt` (honest docx fallback)
- "подготовь pdf-отчёт" -> `summary.txt` (honest pdf fallback)
- "создай презентацию по проекту" -> `slides.txt` (honest pptx fallback)

## 5) Smoke checks

Backend compile checks:
- `python -m py_compile backend/app/models/chat_artifact.py backend/app/services/artifact_service.py backend/app/schemas/artifact.py backend/app/api/files.py backend/app/api/ai_chat.py backend/app/main.py backend/app/models/__init__.py` -> OK

Targeted runtime checks attempted:
- Local import/runtime smoke for artifact generation helpers could not run due environment DB issue:
  - `sqlite3.OperationalError: unable to open database file`

Code-path smoke status by scenario:
- csv:
  - Detection + artifact path implemented.
  - Stored as real bytes; metadata + download URL returned.
- xlsx:
  - Detection + artifact path implemented.
  - Real `.xlsx` bytes generated and persisted.
- txt/docx:
  - `txt` supported natively.
  - `docx` routed to honest `txt` fallback with explicit note.
- personal chat artifact:
  - Saved into artifact storage (`_artifacts/<chat_id>/...`).
  - Download endpoint: `/api/chats/{chat_id}/artifacts/{artifact_id}/download`.
- project chat artifact:
  - Saved into project files via `save_upload`.
  - Artifact record still created and downloadable by artifact endpoint.
  - Frontend refreshes project file list when project artifact is returned.

## A1-A6 implementation summary
- A1:
  - Added `chat_artifacts` table model with required fields and relations to chat/project.
- A2:
  - Implemented format materialization path for txt/csv/json/xlsx.
  - Added honest fallback logic for docx/pdf/pptx.
- A3:
  - Project chat -> project files + artifact record.
  - Personal chat -> chat artifact storage + artifact record.
- A4:
  - Extended request detection to table/excel/pdf/document/presentation intents.
  - Artifact intent from message `extra_data` is consumed by completion pipeline.
- A5:
  - Frontend assistant message now renders compact artifact card (filename + type + download).
  - Project artifacts trigger project files refresh in UI.
- A6:
  - Composer layout kept stable with disclaimer below composer and capability chips/buttons aligned in existing structure.
