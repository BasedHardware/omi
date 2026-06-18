# V17 Memory Product Integration — Implementation Tickets

**Created:** 2026-06-18T20:08:24Z  
**Status:** Oracle-reviewed; blocked for production implementation until P0 amendments are added  
**Source Epic:** `docs/epics/v17_memory_product_integration_epic.md`  
**Decision Brief:** `docs/epics/v17_memory_product_integration_decision_brief.md`  
**Repos:**
- Product: `/root/workspace/omi-memory-ingestion-pipeline`
- Benchmark/eval: `/root/workspace/omi-ingestion-benchmark`

---

## Locked product decisions

| Decision | Direction |
|---|---|
| Product terms | **Short-term**, **Long-term**, **Archive** |
| Short-term | Fresh source-backed memory before/during L2 processing; default-access while fresh/relevant |
| Long-term | Stable L2/ledger-backed memory; default-access |
| Archive | Explicit-query historical/source-backed context; not default-access |
| Context-only | Not a normal user-visible tier; route useful non-long-term context to Short-term or Archive |
| Rollout | Whitelist first; old memory behavior unchanged for everyone else |
| Config | Keep simple: allowlist + mode + backfill enabled/limit + archive opt-in |
| UI | Minimal labels/filter/provenance/edit/delete; users can manage memory by chatting with Omi |
| Agent mode | Memory-management tools: remember, forget, list, search, provenance, visibility/use policy, promote/demote, explicit archive search |
| Third-party/MCP/developer API | Default Long-term + Short-term; Archive requires explicit opt-in + explicit archive query |
| Deletion | Follow existing codebase conventions; extend coverage before any write pilot |
| Vectors | KISS: existing `ns2` memory namespace + strict metadata filters first; separate namespace only if metadata filtering proves unsafe |
| Raw artifacts | Keep raw/source artifacts by default; report ephemeral/drop-prone losses honestly |

---

## Safety-first implementation order

Wave 2 reviewers blocked the first draft because it allowed imports/writes before deletion/purge coverage and snapshot safeguards. This revised order is the implementation contract.

| Order | Tickets | Goal | Gate |
|---:|---|---|---|
| 0 | T00–T05 | Config, contracts, evidence schema, indexes, write-path audit, encryption/redaction rules | V17 defaults off; legacy users unchanged; data schema safe |
| 1 | T06 | Minimum deletion/export/account-purge coverage | Required before any staff/customer V17 write |
| 2 | T07–T10 | Short-term/Archive stores, old-memory inventory, snapshot/high-water mark, raw lineage | 100% accounted inventory or explicit outcome |
| 3 | T11–T12 | No-silent-data-loss verifier + old-memory import write path | Import writes only for allowlisted users and only from stable snapshots |
| 4 | T13–T18 | Patch idempotency, writer lease, patch applier, L2 dry-run/write backfill, lifecycle/aging, review/non-active outcomes | Duplicate-proof Long-term pipeline; no blind head writes |
| 5 | T19–T23 | Vector metadata, read service, external write semantics, chat/MCP/tools/developer policies, agent tools | Default reads = Short-term + Long-term; Archive explicit only |
| 6 | T24–T26 | Minimal UI, admin policy controls, telemetry/ops gates | Simple user surfaces; rollout observable; no metric pollution |
| 7 | T27 | Benchmark migration/backfill eval mode | Honest Base-anchored eval and anti-reward-hacking checks |

---

## Hard rollout blockers

Do not enable the next rollout stage if any blocker is true:

- Non-whitelisted users do not follow legacy memory behavior.
- Any Short-term/Archive/Long-term write can occur before minimum deletion/export/account-purge coverage passes.
- Any old-memory import write lacks source snapshot/high-water mark and drift handling.
- Any Long-term write bypasses ledger, idempotency claim, or per-user writer lease/serialization.
- Any default Omi/chat/MCP/developer/third-party read returns Archive without explicit opt-in + explicit archive query.
- Any raw/source artifact has unknown preservation/loss/tombstone outcome.
- Any duplicate Short-term, Archive, vector, patch application, review item, ledger commit, or source tombstone appears on rerun.
- Any active credential/secret enters Long-term or default third-party access.
- Migration/backfill/repair metrics pollute organic memory-created, engagement, notification, search, export, memory-count, or cohort dashboards.

---

# Tickets

## T00 — Simple V17 rollout config and allowlist

**Goal:** Add the smallest rollout control plane that lets us test V17 without changing old memory behavior by default.

**Files:**
- Create: `backend/config/v17_memory.py`
- Modify: `backend/utils/memory_ingestion/rollout.py`
- Test: `backend/tests/unit/test_v17_memory_config.py`
- Test: `backend/tests/unit/test_memory_rollout.py`

**Config surface:**

```text
V17_MEMORY_ENABLED_USERS=<comma-separated uids>
V17_MODE=off|shadow|write|read
V17_BACKFILL_ENABLED=false|true
V17_BACKFILL_DAILY_LIMIT=<int>
V17_ARCHIVE_OPT_IN_ENABLED=false|true
```

**Acceptance criteria:**

- Empty/missing config means no user is on V17.
- Non-whitelisted users use existing old memory paths unchanged.
- `shadow` permits dry-run/shadow artifacts only.
- `write` permits whitelisted V17 writes only after downstream safety gates pass.
- `read` permits whitelisted V17 read service only after read/vector policy gates pass.
- Product rollout depends on allowlist + mode, not many independent toggles.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_memory_config.py tests/unit/test_memory_rollout.py -q
```

---

## T01 — Product memory tier contracts and DTOs

**Goal:** Define canonical product tier metadata and additive DTO fields.

**Files:**
- Create: `backend/models/memory_tiers.py`
- Create: `backend/models/v17_product_memory.py`
- Modify: `backend/models/memories.py`
- Modify: `backend/models/v17_memory_contracts.py`
- Test: `backend/tests/unit/test_memory_tiers.py`
- Test: `backend/tests/unit/test_v17_product_memory.py`
- Test: `backend/tests/unit/test_v17_memory_contracts.py`

**Required fields:**

```text
memory_tier = short_term | long_term | archive
allowed_use = default | explicit_query | admin_debug | export_only
normal_default_access = true|false
explicit_archive_query_only = true|false
source_refs
provenance_summary
risk_flags
source_tombstoned
migration_source
```

**Acceptance criteria:**

- Product terminology is Short-term / Long-term / Archive.
- `context_only` may remain an internal route, but is not a product tier.
- Legacy records without tier fields remain API-compatible.
- Archive defaults to `normal_default_access=false`.
- Short-term + Long-term default to normal access unless sensitivity/privacy blocks.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_tiers.py tests/unit/test_v17_product_memory.py tests/unit/test_v17_memory_contracts.py -q
```

