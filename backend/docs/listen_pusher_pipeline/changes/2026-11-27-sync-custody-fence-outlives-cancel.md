# Sync custody fence belongs to the storage work (SCA-3748)

Serve-cohort `/v2/sync-local-files` uploads hold a `custody:<job_id>` token in
`record_upload_sessions` while their original audio is archived. Pusher's seal
refuses with `producer_pending` while any token remains.

Before this change, cancelling the request (client disconnect, request timeout,
shutdown) ran the wrapper's `finish(accepted=False)` at once. A started
`sync_executor` archive worker, or a `storage_executor` late-WAL retained-copy
worker, kept writing, so the token could clear, Pusher could seal at the
unchanged revision, and the audio could commit after the seal.

Invariant: the fence's lifetime belongs to the storage work, not to the
request. The phone is never ACKed without durable custody, and the receipt and
revision reflect durable storage.

- Every fenced step (`begin`, each per-file archive, its renewal, the
  `retain_upload` chunk writes) runs on its executor thread to its real outcome.
  Cancelling the request abandons only a step that has not started.
- Only one worker-side completion releases the token. It runs on `db_executor`
  once the request has closed the fence and every started step has settled.
  It removes the route's temp files first (the workers own them), then runs
  `finish`. A live request accepts what its response acknowledged, as before.
  A cancelled request records what storage durably committed: if a file
  committed, `accepted=True` and the revision bump are correct, because the
  phone got no ACK and retries idempotently against create-only objects.
- A live request waits for that completion and answers from its real outcome,
  so it never returns 503 over an accepted receipt. A cancelled request never
  awaits again, so repeated or AnyIO scope cancellation cannot interrupt it.
- Every fenced storage commit starts within `CUSTODY_STORAGE_BUDGET_SECONDS`
  (900 s) of begin and is bounded by the storage client's timeout and retry
  deadline (`CUSTODY_WRITE_SECONDS`, 60 s). Their sum stays well under half the
  custody lease (3900 s), so if the process dies before completion, the token
  waits for lease expiry and repair, and no live writer can outlast it.
- An ambiguous `begin` whose retry sees opt-out or an ineligible row writes
  nothing. Its committed token expires on its lease. That delays the seal by at
  most one lease, with no privacy-blocked write.

`RECORD_TOKEN_LEASE_MODE=off`, `shadow` and serve 0% do not reach the fenced
path; the route's cleanup and every storage call stay as they were. No new
environment variable or data migration.
