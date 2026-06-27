# memory Memory Product Integration — Normative Architecture

**Status:** Locked product/architecture decisions after Oracle prescription + David decisions
**Date:** 2026-06-18
**Supersedes:** Historical Wave 1/2/3 planning language in `memory_product_integration_epic.md` where it conflicts with this document.

---

## 1. Product model

| Concept | Normative decision |
|---|---|
| Product tiers | Exactly `short_term`, `long_term`, `archive`. |
| Short-term | Fresh/default-access source-backed memory, while useful and not yet stabilized. |
| Long-term | Stable synthesized memory, backed by ledger commits. |
| Archive | Explicit-query historical/source-backed context; never default access. |
| Context-only | Not a product tier. May remain only as a legacy/internal processing alias and must normalize to Archive or another non-default outcome. |
| Review/reject/skip | Processing outcomes, not user-visible product tiers. |
| UI stance | Keep UI minimal: tier labels/filter/provenance/delete; deeper management through Omi/agent tools. |

Default access policy:

- Omi/chat/agent/MCP/developer/third-party default memory access = eligible **Short-term + Long-term**.
- Archive requires an explicit Archive operation and applicable app/user/admin policy.
- Sensitivity, visibility, source state, review state, and app grants can restrict any default access.

---

## 2. Storage and identity

### Canonical product-memory store

Use one tiered product-memory collection:

```text
users/{uid}/memory_items/{memory_id}
```

Do **not** create separate canonical Short-term and Archive collections.

Existing/current stores:

- `users/{uid}/memories` remains the current legacy compatibility/projection store during rollout.
- Existing `users/{uid}/short_term` is not the memory canonical store; treat it as legacy/adapter input only if needed.
- Existing ledger collections remain Long-term source of truth.

### Long-term authority

- Long-term source of truth remains the append-only memory ledger.
- `memory_items/{memory_id}` contains the transactionally synchronized product projection for Long-term reads/UI/API compatibility.

### Stable identity

- Mint opaque server-generated `memory_id` at first persistence.
- Keep `memory_id` for one-to-one transitions: Short-term → Long-term, Short-term → Archive, Long-term → Archive.
- For many-to-one consolidation, target Long-term `memory_id` wins; old IDs become resolvable aliases.
- Keep separate immutable operation/commit IDs and monotonically increasing item `version`.
- Never encode content, tier, source text, or user-visible claims into public IDs.

Canonical item shape must separate:

```text
memory_id
canonical_memory_id / alias metadata
version
tier = short_term | long_term | archive
status = active | superseded | hidden | tombstoned
processing_state = pending | processed | blocked
content
evidence[]
source_state = active | missing | tombstoned | purged
sensitivity_labels[]
visibility
user_asserted
captured_at
updated_at
expires_at  # required for Short-term
ledger_commit_id / ledger_sequence  # required for active Long-term
```

Access is derived from canonical state; do not persist drifting booleans like `normal_default_access` as authority.

---

## 3. Rollout and rollback

Keep a simple external rollout mode, but define exact semantics:

| Mode | Behavior |
|---|---|
| `off` | Legacy only. No memory reads/writes/workers for non-whitelisted users. |
| `shadow` | Legacy authoritative; memory audit artifacts only; no product-visible writes. |
| `write` | Legacy reads remain authoritative; memory sidecar writes may run for whitelisted users after gates pass. |
| `read` | Superset of `write`; memory read service becomes authoritative for whitelisted users. |

Required per-user rollout state:

```text
mode_epoch
cutover_epoch
account_generation
last_reconciled_legacy_revision
fallback_projection_ready
stage gate statuses
```

Rollback:

- `read → write` can be one config change only because reads fall back to the reconciled memory-derived compatibility projection.
- `write → off` is not a blind flag flip after persistent memory writes; it requires explicit decommission reconciliation.
- Rollback must not make memory-created memories disappear, resurrect deleted legacy values, or expose stale vectors.

---

## 4. Write protocol

### Long-term application

Use one atomic Firestore transaction over the per-user memory control/head documents.