---

## T02 — Canonical evidence/provenance schema

**Goal:** Define one evidence object shape used by patch adapter, ledger, source tombstones, projection repair, read service, export, and deletion.

**Files:**
- Create: `backend/models/memory_evidence.py`
- Modify: `backend/models/v17_product_memory.py`
- Modify: `backend/models/v17_memory_contracts.py`
- Modify: `backend/utils/memory/v17_patch_adapter.py`
- Modify: `backend/database/memory_ledger.py`
- Test: `backend/tests/unit/test_memory_evidence_schema.py`

**Schema must cover:**

```text
source_type
source_id
conversation_id
artifact_refs
quote_refs / span refs
content_hash
lineage_id
source_deleted/source_tombstoned
provenance_visibility
encryption_or_redaction_status
patch_id / commit_id when applicable
```

**Acceptance criteria:**

- Same evidence shape round-trips through V17 patch adapter, ledger commits/fold, source tombstone logic, projection repair, read service, export, and deletion tests.
- Source deletion can identify and tombstone evidence produced by V17 patches.
- Evidence with unavailable raw artifact still has explicit missing/loss reason.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_evidence_schema.py -q
```

---

## T03 — V17 collections and Firestore/index plan

**Goal:** Centralize new collection paths and document query/index shapes before writes.

**Files:**
- Create: `backend/database/v17_collections.py`
- Create: `docs/epics/v17_memory_firestore_indexes.md`
- Test: `backend/tests/unit/test_v17_collections.py`

**Collections:**

```text
users/{uid}/memory_short_term/{short_term_id}
users/{uid}/memory_archive/{archive_id}
users/{uid}/memory_patch_applications/{idempotency_key}
users/{uid}/memory_lineage/{lineage_id}
users/{uid}/memory_backfill_runs/{run_id}
users/{uid}/memory_backfill_cursors/{cursor_id}
users/{uid}/memory_export_jobs/{job_id}
users/{uid}/memory_deletion_jobs/{job_id}
```

Existing Long-term stores remain:

```text
users/{uid}/memory_state/head
users/{uid}/memory_commits/{commit_id}
users/{uid}/memories/{memory_id}  # compatibility projection
```

**Acceptance criteria:**

- No V17 code hardcodes collection names outside `v17_collections.py`.
- Index doc covers Short-term, Archive, patch applications, lineage, backfill cursors, review/status queries.
- Cursor pagination is preferred over offset for high-volume migration paths.
- Production write rollout is blocked until indexes are deployed/tested or manual deployment is documented.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_collections.py -q
```

---

## T04 — Encryption/redaction and sensitive-data policy for new V17 stores

**Goal:** Ensure V17 stores respect existing enhanced-protection and logging/security conventions, with explicit policy for sensitive categories.

**Files:**
- Create: `docs/epics/v17_memory_data_protection.md`
- Create: `backend/utils/memory/v17_redaction.py`
- Modify: `backend/models/v17_product_memory.py`
- Test: `backend/tests/unit/test_v17_memory_redaction.py`

**Stores covered:**

```text
Short-term records
Archive records
Long-term ledger commits
patch applications
lineage
search replay artifacts
review/non-active route payloads
vector metadata
export snapshots
telemetry/error payloads
```

**Sensitive taxonomy:**

```text
credentials/secrets
financial
health
intimate/sexual
minors
third-party personal data
workplace confidential
identity/authentication
safety risk
```

For each category, define whether it may be stored in Short-term, included in default access, backfilled to Long-term, visible in Archive search, exported by default, or exposed to MCP/third-party tools.

**Acceptance criteria:**

- Enhanced-protection users do not get plaintext memory content, evidence quotes, raw artifacts, search replay payloads, review payloads, lineage payloads, vector metadata, or export snapshots stored outside the approved encryption/redaction model.
- Credentials/secrets are never active Long-term and never exposed through default third-party/MCP/developer access.
- Sensitive false positives can be preserved with restricted access rather than silently dropped.
- Logs use sanitized/summarized data only.
- Tests cover sensitive content, error messages, and export snapshots.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_memory_redaction.py -q
```

---

## T05 — Source-of-truth and write-path audit

**Goal:** Identify and gate every current memory mutation path before V17 write mode.

**Files:**
- Create: `docs/epics/v17_memory_write_path_audit.md`
- Create: `backend/services/v17_memory_write_service.py` (skeleton only)
- Test: `backend/tests/unit/test_v17_non_whitelisted_legacy_unchanged.py`

**Audit these files/functions:**

```text
backend/routers/memories.py
backend/routers/developer.py
backend/routers/mcp.py
backend/routers/tools.py
backend/utils/conversations/process_conversation.py
backend/database/memories.py
backend/database/memory_ledger.py
backend/database/review_queue.py
backend/database/vector_db.py
```

**Acceptance criteria:**

- Document every create/edit/delete/review/visibility/source-delete route.
- For each route, classify: legacy-only, V17 shadow, V17 write-service, blocked/deferred.
- Non-whitelisted tests prove old behavior remains unchanged.
- No Long-term write can bypass ledger once V17 write mode is enabled.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_non_whitelisted_legacy_unchanged.py -q
```

---

## T06 — Minimum deletion/export/account-purge coverage gate

**Goal:** Extend existing deletion/export/account-purge conventions to V17 metadata before any staff/customer V17 write.

