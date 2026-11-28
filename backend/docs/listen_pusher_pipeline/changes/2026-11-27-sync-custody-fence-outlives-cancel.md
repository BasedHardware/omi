# Sync custody fence outlives a cancelled archive (SCA-3748)

Serve-cohort `/v2/sync-local-files` uploads hold a `custody:<job_id>` token in
`record_upload_sessions` while their original audio is archived. Pusher's seal
refuses with `producer_pending` while any token remains.

Before this change, cancelling the request (client disconnect, request timeout,
shutdown) ran the wrapper's `finish(accepted=False)` at once. A started
`sync_executor` archive worker kept writing to GCS, so the token could clear,
Pusher could seal at the unchanged revision, and the audio could commit after
the seal. A queued `finish` that was cancelled at shutdown never ran, leaving its
token until lease expiry. A `begin` whose committed reply was lost, and whose
retry then saw opt-out or an ineligible row, returned `False` and stranded its
own token.

Now:

- Each fenced step (`begin`, each per-file archive, its renewal, `finish`)
  settles on its worker thread. A cancelled request abandons a step that has not
  started and waits, through repeated asyncio or AnyIO cancellation, for a
  started one. Only then do temp-file cleanup and `finish` run. The original
  cancellation is re-raised.
- `finish` reads cancellation as it starts. A request cancelled before `finish`
  ran is never an accepted receipt and never bumps the revision.
- If a step outlives the custody lease, or teardown cancels the queued
  `finish`, the token stays for lease expiry and repair. It is never cleared
  early.
- `begin` checks this request's exact token before its opt-out and eligibility
  refusals, and removes it in the same transaction under the refusal path's
  existing authority check. A cancelled or failed `begin` keeps its candidate
  token separate from confirmed ownership, and it is reconciled after settlement.

The contract is unchanged. `RECORD_TOKEN_LEASE_MODE=off`, `shadow` and serve 0%
do not reach the fenced path. No new environment variable or data migration.
