# Capture ownership — C1 / C2

Builder: App core. Contract skeletons change no behavior. Protected acceptance:
`app/test/spine/c1_*`; run `TZ=UTC bash app/test.sh`; retire markers only.
Evidence: recovery `edc8683e80`, `97ec3d9cea`; FGS `9495f70852`; stale callbacks
`05c43c014d`, `348d5f31dc`; persistence `ff90d5988f`.

## Decisions (the consuming lane's ten questions)

1. **Recovery actor.** Inject the EXISTING `RecordingTransferCoordinator.instance`
   into production CaptureSessionOwner; SyncProvider continues configuring that
   same object until C2. Tests inject a configured isolated coordinator. C1 routes
   capture finalization through `requestRecovery`; it does NOT yet establish sole
   ownership across the app. C2 routes SyncProvider startup/retry/cooldown,
   DeviceProvider connect, SyncReconciler foreground/cooldown and auto-sync/UI
   intents through the same request owner, then moves configuration to composition.
   Only then claim one external wake actor. Coordinator retry stays internal.
   Concurrent requests join; a later request runs again. C2 discovery assigns
   account-local monotonic inventoryRevision; a higher revision during a pass
   queues one serial pass. C1 capture supplies no revision. Preserve userRetry's
   auto-upload bypass even when it arrives during a disabled-auto-upload pass.
2. **FGS actor.** CaptureSessionOwner arbitrates capture's injected start/stop
   effects. Latest desired hold wins: stop during pending start waits, then stops
   once; failure propagates and permits retry. Home's static FGS call remains an
   App UI handoff, NOT a C1 edit or completion claim. App UI later replaces it with
   intent to this SAME owner; do not claim global exclusivity before that lands.
   Location permission alone is not a hold; preserve BLE/phone eligibility and
   native MicArbiter/session behavior. Intent is platform-neutral; production effects
   are Android-only, with iOS cleanup composition-owned.
3. **Exemplar.** Real CaptureProvider AND CaptureController; explicit composition
   forwards every seam intact, never a test-only subclass. Both production
   construction arms use composeProductionCaptureProvider.
4. **Seams/defaults.** Reuse capture_seams.dart and CaptureReplayWorld. Required:
   socket, FGS effects, BLE listener boundary, preferences, connectivity, auth,
   WAL/mic, clock/scheduling, location, codec/permissions, segment store, telemetry,
   device lookup. No AnalyticsManager dependency: keep lifecycle telemetry; move
   the three existing product-event operations (transcribeLaterToggled,
   omiDoubleTap, conversationCreated) behind existing CaptureExternalActions,
   whose production adapter preserves their current emissions. C7 owns naming. BLE exposes only add/remove finalized listener. Keep the
   existing preferences/store types as explicit objects: capture reads dozens of
   settings, not just mute. A mute-only replacement loses batch/STT/native config.
   Dart `implements` + overridden noSuchMethod IS valid (pinned analyzer passes);
   strict fakes throw on unexpected calls. Production adapters can narrow later.
   Final adoption removes all implicit defaults: no-argument controller/provider
   must refuse before ConnectivityService or any global initialization. Production
   defaults resolve only in composeProductionCaptureProvider, which refuses
   FLUTTER_TEST first. Existing defaults survive ONLY during staged migration;
   no new program test/probe may use them. The final guard is not marked done early.
5. **Generation.** One owner `_sessionGeneration`; bump synchronously on stop,
   dispose, identity/source/device replacement, including same-id ABA. Remove
   `_websocketInitGeneration` AND `_sessionGeolocationGeneration` as each path
   migrates. Configuration is a connect-attempt key within that generation, not
   another capture generation. Native mic and telemetry IDs remain correlation.
   Capture token before await; check after EACH await, including error/finally,
   before mutation/effect: codec→STT/socket, refresh→reconnect, permission/fix→upload,
   upload→WAL publication, finalize→recovery, queued replaceSession→fingerprint.
   Issued durable writes remain bound to their original account/session; do not
   undo them or publish their completion into a new session. Admitted recovery
   survives capture stop; account change retires its account-owned coordinator.
