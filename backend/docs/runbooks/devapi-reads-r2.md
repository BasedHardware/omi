# Developer API / promote read cuts, round 2

Source baseline: #22127. These are code and hermetic-fixture results, not deployed
measurements. No production data, credentials, flags, backfill or deployment was
used for this work.

## Controls

All controls ship on when unset; only trimmed, case-insensitive `false` disables.
Existing auth, grants, rate limits, request budgets, response validation and
locked-row filtering execute before cache hits.

| Control | On | `false` |
| --- | --- | --- |
| `OMI_STAGED_PROMOTE_LONG_TTL_ENABLED` | Empty projection TTL 3,600 s | Previous 90 s TTL |
| `OMI_DEV_ACTION_ITEMS_VERSION_CACHE_ENABLED` | Versioned encrypted task pages, TTL 900 s | Previous 10 s cache |
| `OMI_DEV_MEMORY_ADAPTIVE_CATEGORY_SCAN_ENABLED` | Start at requested category window, grow to 500 | Previous 500-row category chunks |
| `OMI_MEMORY_INCREMENTAL_INDEX_WINDOWS_ENABLED` | Seek after last snapshot when a hidden-row window grows | Reread expanding prefixes |

`OMI_EXTERNAL_LIST_CACHE_ENABLED=false` still bypasses all response caches.
`OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED=false` still bypasses negative
caching. `OMI_EXTERNAL_LIST_METRICS_ENABLED=false` disables HTTP measurement and
the new per-request read histogram. Cache invalidation stays active when readers
are disabled, protecting enabled readers and subsequent re-enablement.

Hour-long promote markers use a separate key suffix. Disabling its long-TTL
lever immediately stops reading already stored hour-long markers and uses the
released 90-second namespace. The full empty-cache switch bypasses both.

## Task writer coverage

`database.action_item_write_fence` installs SDK commit fences from `database._client`.
The response cache imports only the pure Redis version protocol in
`database.action_item_versions`; it does not require SDK classes.
It inspects actual pending Write protobuf document paths, rather than trusting a
list of route names or a post-write callback. One version per UID covers the
entire `users/{uid}/action_items` collection. Document set/create/update and field
transforms use WriteBatch; direct document delete is separately wrapped because
it calls Commit without WriteBatch. Sync/async transaction commit, sync/async
WriteBatch, and BulkWriteBatch (BulkWriter) are covered. Each batch fences every
affected owner, including mixed-owner batches. Other collections add no Redis IO.
No Firestore query or extra Firestore write is added to mutations. The small
`database.redis_connection` module shares connection settings without importing
product database helpers at SDK bootstrap. The slim batch-worker lock adds the
same pinned Redis client so SDK fence installation has its dependency there too.

Serving writer audit (direct and dynamic collection references):

- `database/action_items.py`: CRUD, conditional channel undo, multi-item updates,
  Reminder sync, soft/hard deletion, conversation retirement, unlock.
- `database/action_item_refresh.py`: automatic refresh/donor reconciliation,
  completion carry and delivery bookkeeping; shared live/sync/background caller.
- `database/candidates.py`: atomic Candidate acceptance creates or updates tasks
  without calling the ordinary CRUD helpers.
- `database/staged_tasks.py`: legacy recovery directly creates task documents.
- `database/goals.py`: unlink task goal references.
- `database/review_changes.py`, `chat_edits.py`: dynamic collection journal
  mutations and exact undo/redo, including deletion of a formerly absent field.
- `database/user_data_deletion.py` / `_client.delete_collection_recursive`:
  enumerated subcollections and recursive account deletion.
- `utils/task_intelligence/chat_first_e2e_fixture.py`: synthetic fixture resets.
- Standalone `migrations/004_migrate_action_items_to_collection.py`: now explicitly
  installs the same SDK fences before constructing its Firebase client.

