# memory Memory Product Integration — Normative Architecture

**Status:** Locked product/architecture decisions after Oracle prescription + David decisions
**Date:** 2026-06-18
**Last updated:** 2026-07-27 — broad Short-term intake, one terminal consolidation route, and atomic graph-backed Long-term admission
**Supersedes:** Historical Wave 1/2/3 planning language in `memory_product_integration_epic.md` where it conflicts with this document.

---

## 1. Product model

| Concept | Normative decision |
|---|---|
| Product tiers | Exactly `short_term`, `long_term`, `archive`. |
| Short-term | Broad, fresh, source-backed intake while useful and not yet stabilized. Every new memory starts here. |
| Long-term | Stable synthesized memory, backed by an atomic promotion admission receipt, ledger commit, and per-memory graph assertion. |
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
- A newly admitted active Long-term item is authoritative only when its
  `memory_items/{memory_id}` row, server-authored promotion admission receipt,
  and `memory_graph_assertions/{memory_id}` document share the same atomic
  ledger commit and version fences.
- Shared knowledge-graph nodes/edges, keyword indexes, vectors, and compatibility
  rows are derived projections. They never substitute for the per-memory
  assertion or canonical item.

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
promotion.admission_receipt  # required for every new Short-term → Long-term admission
graph_ready / graph_assertion_id / graph_plan_hash  # required for admitted active Long-term
```

Access is derived from canonical state; do not persist drifting booleans like `normal_default_access` as authority.

---

## 3. Universal operations and rollback

Every authenticated account uses the same memory authority. Deployment modes
are global incident/cost declarations only; they never select users or stores:

| Mode | Behavior |
|---|---|
| `off` | Pause new canonical intake and scheduled maintenance; keep the universal dual-format reader so canonical data never disappears. |
| `shadow` | Deprecated observation declaration; it cannot change product routing. |
| `write` | Canonical intake enabled globally; the universal reader remains authoritative. |
| `read` | Normal universal operation: canonical writes plus canonical/historical merged reads. |

Required per-account correctness state:

```text
account_generation
head_commit_id / source_generation
writes_blocked
historical materialization overrides and tombstones
```

Rollback:

- The universal dual-format reader is the rollback floor. Never roll back to a
  legacy-only reader after canonical writes have started.
- A global pause may stop intake or L2 work, but cannot make canonical memories
  disappear or resurrect suppressed historical rows.
- Privacy tombstones and account-generation fences are irreversible routing
  authority even while provider cleanup is retrying.

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
the server-authored promotion admission receipt and graph plan for a Short-term → Long-term transition
```

The transaction must write atomically:

```text
memory_commits/{commit_id}
memory_state/head
memory_operations/{operation_id}
affected memory_items/{memory_id}
memory_graph_assertions/{memory_id} for every newly admitted active Long-term item
memory_outbox/{event_id}
memory_legacy_fallback/{memory_id} when required for rollback/cutover
```

Rules:

- LLM/model output never supplies trusted IDs, observed head, packet ID, run ID, or idempotency key.
- Server creates `operation_id` and stable proposal fingerprint.
- Logical idempotency excludes observed head, retry count, and patch array index.
- Head mismatch creates `needs_replan`, not blind apply.
- A process crash before transaction leaves retryable operation; crash after commit is harmless and replay returns stored result.
- No new active Long-term commit may exist without the matching admission
  receipt, version-fenced graph assertion, head, operation result, product
  item, and outbox records.
- Projection delivery is not part of admission. The transaction durably
  records projection intent; bounded workers hydrate current authoritative
  state, apply idempotent/version-checked side effects, and retry failures.

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
- Every newly captured candidate starts as `tier=short_term`, including
  conversation extraction, first-party “remember this,” imports, generic API
  writes, plugins, and integrations.
- Existing `L1MemoryArchiveItem` may stay only as a deprecated fixture/import adapter.
- Historical migration/backfill may materialize a prior tier under its explicit
  migration policy; that is not new intake and must not introduce a reusable
  direct-to-Long-term write path.

Short-term lifecycle:

- Default freshness window: **30 days** from capture or last corroboration.
- Required normalization and TTL audit run before one authoritative
  consolidation pass.
- Every pending, eligible item receives exactly one terminal consolidation
  route: `promote`, `archive`, `review`, or `reject`. Model output must be an
  exact partition of the pending batch before any route mutates state.
- `promote` is the only route to Long-term. It binds the current item revision,
  output content hash, evidence IDs, supersedes set, and graph plan into a
  server-authored admission receipt, then writes the Long-term item and
  per-memory graph assertion in the same transaction.
- `archive`, `review`, and `reject` settle outside default access according to
  their status/review policy; they never fall through to promotion.
- There is no generic batch/daily promotion pass and no first-party,
  user-asserted, or fast-track bypass.
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
- Canonical commits persist keyword/vector/compatibility projection intent in
  `memory_outbox`; consumers lease due events, hydrate authoritative state,
  apply idempotent/version-checked side effects, retry failures with bounded
  backoff, and acknowledge only success. Deletes and tombstones outrank
  upserts.
- Repair must never overwrite a newer edit/delete.

Read service rules:

- Default result set = active Long-term + eligible Short-term.
- Archive requires explicit Archive operation; `tier=all` alone is insufficient for third parties.
- Deduplicate Short-term/Long-term via alias/lineage on default lists and
  searches; prefer the active Long-term canonical survivor while retaining
  unique fresh Short-term evidence.
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
- Third-party/API writes, like every other new intake surface, enter Short-term.

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
