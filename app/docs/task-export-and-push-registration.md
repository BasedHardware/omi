# Task export routing and push registration

These client paths reuse the saved task-integration status and authenticated
session generation. The registration request carries an optional order field.
Provider grants are unchanged.

## Routing authority

- The backend's `default_app` selects automatic exports. EventKit permission
  authorizes native access; it does not select Apple Reminders.
- Manual task creation retains the existing backend cloud-export path and its
  `skip_apple_reminders` contract. The phone's direct Apple path requires a
  fresh, connected Apple default before creating a reminder. Unknown, failed,
  disconnected or another selected destination never falls back to Apple.
  An eligible task created as completed becomes a completed Apple Reminder.
- Bulk Export waits for pending default saves and resolves the saved default
  through `TaskIntegrationProvider`. Connected-app enumeration order is not a
  routing decision. A changed selection cancels the pending export; concurrent
  taps cannot start multiple exports from the same bar.
- Cloud destination resolution does not call or wait for EventKit. An Apple
  destination still requires native permission; an unavailable status read
  offers retry instead of claiming a connected provider needs reconnecting.
- Automatic task export and explicit bulk export use the same EventKit
  identity derived from the account and task. EventKit saves the identity
  alongside the reminder. A retry finds it across readable lists, including
  completed reminders, then writes the same identifier to the backend.
  Reminders are matched by identity so existing edits and unrelated reminders
  with the same title stay intact. Concurrent exports share one lookup.
  An unavailable lookup defers export.
- The direct task-create route leaves Apple export to the phone. Native
  push-driven sync for other task sources and changes to linked reminders
  keep their existing paths.

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
The client reserves a device-local order before each registration attempt and
reuses it for transport retries. The backend compares it with the stored device
order in the same Firestore transaction that saves the token and updates the
summary timezone. A superseded request receives 409. An identical retry
acknowledges the existing write without replaying the timezone update.
Unversioned requests retain the released-client behavior.
A rotation consumed while APNs is pending satisfies the coalesced wake. Only a
later, unconsumed rotation triggers another attempt, so an unnecessary SDK read
cannot replace that accepted token with an older cached value.

## Verification and rollout checklist

- [x] Focused registrar, automatic export, saved-default and bulk-button tests.
- [x] Production HTTP/provider/UI flow on an isolated iOS simulator: both apps
      connected, Todoist selected, create and bulk export, zero Apple writes.
- [x] Local HTTP retry after delayed APNs and refused registration receipt.
- [x] Regressions for rotation during acquisition and unrelated stalled/failed
      EventKit permission; Apple still requires its own permission.
- [x] Production backend HTTP create → background automatic export → Todoist
      adapter → export marker, without FCM registration, including refused and
      disconnected providers. Token-save refusal → retry → shared push sender
      is covered separately. Storage/auth and final provider I/O are synthetic.
- [x] Loopback HTTP and Firestore proof for delayed token writes, idempotent
      retries, schedule preservation and compatibility with released clients.
- [x] `integration_test/apple_reminders_retry_test.dart` on an isolated iPhone 16
      Pro simulator with iOS 26.5 and Reminders permission. Real EventKit
      preserved the edited reminder when the loopback server withheld the
      acknowledgement after saving the task link. The task used the backend's
      completed status. Concurrent exports of distinct tasks with the same title
      also produced one reminder per task.
- [ ] Repository mobile journeys, preflight, final diff and CI for the current commit.
- [ ] Merge, then release the backend before the mobile build so that ordered
      requests are enforced. The optional Firestore field requires no backfill.

The integration target `integration_test/task_notification_recovery_capture.dart`
uses the production providers, export service, HTTP codecs and AuthService
fences. Its loopback server substitutes external services; Firebase/APNs token
I/O and EventKit permission/create are fixtures. It is not proof of an actual
Todoist delivery or a real lock-screen push. Existing provider configuration is
unchanged. After release, Support separately checks the affected app version,
notification permission/Focus settings and a timestamped failed push/task for
the reported beta OS. No customer account diagnosis or delivery guarantee can
be inferred from the local test.