`action_item_sync`, `summary_tasks`, task recommendation/context readers and
vector backfills read task rows; they do not mutate the task collection. The SDK
boundary also covers new writers using the same SDK, dynamic document references,
and later clients constructed after installation. It is tested with real SDK
DocumentReference, batches, transactions and async counterparts, with fake RPCs
and real Lua execution in fakeredis. This caught the direct-delete bypass.

Redis versions use random tokens with a seven-day TTL; missing/evicted metadata
cannot alias a previously cached version. Begin publishes a persistent busy
fence and a writer ticket; completion rotates only after all overlapping writers
finish. Unconfirmed tickets poison caching. Commit exceptions also invalidate,
since BulkWrite may partially apply and a failed RPC reply can be ambiguous.
Readers bypass during busy/unavailable states and recheck versions on hits and
before background population. A late old fill can only address its old key.
Bodies retain AES-GCM encryption, authenticated opaque keys, owner/auth/query
isolation, query-start deadlines, size limits and bounded population admission.

A process death after `begin`, or cancellation before `finish`, can orphan a
writer ticket. That user then remains uncached even after later confirmed writes.
This is intentional fail-closed behavior shared with promote, not an automatic
lease: expiring an uncertain ticket could release a still-running durable write.
Do not add a writer-hash TTL as recovery. Any separately authorized operator
repair must first quiesce and resolve all affected writers, discard their cached
entries, then reset the fence metadata together. No such repair was run here.

As with the existing promote fence, immediate invalidation depends on Redis
confirming a pre-write fence. A total Redis outage spanning both begin and end,
Redis metadata loss, or an older/external writer can leave a previously published
entry until its original deadline. This is an availability cache, not durable
mutation authority. Ship all task producers together on the two-lane train;
use the version-cache kill switch for an older-writer rollback or if strict
freshness through Redis outages is required. This PR does not flip that switch.

## Routes kept at ten seconds

Developer memories and conversations retain their existing ten-second cache.
A parent-document version alone cannot safely authorize a longer result cache:

- Memories merge `memories`, `memory_items`, historical suppression overrides,
  pending processing/admission and lifecycle visibility. Ledger apply, background
  maintenance, privacy purge, review undo, source retraction, sync/postprocess and
  migration writers affect those inputs. Time-based visibility also changes
  without a collection write.
- Conversations include content from sync assignment/finalization, batch
  projection, listen, transcript review, source deletion, folder/starred changes,
  unlock, and auxiliary people/folder rendering. Relevant direct writers include
  `conversation_mutations`, `batch_pipeline_projection`, `batch_pipeline_store`,
  `sync/assignment`, `processing_attention`, `review_transcript_changes`,
  `folders`, `screen_frames`, and account deletion. Parent-only invalidation
  misses auxiliary-name changes. A safe long cache needs that complete dependency
  contract and producer rollout, beyond a task collection commit fence.

No aggregate cache savings are claimed for these routes. Their read reductions
below are independent of response caching.

## Why a request costs about 1,100 reads

The default Developer task page is 100 rows. If explicit active rows do not fill
it, a single missing/null `completed` row makes the legacy path read up to 800
candidates. It then reads the completed bucket with 32 deleted-row slack. The
fixture with two legacy active rows and 900 completed rows reads 932 documents /
aggregation equivalents to return 100 rows. Explicit `completed` filters exclude
missing/null rows, so removing that scan without repairing data loses tasks.
The slack also participates in the released final product sort; simply deleting
it can change which due-dated rows make a page. This PR preserves that order.

`backfill_action_item_completion.py` is an explicit-user, at-most-400-row,
resumable operator tool, dry-run by default. It stamps only missing/null
`completed` using the existing read normalizer, with snapshot update-time
preconditions. It preserves concurrent edits and reports conflicts. It never
runs from an HTTP read, never stamps content/timestamps, and was not run on prod.
The same fixture then reads 134 with identical rows (85.6% cold-read reduction).
The existing cheap aggregation probe remains authoritative: a later legacy
restore re-enables the compatibility scan. A permanent migrated marker is not
trusted because exact undo/recovery can restore absent fields. After an approved
operator sweep, repeat from the beginning until conflicts are zero; sparse late
legacy writes remain visible even before the next sweep.