6. **Overlap.** Same generation/config joins connect, including keepalive ticks.
   Changed config supersedes, closes a late socket once; logical cancellation
   does not cancel the OS. Stop invalidates before native teardown. Tests also
   require a tick to reconnect autonomously, so a disconnected helper cannot pass.
7. **Scope.** SyncProvider/DeviceProvider bare construction is C2. C1 constrains
   capture and its extracted implementation, not C2's five legacy wake sites.
   Home belongs to App UI. No simultaneous rewrites of those owners.
8. **Ratchet.** Follow PENDING_CONTRACTS.md's adoption rule. Declare migrated
   file/rule pairs in `app/contracts/capture/boundary-baseline.json` `adopted`.
   Legacy inventory is informational; new files start at zero. Composition is
   the global-read adapter; CaptureLifetime owns raw acquisition. Static adoption
   scans capture_* ownership extractions, not pre-existing STT policy/cache
   adapters. Those helpers are not an expanded C1 migration requirement.
   Lexical checks ignore comments/strings, may flag same-named unrelated calls,
   and can miss aliases/dynamic dispatch. They complement real-provider effects;
   they cannot prove transitive ownership or replace behavioral tests.
9. **Dispose/tests.** Each owner has CaptureLifetime. Register timers, subscriptions,
   listeners and late acquisitions immediately. Close invalidates first and drains
   despite removal errors, joining explicit release/subscription cancellation already
   in flight. Concurrent closes join. Terminal
   resources untrack, including asFuture; replacement/error/done callbacks stay
   closed-guarded. Later close is inert. Scheduler-wide inventory
   must be empty after teardown; tests exercise real provider behavior plus an
   isolated constructor with no plugin/global setup. One prepareCurrent primitive
   test is sufficient; codec/auth/location/persistence use distinct production tests.
10. **Initialization.** C2 SyncProvider initialization must expose failed/ready
    separately; preserve known data and permit retry, never swallow into ready.

## Mergeable cuts and fan-out

Extract `capture_lifetime.dart`, `capture_session_owner.dart`, composition;
then move socket setup to `capture_socket_session.dart` and persistence/location
to `capture_session_persistence.dart`. Each extraction reduces the 2,710-line
controller; C5's 1,500-line baseline is no growth allowance.

Do not call the complete migration six hours-PRs. Accept 3–5 days for composition
and test conversion, 1.5–2 days for socket/generation; split reviewable commits:
(1) lifetime primitive; (2) explicit forwarding path alongside existing defaults;
(3+) migrate existing test groups in small batches, every group passing the owner
suite; (4) production cutover: both main.dart arms call
composeProductionCaptureProvider, which injects CaptureSessionOwner wrapping
RecordingTransferCoordinator.instance and Android-only FGS start / both-platform
stop. Do not default sessionOwner on CaptureProvider() — that constructor remains
a test/fixture seam until final adoption refuses it; putting the owner there
would pull ForegroundUtil and the coordinator singleton into the remaining
test CaptureProvider() sites and violate the exemplar walk. Implicit-constructor
default-removal is still later;
(5+) socket then persistence fences, each with its production tests;
(6) capture recovery request and FGS intent extraction — landed on
CaptureSessionOwner: concurrent wakes join one drain, FGS latest-hold wins,
stale finalize cannot wake a later session. Home's static FGS and C2's five
wake sites stay out; the default constructor still falls back to the singleton
coordinator. Retire only satisfied
markers; whole-C1 adoption waits until the last cut. No long-lived hot-file rewrite.

Cut (4) production wiring landed: both ChangeNotifierProxyProvider4 `create`
and `update`'s null-construction fallback call composeProductionCaptureProvider,
preserving update and existing store/action wiring. DeviceProvider()/SyncProvider()
stay until C2. App UI owns the separate Home FGS handoff. The all-lib wake cut
is C2; AnalyticsManager and duplicate helper tests are removed.

C2 order: sync_provider → device_provider → local_wal_sync → memories_provider.
Per-file done: production construction with explicit fakes, each awaited boundary
rejects obsolete/disposed work with a successful current-generation control,
concurrent intents coalesce, all resources cancel, failed init is observable and
retry recovers; declare adoption for each migrated pattern and retain journeys.
Settings/plans/payments can reuse generation checks for stale rollback and explicit
loading/error state. Their context-after-await cases are linted; no C1 scope there.
