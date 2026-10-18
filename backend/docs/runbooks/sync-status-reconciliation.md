# Durable completion in legacy sync polling

`GET /v2/sync-local-files/{job_id}` retains its released-client response shape.
`bp_` handles already use the durable batch intake. Legacy handles normally use
Redis; an expired Redis execution record is not evidence of unfinished content.

`SYNC_DURABLE_STATUS_RECONCILIATION` defaults to `false`. When enabled, a
non-completed/missing legacy execution record can return `completed` from a
validated durable content receipt. The association must be proved by either:

- the authenticated Redis job's immutable `content_id`;
- the original `sync_redrive_required` custody record's owner, job and content;
- exactly one ledger record with the requested job ID, scoped to the caller.

The read transaction validates the all-success result and current account,
protection and conversation privacy fences. It returns the **requested** job ID,
even if a redrive finished that content under a different handle. Empty/silence
results and results updating an existing conversation are valid completions.
No Redis, ledger, lease, audio or conversation mutation occurs. Read/fence errors
return retryable 503 rather than a missing-job response. Existing completed Redis
responses bypass the extra reads. A recovered lookup emits shared fallback
telemetry from `redis_status` to `durable_completion` without customer labels.

This does not infer success from age, an empty queue, a discard or a missing
conversation. Invalid, held and failed receipts keep the legacy behavior. If an
old handle has lost **all** associations after redrive, it remains unknown: the
client's confirmed-404 retained-audio recovery still owns it. Restoring such an
association requires separately reviewed custody evidence, never timestamp
matching or declaring an expired job successful.

Before enabling, measure the added Firestore reads for outstanding legacy polls,
then canary completed-empty, merged-target, redriven and expired-handle cases on
a retained test WAL. Confirm that the phone changes `uploaded` to `synced`, while
unknown/failed/held audio remains retained. Rollback is setting the flag to
`false`; this read-only path has no stored state to undo. Deployment and flag
changes require their own authorization.

Regression contract: `backend/tests/unit/test_sync_completed_status.py` exercises
the actual HTTP route with isolated Redis and strict Firestore transactions.
