# V3 reconcile retries and processing declines

SCA-2918. The [reconcile HTTP contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
covers the Cloud Tasks target on backend-sync.

Each affected Firestore transaction can start up to three fresh attempts with jitter. A 45-second
retry budget and duration reserve limit when a subsequent attempt can start. Rollback and lease
cleanup preserve a propagating primary error. Projection commits batch revision, tombstone, and
new-target reads, and split pointer-backed outputs at the shared transcript preload limit.
Source, deletion, privacy, and custody checks run again on every attempt. The writer context
keeps the first persistence outcome for its leased conversation, including success, so a
synchronous nested notes refresh cannot replace it.

| HTTP 409 reason | `omi_conversations_v3_races_total` reason | Condition |
| --- | --- | --- |
| `dependency_warming` | `transaction_contention` | Fresh attempts exhausted on atomic Firestore contention |
| `dependency_warming` | `transaction_expired` | Fresh attempts exhausted on a retired transaction |
| `dependency_warming` | `transaction_retry_deadline` | Retry deadline or duration reserve exhausted |
| `persistence_fenced` | `processing_source_changed` | Processing settlement lost its source or lease |
| `persistence_fenced` | `v3_processing_not_completed` | Notes persistence refused an old summary lease or transcript revision |

`CONVERSATIONS_V3_RECONCILE_RETRY_RESPONSE` defaults to on. Set it to `off` on backend-sync
to restore the prior HTTP error mapping. The switch affects those 409 responses. Transaction
retries, decline settlement, and the provider-specific response follow their existing controls.

A terminal decline settles the exact declined document version as skipped when its summary lease and
processing obligation still match. This covers deletion, stale capture-group authority, superseded
repair revisions, and protected manual titles. Missing rows and foreign finalization generations
are outside the writer's custody. Successful skips record
`omi_conversations_v3_reconciles_total{outcome="processing_skipped_<reason>"}` after commit.
The sweeper sees the cleared pending marker.

Changes in processing ownership, same-revision repair eligibility, smart-merge authority, or transcript
identity membership can recover on a new attempt. Live work stays pending with a row-local
`v3_process_retry_after` timestamp. Owner drain, transaction admission, and sweep honor the
15-minute cooldown. Owner drain walks up to four document-ID-ordered pages of 128 pending
rows, with at most 512 fetched documents and 128 due results per scan. The first page stays
sufficient when every row is due. The existing attempt budget still applies. Backfill uses its
own continuation.

The [Firestore emulator suite](../../../tests/integration/test_conversations_v3_sync_custody_firestore.py)
covers new transaction IDs, custody, pointer batch splitting, terminal skips, transient cooldown, and
a newer obligation replacing a declined version. The [route suite](../../../tests/unit/test_conversations_v3_tasks_retryable.py)
covers the switch, HTTP classes, and counters. Production acceptance uses a full hour on the serving
backend-sync revision with reconcile 5xx below 1%, committed reconcile throughput at or above the
comparable baseline, and retries reported by class.