Do **not** build a standalone distributed writer lease service unless a future writer cannot participate in the transaction.

The transaction must read/verify:

```text
memory_control/state
memory_state/head
memory_operations/{operation_id}
account_generation / writes_blocked
all referenced source/memory versions and tombstones
```

The transaction must write atomically:

```text
memory_commits/{commit_id}
memory_state/head
memory_operations/{operation_id}
affected memory_items/{memory_id}
memory_outbox/{event_id}
memory_legacy_fallback/{memory_id} when required for rollback/cutover
```

Rules:

- LLM/model output never supplies trusted IDs, observed head, packet ID, run ID, or idempotency key.
- Server creates `operation_id` and stable proposal fingerprint.
- Logical idempotency excludes observed head, retry count, and patch array index.
- Head mismatch creates `needs_replan`, not blind apply.
- A process crash before transaction leaves retryable operation; crash after commit is harmless and replay returns stored result.
- No commit may exist without matching head, operation result, and product projection.

### Operation journal

Use one server-owned `users/{uid}/memory_operations/{operation_id}` journal for active and non-active outcomes.

Typed synthesis result statuses:

```text
success
partial
retryable_failure
permanent_failure
```

Per-candidate outcomes:

```text
proposed
archive
review
reject
skip
invalid
```

No empty-list failure semantics. Provider failures, parse errors, malformed candidates, quote-wrapper candidates, policy rejections, and no-action decisions must become auditable outcomes.

A cursor may advance only when every input has a terminal outcome or a recorded retryable state.

---

## 5. Live ingestion and lifecycle

- Replace generic `L1MemoryArchiveItem` as the normal source-backed extraction contract with `SourceBackedMemoryCandidate`.
- Fresh extracted candidates start as `tier=short_term` unless imported/aged directly to Archive by explicit policy.
- Existing `L1MemoryArchiveItem` may stay only as a deprecated fixture/import adapter.
- Explicit first-party “remember this” may create Long-term directly as a user assertion.
- Automated extraction and generic third-party/API writes default to Short-term.

Short-term lifecycle:

- Default freshness window: **30 days** from capture or last corroboration.
- Successful Long-term promotion transitions/supersedes source-backed items atomically.
- Unprocessed expiry moves the item to Archive with reason `expired_unprocessed`.
- Review defaults unresolved items to Archive, not a user-visible review tier.
- MVP review remains internal/admin/conversational; no mandatory end-user review queue.

---

## 6. Read/search/vector policy

Use existing `ns2` memory vector namespace first.

Mandatory guardrails:

- Product code may query `ns2` only through one fail-closed memory search gateway.
- Authenticated UID and consumer policy are server-derived, never request-derived.
- Missing/malformed tier/status/user/version/source-state metadata fails closed.
- Vector results are candidate IDs only; authoritative `memory_items` hydration is required before returning anything.
- Hydration rejects stale versions, cross-user records, Archive in default mode, hidden/tombstoned records, and restricted sensitivity/app-scope records.
- Outbox consumers are idempotent/version-checked; deletes and tombstones outrank upserts.
- Repair must never overwrite a newer edit/delete.

Read service rules:

- Default result set = active Long-term + eligible Short-term.
- Archive requires explicit Archive operation; `tier=all` alone is insufficient for third parties.
- Deduplicate Short-term/Long-term via alias/lineage.
- User corrections outrank Long-term; current Long-term outranks inferred Short-term.
- Initial prompt budget: 70% Long-term / 30% Short-term, adjustable after benchmark evidence.
- Product list pagination uses unified `memory_items` and stable `(updated_at, memory_id)` cursor.

---

## 7. Deletion/export/account-purge policy from current product behavior

Current code behavior found in product repo:

| Flow | Current behavior |
|---|---|
| Single memory delete | `DELETE /v3/memories/{memory_id}` calls `database.memories.delete_memory`, which hard-deletes the Firestore memory doc, then best-effort deletes the Pinecone memory vector. It does not delete the source conversation/audio/import artifact. |
| Delete all memories | `DELETE /v3/memories` enumerates memory IDs, deletes all Firestore memory docs, then batch-deletes memory vectors. It does not delete conversations/audio. |
| Conversation delete | `database.conversations.delete_conversation` deletes the conversation's `photos` subcollection, then hard-deletes the conversation doc. Source-tombstone ripple into memories exists separately in `database.memories.ripple_source_deletion` and must be explicitly integrated where needed. |
| Account delete | `DELETE /v1/users/delete-account` revokes Firebase auth, cancels subscription best-effort, starts background wipe, best-effort deletes derived vectors and GCS conversation recordings, then recursively deletes all Firestore user subcollections and the user doc. Known follow-up gaps are documented in code: X-post vectors, speech-profile/person-sample/private-cloud-sync/chat-upload GCS blobs, externally indexed Typesense. |
| Store-recording permission delete | `DELETE /v1/users/store-recording-permission` sets permission false and deletes all conversation recordings. |
| Source deletion ripple | Existing `ripple_source_deletion` tombstones evidence, retracts memories with no active evidence, and tombstones short-term source records, but this is not the same as generic conversation delete unless wired into that path. |

memory deletion/export must follow and extend these conventions:

- Memory deletion removes Omi's memory item/projection/vector/search visibility; it does **not** delete original conversation/audio/imported raw artifacts unless the product's source/account deletion flow does so.
- Source deletion tombstones evidence/lineage and may retract/supersede memories, but raw artifact retention follows the source/account policy below.
- Account deletion must block future writes first, increment account generation, cancel queued jobs, delete/tombstone memory Firestore state and vectors, and follow current product account-wipe conventions.
- memory must not promise stronger erasure than product currently implements without a separate product/legal decision.
- The ledger/history erasure model remains: align with current hard-delete/account-wipe behavior; if append-only history is retained before full deletion, it must be encrypted and excluded from all product/search/export surfaces after deletion.

---

## 8. Raw/source artifact retention

David decision: **retain raw/source artifacts forever for now**, subject to existing source/account deletion controls.

Normative policy:

- Preserve available raw/source artifacts indefinitely by default.
- Do not add a user-facing raw-retention TTL or toggle for memory MVP.
- Copy ephemeral/raw bytes into durable encrypted storage before drop wherever technically feasible.
- Historical already-missing ephemeral data remains explicit loss; do not claim it was preserved.
- Memory deletion does not delete raw/source artifacts.
- Source/account deletion and existing recording-permission deletion remain the mechanisms that can remove raw artifacts.
- Record raw artifact lineage and preservation/loss outcome for every source-backed item.

---

## 9. Third-party/app permissions

- Existing broad memory permission maps to default memory access: Short-term + Long-term.
- Archive and raw provenance require separate explicit capability/request.
- Revocation must take effect server-side regardless of cached vector results.
- Third-party/API generic writes default to Short-term, not Long-term, unless first-party/user-asserted policy explicitly applies.

---

## 10. Benchmarks and launch gates

Before Long-term write mode:

- Base Omi remains the leftmost/visible anchor in every evolution graph/report.
- Report active-only, active+review, active+Archive, and all non-rejected yield.
- Useful-grounded-safe yield non-inferiority margin: no worse than 5 memories per 100 contexts relative to Base unless explicitly approved.
- Active Long-term harmful/noisy: no more than 25 per 100 contexts.
- Active credentials/secrets: zero.
- Archive returned by default-policy tests: zero.
- Duplicate logical operation or commit on replay: zero.
- Every non-active candidate in the fixed offline set gets a missed-useful audit.
- Migration/backfill/repair metrics cannot count as organic creation, engagement, notification, search, export, memory growth, or cohort activation.

---

## 11. Decisions still requiring external/legal confirmation

Only one remaining non-engineering question is unresolved:

- Whether current and future account-deletion promises legally require physical deletion of append-only history immediately, or whether encrypted crypto-erasure plus async physical cleanup is acceptable.

Until answered, memory implementation should mirror current product deletion behavior and avoid adding new user-visible deletion promises beyond current product semantics.
