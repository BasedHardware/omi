# INV-VOICE-1: One desktop voice-turn lifecycle owner

**Status:** locked
**Statement:** `VoiceTurnCoordinator` and its reducer are the only owners of a
desktop voice turn's logical lifecycle.

The macOS push-to-talk and realtime paths have one logical lifecycle owner:
`VoiceTurnCoordinator`, whose state changes only through `VoiceTurnReducer`.
Microphone, provider, tool, journal, and playback objects are physical drivers;
SwiftUI and floating-bar state are projections.

`VoiceTurnReducer`, `VoiceTurnEvent`, and the mutable `VoiceTurnModel` live inside
the strict `VoiceTurnDomain` target. App code may publish only typed
`VoiceTurnFact` values through the coordinator/domain facade and observe its
read-only model snapshot. The compiler therefore prevents an app driver from
constructing a lifecycle event or reducing state directly; behavior tests still
verify that every required fact is published.

## MUST NOT

- Reintroduce a parallel PTT/realtime lifecycle enum, current-turn boolean, or
  completion timer in a microphone, provider, playback, or UI driver.
- Accept an asynchronous callback without its reducer-issued turn and effect
  identity.
- Declare a turn successful before provider, tools, playback, and canonical
  journal fences have all closed.
- Treat durable outbox enqueue as journal acceptance.
- Route realtime delegation through a second Swift text classifier.

## Contract

- Every logical turn has one `VoiceTurnID`. Starting a replacement records the
  superseded turn and terminalizes it once; callbacks for that turn cannot mutate
  the replacement.
- Every asynchronous provider attempt, reconnect/replacement, tool call, playback
  lease, and journal write carries a reducer-issued `VoiceEffectIdentity`. It
  contains the immutable turn generation plus a unique effect ID. A callback must
  match both the turn and the currently registered effect.
- Capture, provider response, pending tools, local playback, and canonical journal
  acceptance are independent completion fences. Success is emitted once, and only
  after every active fence has closed.
- Playback drain for a non-realtime output lane is provider completion; native
  realtime audio still waits for both server completion and the local PCM drain.
- Canonical kernel-journal acceptance is required for success. Durable outbox
  enqueue alone is not acceptance. Journal rejection or timeout fails the turn.
- Reconnect and replacement state belongs to the reducer. The realtime controller
  may buffer bounded PCM while a socket authenticates, but that buffer does not
  decide whether the turn is recording, responding, finished, or current.
- Transport authentication is not input admission. Buffered PCM may reach a
  realtime provider only after the exact current kernel context identity is
  installed on that physical session; a missing, stale, or superseded identity
  fails closed into the existing fallback route.
- A PTT press starts capture independently of session maintenance. It either
  uses an exactly admitted binding immediately, retains its one logical turn
  through one controller-owned rebind, or takes one typed transcription
  fallback; a generic warm timeout, cancelled-turn fence, or background schema
  refresh must never require the user to repeat the press.
- `RealtimeHubController` is the sole owner of ordinary physical-session
  handoffs. Context, schema, settings, and post-turn maintenance request its
  typed handoff boundary; no asynchronous prefetch may tear down a session
  directly.
- A physical release is idempotent once the reducer has a pending hub commit.
  `PushToTalkManager` must not start batch transcription for that same audio; only
  a still-finalizing turn with no accepted/deferred hub commit may take the batch
  fallback.
- A barge-in replacement session starts only after the canonical snapshot proves
  it contains every just-persisted interrupted turn ID. A merely resolved but
  stale snapshot is retried and never becomes provider context.
- Provider failure captures the visible user/assistant exchange into a per-
  continuity-key journal obligation before terminal cleanup clears local text.
  Concurrent turn B persistence cannot invalidate turn A's acceptance receipt.
- Context capture publishes one versioned captured/omitted outcome to the turn.
  A late context result for a superseded turn is dropped.
- User interrupt is a typed reducer event. It revokes tools/output and terminalizes
  exactly once; late tool and playback callbacks remain stale.
- PTT status text is failure-only. Recording, transcription, fallback recovery,
  and barge-in replacement remain visual states; only actionable typed capture,
  provider, tool, journal, or playback failures may show a text banner.
