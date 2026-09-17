# Capture ownership — C1 / C2

Contract, not an implementation. Builder: App core. Protected acceptance:
`app/test/spine/c1_*`; run `TZ=UTC bash app/test.sh`. Remove only pending markers.
Evidence: WAL races `edc8683e80`, `97ec3d9cea`; FGS race `9495f70852`;
late callbacks `05c43c014d`, `348d5f31dc`; persistence race `ff90d5988f`.

## Decisions (answers to the consuming lane's ten questions)

1. **Recovery.** One constructed `RecordingTransferCoordinator` owns reconcile,
   discover and drain. `CaptureSessionOwner` alone submits external wakes through
   an injected coordinator; callers get only `CaptureRecoveryRequests`.
   SyncProvider startup/retry/cooldown, DeviceProvider connect, CaptureController
   finalize, SyncReconciler foreground/cooldown, and auto-sync page become
   `requestRecovery(trigger)`. UI `syncWal` submits an intent, never drains beside
   recovery. Coordinator-internal retry/connectivity stays internal. Concurrent
   requests for the same inventory wave join one future/drain; a subsequent
   request after completion runs again. A newly discovered WAL during a pass is
   a new inventory revision, requiring a serial next pass, not a dropped wake.
   `requestRecovery(trigger, inventoryRevision: n)` carries the account-local
   monotonic WAL discovery revision; same/absent revision joins the current wave,
   a higher revision queues one serial pass. Discovery owns that number, not UI.
   Preserve userRetry's auto-upload bypass when coalescing, including a retry
   arriving during a disabled-auto-upload pass; do not disable recovery.
2. **FGS.** `CaptureSessionOwner` is the sole start/stop actor, using injected
   effects wrapping ForegroundUtil. Home and capture only update capture/permission
   intent. Location permission alone is not a hold. Preserve BLE/phone keepalive
   eligibility; do not redesign native PhoneMicForegroundService or MicArbiter.
   Latest desired hold wins: false during pending start waits for start, then
   stops exactly once. Errors propagate; retry remains possible. iOS cleanup is
   an explicit composition-owned cleanup, not Home starting an Android hold.
3. **Exemplar.** Real `CaptureProvider` **and** its base controller. The required
   dependency aggregate is forwarded intact by `composeCaptureProvider`; no
   subclass that replaces production decisions. Production uses this same path.