**Files:**
- Create: `backend/services/memory_deletion_service.py`
- Create: `backend/services/memory_export_service.py`
- Create: `backend/database/v17_account_purge.py`
- Modify: `backend/routers/memories.py`
- Modify: `backend/routers/conversations.py`
- Modify: `backend/routers/users.py`
- Modify: `backend/database/memories.py`
- Modify: `backend/database/vector_db.py`
- Modify: `backend/routers/sync.py`
- Modify: `backend/routers/pusher.py`
- Test: `backend/tests/unit/test_memory_tier_deletion.py`
- Test: `backend/tests/unit/test_memory_tier_account_purge.py`
- Test: `backend/tests/unit/test_memory_tier_export.py`

**Acceptance criteria:**

- No Short-term, Archive, Long-term, lineage, patch application, vector, review, backfill, import metadata, or source-tombstone writes may be enabled for staff/customer users until this ticket’s tests pass.
- Memory deletion follows existing semantics and deletes/tombstones associated tier/vector data.
- Deleting a memory does not silently delete raw source artifacts unless existing flow does so.
- Conversation/source deletion tombstones source refs/evidence according to existing conventions.
- Account purge removes Short-term, Long-term, Archive, lineage, vectors, patch applications, backfill metadata, review records, and source tombstones.
- Export can include Long-term, Short-term, Archive, provenance/source refs, tombstones/deleted history where existing export policy allows.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_tier_deletion.py tests/unit/test_memory_tier_account_purge.py tests/unit/test_memory_tier_export.py -q
```

---

## T07 — Short-term and Archive persistent stores

**Goal:** Store source-backed Short-term and Archive memories with deterministic IDs and tier policy.

**Files:**
- Create: `backend/database/product_memory_items.py`
- Create: `backend/utils/memory/product_memory_import_service.py`
- Modify: `backend/database/short_term_memories.py` or document why not reused
- Test: `backend/tests/unit/test_product_memory_items.py`
- Test: `backend/tests/unit/test_product_memory_import_service.py`

**Storage behavior:**

Short-term:

```text
memory_tier=short_term
normal_default_access=true
explicit_archive_query_only=false
```

Archive:

```text
memory_tier=archive
normal_default_access=false
explicit_archive_query_only=true
```

**Acceptance criteria:**

- Deterministic ID/idempotency key prevents duplicates on rerun.
- Every record has source refs or explicit missing-source reason.
- Sensitive/secret records are not default-access.
- Archive cannot be returned by default policy.
- Raw/source artifacts are not deleted or modified.
- Store choice is unambiguous: either reuse/wrap existing `users/{uid}/short_term` or define the new store as authoritative.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_product_memory_items.py tests/unit/test_product_memory_import_service.py -q
```

---

## T08 — Old Omi memory inventory dry-run

**Goal:** Inventory legacy `users/{uid}/memories` without writes/deletes.

**Files:**
- Create: `backend/database/old_omi_memory_inventory.py`
- Create: `backend/utils/memory/old_omi_memory_inventory.py`
- Create: `backend/migrations/008_old_omi_memory_inventory.py`
- Test: `backend/tests/unit/test_old_omi_memory_inventory.py`

**Terminal outcomes:**

```text
eligible_short_term
eligible_archive
skipped_deleted
skipped_empty
failed_validation
failed_decryption
duplicate_doc_id
duplicate_content_hash
quarantined_sensitive
needs_manual_review
source_missing_but_memory_preserved
explicit_loss
```

**Acceptance criteria:**

- 100% of scanned legacy docs get exactly one terminal outcome.
- Dry-run writes nothing except local report output.
- Deleted/invalidated memories are accounted for but not resurrected.
- Decryption failures and malformed docs are explicit outcomes.
- Report is deterministic across reruns on the same snapshot.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_old_omi_memory_inventory.py -q
```

---

## T09 — Source snapshot and high-water-mark protection

**Goal:** Prevent old-memory imports and any future bulk source migration from missing, duplicating, or resurrecting records during concurrent edits/deletes.

**Files:**
- Create: `backend/database/v17_source_snapshots.py`
- Create: `backend/utils/memory/v17_source_snapshot.py`
- Modify: `backend/utils/memory/old_omi_memory_inventory.py`
- Modify: `backend/utils/memory/old_omi_memory_import.py` (if created later, add interface now)
- Test: `backend/tests/unit/test_v17_source_snapshot.py`

**Snapshot fields:**

```text
snapshot_id
uid
source_collection
created_at
high_water_timestamp_or_cursor
doc_count
schema_fingerprint
per_doc_update_time_or_version
deleted_state_seen
job_id
```

**Acceptance criteria:**

- Import write mode can only import from a recorded snapshot/high-water mark.
- Any bulk migration/import path that reads mutable source rows must use this snapshot/high-water contract, not only old Omi memory import.
- Records changed, deleted, or newly created after snapshot are reported as drift and not silently imported.
- Concurrent user deletes win over migration/import writes.
- Deleted records are not resurrected.
- Drifted records receive terminal outcome: `snapshot_drift_requeue` or `snapshot_drift_skipped`.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_source_snapshot.py -q
```

---

## T10 — Raw artifact accounting and lineage

**Goal:** Track raw/source artifacts and lineage from source → Short-term/Archive → Long-term.

**Files:**
- Create: `backend/database/memory_source_lineage.py`
- Create: `backend/utils/memory/raw_artifact_accounting.py`
- Modify: `backend/routers/sync.py`
- Modify: `backend/routers/pusher.py`
- Modify: `backend/routers/imports.py`
- Modify: `backend/utils/conversations/process_conversation.py`
- Test: `backend/tests/unit/test_raw_artifact_accounting.py`
- Test: `backend/tests/unit/test_memory_source_lineage.py`

**Accounting outcomes:**

```text
preserved
ephemeral_already_missing
dropped_before_copy
deleted_by_user
account_purged
copy_failed
explicit_loss
```

**Acceptance criteria:**

