# Firestore write attribution

`database/firestore_write_probe.py` counts billed-equivalent Firestore writes
for every process that imports `database/_client.py`. It is the write-side
twin of the read probe (`firestore-read-attribution.md`). Before it, the only
write signal was `firestore.googleapis.com/document/write_count`, labelled by
`op` alone, and Firestore data-access audit logs are off, so the write bill
(about $57/day on 2026-10-30, 41M writes/day) had no collection or caller
dimension.

The probe wraps the transport methods `FirestoreClient.commit` and
`batch_write` (sync and async). Every SDK write path reaches one of them, and
the request is counted as sent, so writes that commit-boundary patches append
(list-projection rows and versions, memory change heads) are counted under
their own collections. `database._client` installs the probe before those
patches.

| Counter | Labels |
|---|---|
| `omi_firestore_billed_writes_total` | `collection`, `op`, `database` (`default` / `named`) |
| `omi_firestore_billed_writes_by_caller_total` | `collection`, `op`, `caller` |
| `omi_firestore_billed_writes_by_origin_total` | `origin`, `collection`, `op` |
| `omi_firestore_write_caller_label_overflow_total` | none |
| `omi_firestore_ambiguous_commit_writes_total` | none |
| `omi_firestore_noop_writes_by_caller_total` | `collection`, `caller` |

`op` is `create`, `update` (exists or last-update-time precondition: `update()`), `merge` (mask,
no precondition: `set(merge=True)`), `set` (whole-document replace), `delete`
or `transform` on the aggregate counter. The caller and origin counters
report merge as `set` and transform as `update`. A failed Commit counts nothing.
BatchWrite counts only writes
with an OK status. A Commit that fails with DeadlineExceeded or Unavailable
may still have applied; its writes go to the ambiguous counter. Collection patterns
reuse the read probe's allowlist and callers share its per-process limit of 1536.
BulkWriter captures caller and origin as each operation is queued, including
operations flushed from another thread or retried by the SDK. Companion writes
appended by Omi's commit wrappers use the submitting caller and origin when the
batch has one submitter, and `other`/`unset` in mixed batches.

Listen and pusher include both attribution counters in their fast GMP scrape.
The worker exports them through its custom metrics registry. Cloud Run sync
and projection pump permit both families. The probe installs by default.
`FIRESTORE_WRITE_PROBE_ENABLED=false` skips installation at process startup.
The legacy `OMI_FIRESTORE_WRITE_PROBE_ENABLED=false` setting also disables it.

A no-op write (Cloud Monitoring `UPDATE_NOOP`) is still billed. Firestore
returns the document's previous `update_time` for a write that changed nothing,
so a Commit result whose `update_time` is earlier than the response
`commit_time` is counted on the no-op counter. BatchWrite has no commit time
and is not classified. The counter is a lower bound: a second write to the same
document in one Commit reports this commit as its previous time whether or not
it changed anything, so such no-ops are not counted.

```promql
# No-op writers (billed, changed nothing)
topk(25, sum by (job, caller, collection) (rate(omi_firestore_noop_writes_by_caller_total[1h])))

# Writes per second by collection and op
sum by (collection, op) (rate(omi_firestore_billed_writes_total[30m]))

# Top write call sites
topk(25, sum by (job, caller, collection, op) (rate(omi_firestore_billed_writes_by_caller_total[1h])))

# Coverage against Cloud Monitoring (UPDATE + UPDATE_NOOP + CREATE + DELETE)
sum(rate(omi_firestore_billed_writes_total{database="default"}[30m]))
/
(avg_over_time(sum(avg by (op) (stackdriver_firestore_instance_firestore_googleapis_com_document_write_count))[30m:1m]) / 60)
```
