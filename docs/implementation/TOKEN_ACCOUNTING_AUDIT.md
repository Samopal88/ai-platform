# Token And Storage Accounting Audit

Date: 2026-04-30

## Current Status

- Chat completion estimates prompt and completion tokens.
- `record_usage()` stores input, output, embeddings, image units, web units and monthly period.
- `/api/billing/me` reports used, limit, remaining tokens, storage used and storage limit.
- Project creation is limited by plan.
- File upload is limited by total storage.

## Verified Paths

- Chat completion records usage after assistant response.
- Web search usage is recorded as `units_web` when search results are used.
- Billing summary reads usage from `UsageRecord`.
- Storage limit checks run before file upload.

## Gaps To Close

- Media endpoints currently return `503`; after provider wiring they must call `record_usage()` with `units_images` or speech units.
- File edit preview/approve should be reviewed for whether token usage is recorded consistently.
- Embedding/indexing usage is represented in the schema but needs an end-to-end accounting test.
- Plan upgrade/downgrade behavior needs explicit tests for current monthly usage over the new limit.
- Storage decrease on file delete must be verified against real project files.

## Required Tests Before Sales

- User exhausts free token limit and receives `402`.
- User uploads files until storage limit and receives `402`.
- Paid plan increases token/storage/project limits.
- Chat, web, media and file-edit usage appear in `/api/billing/me`.
