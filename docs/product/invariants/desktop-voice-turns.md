# INV-VOICE-1: One desktop voice-turn lifecycle owner

**Status:** locked
**Statement:** `VoiceTurnCoordinator` and its reducer are the only owners of a
desktop voice turn's logical lifecycle.

The macOS push-to-talk and realtime paths have one logical lifecycle owner:
`VoiceTurnCoordinator`, whose state changes only through `VoiceTurnReducer`.
Microphone, provider, tool, journal, and playback objects are physical drivers;
SwiftUI and floating-bar state are projections.

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
- A physical release is idempotent once the reducer has a pending hub commit.
  `PushToTalkManager` must not start batch transcription for that same audio; only
  a still-finalizing turn with no accepted/deferred hub commit may take the batch
  fallback.
- A barge-in replacement session starts only after the canonical snapshot proves
  it contains every just-persisted interrupted turn ID. A merely resolved but
  stale snapshot is retried and never becomes provider context.
- Context capture publishes one versioned captured/omitted outcome to the turn.
  A late context result for a superseded turn is dropped.
- User interrupt is a typed reducer event. It revokes tools/output and terminalizes
  exactly once; late tool and playback callbacks remain stale.
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
- `desktop/macos/Desktop/Sources/FloatingControlBar/PushToTalkManager.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift`

## Guard tests

- `desktop/macos/Desktop/Tests/VoiceTurnReducerTests.swift`
- `desktop/macos/Desktop/Tests/VoiceTurnOutputOwnershipTests.swift`
- `desktop/macos/Desktop/Tests/RealtimeHubBargeInContinuityTests.swift`
- `desktop/macos/Desktop/Tests/CrossSurfaceContractSmokeTests.swift`
- `desktop/macos/agent/tests/convergence-authority-ratchet.test.ts`

## Path globs

- `desktop/macos/Desktop/Sources/FloatingControlBar/VoiceTurn*.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/PushToTalkManager.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift`

## PR rule

Name `INV-VOICE-1` in the PR body if you touch the path globs above.
