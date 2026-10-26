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

One privacy denial is answered terminally. When the conversation walk finds a
conversation the user deleted (tombstone, or a user soft-delete without a
server redirect), the content was already processed and the deletion is final:
the route answers `completed` with an empty result and
`reason_code: conversation_deleted`. Before this, it answered 404, and the phone
re-uploaded the deleted audio as a new WAL. No conversation ID is echoed.
Account, protection and generation denials, redirect anomalies and recording
privacy changes keep the pre-reconciliation response.

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

## Archival acknowledgement of expiry-retired handles

The Oct 15–17 expiry path removed accepted legacy jobs without processing them.
Their bytes are restored and held in custody, but the phone polls the dead
handles forever: it confirms a 404 only with a second 404 five minutes later in
the same process, and a large dead backlog never reaches it. That poll budget
also starves status checks for new uploads.

After Redis and durable-completion reconciliation both decline, the route reads
`sync_retired_handles/{handle}` (`uid`, `job_id`, `content_id`, `campaign`) and
the admission `sync_retired_handle_owners/{uid}` (`enabled: true`). An exact
owner and handle match, together with the account fence, returns `completed`
with an empty result and `reason_code: sync_retired_preserved`. That is the
only status released apps treat as terminal without retrying: `failed`
re-uploads and an unknown status polls forever.

- The phone marks the WAL `synced` and deletes its local copy after
  `autoRemoveSyncedCopiesDays` (default 30). Keep custody holds at least that
  long after the acknowledgement.
- No ledger, Redis or hold mutation is made, so the content stays `retryable`
  for an operator redrive.
- A real completion found later through the paths above always wins.

Rollout: an operator writes the handle records and admits owners one at a
time. Rollback: delete the owner admission, or set
`SYNC_RETIRED_HANDLE_ACK_ENABLED=false`. Lookup errors fail open to the 404.
Contract: `backend/tests/unit/test_sync_retired_handle_ack.py`.