Example **only after separately authorized account-data access**, with an agent
GCP tier selected by the operator:

```sh
python scripts/backfill_action_item_completion.py --uid "$TASK_OWNER" --limit 400
# --apply explicitly writes one page; --cursor resumes the returned next_cursor.
```

For memory categories the old helper requested 500 merged rows even for a
26-row lookahead page. Each historical candidate can incur two index reads,
canonical and override status lookups, plus full-doc hydration. A dense-category
fixture (half its rows missing `updated_at`) reads 2,250 for 26 returned rows.
The adaptive path reads 130 with identical rows (94.2% lower). The entire sparse
category loop is now one admitted MemoryService read, sharing the same request
budget and provider evidence. Repeated internal windows must not exhaust the
two whole-operation attempt allowance. Sparse categories still grow until the
page fills, the source ends, or the existing 5,000 window/budget is exhausted.

Hidden historical rows formerly caused each index window to reread its entire
prefix. Snapshot `start_after` now reads only the suffix needed to grow it. Both
`updated_at` and `created_at` windows remain, including legacy missing fields,
visibility filtering, final merge and stable ordering. The mixed canonical /
historical fixture reads 84 instead of 124 (32.3% lower), with identical rows.
Canonical identity and suppression checks remain authoritative.

Date-bounded callers keep the released expanding-prefix query shape: Firestore
SDK snapshot cursors can normalize additional inequality order fields there.
The Developer/MemoryService windows optimized here do not pass date bounds.

## Measurement and modeled savings

`omi_external_list_firestore_reads_per_request{route}` is a histogram over the
existing SDK read-trace amounts. It includes auth/dependency reads, missing
lookups, aggregation billing equivalents, empty-query floors and offsets. It
uses a fresh shared holder per ASGI request so sync dependencies and executor
context copies charge one request. The holder closes at the final response
body; detached workers and BackgroundTasks cannot inflate a completed request.
It includes zero-read hits and failures. Only the five fixed list/promote paths
are labeled, never UID/query/key. The existing `omi_.*` GMP exporter includes it.

```promql
sum by (route) (rate(omi_external_list_firestore_reads_per_request_sum[15m]))
/ sum by (route) (rate(omi_external_list_firestore_reads_per_request_count[15m]))
histogram_quantile(0.95, sum by (route, le) (rate(omi_external_list_firestore_reads_per_request_bucket[15m])))
```

The supplied post-#22127 read/day figures are baseline inputs, not re-measured
here. At stable 60-second polls, unchanged query/auth/owner, no writes, no
concurrent misses, healthy Redis and eligible response sizes:

| Route | Model | Conditional reduction |
| --- | --- | --- |
| Action items | One origin per 15 polls instead of every poll | 93.3% list reads; up to 41.2M of supplied 44.1M/day before auth, churn and eligibility |
| Memories | Dense-category fixture 2,250 → 130; hidden-window fixture 124 → 84 | 94.2% and 32.3% for those fixtures; aggregate unknown until category/offset distribution is measured |
| Conversations | Retains ten-second TTL and existing reader | 0% claimed |
| Promote | One origin per 60 polls, each other call still reads its control fence | With R=330: `1 + (R-1)/60 = 6.48` reads/call versus supplied ~160; 95.9%, up to 31.6M of 32.9M/day conditional on stable empties |

The action-item backfill reduction is additional cold-miss work reduction, not
added arithmetically to cache savings. No backfill savings are realized until
an authorized sweep runs. Empty frequency, writer/query churn, auth reads,
concurrency, large responses and Redis faults reduce the cache forecast. Do not
apply fixture percentages to all 18.7M memory reads/day. Verify the running
release identity and this histogram after the train deploys before calling any
of these deployed savings.