- Raw/source artifacts are kept by default when available.
- Ephemeral sync/pusher losses are observable and not claimed as preserved.
- Artifact hash/size/path recorded when bytes are available.
- Lineage connects source row/doc to Short-term/Archive item and later Long-term patch/commit.
- Logs/API reports do not expose raw sensitive content.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_raw_artifact_accounting.py tests/unit/test_memory_source_lineage.py -q
```

---

## T11 — No-silent-data-loss verifier v1

**Goal:** Produce per-user/job reports proving every source/legacy/raw artifact has lineage or explicit outcome.

**Files:**
- Create: `backend/utils/memory/no_data_loss_verifier.py`
- Create: `backend/routers/memory_admin.py`
- Test: `backend/tests/unit/test_no_data_loss_verifier.py`

**Required report fields:**

```text
uid/account scope
source type/source ID/raw artifact ID
terminal outcome
timestamp
job/run ID
remediation state
preserved vs observable loss
lineage IDs
sample IDs without raw sensitive text
```

**Report chain:**

```text
legacy memory / source row / raw artifact
→ Short-term or Archive item OR explicit skip/loss/tombstone reason
→ L2 packet if selected for backfill
→ search replay hash
→ patch
→ ledger commit OR route outcome
→ projection/vector/card if active Long-term
```

**Acceptance criteria:**

- Unknown outcome makes report red.
- Missing raw artifact accounting makes report red.
- Missing remediation state makes report red.
- Duplicate terminal outcomes make report red.
- Report distinguishes preserved vs observable loss.
- Staff/customer write rollout is blocked until report can run on allowlisted users.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_no_data_loss_verifier.py -q
```

---

## T12 — Old Omi memory import to Short-term/Archive

**Goal:** Import old Omi memories for allowlisted users into Short-term/Archive candidates, never directly Long-term.

**Files:**
- Create: `backend/utils/memory/old_omi_memory_import.py`
- Create: `backend/migrations/009_old_omi_to_short_term_archive.py`
- Modify: `backend/database/import_jobs.py`
- Modify: `backend/models/import_job.py`
- Modify: `backend/routers/imports.py`
- Test: `backend/tests/unit/test_old_omi_memory_import.py`

**Gates before write mode:**

- T06 deletion/export/purge minimum coverage passes.
- T08 dry-run inventory has 100% terminal outcomes.
- T09 source snapshot/high-water mark exists and drift handling passes.
- T11 no-silent-data-loss verifier is green for sampled/cohort users.

**Routing policy:**

| Old memory type | Target |
|---|---|
| Recent/high-confidence/manual | Short-term candidate, prioritized for backfill |
| Older/source-backed | Archive first, backfill eligible |
| Noisy/uncertain/sensitive | Preserved with flags; not default Long-term |
| Deleted/invalidated | Explicit skip/tombstone outcome |

**Acceptance criteria:**

- Non-allowlisted users are not imported.
- Old source docs are untouched.
- No Long-term/ledger active memory is created by import.
- Rerun/resume by job ID does not duplicate Short-term/Archive records.
- Import does not emit organic `Memory Created` or engagement analytics.
- Deleted/invalidated records cannot be imported except as explicit tombstone/skip outcomes.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_old_omi_memory_import.py -q
```

---

## T13 — Patch application idempotency record

**Goal:** Transactionally claim patch idempotency before any Long-term ledger write.

**Files:**
- Create: `backend/database/v17_patch_applications.py`
- Test: `backend/tests/unit/test_v17_patch_applications.py`

**Acceptance criteria:**

- Same `(uid, idempotency_key)` cannot be claimed twice as separate applied patches.
- Status transitions are explicit: `claimed`, `applied`, `skipped`, `conflict`, `failed`.
- Sanitized errors only.
- Account purge/delete coverage includes patch applications before write pilot.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_patch_applications.py -q
```

---

## T14 — Per-user Long-term writer lease/serialization

**Goal:** Ensure only one Long-term writer mutates a user’s ledger head at a time.

**Files:**
- Create: `backend/database/v17_memory_writer_leases.py`
- Create: `backend/services/v17_memory_writer_lease.py`
- Test: `backend/tests/unit/test_v17_memory_writer_lease.py`

**Lease fields:**

```text
uid
lease_id
owner_type=backfill|live_extraction|manual_edit|delete|review|mcp|developer|repair
owner_job_id
expires_at
heartbeat_at
created_at
```

**Acceptance criteria:**

- At most one Long-term ledger writer per user may mutate ledger head at a time.
- Live extraction, backfill, user edits, review accepts, deletes, MCP/developer writes, and repair writes acquire the same lease or equivalent serialized transaction.
- Crash/timeout releases or expires lease safely.
- Tests cover concurrent patch apply, user edit, delete, review accept.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_memory_writer_lease.py -q
```

---

## T15 — Long-term patch applier and ledger write service

**Goal:** Apply L2 patches to Long-term memory through append-only ledger with idempotency and conflict handling.

**Files:**
- Create: `backend/utils/memory/v17_patch_applier.py`
- Create/extend: `backend/services/v17_memory_write_service.py`
- Modify: `backend/utils/memory/v17_patch_adapter.py`
- Modify: `backend/database/memory_ledger.py`
- Modify: `backend/database/review_queue.py`
- Modify: `backend/utils/memory/v17_projections.py`
- Test: `backend/tests/unit/test_v17_patch_applier.py`
- Test: `backend/tests/unit/test_v17_memory_write_service.py`

**Rules:**

- All active Long-term changes go through ledger.
- Idempotency claim from T13 is required.
- Writer lease/serialization from T14 is required.
- `HeadConflict` records conflict and triggers replan/retry; no blind apply.
- Evidence schema from T02 is used consistently.
- Patch applier cannot apply in `V17_MODE=shadow`.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_patch_applier.py tests/unit/test_v17_memory_write_service.py tests/unit/test_memory_ledger.py -q
```

---

## T16 — Progressive Long-term backfill dry-run

**Goal:** Build dry-run Long-term backfill over Short-term/Archive without ledger writes.

