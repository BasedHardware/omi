# Task export routing and push registration

These client paths reuse the saved task-integration status and authenticated
session generation. They do not add a backend contract or change provider grants.

## Routing authority

- The backend's `default_app` selects automatic exports. EventKit permission
  authorizes native access; it does not select Apple Reminders.
- Manual task creation retains the existing backend cloud-export path and its
  `skip_apple_reminders` contract. The phone's direct Apple path requires a
  fresh, connected Apple default before creating a reminder. Unknown, failed,
  disconnected or another selected destination never falls back to Apple.
- Bulk Export waits for pending default saves and resolves the saved default
  through `TaskIntegrationProvider`. Connected-app enumeration order is not a
  routing decision. A changed selection cancels the pending export; concurrent
  taps cannot start multiple exports from the same bar.
- Explicit individual exports and updates/deletion of existing linked reminders
  retain their existing behavior. This change does not move or delete historical
  tasks, create a distributed export transaction, or repair unrelated provider
  authorization failures.

## Registration ownership

`FcmTokenRegistration` owns token acquisition, accepted HTTP persistence and a
bounded retry schedule for one `AuthSessionSnapshot`. Restored authenticated
shell startup, successful notification permission, foreground resume and token
rotation all reach that owner. Auth generation changes revoke pending work; the
existing authenticated entry points admit a replacement owner. Listeners install once before
acquisition. iOS waits for APNs before requesting FCM; Android skips that wait.

Every SDK/HTTP wait has a deadline. A failed attempt keeps its retry budget;
external lifecycle/permission wakes renew it. Only an accepted token/timezone
receipt deduplicates subsequent writes. Account/generation changes invalidate
pending reads and retries, and guarded HTTP sends cannot borrow a replacement
account. Guarded HTTP responses recheck the owner before refresh or account
deletion side effects, including replay responses. Intercom remains best effort and cannot block Omi's accepted receipt.
Tokens and task contents are excluded from the new diagnostic logs.

## Verification and rollout checklist

- [x] Focused registrar, automatic export, saved-default and bulk-button tests.
- [x] Production HTTP/provider/UI flow on an isolated iOS simulator: both apps
      connected, Todoist selected, create and bulk export, zero Apple writes.
- [x] Local HTTP retry after delayed APNs and refused registration receipt.
- [ ] Repository mobile journeys, preflight, final diff and exact-head CI.
- [ ] Merge and mobile store release (no backend deployment/schema change).

The integration target `integration_test/task_notification_recovery_capture.dart`
uses the production providers, export service, HTTP codecs and AuthService
fences. Its loopback server substitutes external services; Firebase/APNs token
I/O and EventKit permission/create are fixtures. It is not proof of an actual
Todoist delivery or a real lock-screen push. Existing provider configuration is
unchanged. After release, Support separately checks the affected app version,
notification permission/Focus settings and a timestamped failed push/task for
the reported beta OS. No customer account diagnosis or delivery guarantee can
be inferred from the local test.
