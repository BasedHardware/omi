# memory Milestone 1 Oracle Review — Foundations

**Date:** 2026-06-19  
**Milestone:** P0 foundations: rollout state, canonical product-memory/evidence models, unified collection constants, Firestore indexes.
**Initial verdict:** BLOCKED.
**Resolution:** Required fixes incorporated in commit following this review: gate-aware rollout resolution, strict persisted model metadata, fail-closed access policy, user-asserted Archive transitions, typed artifact/source outcomes, alias validation, stronger index tests.

---

## 1. Verdict: **BLOCKED**

The overall direction is sound: the implementation has the correct three tiers, unified `memory_items` collection, canonical status/state enums, opaque IDs, Long-term ledger linkage, Short-term expiry support, and plausible initial indexes.

Milestone 1 is nevertheless blocked from serving as the foundation for Milestone 2 because several security- and identity-critical behaviors currently contradict the normative architecture:

* Rollout capabilities can be enabled without consulting per-user rollout state or stage gates.
* The default-access helper is fail-open and can authorize Archive through a caller-provided string.
* Missing persisted metadata silently defaults to authoritative values such as `status=active`, `version=1`, and `source_state=active`.
* The model prohibits preserving `user_asserted` when a Long-term item moves to Archive.
* Raw-artifact preservation/loss outcome is not actually required by the evidence model.

This is a static review of the supplied files; it does not include executing the tests or inspecting unprovided call sites.

## 2. Required fixes before proceeding to Milestone 2

### A. Make rollout capability resolution depend on persisted per-user state

Affected code:

* `backend/config/v17_memory.py::MemoryRolloutConfig.for_user`
* `backend/config/v17_memory.py::decide_memory_rollout_capabilities`
* `backend/config/v17_memory.py::MemoryRolloutState.can_transition_to`

`for_user()` currently uses only the global mode and allowlist. It can return `memory_reads_enabled=True` even when the user’s `fallback_projection_ready` is false or their stage gates have failed. `decide_memory_rollout_capabilities()` also provides a public bypass around the allowlist and state entirely.

Required change:

* Add typed stage-gate statuses to `MemoryRolloutState`, as explicitly required by the architecture.
* Introduce one public resolver taking both `MemoryRolloutConfig` and `MemoryRolloutState`.
* Enable `write` only after the applicable write gates pass.
* Enable `read` only after read gates pass and `fallback_projection_ready=True`.
* Make `decide_memory_rollout_capabilities()` private or require the full state/gate input.
* Ensure a blocked account/control state cannot receive write capability.
* Validate nonnegative `mode_epoch`, `cutover_epoch`, and `account_generation`.

`MemoryRolloutState` is also not currently an enforceable state machine. A caller can directly assign `state.mode = MemoryRolloutMode.off` and bypass `can_transition_to()`. Add a transition operation that returns or persists a validated new state, increments `mode_epoch`, and updates `cutover_epoch` according to defined semantics. Prefer making direct state mutation impossible.

Also cover rollback to every legacy-authoritative mode. The implementation protects `read → write`, but `read → shadow` currently bypasses the fallback-readiness check even though both targets return authority to legacy reads.

### B. Separate trusted creation defaults from strict persisted-item hydration

Affected code:

* `backend/models/product_memory.py::MemoryItem`
* `backend/models/memory_evidence.py::MemoryEvidence`

The canonical stored model currently defaults security-critical fields:

```python
version = 1
status = active
processing_state = pending
source_state = active
sensitivity_labels = []
visibility = "private"
```

If a Firestore document is missing `status`, `version`, or `source_state`, Pydantic supplies a value rather than failing closed. In particular, a malformed record can become active source-backed version 1 data.

Use separate concepts:

* A trusted server-side creation factory or command model may supply initial defaults.
* The canonical persisted/hydrated model must require all canonical metadata to be explicitly present.

At minimum, persisted hydration must require:

* `version`
* `tier`
* `status`
* `processing_state`
* `source_state`
* `sensitivity_labels`
* `visibility`
* `user_asserted`
* `captured_at`
* `updated_at`

Use strict validation or equivalent repository-level presence checks. Do not expose `MemoryItem` directly as an API/model-output input type. The server must continue to mint `memory_id`.

Additional required invariants:

* Require `expires_at` for every Short-term item, not only active Short-term items. The normative shape says it is required for Short-term.
* Require nonblank `content` for active items.
* Require timezone-aware timestamps.
* Require `updated_at >= captured_at`.
* Require a Short-term expiry later than its capture time at creation.
* Prevent an active Long-term item with `processing_state=blocked`. Prefer requiring active Long-term items to be `processed`.
* Ensure models cannot be mutated after validation into an invalid state, either through immutability, assignment validation, or mandatory validation immediately before persistence.

### C. Replace `derived_default_access_allowed()` with a fail-closed policy boundary

Affected code:

* `backend/models/product_memory.py::derived_default_access_allowed`
* `backend/tests/unit/test_memory_normative_foundations.py::test_product_memory_item_invariants_short_term_long_term_archive`