**Files:**
- Create: `backend/utils/memory/l2_backfill_orchestrator.py`
- Create: `backend/database/l2_backfill_jobs.py`
- Create: `backend/jobs/v17_l2_backfill_worker.py`
- Create: `backend/routers/memory_backfill.py`
- Test: `backend/tests/unit/test_l2_backfill_orchestrator.py`
- Test: `backend/tests/unit/test_l2_backfill_jobs.py`

**Acceptance criteria:**

- Dry-run writes zero ledger commits and zero active Long-term facts.
- Cursor resumes after crash.
- Sensitive records excluded unless explicit policy enables them.
- Route distribution includes active/review/archive/reject/hidden/skip.
- Anti-reward-hacking metrics count useful memories left in Archive/review/reject.
- Replay hash is stable for same inputs.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_l2_backfill_orchestrator.py tests/unit/test_l2_backfill_jobs.py -q
```

---

## T17 — Review/non-active route persistence and idempotency

**Goal:** Persist review, Archive/context, reject, hidden, and skip outcomes so they are auditable and duplicate-proof.

**Files:**
- Create: `backend/database/v17_non_active_memory_routes.py`
- Modify: `backend/database/review_queue.py`
- Modify: `backend/utils/memory/v17_patch_applier.py`
- Test: `backend/tests/unit/test_v17_non_active_routes.py`

**Acceptance criteria:**

- Same patch/run cannot create duplicate review items.
- Review, Archive/context, reject, hidden, and skip outcomes persist idempotency key, source IDs, reason, route, run ID, and audit metadata.
- Non-active outcomes are visible to no-silent-data-loss reports and benchmark/reward-hacking audits.
- Non-active outcomes never appear in default Long-term reads.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_non_active_routes.py -q
```

---

## T18 — Progressive Long-term write-mode backfill and operational budgets

**Goal:** Enable capped Long-term backfill writes for allowlisted users after T13–T17 pass.

**Files:**
- Modify: `backend/utils/memory/l2_backfill_orchestrator.py`
- Modify: `backend/jobs/v17_l2_backfill_worker.py`
- Modify: `backend/routers/memory_backfill.py`
- Modify: `backend/config/v17_memory.py`
- Test: `backend/tests/unit/test_l2_backfill_write_mode.py`
- Test: `backend/tests/unit/test_v17_backfill_limits.py`

**Budgets:**

```text
users/day
Short-term/Archive imports/day
Long-term backfill items/day
L2 calls/day
global LLM calls/day
review items/day
Firestore reads/writes/day or throughput
vector upserts/deletes/day or throughput
cost/day
support tickets / error rate
queue age
job latency
```

**Acceptance criteria:**

- Write mode processes at most configured batch size/daily cap.
- Document initial threshold values for every listed budget before enabling write mode, even if values are conservative placeholders.
- Exceeding budgets auto-pauses affected stage.
- Duplicate-proof across reruns/crashes.
- Head conflicts do not corrupt state.
- Pause/rollback stops workers without cursor corruption.
- Metrics emitted as migration/backfill, not organic engagement.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_l2_backfill_write_mode.py tests/unit/test_v17_backfill_limits.py -q
```

---

## T19 — Short-term lifecycle and aging policy

**Goal:** Prevent Short-term from becoming an unbounded default-access bucket.

**Files:**
- Create: `backend/utils/memory/short_term_lifecycle.py`
- Create: `backend/jobs/v17_short_term_lifecycle_worker.py`
- Modify: `backend/database/product_memory_items.py`
- Test: `backend/tests/unit/test_short_term_lifecycle.py`

**Lifecycle outcomes:**

```text
remain_short_term
promote_to_long_term
archive
reject_or_hide
source_tombstoned
```

**Acceptance criteria:**

- Short-term records cannot remain default-access indefinitely without explicit lifecycle decision.
- Stale or L2-processed records transition to Long-term, Archive, or hidden/rejected according to policy.
- Default reads exclude stale Short-term.
- Lifecycle transitions are idempotent and auditable.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_short_term_lifecycle.py -q
```

---

## T20 — Existing-namespace vector metadata filters and repair

**Goal:** Use existing `ns2` memory namespace with strict metadata filters for tier-safe retrieval.

**Files:**
- Create: `backend/database/v17_vector_metadata.py`
- Create: `backend/migrations/010_repair_v17_memory_vectors.py`
- Modify: `backend/database/vector_db.py`
- Modify: `backend/utils/memory/v17_projections.py`
- Modify: `backend/database/projection_repair.py`
- Test: `backend/tests/unit/test_v17_vector_metadata.py`
- Test: `backend/tests/unit/test_v17_vector_filters.py`

**Acceptance criteria:**

- Vector IDs are deterministic and collision-proof across Short-term, Long-term, Archive, and legacy records.
- Default Omi/chat/third-party vector search cannot return Archive.
- Explicit archive search returns Archive only.
- Sensitive/hidden/source-tombstoned records excluded by default.
- Rerunning vector repair creates no duplicate vectors.
- Deleting/tombstoning source or memory removes or marks stale vectors so default search cannot return them.
- Drift report includes duplicate IDs, missing vectors, stale vectors, metadata mismatches, orphan vectors, and failed repairs.
- Existing legacy vector behavior unchanged for non-whitelisted users.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_vector_metadata.py tests/unit/test_v17_vector_filters.py -q
```

---

## T21 — Unified memory read service and API compatibility

**Goal:** Centralize read policy so default product reads return Short-term + Long-term; Archive only by explicit query/opt-in.

**Files:**
- Create: `backend/services/memory_read_service.py`
- Create: `backend/models/memory_read.py`
- Modify: `backend/utils/memory/v17_read_api.py`
- Modify: `backend/routers/memories.py`
- Modify: `backend/database/memory_reads.py`
- Test: `backend/tests/unit/test_memory_read_service.py`
- Test: `backend/tests/unit/test_v3_memories_tier_compat.py`

**`GET /v3/memories` optional params:**

```text
tier=short_term|long_term|archive|all
include_archive=false
include_source_refs=false
include_provenance=false
include_review=false
```

**Acceptance criteria:**

- Non-whitelisted users use legacy reads.
- Whitelisted read mode default returns Short-term + Long-term.
- Archive requires explicit params/opt-in.
- Existing clients parse unchanged/additive response shape.
- Old clients ignore unknown tier/provenance fields and existing `limit`/pagination behavior continues during rollout.
- Server-side tier filters and cursor pagination are available before large imports are visible.
- Rollback to legacy read is one config change.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_read_service.py tests/unit/test_v3_memories_tier_compat.py -q
```

