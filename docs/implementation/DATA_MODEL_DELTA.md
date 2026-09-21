# Data Model Delta

Date: 2026-04-29
Source documents:

- `docs/DATA_MODEL.md`
- `docs/VISION_DOCUMENT.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- current backend models under `backend/app/models`

## Current Implemented Models

Current real model layer includes:

- `User`
- `Project`
- `Chat`
- `Message`
- `File`
- `Job`
- `ChatArtifact`

These models cover the basic demo flow:

- user identity
- projects
- chats
- messages
- uploaded files
- generated/downloadable chat artifacts
- internal jobs

## Current Gaps

### 1. Plans

Missing model:

- `Plan`

Required fields:

- `id`
- `code`
- `name`
- `project_limit`
- `storage_limit_total`
- `storage_limit_per_project`
- `token_limit_month`
- `price_amount`
- `price_currency`
- `is_active`
- `created_at`
- `updated_at`

Reason:

- User currently stores plan-like fields directly, but paid SaaS needs canonical plan definitions.

### 2. Subscriptions

Missing model:

- `Subscription`

Required fields:

- `id`
- `user_id`
- `plan_id`
- `provider`
- `provider_customer_id`
- `provider_subscription_id`
- `status`
- `current_period_start`
- `current_period_end`
- `cancel_at_period_end`
- `created_at`
- `updated_at`

Reason:

- Paid access must be derived from actual subscription/payment state, not just `users.plan_type`.

### 3. Payments

Missing model:

- `Payment`

Required fields:

- `id`
- `user_id`
- `provider`
- `provider_payment_id`
- `kind`
- `status`
- `amount`
- `currency`
- `metadata`
- `idempotency_key`
- `created_at`
- `updated_at`

Reason:

- Payment webhooks must be auditable and idempotent.

### 4. Usage

Missing model:

- `UsageRecord`

Required fields:

- `id`
- `user_id`
- `project_id`
- `chat_id`
- `message_id`
- `operation`
- `provider`
- `model`
- `tokens_input`
- `tokens_output`
- `tokens_embeddings`
- `units_images`
- `units_web`
- `total_tokens`
- `estimated_cost`
- `currency`
- `period_month`
- `created_at`

Reason:

- Current usage is approximate metadata in messages. Billing needs authoritative usage rows.

### 5. File Versions

Missing model:

- `FileVersion`

Required fields:

- `id`
- `file_id`
- `version_number`
- `storage_path`
- `size`
- `mime_type`
- `created_by`
- `created_reason`
- `created_at`

Reason:

- Vision requires optional file versioning with max 3 retained versions.
- AI file editing must be reversible.

### 6. File Modes

Current `File` model lacks:

- `mode`
- `versioning_enabled`
- `extraction_status`
- `index_status`
- `last_indexed_at`
- `text_hash`

Required mode values:

- `read_only`
- `editable`
- `generated`

Reason:

- AI must know which files can be edited.
- UI must show indexing/editing state.

### 7. Extracted File Chunks

Missing model:

- `FileChunk`

Required fields:

- `id`
- `project_id`
- `file_id`
- `chunk_index`
- `content`
- `metadata`
- `token_count`
- `created_at`

Reason:

- Current implementation injects whole extracted files into prompt.
- Scalable context requires chunking.

### 8. Embeddings

Missing model:

- `Embedding`

Required fields:

- `id`
- `project_id`
- `file_id`
- `chunk_id`
- `provider`
- `model`
- `embedding vector`
- `created_at`

Reason:

- Vision requires pgvector search over file chunks.

### 9. Memories

Current implementation:

- file-based JSON memory under `storage/memory`.

Missing DB model:

- `Memory`

Required fields:

- `id`
- `project_id`
- `user_id`
- `type`
- `key`
- `content`
- `source`
- `expires_at`
- `created_at`
- `updated_at`

Reason:

- Project memory must be durable, queryable, scoped, and migratable.

### 10. Summaries

Missing model:

- `Summary`

Required fields:

- `id`
- `chat_id`
- `project_id`
- `summary_text`
- `from_message_id`
- `to_message_id`
- `model`
- `tokens_input`
- `tokens_output`
- `created_at`

Reason:

- Context compaction requires durable summaries.

### 11. Agent Tasks

Current implementation:

- `Job` exists, plus internal manager/autopilot state files.

Needed production-facing model:

- `AgentTask`

Required fields:

- `id`
- `user_id`
- `project_id`
- `chat_id`
- `status`
- `task_type`
- `mode`
- `prompt`
- `plan`
- `result`
- `error`
- `requires_approval`
- `approved_at`
- `created_at`
- `updated_at`

Reason:

- User-facing AI file edits need visible task status and approve/reject/continue.

### 12. File Edit Proposals

Missing model:

- `FileEditProposal`

Required fields:

- `id`
- `task_id`
- `file_id`
- `base_version_id`
- `proposed_content_path`
- `diff_text`
- `status`
- `approved_by`
- `approved_at`
- `applied_version_id`
- `created_at`

Reason:

- The key differentiator needs safe preview before mutation.

### 13. Legal Acceptance

Current implementation:

- file-based `storage/auth_acceptance.json`.

Missing DB model:

- `LegalAcceptance`

Required fields:

- `id`
- `user_id`
- `terms_version`
- `privacy_version`
- `accepted_at`
- `ip_address`
- `user_agent`

Reason:

- Paid SaaS needs auditable legal acceptance.

## Migration Priority

1. `Plan`
2. `Subscription`
3. `Payment`
4. `UsageRecord`
5. `LegalAcceptance`
6. `FileVersion`
7. `File.mode` and indexing status columns
8. `FileChunk`
9. `Embedding`
10. `Memory`
11. `Summary`
12. `AgentTask`
13. `FileEditProposal`

## Phase 2.2 Input

Phase 2.2 should remove production schema mutation from `main.py` and prepare the codebase so Phase 2.3 can add a clean Alembic migration chain for this delta.

