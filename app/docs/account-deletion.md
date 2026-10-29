# Account deletion safety

The mobile client reads `GET /v1/users/deletion-status` at authenticated entry
and again at deletion confirmation. The backend owns the policy. Optional fields:

- `pending_deletion`: show the restore decision before constructing product UI.
- `wipe_at`: ISO-8601 deadline; whole remaining days are rounded down.
- `grace_period_days` (also accepts `grace_days`): pre-delete policy duration.
  Omit or return zero when the backend cannot honor a grace window.
- `loss_summary.held_recordings` and `loss_summary.backlog_conversations`:
  server-held counts shown together as recordings still processing.

Before deletion, the backend reports the enabled policy duration as
`grace_period_days`; the new flow opts in with `DELETE /v1/users/delete-account?grace=true`.
Clients that omit the query parameter keep immediate erasure, preserving the
behavior of released apps without restore UI. A missing or zero policy duration
uses immediate-deletion copy. No client constant supplies a duration. A missing
deadline on a pending account does not imply time remaining; restoration remains
a server decision.

A 404/405 status endpoint permits legacy sign-in, with a bounded fallback event.
Other status errors offer Retry. A transport outage preserves offline startup only for the same cached, onboarded owner and never for an owner already confirmed pending deletion; this fallback grants no grace window. Deletion confirmation
can still use local WAL evidence and immediate-loss copy if policy lookup fails;
if the local inventory itself cannot be read, confirmation requires Retry.

Local loss counts require the current UID and phone storage. Uploaded and synced
WALs are excluded: an uploaded file awaiting server processing is not phone-only.
Unknown/foreign ownership is excluded, as are unreadable/corrupt or server-rejected
unsupported audio. Server-held recordings get immediate-loss warnings only without
a reported grace window. Phone-only recordings always warn of loss on deletion.

The backend DELETE route uses authenticated, owner-only deletion access so a
pending owner can finish erasing without reopening ordinary product writes.

`POST /v1/users/restore-account` must return `restored: true` before the app resumes.
Restoration restarts shell initialization and rechecks status. It does not restart
billing or reconnect revoked integrations. Finish deleting first reveals a second
explicit destructive confirmation, then uses `DELETE /v1/users/delete-account`
with `erase_now: true`; failure leaves the decision visible. Accepted deletion
uses the same UID-scoped local purge and session cleanup as normal account deletion.

Pause Omi calls the existing capture pause and device-off paths, waits for them,
then exits the deletion flow with confirmation. Sign-in and billing remain intact;
Continue Deleting proceeds to feedback and typed confirmation.

Verification is hermetic: `test/widgets/deletion_safety_test.dart` and
`test/unit/backend/http/deletion_contract_test.dart`. The render harness and PNGs
are copied into the PR's UI evidence directory; no real deletion is invoked.