---

## T22 — External write semantics for APIs/tools

**Goal:** Define and implement tier-specific write semantics for `/v3`, developer API, MCP, tools, and agent memory tools.

**Files:**
- Modify: `backend/routers/memories.py`
- Modify: `backend/routers/developer.py`
- Modify: `backend/routers/mcp.py`
- Modify: `backend/routers/tools.py`
- Modify: `backend/services/v17_memory_write_service.py`
- Modify: `backend/services/memory_deletion_service.py`
- Test: `backend/tests/unit/test_v17_external_write_semantics.py`

**Routes covered:**

```text
POST /v3/memories
PATCH /v3/memories/{id}
PATCH /v3/memories/{id}/visibility
DELETE /v3/memories/{id}
DELETE /v3/memories
Developer API memory create/edit/delete
MCP memory create/edit/delete
Tools memory create/edit/delete
Agent remember/forget/update
```

**Acceptance criteria:**

- Non-whitelisted users remain legacy-only.
- New manual memories default to Short-term unless explicitly stable/Long-term.
- Long-term writes go through ledger/write service only.
- Deletes go through memory deletion service and existing conventions.
- Archive cannot be created/exposed accidentally.
- Third-party/MCP/developer writes cannot create Archive-visible or Long-term-visible records without policy and tier validation through the write service.
- No V17-enabled external write route mutates `users/{uid}/memories`, vectors, Short-term, Archive, review records, or Long-term ledger directly.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_external_write_semantics.py -q
```

---

## T23 — Chat, tools, MCP, developer API read policies

**Goal:** Apply read service to all product/agent/third-party surfaces.

**Files:**
- Modify: `backend/utils/llms/memory.py`
- Modify: `backend/utils/retrieval/tools/memory_tools.py`
- Modify: `backend/utils/retrieval/tool_services/memories.py`
- Modify: `backend/utils/retrieval/agentic.py`
- Modify: `backend/utils/retrieval/graph.py`
- Modify: `backend/routers/chat.py`
- Modify: `backend/routers/tools.py`
- Modify: `backend/routers/mcp.py`
- Modify: `backend/routers/developer.py`
- Test: `backend/tests/unit/test_chat_memory_policy.py`
- Test: `backend/tests/unit/test_tools_memory_policy.py`
- Test: `backend/tests/unit/test_mcp_memory_policy.py`
- Test: `backend/tests/unit/test_developer_memory_policy.py`
- Test: `backend/tests/unit/test_third_party_memory_policy.py`

**Policy matrix:**

| Consumer | Default tiers | Archive |
|---|---|---|
| Omi chat | Short-term + Long-term | explicit search only |
| Agent mode | Short-term + Long-term | explicit tool/search only |
| MCP/third-party | Short-term + Long-term | opt-in + explicit query only |
| Developer API | Short-term + Long-term | opt-in + explicit query only |
| Admin/eval | configurable | configurable |

**Archive opt-in contract:**

- Admin/app policy must permit Archive.
- Request/tool must explicitly ask for Archive.
- Sensitive/review/hidden/source-tombstoned still excluded unless admin/eval policy explicitly permits.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_chat_memory_policy.py tests/unit/test_tools_memory_policy.py tests/unit/test_mcp_memory_policy.py tests/unit/test_developer_memory_policy.py tests/unit/test_third_party_memory_policy.py -q
```

---

## T24 — Agent-mode memory management tools

**Goal:** Let Omi manage memory conversationally so UI can stay simple.

**Files:**
- Create: `backend/utils/retrieval/tools/memory_management_tools.py`
- Modify: `backend/utils/retrieval/tools/memory_tools.py`
- Modify: `backend/utils/retrieval/agentic.py`
- Modify: `backend/routers/tools.py`
- Test: `backend/tests/unit/test_agent_memory_management_tools.py`
- Test: `backend/tests/unit/test_agent_tools_memory_schema.py`

**Tools:**

```text
remember_memory_tool(content, tier_hint optional)
forget_memory_tool(memory_id or query)
list_memories_tool(tier optional)
search_memories_tool(query, include_archive=false)
search_archive_memories_tool(query)
get_memory_provenance_tool(memory_id)
update_memory_tool(memory_id, content)
set_memory_visibility_or_use_policy_tool(memory_id, policy)
promote_to_long_term_tool(memory_id)
archive_or_demote_memory_tool(memory_id)
review_memory_tool(memory_id, decision)  # only if backend review exists
```

**Acceptance criteria:**

- Remember defaults to Short-term unless user explicitly asks for stable/Long-term memory.
- Forget by query returns candidates and requires confirmation if ambiguous.
- Forget output states whether raw source is affected; default is memory only, following existing deletion conventions.
- Default search returns Short-term + Long-term.
- Archive search is explicit.
- Tool outputs include `memory_id`, `tier`, provenance/source summary, and access policy.
- Tool descriptions use Short-term/Long-term/Archive terms only.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_agent_memory_management_tools.py tests/unit/test_agent_tools_memory_schema.py -q
```

---

## T25 — Minimal user UI surfaces

**Goal:** Add simple tier labels/filter/provenance/delete copy across user-facing surfaces without heavy review UI.

**Mobile files:**
- `app/lib/backend/schema/memory.dart`
- `app/lib/backend/http/api/memories.dart`
- `app/lib/providers/memories_provider.dart`
- `app/lib/pages/memories/page.dart`
- `app/lib/pages/memories/widgets/memory_item.dart`
- `app/lib/pages/memories/widgets/memory_dialog.dart`
- `app/lib/pages/memories/widgets/memory_management_sheet.dart`
- `app/lib/l10n/app_en.arb` and all locale ARBs

**macOS files:**
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryModels.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryStorage.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoriesPage.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/Desktop/Sources/Chat/ChatPrompts.swift`
- `desktop/macos/Desktop/Sources/MemoryExportService.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoryExportDestinationSheet.swift`