- A PTT current-screen answer is admitted only from one pre-overlay capture bound
  to that exact voice turn. Capture itself never delays ordinary PTT output;
  only a reducer-admitted screenshot call seals visual output. The provider may
  propose visual detail only after native code has locally enqueued the exact
  JPEG function-response wire for the same session/response/call/epoch receipt.
  That frozen image must be less than five seconds old when native code mints
  the transport receipt. Once that exact receipt exists, a separate bounded
  report deadline—not the capture timestamp—limits provider reasoning latency;
  expiry fails closed into the deterministic screen-verification failure. The
  paired screenshot/report is one reducer-owned protocol: it retains the
  screenshot effect identity until a verified report or deterministic failure
  closes it, and a completion failure terminalizes the turn rather than leaving
  a pending screenshot tool. A verified report is internal grounding only: it
  clears the screen protocol while preserving the provider-continuation fence,
  so native realtime audio answers the user's original question from the image.
  Only deterministic screen-verification failure is a local terminal result.
  Model-supplied
  evidence IDs and app labels have no authority; native code supplies app identity
  and rejects stale, missing, contradictory, or cross-turn reports without using
  historical chat, memory, OCR, or context summaries as screen authority. A
  cancelled screenshot tool execution must never mutate or speak into a barge-in
  replacement turn.
- `PushToTalkManager` has no `PTTState`, lifecycle timer, or current-turn variable.
  It derives `phase` from the coordinator and forwards snapshots to observers.
- Realtime delegation does not run a second Swift text classifier. Explicit model
  tool intent reaches the kernel's atomic route-and-control path.
- A realtime provider turn that requests tools first opens a dedicated
  `realtime_voice` kernel run/attempt. Every provider call ID is an invocation
  identity under that run; Node authorizes it through the same durable ledger as
  foreground/background tools before Swift performs an effect. Provider turn IDs
  are correlation, never bearer authority, and terminal voice state revokes the
  run capability.
- App code must not import or construct `VoiceTurnEvent` or `VoiceTurnReducer`.
  The target boundary, not a convention, owns that restriction.

## Guard surface

Behavioral reducer/coordinator tests cover normal PTT, release-time responses,
hub warm escalation, reconnect success/failure, replacement with late output and
tools, explicit interruption, local playback drain, journal acceptance/failure,
deadlines, and a rapid three-turn replacement sequence. Tests use an injected
deadline scheduler; lifecycle tests must not sleep on wall clock time.

`scripts/agent-logic-harness.sh --cross-surface-smoke` is the fast deterministic
gate for consecutive turns, reconnect-at-release, barge-in replacement, typing
during PTT, shared journal identity, and exactly-once commit admission. It uses
production reducers/protocols with fixture providers and does not require audio
hardware or a live model.

Non-production `ptt_test_turn` and `ptt_test_burst` actions use the reducer's
typed `.automation` intent. That intent owns synthetic finalization and bypasses
only the physical microphone silence gate; provider, journal, playback, and
terminal reducer fences remain production paths.

The named-bundle continuity gauntlet remains the real-path release gate for typed
chat → PTT → typed follow-up and cross-surface agent continuity.

## Surfaces

- `desktop/macos/Desktop/Sources/FloatingControlBar/VoiceTurn*.swift`
- `desktop/macos/Desktop/Sources/VoiceTurnDomain/VoiceTurnStateMachine.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/PushToTalkManager.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController+ScreenEvidence.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubSessionPolicies.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubInputAdmission.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeTurnPersistence.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeSpawnReceipt.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeToolAuthority.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift`

## Guard tests

- `desktop/macos/Desktop/Tests/VoiceTurnDomainTests/VoiceTurnReducerTests.swift`
- `desktop/macos/Desktop/Tests/VoiceTurnDomainTests/VoiceTurnDomainBoundaryTests.swift`
- `desktop/macos/Desktop/Tests/VoiceTurnOutputOwnershipTests.swift`
- `desktop/macos/Desktop/Tests/RealtimeHubBargeInContinuityTests.swift`
- `desktop/macos/Desktop/Tests/RealtimeScreenEvidenceTests.swift`
- `desktop/macos/Desktop/Tests/VoiceTurnDomainTests/CrossSurfaceContractSmokeTests.swift`
- `desktop/macos/agent/tests/convergence-authority-ratchet.test.ts`

## Path globs

- `desktop/macos/Desktop/Sources/FloatingControlBar/VoiceTurn*.swift`
- `desktop/macos/Desktop/Sources/VoiceTurnDomain/**`
- `desktop/macos/Desktop/Sources/FloatingControlBar/PushToTalkManager.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController+ScreenEvidence.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubSessionPolicies.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubInputAdmission.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeTurnPersistence.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeSpawnReceipt.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeToolAuthority.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift`

## PR rule

Name `INV-VOICE-1` in the PR body if you touch the path globs above.