The current helper has several critical problems:

1. A function named “default access” returns `True` for Archive when passed `"archive_explicit"`, `"admin_debug"`, or `"eval"`.
2. The `consumer` argument is an unrestricted string. Any caller can claim `"archive_explicit"`.
3. Short-term and Long-term use a blacklist:

   ```python
   return consumer not in {"archive_only"}
   ```

   Therefore unknown or misspelled consumers are granted access.
4. It ignores app grants and does not interpret `visibility`.
5. It allows expired Short-term items.
6. It allows `processing_state=blocked`.
7. It allows `content=None`.
8. It has no mechanism for a policy to restrict `source_state=missing`.
9. Sensitivity checking is limited to two exact, case-sensitive strings.

Required design:

```python
is_default_access_eligible(item, server_policy, now)
is_archive_access_eligible(item, archive_operation, server_policy, now)
```

The default predicate must always reject Archive. Explicit Archive access must be a separate operation requiring a server-derived capability and applicable user/app/admin policy.

Both paths must still enforce item status, source policy, sensitivity, visibility/grants, expiry, and processing eligibility. Unknown consumers, policies, labels, or visibility values must fail closed.

The following existing test expectations should be removed:

* Line 123: a bare `"third_party"` string authorizes a private item without any represented grant.
* Line 150: the default-access helper authorizes Archive.

Add negative tests for unknown consumer types, blocked items, expired Short-term items, missing required policy, and Archive requested without an explicit capability.

### D. Preserve `user_asserted` through Archive transitions

Affected code:

* `backend/models/product_memory.py::MemoryItem.validate_tier_invariants`, lines 90–91

This validation is incorrect:

```python
if self.tier == MemoryTier.archive and self.user_asserted:
    raise ValueError(...)
```

`user_asserted` is provenance, not an access tier. The architecture allows `Long-term → Archive` while preserving the same `memory_id`. Clearing `user_asserted` during that transition would erase the fact that the memory originated as a user assertion.

Remove this invariant. If direct creation of an Archive user assertion is undesirable, enforce that in the transition/write command—not in the canonical state model.

Add a test that an active user-asserted Long-term item can transition to Archive with:

* The same `memory_id`
* An incremented `version`
* `user_asserted=True` preserved

### E. Complete the canonical evidence and raw-artifact contract

Affected code:

* `backend/models/memory_evidence.py::MemoryEvidence`
* `backend/tests/unit/test_memory_normative_foundations.py::test_evidence_requires_source_identity_or_typed_missing_reason`

The evidence model does not currently satisfy the requirement to record raw-artifact lineage and preservation/loss outcome for every source-backed item:

* `artifact_refs` defaults to an empty arbitrary dictionary list.
* `encryption_or_redaction_status` is optional and untyped.
* No preservation/loss outcome is required.
* The test name says “typed missing reason,” but `missing_source_reason` is an unrestricted `str`.
* A tombstoned or purged source can omit its reason whenever `source_id` exists.
* `source_id` and `conversation_id` can contradict each other.
* `evidence_id`, `source_type`, `source_id`, and `source_version` accept whitespace-only values.

Introduce at least:

* A typed artifact-reference model
* A typed artifact preservation/loss state
* A typed source-state reason
* Explicit durable reference, unavailable-historical, deleted-by-policy, purged, or not-applicable outcomes as appropriate

For source-backed evidence, require a recorded outcome even when the raw artifact is unavailable.

Also enforce aggregate consistency between item and evidence state. Today this passes:

* Item: `source_state=active`
* Every evidence record: `source_state=tombstoned`

That item can then pass default access. For a non-user-asserted item, `source_state=active` should require at least one eligible active evidence record. Source deletion updates must not leave the item-level aggregate active after its last active evidence is removed.

### F. Choose one authoritative alias representation

Affected code:

* `backend/models/product_memory.py::MemoryItem.canonical_memory_id`
* `backend/models/product_memory.py::MemoryItem.aliases`
* `backend/models/product_memory.py::MemoryItemAlias`
* `backend/database/v17_collections.py::memory_lineage`

There are currently three possible alias authorities:

* `canonical_memory_id` on the old item
* An inline `aliases` list on the target item
* Separate `MemoryItemAlias` records

They can drift, and the inline list can become unbounded in many-to-one consolidation.

Before implementing the write transaction, select one normative resolution strategy. A simple approach consistent with the required atomic `memory_items` writes is:

* Keep the old `memory_items/{old_id}` record.
* Mark it `superseded`.
* Set its `canonical_memory_id` to the winning target.
* Resolve old IDs by following that pointer.
* Do not maintain an unbounded reverse `aliases` array as an authority.

If separate alias documents are retained, define their collection path and include their writes in the atomic protocol. Add validation against self-aliases, blank IDs, and alias cycles.

### G. Strengthen tests so they verify behavior rather than field presence

Affected code:

* `backend/tests/unit/test_memory_normative_foundations.py`
* `backend/tests/unit/test_memory_firestore_indexes.py`

Required additions:

* Capability resolution with failed/missing stage gates
* Read capability with `fallback_projection_ready=False`
* No direct capability bypass
* Transition epoch updates and prohibited direct downgrade paths
* Missing persisted `status`, `version`, or `source_state` fails validation
* Unknown fields or misspelled critical fields do not become active defaults
* Default access always rejects Archive
* Unknown consumers fail closed
* Expired Short-term and blocked items are denied
* Archive preserves `user_asserted`
* Every Short-term status retains `expires_at`
* Item/evidence source-state inconsistencies fail
* Raw-artifact preservation/loss outcome is required
* Alias self-reference and ambiguous authority are rejected

`test_memory_firestore_indexes_are_checked_in_for_unified_memory_store()` converts index fields to sets. That means it would still pass if `updated_at` changed from descending to ascending, `__name__` changed direction, or the fields were in an unusable order. Assert exact ordered `(fieldPath, order)` tuples and `queryScope`.

The operations and outbox indexes are currently tested only by collection name. Assert their actual fields and directions as well.

The checked-in index definitions themselves are reasonable for the listed per-user query shapes. However, explicitly decide whether expiration and outbox workers perform per-user collection queries or cross-user collection-group queries. If they use `collection_group(...)`, `queryScope: "COLLECTION"` is insufficient and the relevant indexes need `COLLECTION_GROUP` variants.

## 3. Nice-to-have fixes that can be deferred

* Return a typed eligibility decision with a denial reason instead of a bare Boolean. This will improve auditability without changing policy.
* Add a persisted `schema_version` so future canonical-model changes can be migrated explicitly.
* Rename `MemoryCollections.all_collection_paths()` to `all_subcollection_paths()` and add a separate method for document paths such as `memory_control/state` and `memory_state/head`.
* Reuse `parse_enabled_users()` inside `MemoryRolloutConfig.from_env()` and validate that `backfill_daily_limit` is nonnegative.
* Add Firestore emulator tests that execute the intended list, expiry, operation, and outbox queries rather than only inspecting JSON.
* Add the `processing_state + expires_at` composite index once the exact unprocessed-expiry worker query is fixed.
* Normalize sensitivity labels and source types at ingestion rather than leaving them as arbitrary strings.
* Document that `archive_opt_in_enabled` controls feature availability only. It must not become the authorization decision for Archive access.
* Add reason codes to capability and transition decisions for operational observability.

## 4. Contradictions with the normative architecture

| Normative requirement                                                                                   | Contradicting implementation                                                                                                 |
| ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Per-user rollout state includes stage-gate statuses                                                     | `MemoryRolloutState` has no stage-gate state.                                                                                   |
| Write/read modes apply only after gates pass                                                            | `MemoryRolloutConfig.for_user()` and `decide_memory_rollout_capabilities()` never inspect gates or persisted rollout state.                |
| Default access is eligible Short-term plus Long-term; Archive requires an explicit operation and policy | `derived_default_access_allowed()` returns `True` for Archive based solely on a magic consumer string.                       |
| Consumer policy is server-derived                                                                       | `consumer: str` is caller-provided and unknown consumers are allowed for Short-term/Long-term.                               |
| Missing or malformed status/user/version/source-state metadata fails closed                             | `MemoryItem` defaults missing `status` to active, `version` to 1, and `source_state` to active.                           |
| Visibility, source state, review state, sensitivity, and app grants can restrict access                 | The helper ignores visibility/app grants, allows blocked processing state, and has only two exact sensitivity-string checks. |
| `expires_at` is required for Short-term                                                                 | The validator requires it only when Short-term is active.                                                                    |
| Long-term may transition to Archive while keeping its stable identity                                   | The model rejects Archive whenever the preserved provenance flag `user_asserted=True`.                                       |
| Every source-backed item records raw-artifact lineage and preservation/loss outcome                     | `artifact_refs` and the encryption/redaction field are optional and untyped; no outcome is required.                         |

One potential contradiction needs clarification: `MemoryCollections.memory_runs` is acceptable as non-authoritative diagnostics, but it must not become a second operation/result journal. The normative architecture requires `memory_operations` to be the single server-owned journal for active and non-active outcomes.

The following parts are aligned and should be retained:

* `MemoryTier` contains exactly `short_term`, `long_term`, and `archive`.
* Review/reject/skip are not represented as product tiers.
* `MemoryCollections.memory_items` uses the unified canonical path.
* No canonical Short-term or Archive collection is introduced.
* Status, processing-state, and source-state enum values match the normative shape.
* Active Long-term items require ledger commit metadata.
* `new_memory_id()` produces opaque, non-content-derived IDs.
* The principal `memory_items` pagination and expiry indexes match the intended unified-store direction.


7m01s · gemini-3.5-flash[browser] · ↑10.03k ↓4.29k ↻0 Δ14.33k
files=8