**Web/Windows files:**
- `web/frontend/src/types/memory.types.ts`
- `web/frontend/src/components/memories/*`
- `desktop/windows/src/renderer/src/hooks/useMemories.ts`
- `desktop/windows/src/renderer/src/pages/Memories.tsx`

**Acceptance criteria:**

- UI labels only: Short-term / Long-term / Archive.
- No L1/L2/Durable/Context-only terminology.
- Archive is visually distinct and not implied as default personalization.
- Server-side tier filters and cursor pagination are used before large imports are visible.
- Simple source/provenance shown where available.
- Delete copy says deleting a memory removes Omi’s memory item/projection/vector; it does not delete original conversation/audio/imported file unless source/account deletion does so.
- Source deletion copy says related evidence may be tombstoned and memories may change.
- All mobile strings use l10n.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/app
flutter test test/memory_tier_model_test.dart test/memories_api_tier_test.dart test/memories_page_tier_filter_test.dart
flutter gen-l10n

cd /root/workspace/omi-memory-ingestion-pipeline/desktop/macos
xcrun swift build -c debug --package-path Desktop
xcrun swift test --package-path Desktop --filter MemoryTierModelTests
xcrun swift test --package-path Desktop --filter MemoryPromptPolicyTests

cd /root/workspace/omi-memory-ingestion-pipeline/web/frontend && npm run typecheck
cd /root/workspace/omi-memory-ingestion-pipeline/desktop/windows/src/renderer && npm run typecheck
```

---

## T26 — Admin policy controls, Chat Lab, telemetry, and rollout kill switches

**Goal:** Keep rollout observable, configurable, and safe without complicating user UI.

**Files:**
- Create: `backend/utils/memory/v17_telemetry.py`
- Create: `web/admin/components/dashboard/memory-policy-selector.tsx`
- Modify: `backend/utils/metrics.py`
- Modify: `backend/routers/metrics.py`
- Modify: `backend/jobs/v17_l2_backfill_worker.py`
- Modify: `web/admin/app/(protected)/dashboard/apps/page.tsx`
- Modify: `web/admin/components/dashboard/app-detail-view.tsx`
- Modify: `web/admin/app/(protected)/dashboard/chat-lab/page.tsx`
- Test: `backend/tests/unit/test_v17_telemetry.py`
- Test: `backend/tests/unit/test_v17_rollout_controls.py`
- Test: `backend/tests/unit/test_v17_metrics_hygiene.py`

**Admin policy options:**

```text
No memory
Long-term + Short-term
Long-term + Short-term + Archive opt-in
Admin/debug configurable
```

**Metrics hygiene fields:**

```text
operation_type=migration|backfill|repair|shadow|import
counts_as_user_memory_created=false
counts_as_engagement=false
counts_as_organic_search=false
counts_as_export_activity=false
counts_as_notification_activity=false
counts_as_memory_count_growth=false unless explicitly dashboard-separated
counts_as_cohort_activation=false
```

**Kill switches must cover:**

```text
inventory
source snapshot/high-water jobs
raw artifact copy/accounting
no-silent-data-loss verifier/admin jobs
old-memory import
Short-term/Archive writes
Long-term dry-run
patch apply
source tombstone propagation
vector repair
export/delete/account-purge side-effecting jobs
read switch
benchmark/repair jobs that touch product state
```

**Acceptance criteria:**

- Chat Lab can test default memory vs explicit Archive search vs no memory.
- Third-party app policy defaults to Long-term + Short-term only.
- Bulk events cannot count as organic memory creation, engagement, notification activity, search, export, memory growth, or cohort activation.
- Stage-specific kill switches are tested before corresponding stage can run.
- Dashboard distinguishes Short-term, Long-term, Archive.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_telemetry.py tests/unit/test_v17_rollout_controls.py tests/unit/test_v17_metrics_hygiene.py -q

cd /root/workspace/omi-memory-ingestion-pipeline/web/admin
npm run typecheck
```

---

## T27 — Migration/backfill benchmark mode

**Goal:** Extend benchmark repo to evaluate old Omi export → Short-term/Archive import → Long-term backfill honestly.

**Benchmark files:**
- Create: `/root/workspace/omi-ingestion-benchmark/scripts/v17_migration_backfill_runner.py`
- Create: `/root/workspace/omi-ingestion-benchmark/scripts/v17_migration_report.py`
- Create: `/root/workspace/omi-ingestion-benchmark/tests/test_v17_migration_backfill_runner.py`
- Create: `/root/workspace/omi-ingestion-benchmark/tests/test_v17_migration_report.py`
- Modify: `/root/workspace/omi-ingestion-benchmark/scripts/v17_4_e2e_pipeline.py`
- Modify: `/root/workspace/omi-ingestion-benchmark/scripts/v10_judge.py`
- Modify: `/root/workspace/omi-ingestion-benchmark/docs/v17_implementation_tickets.md`

**Required reports:**

- Base Omi anchor leftmost and clearly labeled.
- Short-term import completeness.
- Archive completeness.
- Long-term active-only yield.
- Active + review yield.
- Active + Archive yield.
- Active + review + Archive yield.
- All proposed non-rejected yield.
- Missed-useful audit for Archive/review/reject/hidden routes.
- Useful-grounded-safe per 100 contexts.
- Harmful/noisy per 100 contexts.
- Source-stratified route distribution.
- Bootstrap confidence intervals or equivalent uncertainty reporting where feasible.
- Replay/idempotency counts.

**Acceptance criteria:**

- Eval cannot claim quality improvement by hiding useful memories in Archive/reject/review.
- No launch claim based only on cleaner Long-term metrics if total useful yield regresses.
- Useful-grounded-safe yield remains Base-like unless explicit tradeoff is documented.
- Harmful/noisy remains below Base Omi projection.
- Active secrets = 0.
- Non-primary active without explicit identity = 0.

**Verification:**

