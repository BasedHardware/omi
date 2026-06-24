# V17 Milestone 3 Oracle Review — Atomic Apply, Outbox, Search Gateway

**Date:** 2026-06-19  
**Milestone:** Atomic apply skeleton, outbox barriers/watermarks, fail-closed search gateway.  
**Initial verdict:** PASS_WITH_FIXES.  
**Resolution:** Contract-level fixes incorporated after this review: patch/operation payload digest binding before idempotent skip, retryable head mismatch semantics, generation-scoped operation digest, skip-duplicate barrier outbox events, contiguous projection watermark advancement, revision/hash-aware vector hit validation, material memory revision/source metadata. Remaining Firestore adapter, concurrency, IAM/rules, outbox worker, and vector-provider integrations remain deferred production-integration work.

---

# 1. Verdict: **PASS_WITH_FIXES**

The overall design is P0-viable. The important foundations are correct: untrusted/trusted schema separation, server-generated identities, generation fencing, atomic head/materialization/journal/outbox writes, and authoritative hydration before access checks.

However, the written contracts are not yet P0-complete. Do not begin the production Firestore adapter until the fixes below are represented in contracts and tests. The current gaps could cause:

* False idempotent success for a mismatched payload.
* Operations that cannot be retried after head contention.
* Incorrect `skip_duplicate` materialization.
* Cross-generation or inactive evidence being incorporated.
* Projection watermarks claiming freshness despite skipped commits.
* Search returning incomplete or stale results as though they were current.
* Old vector events overwriting newer item versions.

## 2. Required fixes

### A. Bind the patch to the operation before the committed shortcut

The ordering at lines 37–45 is unsafe as written. An already-committed operation is returned before `patch_payload` is validated or shown to match the operation.

Validate and canonicalize the patch before any idempotent return:

```python
patch = DurableMemoryPatch.model_validate(patch_payload)
patch_digest = build_patch_digest(patch)

operation.assert_integrity()

if patch_digest != operation.logical_payload_digest:
    raise OperationPayloadMismatch(
        operation_id=operation.operation_id,
    )

if operation.status is OperationStatus.committed:
    return ApplyResult.idempotent_skip(
        operation_id=operation.operation_id,
        committed_head_commit_id=operation.committed_head_commit_id,
        committed_sequence=operation.committed_sequence,
        mutation_refs=operation.committed_mutation_refs,
        outbox_event_ids=operation.committed_outbox_event_ids,
    )
```

`MemoryOperation` should persist immutable:

* `logical_payload_digest`
* ID schema version
* account and source generations
* operation type
* source packet and target references

The committed result should additionally persist the sequence, resulting memory IDs/revisions, and outbox event IDs. A retry must return this stored result rather than recomputing it.

Also freeze the canonical-ID encoding now. At minimum:

* Domain-separated hashes for patch, operation, commit, memory, and outbox IDs.
* Explicit canonicalization version.
* Unicode normalization.
* Defined absent-versus-null behavior.
* Fixed encoding for confidence rather than platform-dependent floating point.
* Rejection of NaN and infinity.
* Deterministic treatment of sets versus ordered lists.
* Golden test vectors.

Ensure the ID dependency graph is acyclic, for example:

```text
patch_digest -> new_memory_id -> operation_id -> commit_id -> outbox_event_id
```

### B. Separate logical operation identity from head-bound attempts

Line 23 intentionally excludes the observed head from `operation_id`. That is reasonable, but it means a head mismatch must not terminally fail that operation.

Use this state behavior:

| Condition                                    | Operation transition   | Domain writes                              |
| -------------------------------------------- | ---------------------- | ------------------------------------------ |
| Head mismatch                                | No terminal transition | None                                       |
| Stale account/source generation              | Terminal rejection     | Operation journal only                     |
| Source deleted or purged                     | Terminal rejection     | Operation journal only                     |
| Source temporarily unavailable or processing | Retryable/nonterminal  | None, or attempt journal only              |
| Success                                      | Committed              | Head, memory, operation, outbox atomically |

For contention, return a typed result containing the current head:

```python
ApplyResult(
    status=ApplyStatus.retryable_head_mismatch,
    current_head=current_head,
)
```

Do not overwrite an immutable `observed_head` field on the logical operation. Either pass `expected_head` separately to `apply`, or create an attempt identity:

```python
attempt_id = hash_id(
    "omi:v17:apply-attempt:v1",
    operation_id,
    expected_head.sequence,
    expected_head.commit_id,
)
```

This also resolves the contradiction in lines 38–40 between “mark stale_generation” and “do no writes.” The contract should say **no control, memory, or outbox writes**; an operation-only terminal status write is permitted.

### C. Define the production transaction’s authoritative read set

The pure skeleton may accept objects, but the production contract must require those objects to be read authoritatively inside the same Firestore transaction.

The transaction must read:

1. Current account control state and generation.
2. Existing operation document, if any.
3. Source packet and current source-generation state.
4. Every referenced evidence document.
5. Every target and superseded memory item.
6. Current server-side policy inputs needed to derive effective access.
7. Existing deterministic outbox documents when using create-if-absent semantics.

Then it must validate:

```python
assert operation.uid == control.uid
assert operation.account_generation == control.account_generation
assert operation.source_generation == source.source_generation

for evidence in evidence_items:
    assert evidence.uid == control.uid
    assert evidence.account_generation == control.account_generation
    assert evidence.source_generation == operation.source_generation
    assert evidence.state is EvidenceState.active

for target in target_items:
    assert target.uid == control.uid
    assert target.account_generation == control.account_generation
    assert target.lifecycle_state is MemoryLifecycle.active
```

“All evidence IDs are valid at synthesis time” is not sufficient. Every evidence reference must be rechecked at apply time. The singular “source evidence” wording at line 40 should be changed to **all referenced evidence and source records**.

Caller-supplied snapshots must never be considered authoritative. Firestore Security Rules or IAM should also prohibit bypass writes to control, memory, operation, and watermark documents.

### D. Specify a mutation plan for every decision type

Line 44 says a Long-term item is always materialized, but `skip_duplicate` should not create a duplicate item. The contract needs an exhaustive mutation matrix.

Recommended defaults:

| Decision         | Required mutation                                                          |
| ---------------- | -------------------------------------------------------------------------- |
| `add`            | Create one deterministic new item; precondition that it does not exist     |
| `update`         | Revise exactly one active target; advance `item_revision` and content hash |
| `merge`          | Create/update replacement and mark all merged targets superseded           |
| `add_evidence`   | Union evidence into target, recompute access, and advance revision         |
| `skip_duplicate` | No memory mutation                                                         |

Every material memory state must carry at least:

```text
item_revision
source_commit_id
source_commit_sequence
content_hash
account_generation
lifecycle_state
```

For merges and supersession, projection/vector actions must contain tombstones for old active identities as well as an upsert for the resulting item.

I recommend that `skip_duplicate` still commit the operation and advance the audit ledger head. Because search watermarks follow the ledger, it must emit no-op/barrier events for projection and vector subsystems rather than ordinary item upserts.

### E. Derive access and provenance entirely on the server

`default_access_candidate=False` for secret-risk sources is good, but it is only safe if apply cannot subsequently loosen that decision.

The trusted apply layer should derive access as a restrictive join of:

* Current account policy.
* All evidence classifications.
* Source secret/credential risk.
* Existing target restrictions for update/add-evidence.
* Any server-side review requirement.

Conceptually:

```python
effective_access = derive_effective_access(
    account_policy=current_policy,
    evidence=evidence_items,
    existing_memory=target_item,
)

assert not patch.can_override(effective_access)
```

Required invariants:

* Proposal or patch input cannot grant default access.
* An update or merge cannot silently reduce sensitivity.
* Archive capability is additive to normal ownership, generation, and item-policy checks.
* Evidence content is immutable by ID. A content change creates a new evidence ID or version included in the operation identity.
* Evidence deletion/purge state remains mutable and is transactionally checked.

This should be explicit in the apply contract even if the access derivation helper already exists from Milestone 1.

### F. Replace monotonic-only watermarks with contiguous, generation-scoped watermarks

The line 61 test is insufficient. A worker could process sequence 12 before 11, move the watermark to 12, and permanently claim freshness despite missing commit 11. Preventing backwards movement does not prevent gaps.

Use:

```python
@dataclass(frozen=True)
class ProjectionWatermark:
    account_generation: int
    sequence: int
    commit_id: str
```

Advancement must establish the chain:

```python
assert event.account_generation == watermark.account_generation
assert event.commit_sequence == watermark.sequence + 1
assert event.parent_commit_id == watermark.commit_id

apply_all_actions_idempotently(event)
advance_watermark(
    sequence=event.commit_sequence,
    commit_id=event.commit_id,
)
```

Maintain separate projection and vector watermarks. Both are necessary: per-hit validation cannot detect a newly committed item that is completely absent from a lagging vector index.

Each commit should produce exactly one deterministic event per subsystem containing all actions for that subsystem, including an empty barrier action when the commit changed no indexed item.

Recommended event identity:

```python
event_id = hash_id(
    "omi:v17:outbox:v1",
    uid,
    account_generation,
    commit_sequence,
    commit_id,
    subsystem,
)
```

Each item action must include:

```text
item_id
item_revision
content_hash
action: upsert | tombstone | barrier
```

Consumers must perform revision-aware writes so a delayed old event cannot overwrite or delete a newer indexed revision. Watermarks may advance only after the update is query-visible in the downstream store, not merely after dispatch or acknowledgement.

### G. Strengthen the search freshness contract

Lines 52–53 conflate two different concepts:

1. Whether the whole index is synchronized through the required ledger snapshot.
2. Whether an individual vector corresponds to the current authoritative item revision.

These need separate fields and checks.

First, obtain the required snapshot server-side:

```python
required = read_current_control_head(uid)

projection_watermark = read_projection_watermark(
    uid, required.account_generation
)
vector_watermark = read_vector_watermark(
    uid, required.account_generation
)

if projection_watermark != required:
    return SearchResult.retryable_projection_lag(required)

if vector_watermark != required:
    return SearchResult.retryable_vector_lag(required)
```

A caller must not be allowed to supply an arbitrarily old `required_commit_id`. A server-issued pinned snapshot token is acceptable for explicit historical/snapshot queries.

Then validate each hit exactly:

```python
item = authoritative_store.get(
    uid=authenticated_uid,
    account_generation=required.account_generation,
    item_id=hit.item_id,
)

assert item is not None
assert item.lifecycle_state is MemoryLifecycle.active
assert hit.uid == authenticated_uid
assert hit.account_generation == required.account_generation
assert hit.item_revision == item.item_revision
assert hit.source_commit_id == item.source_commit_id
assert hit.content_hash == item.embedding_source_hash
```

`vector_updated_at >= item.updated_at` should not be a correctness gate. A delayed write can have a newer timestamp while containing an older embedding. Keep timestamps for diagnostics only.

Also require:

* Superseded, deleted, and purged memory items are rejected.
* Vector-store text/snippets are never returned; only authoritative hydrated content is returned.
* Archive capability does not bypass ownership, generation, lifecycle, or per-item policy.
* Missing or version-mismatched authoritative hits produce a typed index-integrity/degraded result. In the default strict mode, do not silently turn index corruption into a successful empty result.
* Unauthorized hits may be silently omitted because that is expected policy filtering.

## Minimum additional tests before the skeleton receives a full PASS

Add tests proving:

1. A committed operation plus a different patch payload raises an integrity error rather than idempotently succeeding.
2. A head mismatch leaves the logical operation retryable, and the same operation can commit against a later head.
3. One purged item among several evidence references aborts all domain writes.
4. Cross-user and cross-generation target/evidence references fail closed.
5. `skip_duplicate` creates no memory item but advances the ledger with barrier events.
6. Sequence 12 cannot advance a watermark while sequence 11 is missing.
7. A delayed older vector event cannot overwrite or tombstone a newer revision.
8. A vector with a newer timestamp but the wrong revision/content hash is rejected.
9. A superseded authoritative memory item is never returned.
10. Search refuses an index that is missing the newest commit, even when all returned hits appear internally valid.
11. A caller cannot force acceptance of stale indexes by providing an older required commit.
12. Firestore transaction retry produces identical memory, commit, and outbox IDs.

# 3. What may be deferred

The following can wait for production Firestore integration without changing the logical contracts:

* Exact collection/document layout and naming.
* Firestore transaction callback implementation and retry plumbing.
* Index declarations and query tuning.
* Control-document contention/load testing and later sharding work.
* Outbox worker leases, backoff, dead-letter queues, replay tooling, and metrics.
* Vector-provider-specific consistency polling.
* Embedding model rollout, ranking quality, hybrid search, and pagination.
* Migration, compaction, repair, and full index rebuild tooling.
* Operational dashboards and alert thresholds.

These may be implemented later, but the contract must already require deterministic outbox IDs, contiguous watermarks, revision-aware consumers, transactional authoritative reads, and server-derived authorization.

Before production launch—not necessarily before the next foundation milestone—add Firestore emulator concurrency tests, IAM/Security Rules that deny bypass writes, transaction fault injection, and end-to-end outbox replay tests.

# 4. Decisions from David

No blocking decision is required if the following defaults are accepted:

1. **One linear head per account generation.** Keep the globally serialized head for correctness; revisit partitioning only as a versioned scalability change.
2. **Logical operation IDs remain head-independent.** Head-specific retries use separate attempt IDs.
3. **`skip_duplicate` is audited.** It commits and advances the head, mutates no memory, and emits projection/vector barrier events.
4. **Search is strict by default.** Index lag or integrity mismatch returns a typed retryable/degraded result rather than incomplete success.
5. **Evidence content is immutable.** Changes create a new evidence identity/version.
6. **Access is monotone restrictive.** Update, merge, or added evidence cannot automatically make memory more accessible.
7. **Deleted and purged source states are terminal.** Temporarily inactive/processing states remain retryable.
8. **Both projection and vector indexes have contiguous watermarks.** Per-hit timestamps are diagnostic only.

With those contract amendments and tests, the Milestone 3 skeleton should qualify for **PASS** and be safe to carry into Firestore integration.


8m07s · gpt-5.5-pro[browser] · ↑1.26k ↓4.12k ↻0 Δ5.39k
files=1