4. **Seams.** Socket factory, FGS effects, BleBridge, preferences, connectivity,
   auth, WAL, mic, clock, scheduling, location, codec, permissions, segment store,
   telemetry, device connection lookup and analytics are mandatory dependencies of explicit construction. Reuse
   `capture_seams.dart` (the memo's “CaptureSeams”, not a new service locator).
   SharedPreferencesUtil/BleBridge are initially injected as their existing types;
   narrow interfaces can follow, without a parallel preference store. Production
   defaults move to `composeProductionCaptureProvider` alone, which refuses
   `FLUTTER_TEST` **before** resolving any singleton. Controller/provider may not
   retain a no-argument path to ConnectivityService. Migrate existing tests to
   explicit seams in the builder PR; never probe that old default path.
5. **Generation.** One `_sessionGeneration` owned by CaptureSessionOwner; bump
   synchronously on stop, dispose, auth identity roll, source/device replacement,
   and a new session even if the device/uid is unchanged (ABA). Native mic session
   id and recording telemetry id remain correlation IDs, not alternative fences.
   Replace controller websocket/location validity counters with this token;
   connection configuration revision can supersede an attempt within a session.
   Idiom: capture token before await, check `isCurrent(token)` after **each** await
   before mutation/effect, including error/finally branches. Check codec before
   STT decision and socket open, auth refresh before reconnect, location permission/
   fix before upload and upload before WAL publication, pending finalize before
   recovery request, queued segment write before `replaceSession` and before
   changing its fingerprint on completion. Check again between chained awaits.
   Never undo an issued write: bind uploads and durable writes to their original
   uid/session; an old write may finish in its old slot but cannot affect current
   UI, credentials, or another account. Already admitted WAL recovery persists
   across capture stop; account change retires the account-owned coordinator.
6. **Overlap.** Same generation/config joins one connect future (including ticks,
   connectivity, and explicit start). Different config supersedes the result;
   close a late socket once. Logical cancellation does not claim OS cancellation.
   Stop invalidates before awaiting native teardown. Do not use “force” to create
   another actor or publish a stale socket.
7. **Scope.** SyncProvider and DeviceProvider are C2, not simultaneous exemplar
   rewrites. C1 moves request/act boundaries in tiny dependent PRs; coordinator
   configuration moves out of SyncProvider to composition when its fan-out lands.
8. **Ratchet.** `app/contracts/capture/boundary-baseline.json` covers capture files,
   capture/sync/device/memories providers, local_wal_sync and foreground.dart;
   `.instance.wake(` is checked throughout app/lib. Only changed files pay debt.
   No baseline growth or reintroduction after removal. Composition is the sole
   explicit global-read exception, never a wake exception. This lexical scanner
   ignores strings/comments; aliases, dynamic calls and wrappers can evade it;
   unrelated same-named methods can be false positives. It is a tripwire, not
   behavioral coverage. Protected adoption tripwires additionally require zero
   exemplar global reads, zero singleton wakes, and no Home/controller FGS acts
   before C1 is complete. New rules require spine review, not baseline inflation.
9. **Tests/dispose.** Keep CaptureReplayWorld's WAL/mic/socket fakes; extend its
   production composition path instead of duplicating it. Also retain the
   isolated constructor test with no initialized globals. Each owner has one
   CaptureLifetime: timer factories, stream subscriptions, listener removals and
   late acquisitions register immediately; close invalidates first, cancels all
   even if one removal fails, and is idempotent. Raw acquisitions cannot grow
   under the ratchet. The scheduler's full outstanding-resource inventory, not
   a list of known timer fields, must be empty after teardown. Integration tests
   use the real provider so a working but disconnected owner is insufficient.
10. **Initialization.** SyncProvider may not report ready after failed refresh.
    Its C2 init future must expose failed/ready separately, with a retry that
    converges; retain last-known data and never swallow into initialized=true.

## Small PRs, extraction and fan-out

Extract `capture_session_owner.dart` (generation/recovery request/FGS/connect
arbitration), `capture_lifetime.dart` (resource cleanup), `capture_composition.dart`
(dependencies/default wiring); move socket setup to `capture_socket_session.dart`
and location/segment persistence to `capture_session_persistence.dart` as their
migration PRs land. Keep BLE/WAL/mic processing in the controller initially.
Each extraction must reduce its 2,710 lines; C5's eventual 1,500-line baseline is
not permission to grow. Sequence: explicit composition/forwarding, disposal,
socket+generation, persistence fencing, recovery request migration, FGS ownership.
Each is a behavior-preserving PR sized to merge within hours, with relevant
markers removed only when tests pass. Do not hold the hot file across a giant PR.

C2 order: **sync_provider.dart → device_provider.dart → local_wal_sync.dart →
memories_provider.dart**. These close the ownership loop before expanding to
another provider; main/Home only wire/request, API error handling is C3, chat's
layout heat does not justify capture DI there. Per-file done: real production
class constructs with required fake dependencies and no global initialization;
pause each async dependency, roll identity/dispose, release it, assert zero stale
writes plus a successful current-generation control; concurrent intents cannot
multiply the owned effect; all tracked resources cancel; initialization failure
is observable and retry recovers; singleton debt in that file reaches zero
(composition excluded), journeys unchanged. Instantiate this template as builder
regressions in addition to the immutable spine suite.

Settings/plans/payments may reuse generation checks for stale rollback and
explicit loading/error states. Their context-after-await class is already linted;
C1 adds no FGS/WAL ownership or new scope to that tree.