```bash
cd /root/workspace/omi-ingestion-benchmark
pytest tests/test_v17_migration_backfill_runner.py tests/test_v17_migration_report.py -q
```

---

## T28 — End-to-end idempotency and rollout safety verifier

**Goal:** Add one cross-cutting verifier that proves reruns/crashes do not duplicate side effects and rollout gates are met.

**Files:**
- Create: `backend/utils/memory/v17_safety_verifier.py`
- Create: `backend/tests/unit/test_v17_end_to_end_idempotency.py`
- Create: `backend/tests/unit/test_v17_rollout_safety_verifier.py`
- Modify: `backend/test.sh`

**Idempotency matrix:**

```text
old memory inventory
Short-term/Archive import
raw artifact accounting
lineage creation
vector upserts/deletes/repairs
L2 packet generation
search replay hash
patch synthesis
patch application
ledger commit
review queue / non-active outcome creation
source tombstone propagation
export/delete side effects
account purge side effects
```

**Acceptance criteria:**

- Rerun/crash/replay produces no duplicate active facts, no duplicate review/non-active outcomes, no stale duplicate vectors, and no cursor corruption.
- Verifier can answer whether a user/cohort can move from shadow → write → read.
- `backend/test.sh` includes the V17 ticket tests required for rollout gates.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_end_to_end_idempotency.py tests/unit/test_v17_rollout_safety_verifier.py -q
bash test.sh
```

---

## Spot-check checklist against the Epic

- [x] Short-term / Long-term / Archive product vocabulary.
- [x] No user-visible Context-only state.
- [x] Old memory behavior unchanged for non-whitelisted users.
- [x] Simple config surface.
- [x] Short-term + Long-term default access for Omi/agent/third-party/developer API.
- [x] Archive explicit query/opt-in only.
- [x] Existing deletion conventions extended to V17 tiers before writes.
- [x] Raw/source artifacts kept by default and loss reported honestly.
- [x] Same `ns2` vector namespace with strict metadata filters first.
- [x] No Long-term write bypasses ledger, idempotency claim, or per-user writer lease.
- [x] Patch/ledger/review/vector/source-tombstone idempotency.
- [x] Source snapshot/high-water mark before old-memory import writes and all mutable bulk source migrations.
- [x] Source/legacy/raw no-silent-data-loss verifier.
- [x] Progressive backfill with budgets, documented initial thresholds, pause/resume, rollback, and kill switches.
- [x] Kill switches include snapshot, raw accounting, verifier/admin, source tombstone, export/delete/account-purge side-effecting jobs.
- [x] Benchmarks include Base Omi anchor, uncertainty, route-yield matrix, and anti-reward-hacking missed-useful audits.
- [x] UI stays minimal; memory management available through agent tools.
- [x] Metrics hygiene prevents migration/backfill/repair from polluting organic dashboards.

---

## Wave review log

### Wave 1 — Ticket drafting

Three drafting subagents produced backend/data/control-plane, migration/backfill/eval, and product/API/UI/agent-tool ticket sets.

### Wave 3 — Final review and spot check

Three final review subagents reviewed the revised ticket doc against the Epic and decision brief:

- Backend/data architecture: **APPROVE_WITH_CHANGES**.
- Migration/backfill/eval/ops safety: **APPROVE_WITH_CHANGES**.
- Product/API/UI/agent integration: **APPROVE_WITH_CHANGES**.

Final requested changes incorporated:

- Added Epic supersession note so final Short-term / Long-term / Archive policy overrides older historical Durable/L1/L2/Context-only wording.
- Reaffirmed existing `ns2` + metadata filters as final vector default; separate namespace only fallback.
- Expanded sensitive-data taxonomy in T04.
- Generalized source snapshot/high-water protection to all mutable bulk source migrations, not only old-memory import.
- Required documented initial budget thresholds before write mode.
- Expanded kill switches to source snapshot jobs, raw accounting, no-silent-data-loss verifier/admin jobs, source tombstone propagation, and export/delete/account-purge side-effecting jobs.
- Hardened `/v3` read compatibility for old clients and existing `limit` behavior.
- Added explicit third-party/MCP/developer write-safety criterion.

Final committee outcome before Oracle: **ready to use as the implementation ticket queue**, with the tickets document as the implementation source of truth.

### Oracle review — External architecture/code critique

Oracle review is recorded in `docs/epics/v17_memory_oracle_review.md`.

Verdict: **BLOCKED** for production implementation. T00–T05 can proceed as design/audit work, but no persistent V17 writes, read switch, vector changes, or external API changes should ship until P0 amendments are incorporated.

Oracle P0 blockers to incorporate before implementation:

1. Define one atomic, fenced Long-term write protocol across idempotency claim, writer lease/fencing token, ledger append, head update, source-version check, purge-generation check, and recovery from every crash point.
2. Replace empty-list synthesis failures with typed, auditable outcomes so provider failures, parse errors, malformed patches, quote-wrapper candidates, and policy rejections cannot silently advance cursors or improve benchmarks by disappearance.
3. Replace/adapt current `L1MemoryArchiveItem` contract so fresh source-backed extraction becomes default-access Short-term, not Archive by default.
4. Define rollout/cutover/rollback reconciliation semantics; a simple `off|shadow|write|read` scalar is not enough to prevent disappearing memories or resurrection after fallback.
5. Add deletion/account-purge generation fences and apply-time source tombstone/version checks so delayed workers cannot recreate deleted data.
6. Add durable outbox/projection/vector consistency and fail-closed shared-namespace search gateway before any V17 vector/read rollout.
7. Define stable logical memory identity across Short-term → Long-term/Archive transitions and cross-tier read/dedup/ranking/pagination behavior.
8. Strengthen sensitive-data enforcement, third-party consent/scopes, raw-artifact copy-before-drop, live conversation-to-Short-term ingestion, review backlog resolution, and quantitative launch gates.

The next planning pass should convert these Oracle findings into new P0/P1 tickets and reorder the queue so safety infrastructure, benchmark gates, vector gateway, and rollout verifier precede write-mode tickets.
