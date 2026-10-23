# Firestore quick reads

These structural optimizations default on. Set the corresponding environment
key to `off` to restore the prior read path. The reads loop owns measurement;
the brief's 10.5M/8M/1M/3M reads/day predictions are not measured savings.

| Key | Scope | Origin |
| --- | --- | --- |
| `FSR_SMART_MERGE_PARTITION` | Unbounded smart-merge discarded-barrier scan for explicit devices | `task:smart_merge_partition_lookup` |
| `FSR_KG_CITATION_INDEX` | Reverse-citation node lookup during KG pruning | `task:kg_citation_prune` |
| `FSR_PUBLIC_CATALOG_CACHE` | Public catalog base shared by search and list variants | `task:public_app_catalog` |
| `FSR_COHORT_REQUEST_CACHE` | Membership snapshots inside an existing request scope, at most 64 users | `task:cohort_membership_lookup` |

## Index gate

The release lead must reconcile `firestore.indexes.json` before deploying and
verify the registered `conversations_smart_merge_device_preceding` composite is
READY. The lead uses the existing `backend/scripts/reconcile_firestore_indexes.py`
workflow with the authorized operator identity. This lane performs no cloud writes.
While the new index is missing or building, a missing-index `FailedPrecondition`
falls back to the old query and records shared fallback telemetry. Other errors
propagate. Both attempts retain the caller's transaction.

The finite predecessor query still uses the global six-row window: partitioning
before that limit would admit a predecessor beyond the original window. Missing
or empty device IDs retain the old scan so absent fields remain visible. Discarded
barriers stay unbounded and deleted barriers still count.

## KG coverage and remaining work

Firestore's native `memory_ids` array index is the reverse-citation writer: it
updates atomically with existing node writes, including citation unions, and
Firestore backfills historical documents before the index serves queries. There
is no separate citation collection whose empty result could hide unindexed data.
Chunks of at most 30 memory IDs are fully materialized and deduplicated before
mutations. A missing index returns to the old scan before any write.

The global surviving-node and edge scans remain because the old operation also
removes unrelated pre-existing dangling edges. Replacing them with only native
`source_id`/`target_id` adjacency queries requires a separately proven global
orphan-cleanup contract and coverage protocol. This release therefore reduces
the initial node scan only; it does not claim the full P8 adjacency prediction.
No canonical-memory or deletion/hold authority is changed.

## Cache bounds

The public catalog uses one existing cache/invalidation key, a process single-flight
with 30-second TTL and the existing 600-second Redis backing. Disabling this
optimization restores Redis read-through. Empty lists are hits;
the shared raw catalog is copied before enrichment. Private/user app slices and
authorization reads retain their existing paths. Pub/sub initialization is
serialized so simultaneous first requests share one cache. Single-flight is
per process; Redis shares completed values across processes.

The cohort snapshot adds no cross-request lifetime. It wraps the existing
60-second process cache, stores successful membership maps only, and clears on
request teardown. Fresh-read scopes and the kill switch bypass request reuse.
Predicates, environment fallbacks and fail-closed unavailable behavior still run
at each check. Long-lived background contexts cannot reuse a closed holder.

## Grading

Compare absolute caller totals as well as origins. The SDK probe attributes the
new inner collector to `smart_merge:collect` (including the unchanged finite
window) and indexed node lookups to `knowledge_graph:_citation_nodes`; the
remaining graph sweeps stay under `knowledge_graph:prune_memory_citations_from_kg`.
Grade those callers together against the old `smart_merge:find_preceding_conversations`
and `knowledge_graph:prune_memory_citations_from_kg` baselines. Count new origins
together with the old callers so relabelling cannot look like savings. Fleet
savings require complete service coverage and billing confirmation.
