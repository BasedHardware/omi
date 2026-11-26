# Batched reads in the v3 projection commit

About 9% of `/v1/conversations-v3/reconcile` requests failed with 5xx in the
11-23 window. The projection commit transaction read each recording and existing
derived row with its own `get`, so a large owner-day held the transaction open
across many serial round trips and hit contention and deadline failures.

`commit_projection` now reads those documents in one transactional `BatchGet`
per chunk of `CLAIM_READ_CHUNK` IDs. All reads still happen before any write,
and the revision checks are unchanged. A missing or reordered snapshot in the
BatchGet response maps back to its ID.

Failures in the commit now log
`event=v3_reconcile stage=projection_commit outcome=<firestore reason> trace_id=<request trace>`,
so the next fix can be chosen by cause. `Conflict` still propagates unchanged.

See the [pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).

## Rollout and rollback

`CONVERSATIONS_V3_BATCH_COMMIT_READS` defaults to `on` on every service that
runs the v3 reconcile (`backend`, `backend-sync`, `backend-sync-backfill`). Set
it to `off` to restore the serial per-document reads. No stored data changes.

## Production readback

Reconcile non-2xx share under 1% for a full hour on the serving revision, from
Cloud Run `request_count` by response class. If it stays above 1%, group the
`stage=projection_commit` warnings by `outcome`.
