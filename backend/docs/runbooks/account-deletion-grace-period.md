# Account deletion grace period

`DELETE /v1/users/delete-account?grace=true` keeps the account's existing Firebase UID and
starts the configured grace period when the client explicitly opts in. Requests
without `grace=true` keep the existing immediate-erasure behavior, including
requests from released clients that do not have restore UI. It cancels billing,
revokes Firebase refresh tokens, and removes owner API/OAuth credentials when
the request is accepted. The `account_deletions/{uid}` marker immediately fences ordinary API,
capture, and processing access. Authentication remains enabled so the owner can
sign in to the same UID; blocked requests return
`account_pending_deletion`. The status, restore, and `erase_now` routes use a
restricted auth dependency and do not run normal account registration or
content recovery.

## Owner API

- `GET /v1/users/deletion-status` returns the current deletion status,
  `pending_deletion`, `wipe_at`, the enabled `grace_period_days` policy for a
  new deletion, and metadata-only loss counts for held audio and deferred
  processing backlog. A disabled kill switch reports zero grace days.
- `DELETE /v1/users/delete-account` accepts `{"erase_now": true}` to bypass
  the grace period, including when promoting an existing pending request.
  Grace requires the explicit `?grace=true` query parameter and a positive
  configured window; omitting it erases immediately.
- `POST /v1/users/restore-account` cancels a still-future grace marker. Restore
  changes the marker to `cancelled`, lifting the access and capture fences. The
  subscription remains cancelled, and deleted API/OAuth credentials must be
  recreated. If the deadline has passed or a wipe has been claimed, restore
  returns `409 account_deletion_not_restorable`.

The Firebase Auth user is intentionally not disabled. This keeps sign-in
available for the same UID; the durable marker supplies the pending-deletion
state and blocks every ordinary route until restore or wipe. Refresh tokens are
revoked at admission, so a client may need to sign in again before restoring.

## Configuration and execution

- `ACCOUNT_DELETION_GRACE_ENABLED` defaults to `true`. Explicit `false` is the
  global kill switch and returns even opted-in deletion requests to the
  existing immediate-wipe path.
- `ACCOUNT_DELETION_GRACE_WINDOW_DAYS` defaults to `14`; values are clamped to
  `0..365` whole days.
- `ACCOUNT_DELETION_DISPATCH_MODE=cloud_tasks` remains the production wipe
  executor. The reconciler selects `pending_deletion` markers only when
  `wipe_due_at` has passed and immediate billing/session actions are recorded
  as complete. The Cloud Tasks claim checks the same deadline transactionally.
  A restore and a due-time claim therefore have one Firestore transaction
  winner.
- The worker still acquires the existing destructive-operation gate and
  rechecks legal-hold authority before provider cleanup, owner-prefix sweeps,
  vector removal, or recursive Firestore deletion. Those gates are unchanged.

## Audio custody audit

The account wipe is the only account-wide owner-prefix erasure and now runs only
after the grace deadline. Its private-cloud prefix sweep includes
`chunks/{uid}/`, including `chunks/{uid}/cap-held/`; the separate recordings
bucket and batch-pipeline owner prefixes are removed by the same final wipe.
Held-audio manifests have no application TTL. Batch artifact retention is armed
only after successful projection completion; unfinished or failed held work has
no cleanup deadline. Completed batch artifacts may still follow their existing
completion-based retention while an account is active. User-initiated
conversation deletion and recording-permission deletion keep their existing
immediate semantics.

## Owner sign-off

The privacy policy and account-deletion confirmation copy must receive product
and privacy-owner sign-off before the user-facing rollout. The current app UI is
not changed in this backend change; it should explain the deadline, restore
option, billing cancellation, and the held/backlog counts returned by status.
