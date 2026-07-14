# Ground truth: warm-hub / VoiceTurn event-sourced reducer (PR #9370 port target)

Source: Mac frozen tag v0.12.72, `desktop/macos/Desktop/Sources/FloatingControlBar/`.
All line numbers below refer to that tag as checked out at
`C:\Users\chris\projects\omi\.worktrees\mac-ref\desktop\macos\Desktop\Sources\FloatingControlBar\`.

**`RealtimeHubController` is a facade over `VoiceTurnCoordinator` + `VoiceTurnReducer`.**
It still owns provider-transport mechanics (session lifecycle, mic feed, tool
dispatch), but per-turn *state* — what phase the turn is in, what's legal next,
deadlines, terminal reasons — belongs entirely to `VoiceTurnReducer`
(`VoiceTurnStateMachine.swift`), driven by `VoiceTurnCoordinator`
(`VoiceTurnCoordinator.swift`). The controller calls
`VoiceTurnCoordinator.shared.send(...)` to report provider events into the
reducer, and reads `VoiceTurnCoordinator.shared.activeTurnID` /
`.activeTurn` to gate its own behavior. Do not port `RealtimeHubController`'s
scattered booleans (`inputTurnInProgress`, `responding`,
`realtimePlaybackActive`, etc.) as the state model — those are legacy
mechanics that will be superseded as the port lands; the *authoritative* state
is the reducer's `VoiceTurnPhase`.

---

## 1. The reducer: states, events, transitions, typed IDs, fencing

File: `VoiceTurnStateMachine.swift` (902 lines). Pure value-type reducer:
`VoiceTurnReducer.reduce(VoiceTurnModel, VoiceTurnEvent) -> VoiceTurnReduction`
(model + effects list; no I/O inside the reducer itself).

### Typed IDs (all `Hashable, Equatable, Sendable`, wrapping a `UUID` or opaque string)

| Type | Wraps | Purpose |
|---|---|---|
| `VoiceTurnID` | `UUID` | Identity of one PTT turn (hold→reply). Created once per `begin()`. |
| `VoiceCaptureID` | `UInt64` | Identity of one mic-capture session within a turn. |
| `VoiceSessionID` | `UUID` | Identity of one warm-hub WebSocket connection. |
| `VoiceResponseID` | `String` | Identity of one provider response/reply. |
| `VoiceToolCallID` | `String` | Identity of one in-flight tool call. |
| `VoiceLeaseID` | `UUID` | Identity of one output-playback lease (`VoiceOutputLease`). |

`VoiceTurn` (the live turn record) carries `id: VoiceTurnID`, plus optional
`captureID`, `sessionID`, `responseID`, a `Set<VoiceToolCallID>`
(`pendingToolCallIDs`), and an optional `activeLease: VoiceOutputLease`.

### The fencing rule (typed-ID fencing — port this exactly)

Every event carries `var turnID: VoiceTurnID?` (computed property, line
277–298). At the top of `reduce()` (lines 411–418):

```swift
guard var turn = model.turn else { stale(...); return }
guard event.turnID == turn.id else { stale(...); return }
```

Any event whose `turnID` doesn't match the currently-live turn is dropped as
**stale** (`model.staleEventCount += 1`, effect `.staleEventDropped`) — it
never mutates state. This is the single fencing choke point: a turn that was
superseded by barge-in, or a callback that arrives after `cancel`/`finish`,
cannot resurrect or corrupt a newer turn. `.cleanup` and `.reset` are the only
turn-independent events (no `turnID`).

**Nested identity fencing inside phases** — the top-level turn-ID check isn't
the only fence; several transitions add a second-order identity check before
accepting an event, because a turn can span multiple sessions/responses
(barge-in replacement):
- `hubReady` (line 500): only valid when `turn.route == .hubWarmWait`, else stale.
- `hubCommitAccepted` (line 509): if `turn.sessionID` is already set, the incoming
  `sessionID` must match or it's stale — prevents a replaced session's `hubReady`
  from silently re-pointing an in-flight turn.
- `providerResponseStarted` / `providerTurnFinished` (lines 580, 602): reject unless
  `acceptsProviderOutput(phase)`; if `turn.sessionID`/`turn.responseID` already set,
  a mismatching incoming ID is stale, not applied.
- `toolFinished` (line 632): the `callID` must be in `pendingToolCallIDs`, else stale.
- `playbackStarted` (line 651): `lease.turnID == turn.id` required, else stale; a
  *different* already-active lease makes it `invalid` (not stale — a real bug).
- `playbackDrained` (line 672): `turn.activeLease?.id == leaseID` required, else stale.
- `captureFailed` (line 483): if both turn's and event's `captureID` are non-nil and
  differ, stale.
- `deadlineFired` (line 733): the phase must still contain that `VoiceTurnDeadline`
  in its `Set<VoiceTurnDeadline>`, else stale — a canceled/superseded timer that
  still fires (race) is a no-op.

`RealtimeHubController` mirrors this same pattern one layer up in
`acceptsTurnEvent` (line 2492): before even calling into the coordinator, it
checks `identity.turnID == voiceOutputCoordinator.snapshot().turnID` and
`RealtimeHubEventOwnership.accepts(...)` against `activeTurnID`/`activeResponseID` —
belt-and-suspenders because provider socket callbacks can race a turn boundary
at the transport layer before the typed event even reaches the reducer.

### State set — `VoiceTurnPhase` (line 117)

```
idle
pendingLockDecision
recording
lockedRecording
finalizing
awaitingResponse
awaitingTools
playing(VoiceOutputLane)
terminal(VoiceTurnTerminalReason)
```

- `isRecording` = `.recording || .lockedRecording || .pendingLockDecision`
- `isTerminal` = `case .terminal` (carries a typed `VoiceTurnTerminalReason`, one
  of: `success, tooShort, silentRejected, cancelled, interruptedByBargeIn,
  permissionDenied, captureFailed, transcriptionFailed, providerFailed,
  providerNoResponse, hubWarmTimeout, deferredCommitTimeout,
  bargeInReplacementTimeout, toolTimeout, playbackFailed, cleanup`)

`VoiceTurnRoute` (line 74) is orthogonal to phase — tracks which STT/reply
path the turn is using: `undecided | hubWarmWait | hub(sessionID:) | omniSTT |
deepgramBatch | deepgramLive | agentFollowUp`.

`VoiceTurnIntent` (line 67): `hold | locked | agentFollowUp | automation` — set
at `begin()`, mutated to `.locked` by the `lock` event.

### Event set — `VoiceTurnEvent` (line 241), 25 cases

`start, openLockWindow, lock, finalize, captureStarted, captureFailed,
selectRoute, hubReady, hubCommitAccepted, hubCommitDeferred,
hubCommitDeferredForReplacement, transcriptionStarted, transcriptionFinal,
transcriptionFailed, providerResponseStarted, providerTurnFinished,
toolStarted, toolFinished, playbackStarted, playbackDrained, playbackFailed,
transcriptChanged, hintChanged, responseWaitingChanged, responseActiveChanged,
clearPresentation, deadlineFired, finish, cancel, cleanup, reset`

### Transition table (guard → phase change; violations become `.invalid` or `.stale`)

| Event | Valid from | → New phase | Notes |
|---|---|---|---|
| `start(turnID, intent)` | any (terminates prior turn as `.interruptedByBargeIn` if not already terminal) | `.recording` (or `.lockedRecording` if intent `.locked`) | Schedules `captureStart` deadline. Resets `staleEventCount`/`invalidTransitionCount`/`duplicateTerminalCount`. |
| `openLockWindow` | `.recording` only | `.pendingLockDecision` | Schedules `lockDecision` deadline. |
| `lock` | `.recording` or `.pendingLockDecision` | `.lockedRecording` | Cancels `lockDecision`; sets `intent = .locked`. |
| `finalize` | any `isRecording` phase | `.finalizing` | Cancels `lockDecision`+`captureStart`; effect `.stopCapture`. |
| `captureStarted` | `isRecording` | (same) | Cancels `captureStart` deadline, sets `captureID`. Off-phase → stale + `.stopCapture` (kill the orphan capture). |
| `captureFailed` | any non-terminal (ID-fenced) | → `terminate(.captureFailed)` | |
| `selectRoute` | `isRecording` or `.finalizing` | (same phase) | Sets `route`; `.hubWarmWait` schedules `hubWarm` deadline. |
| `hubReady` | route `== .hubWarmWait` (else stale) | (same phase) | Cancels `hubWarm`; route → `.hub(sessionID:)`. |
| `hubCommitAccepted` | `.finalizing`, OR `.awaitingResponse` with `deferredCommit`/`bargeInReplacement` deadline pending | `.awaitingResponse` | Cancels deferred/bargeIn deadlines; schedules `providerResponse`. |
| `hubCommitDeferred` | `.finalizing` + hub route | `.awaitingResponse` | Schedules `deferredCommit` deadline. |
| `hubCommitDeferredForReplacement` | `.finalizing` + hub route | `.awaitingResponse` | Schedules `bargeInReplacement` deadline (distinct from `deferredCommit`). |
| `transcriptionStarted` | `.finalizing` only | (same) | Schedules `transcription` deadline. |
| `transcriptionFinal` | `.finalizing` (else stale) | `.awaitingResponse` | Cancels `transcription`; schedules `providerResponse`. |
| `transcriptionFailed` | any non-terminal | → `terminate(.transcriptionFailed)` | |
| `providerResponseStarted` | `acceptsProviderOutput` phase (`.awaitingResponse/.awaitingTools/.playing`) | (same) | Cancels `providerResponse`/`deferredCommit`/`bargeInReplacement`. |
| `providerTurnFinished` | `acceptsProviderOutput` | if no active lease & no pending tools → `terminate(.success)`, else stays | Sets `providerFinished = true`. |
| `toolStarted` | `acceptsProviderOutput` | `.awaitingTools` | Adds to `pendingToolCallIDs`; schedules `pendingTools` deadline. |
| `toolFinished` | callID must be pending | when set empties: `.playing(lane)` if lease active, else `terminate(.success)` if provider already finished, else back to `.awaitingResponse` (reschedule `providerResponse`) | |
| `playbackStarted` | `acceptsProviderOutput`, lease.turnID matches | `.playing(lane)` | Cancels `providerResponse`; schedules `playbackDrain`. |
| `playbackDrained` | lease ID matches active lease | `terminate(.success)` if done, else `.awaitingTools` or `.awaitingResponse` | |
| `playbackFailed` | lease ID matches (or nil) | → `terminate(.playbackFailed)` | |
| `deadlineFired(deadline)` | deadline must be in the turn's active `Set` | varies (see §2 timeouts) | |
| `finish(reason)` / `cancel(reason)` | any non-terminal | → `terminate(reason)` | Duplicate on an already-terminal turn just increments `duplicateTerminalCount`. |
| `cleanup` | — | → `terminate(.cleanup)` if a turn exists | Turn-independent. |
| `reset` | turn is nil or terminal | `model.turn = nil` | Non-terminal → `.invalid`. Turn-independent event, but content-guarded. |
| `transcriptChanged`/`hintChanged`/`responseWaitingChanged`/`responseActiveChanged`/`clearPresentation` | any non-terminal | (no phase change) | Pure UI-projection updates; `hintChanged` (re)schedules `hintVisibility`. |

`acceptsProviderOutput(phase)` (line 788) = `true` only for
`.awaitingResponse, .awaitingTools, .playing`; false for every recording/idle/
finalizing/terminal phase — this is what stops a stray provider callback from
mutating a turn that's still capturing mic audio.

### `terminate()` (line 817) — the single terminal path

All roads to a terminal phase go through one private `terminate()`:
1. No-op with `duplicateTerminalCount += 1` if already terminal.
2. Emits `.stopCapture` if a capture is running.
3. Emits `.cancelHub(route)` **unless** `preservesHubForBargeInHandoff` is true
   (only true when `reason == .interruptedByBargeIn` AND `route` is `.hub` —
   this is what lets a barge-in reuse the still-open warm socket instead of
   tearing it down, the "atomic handoff" tested by
   `testHubBargeInPreservesProviderRuntimeForAtomicHandoff`).
4. Emits `.stopPlayback` if a lease is active (same handoff exception).
5. Emits `.cancelAllDeadlines`, then `.terminal(record)`.
6. Clears `deadlines`, `pendingToolCallIDs`, `activeLease`; sets
   `phase = .terminal(reason)`; resets `projection = .idle`.
7. Sets a terminal-only user-facing hint string per reason (e.g. `tooShort` →
   "Hold longer to record", `captureFailed` → "Microphone unavailable — try
   again") and schedules a `hintVisibility` deadline to auto-clear it.

### Deadlines (all in `VoiceTurnReducer.Deadlines`, line 359) — port these values

| Deadline | Default | Fires from | On fire |
|---|---|---|---|
| `lockDecision` | 0.4s | `pendingLockDecision` | → `.finalizing` (short tap resolves to finalize) |
| `captureStart` | 3s | recording phases | → `terminate(.captureFailed)` |
| `hubWarm` | 1s | `route == .hubWarmWait` | `.fallbackToTranscription(hubWarmTimeout)` effect + route → `.deepgramBatch`; if still `.finalizing`, reschedules `transcription` |
| `transcription` | 12s | `.finalizing` (after `transcriptionStarted`) | → `terminate(.transcriptionFailed)` |
| `providerResponse` | 20s | `.awaitingResponse`/after tool/playback resume | → `terminate(.providerNoResponse)` |
| `pendingTools` | 30s | `.awaitingTools` | → `terminate(.toolTimeout)` |
| `deferredCommit` | 8s | `.awaitingResponse` (deferred hub commit path) | → `terminate(.deferredCommitTimeout)` |
| `bargeInReplacement` | 8s | `.awaitingResponse` (barge-in replacement commit path) | → `terminate(.bargeInReplacementTimeout)` |
| `playbackDrain` | 30s | `.playing` | → `terminate(.playbackFailed)` |
| `hintVisibility` | 2s | any terminal hint / live `hintChanged` | Clears `projection.hint` (does NOT terminate/resurrect) |

Deadlines are per-turn-ID (`DeadlineKey{turnID, deadline}` in the coordinator,
line 96–103) — a canceled deadline for turn A can never fire against turn B
even if B reuses the same wall-clock slot (`testCancelledDeadlineCannotMutateLaterTurn`).

### Effects (`VoiceTurnEffect`, line 338) — what the coordinator must execute

`scheduleDeadline / cancelDeadline / cancelAllDeadlines / stopCapture /
cancelHub(route) / fallbackToTranscription(reason) / stopPlayback(leaseID) /
terminal(record) / staleEventDropped / invalidTransition`

The reducer is pure — it only *describes* effects; `VoiceTurnCoordinator.process(_:)`
(line 219) is what actually calls the scheduler, records diagnostics
(`DesktopDiagnosticsManager.recordVoiceTurnTerminal` /
`.recordVoiceTurnAnomaly`), and invokes the injected `effectHandler` closure
that `RealtimeHubController`/`PushToTalkManager` wire up to do the real I/O
(stop mic capture, tear down/reuse the hub socket, stop PCM playback, etc.).

### Coordinator-level guarantees (`VoiceTurnCoordinator.swift`)

- **Atomic-apply + FIFO re-entrancy** (line 154–186, `send`/`apply`): one
  `reduce()` call fully completes — model assignment, effect delivery,
  presenter projection, snapshot callback — before the next event is applied.
  If an effect/snapshot callback calls `send()` again synchronously (common:
  UI reacts to a projection change by issuing a new command), that event is
  queued (`pendingEvents`) and drained **after** the current one finishes, not
  recursively. This is the same "synchronous state-machine callback" pattern
  documented in `desktop/macos/AGENTS.md`. Windows must reproduce this — a
  React `dispatch` inside a `useEffect` reacting to state is the natural
  place this bites.
- **`begin(intent:id:)`** (line 145): if the current turn is already terminal,
  auto-sends `.reset` first, then `.start`. This is the only public entry
  point that manufactures a fresh `VoiceTurnID` (`VoiceTurnID()` default arg).
- **`activeTurnID`/`activeTurn`** (line 127–128): `nil` whenever
  `model.turn?.phase.isTerminal == true` — terminal turns are invisible to
  callers checking "is a turn live right now", even though the model object
  still exists briefly for the terminal-hint display window.
- **Timeline ring buffer** (`timelineLimit: 256`, line 108, 282–303): every
  event appends a `VoiceTurnTimelineEntry` (sequence, turnID, event label,
  phase before/after, route, terminal reason, stale/invalid counters) —
  diagnostics-only, bounded, never carries transcript/hint payloads
  (`diagnosticLabel` is deliberately payload-free, tested by
  `testDiagnosticLabelsNeverContainSpeechOrErrorPayloads` /
  `testTimelineNeverStoresAssociatedSpeechPayloads`).

---

## 2. Warm-socket lifecycle

File: `RealtimeHubController.swift` unless noted; `RealtimeHubSession.swift` for
the socket/provider protocol layer; `RealtimeHubSettings.swift` for provider
selection.

### Provider selection (`RealtimeHubSettings.swift`)

`RealtimeHubProvider: .openai | .gemini`. No separate hub picker — it follows
`RealtimeOmniSettings.shared.effectiveProvider` (`gptRealtime2 → .openai`,
`geminiFlashLive`/`.auto → .gemini`). `canConnect` = a BYOK key exists for
`provider.byokProvider`. Managed (non-BYOK) users go through ephemeral-token
minting instead (see below). `alternate` provider is the failover target
(openai↔gemini) when the primary can't connect.

### `ensureWarm()` (line 1113) — open-if-not-already-warm

No-op if `session != nil && sessionProvider == effectiveProvider`. Otherwise
tears down any existing session and:
1. **BYOK path**: if `APIKeyService.byokKey(provider.byokProvider)` exists and
   `CredentialHealthManager` hasn't marked that key fingerprint bad, connect
   client-direct (`startSession(provider:, auth: .byokKey(key))`).
2. **Managed path**: if signed in, `mintAndConnect(provider:)` — async fetch
   an ephemeral token from the backend (`POST` via `APIClient.mintRealtimeToken`),
   then `startSession(auth: .ephemeral(token))`. Guarded by `minting` bool
   (no concurrent mints); re-checks `effectiveProvider == provider &&
   session == nil` after the async mint returns before connecting (settings
   or a competing connect could have changed the picture mid-mint).
3. Neither available → hub stays inert, PTT silently falls back to legacy
   cascade (no session created, no error).
Gated by `cancelContinuityFenceActive` (deferred behind a canceled-turn
fence — see `cancelTurn` below) and
`RealtimeHubLifecyclePolicy.canStartGeneralWarmSession` (must not race a
barge-in replacement's own session startup).

### `startSession()` (line 1236)

Builds the system instruction (`RealtimeHubTools.systemInstruction`) from
`aboutUserCard` + `voiceSessionSeedContext()` (kernel-projected conversation
seed + pending outbox turns + floating-agent status) + user languages,
constructs a fresh `RealtimeHubSession`, resets `lastWarmAt = nil`,
`hubConnected = false`, assigns a new `VoiceSessionID()`, calls `s.start()`.
`hubConnected` only flips `true` in `hubDidConnect` (post-auth "ready"),
which is what gates `isActive` — a stale/revoked key that never completes
handshake never costs a turn (PTT silently uses cascade instead).

### `sendSessionSetup()` (`RealtimeHubSession.swift` line 730)

Sent once the socket opens, provider-specific:
- **OpenAI**: `session.update` with `instructions`, `output_modalities: [audio]`,
  input `turn_detection: null` (**PTT controls turns, not server VAD**),
  whisper-1 input transcription (+ optional language hint), 24kHz PCM in/out,
  voice `marin`, tools + `tool_choice: auto`.
- **Gemini**: `setup` with model `models/<modelID>`, `responseModalities:
  [AUDIO]` (TEXT modality is rejected with close 1007 — every current Gemini
  Live model is native-audio only), `temperature: 0.3` (low, for consistent
  tool-choice routing), `mediaResolution: HIGH`, pinned voice `Charon`,
  function declarations, `inputAudioTranscription`/`outputAudioTranscription`
  both enabled, **manual activity detection** (`automaticActivityDetection.disabled:
  true` — the app sends explicit `activityStart`/`activityEnd`, not
  server-side VAD), `turnCoverage: TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO`
  (so a screenshot frame sent after `activityEnd` still counts as part of the
  turn), `contextWindowCompression.slidingWindow` (prevents unbounded context
  growth degrading reply latency over a long-lived warm session).

### Keep-warm-between-turns

The session is opened once by `ensureWarm()` and reused across turns — `beginTurn`/
`commitTurn`/`cancelTurn` never close it on success. `lastTurnAt` is stamped on
every `beginTurn` (used only to gate re-warm timing heuristics, not a TTL
itself).

### Idle-close handling (Gemini ~2.5min, WS close 1008) → re-warm

`hubDidError(message:source:)` (line 3471) is the single close/error handler.
`aliveFor = now - lastWarmAt` (only if `hubConnected`, else 0).
`RealtimeHubCloseClassifier.category(...)` (line 35, `RealtimeHubController.swift`
top) classifies a `"websocket closed (1008)"` message:
- `hasActiveTurn == false && aliveFor >= 60s` → `.expectedIdleTeardown` (quiet
  log only, never reported to Sentry — this is the normal Gemini idle-close).
- Else → auth-failed / quota-exceeded / `.providerPolicyCloseFast` (fast
  closes ARE reported — they usually mean real auth/policy/config rejection).

On any close: `teardownSession()`, then:
- `credentialFailureClass == .providerAuthFailed` → failover to alternate
  provider if `aliveFor < 10s`, else just stop.
- `credentialFailureClass == .providerQuotaExceeded` → failover to alternate.
- Otherwise (the idle-close / transient case): **if `aliveFor > 60s`**, reset
  `hubReconnectStrikes = 0` and clear any failover state (a socket that
  survived past the idle window is treated as healthy — reset the churn
  budget and return to the Auto-picked provider). Then, gated by
  `!reconnectPending && hubReconnectStrikes < maxReconnectStrikes (5)`:
  increment strike count, set `reconnectPending = true`, and
  `DispatchQueue.main.asyncAfter(1.5s)` → `ensureWarm()` (only if
  `session == nil`, i.e. nothing already reconnected in the meantime).

**`maxReconnectStrikes = 5`** (line 552) — after 5 consecutive *fast, non-survived*
failures (e.g. a stale/revoked key), the hub gives up re-warming so it doesn't
hammer a dead endpoint; the strike counter only resets on a socket that lived
past 60s or on `settingsChanged`/explicit refresh paths, not on every
reconnect attempt.

### `systemDidWake()` — zombie-session drop (line 993)

Registered once in `setup()` against `NSWorkspace.didWakeNotification`. After
sleep, a long-lived WS can come back "zombie": open at the socket level (so a
PTT routes to it) but the server is actually gone — commit → no reply → no
close event → hang, with no automatic recovery. `systemDidWake()` calls
`requestSessionRefresh(reason: "system_wake")`, which (via
`RealtimeHubLifecyclePolicy`) only acts while idle (no active turn, not
mid-mint) so it never interrupts a live turn or races an in-flight connect —
it forces `session = nil` (teardown) so the next `ensureWarm()` rebuilds
instead of no-op'ing on the stale-but-"already warm" socket.

### `reconnectWarmSessionIfSeedStale()` (line 1345) — trigger

Warm sessions bake their system instruction (conversation seed context) at
connect time. Called from `beginTurn`'s async preparation task
(`turnPreparationTask`, after `refreshVoiceSeedContext()` resolves). Compares
freshly-fetched `voiceSessionSeedContext()` against
`sessionVoiceSeedContextSnapshot` (captured at `startSession`); if they
differ:
- If a voice turn is currently active (`hasActiveVoiceTurn || inputTurnInProgress`),
  **defer** — sets `pendingSessionRefreshReason = "voice_seed_changed"` and
  waits for `voiceTurnDidTerminate` to apply it once idle.
- Else, `teardownSession()` immediately so the **next** `ensureWarm()`
  reconnects with the fresh seed (newer main-chat/typed turns must be visible
  to the next PTT reply).

Also triggered (same mechanism, `requestSessionRefresh`) by
`settingsChanged` (provider picker / `RealtimeOmniSettings` change) and
`voiceLanguagesChanged`.

---

## 3. beginTurn / commitTurn / cancelTurn semantics + audio buffering across turn boundaries

All three are on `RealtimeHubController`, called by `PushToTalkManager` (the
PTT hotkey driver) — see §4.

### `beginTurn(turnID:)` (line 1936)

PTT-down. Establishes the barge-in decision BEFORE touching any state:
`bargeIn = responding || realtimePlaybackActive || voicePlaybackActive` (a
prior reply still in flight or still audibly playing). Resolves
`bargeInAction` via `RealtimeHubBargeInAction.decide(...)` against
`session?.bargeInStrategy` (`.inSessionCancel` for OpenAI — cancels the
in-flight response over the same socket and clears the input buffer;
`.replaceSession` for Gemini — Gemini has no reliable in-session cancel for a
streaming reply, so the controller reconnects a fresh socket and lets it
buffer the new turn while it opens, i.e. `restartSessionForBargeIn`).

Resolves/reuses the `VoiceTurnID` (`requestedTurnID ?? activeTurnID ?? coordinator.begin(intent: .hold)`),
mints a new `VoiceResponseID`, resets ALL per-turn scratch state
(`turnTranscript`, `assistantText`, `turnAudio16k` buffer, tool tracking,
`turnEpoch += 1`, etc.) — **`turnEpoch`/`turnGeneration`/`realtimePlaybackEpoch`
are monotonic counters used to invalidate late async callbacks from the
previous turn** (the Swift-side equivalent of the `startSeq` pattern already
in Windows `voiceController.ts`). Kicks off an async `turnPreparationTask`
that: refreshes the voice seed context → calls
`reconnectWarmSessionIfSeedStale()` → (for OpenAI) queues
`session.beginInputTurn(turnID:responseID:interrupting:)` on the session's
serial transport queue, which for Gemini means sending `activityStart`.

### `commitTurn()` (line 2251)

PTT-up. Sets `inputTurnInProgress = false`, `responding = true`. Kicks a
detached full-buffer local-language-ID task over the accumulated
`turnAudio16k` (used for the "bubble fallback" transcript, not the primary
path). Three outcomes:
1. **`pendingBargeInReplacement` still not ready** (Gemini session-replace
   barge-in mid-flight): mark `pending.pendingCommit = true`, send
   `.hubCommitDeferredForReplacement` to the reducer, return
   `.deferredForReplacement`. The commit is buffered until the replacement
   session finishes connecting.
2. **`pendingSessionReconnect` still not ready** (seed-stale or canceled-turn
   reconnect in flight): mark pending, send `.hubCommitDeferred`, call
   `ensureWarm()`, return `.deferredForReconnect`.
3. **Normal**: hint transcription language, queue `beginInputTurn` +
   `commitInputTurn()` on the session, send `.hubCommitAccepted(sessionID:,
   responseID:)` to the reducer, return `.accepted`.

If `session == nil` outright: `responding = false`, exit voice UI, return
`.rejectedNoSession` (caller falls back to legacy transcription).

### `cancelTurn(turnID:)` (line 2411)

Silent-tap / explicit-cancel path — "must leave NO open turn behind, or the
model answers the non-speech later." Fenced by
`voiceOutputCoordinator.snapshot().turnID == requestedTurnID` (stale cancel
ignored). Resets turn scratch state, calls `session?.abandonInputTurn()`
(closes the speech/activity window without committing — model never sees
it as a real utterance). **Session disposition depends on the reducer's
recorded terminal reason**: if the terminal reason for this turn was
`.success`, the *existing* warm session is kept (fast next-turn path);
any other reason (e.g. `.tooShort`, `.silentRejected`, `.cancelled`)
**tears down and rebuilds** the session behind a
`cancelContinuityFenceActive` fence — because an abandoned provider input can
still emit stray commit/activity acknowledgements, and every abandoned turn
needs a clean socket boundary before a later turn reuses the transport. The
rebuild is deferred (`canceledTurnRewarmTask`) until any pending persistence
work for the interrupted/canceled turn's continuity record finishes, then
calls `refreshVoiceSeedAfterPersistenceFence` → `teardownSession()` →
`ensureWarm()`.

### Audio buffering across turn boundaries

- **Mid-turn**: mic PCM accumulates in `turnAudio16k` (full-buffer, used for
  the local-LID fallback decode) AND is streamed live to the session via
  `feedAudio`/`session.sendAudio` — both happen concurrently, not
  sequentially.
- **While the hub is warming (not yet connected) on PTT-down**:
  `startRealtimeHubWarmWait()` (in `PushToTalkManager.swift`, line 1365)
  buffers captured mic audio into `batchAudioBuffer` (batch mode) rather than
  dropping it, while `ensureWarm()` connects in the background. When the hub
  resolves ready, `resolveRealtimeHubWarmWait(ready: true)` calls
  `startRealtimeHubCapture(bufferWhileWarming: true)`, which flushes the
  buffered audio into the now-live turn via
  `RealtimeHubController.shared.feedAudio(bufferedAudio, turnID:)` before
  continuing live capture. If the warm-wait times out AFTER PTT-up
  (`state == .finalizing`), the buffered audio is either committed as a
  buffered hub turn (`commitBufferedRealtimeHubTurn`) or transcribed via the
  legacy STT fallback (`transcribeBufferedWarmWaitAudio`) — never silently
  dropped.
- **On barge-in replacement (Gemini)**: `PendingBargeInReplacementTurn` /
  `PendingRealtimeSessionReconnectTurn` hold an `audioBuffer` of chunks fed
  during the window between PTT-down and the replacement session becoming
  authenticated; replayed in order once the new session is ready, before any
  commit is allowed through.
- **On successful turn completion**: no residual audio carries into the next
  turn — `turnAudio16k.removeAll(keepingCapacity: true)` happens at the START
  of the next `beginTurn`, not at commit, so the buffer is available for the
  local-LID decode during the CURRENT turn's response-waiting window right up
  until the next hold starts.
- **Silent/too-short turns are explicitly discarded**, never sent: both
  `commitBufferedRealtimeHubTurn` (buffered path) and the live path check
  `hubTurnHasSpeech(pcm16k:)` before committing; a silent buffer triggers
  `cancelTurn` + `.finish(reason: .tooShort | .silentRejected)` instead of a
  provider commit.

---

## 4. PTT (global hotkey) → `beginTurn` wiring

File: `PushToTalkManager.swift`. The global hotkey itself is registered via
`GlobalShortcutManager.swift` (small — resolves a configured key combo to a
down/up callback pair); `PushToTalkManager` is the consumer that owns the
capture/turn lifecycle, not the hotkey mechanism itself.

**Key-down** (line ~424 / ~479): `PushToTalkManager` calls
`voiceTurnCoordinator.begin(intent: .hold)` (or `.locked` for the lock-window
path) to mint the `VoiceTurnID`, stores it as `currentVoiceTurnID`. This is
the ONLY place a `VoiceTurnID` is manufactured for a real (non-headless) PTT
press.

**Routing decision** (lines 1308–1333, in the key-down handler): after
permission checks and the agent-follow-up special case (routes to
`startOmniTranscription()` directly — follow-ups always need an STT
transcript to hand to the agent, never the hub model itself):
```swift
if RealtimeHubController.shared.isActive {
  voiceTurnCoordinator.send(.selectRoute(turnID:, route: .hub(sessionID: nil)))
  startRealtimeHubCapture(bufferWhileWarming: false)
} else {
  startRealtimeHubWarmWait()   // route = .hubWarmWait, buffer audio while ensureWarm() connects
}
```
`startRealtimeHubCapture` is what actually calls
`RealtimeHubController.shared.beginTurn(turnID: currentVoiceTurnID)` (line
1339) and then starts mic capture (`startMicCapture()`).

**Key-up / release**: the PTT state machine (separately defined states in
`PushToTalkManager`, `.listening → .finalizing → ...`) drives
`RealtimeHubController.shared.commitTurn()` (line 1441, and the buffered-path
equivalent at line ~902) once finalization completes, or
`RealtimeHubController.shared.cancelTurn(turnID:)` (lines 276, 887, 1429) on
silent/too-short/canceled outcomes.

**`prefetchVoiceSeedContextIfNeeded()`** (lines 427, 467) is called on PTT
key-down BEFORE `beginTurn`, so the seed-staleness reconnect check inside
`beginTurn`'s async preparation task has a head start and can finish before
audio needs to flow.

---

## 5. Windows gap analysis — what changes, what's already right, ownership

### Current Windows state (confirmed by reading the actual files)

- **`sessionMachine.ts`** (`lib/voice/`): 4 flat states —
  `idle | connecting(provider) | live(provider, muted) | error(message, retryable)`.
  **No per-turn concept at all.** One session = one continuous "live" state;
  there is no notion of discrete PTT turns, no barge-in, no typed turn/session/
  response/lease IDs, no deadlines, no terminal-reason taxonomy.
- **`voiceController.ts`**: session-scoped orchestrator (mint → connect →
  live), a module-level `startSeq` counter for invalidating stale async
  starts (this IS the Mac's `turnEpoch`/fencing pattern, but applied at
  session-start granularity, not turn granularity), an `EchoGate` driver for
  mic-mute-during-playback, TTS playback. **No warm-socket-kept-open-between-
  turns model** — `startVoiceSession`/`stopVoiceSession` is session-lifecycle,
  not turn-lifecycle; there is exactly one "session" per hands-free
  conversation with no PTT-hold semantics inside it.
- **`VoiceSessionSurface.tsx`**: confirmed mounted only in the Home chat area
  (`components/voice/`), stops the session on unmount (`useEffect(() =>
  () => stopVoiceSession(), [])`) — i.e. today's realtime voice is
  page-scoped, not system-wide, and is a manual "Start voice chat" button
  flow, not a PTT-hotkey flow.
- **`lib/ptt/*` + `hooks/usePushToTalk.ts`**: confirmed, by grep, to contain
  **zero references** to `voiceController` or any Voice* symbol. This is a
  fully separate STT/dictation state machine (`ptt/machine.ts`): `idle →
  holding → draining → (streamFinalize | batching) → commit(text)`. It
  produces a **text transcript** for the chat input box — no realtime model
  connection, no spoken reply, no barge-in. This is the Mac's legacy
  Deepgram-cascade dictation path, not the hub path.

### What must be added to reach parity (capability only, no UI restyle)

1. **A `VoiceTurnReducer` port** — a new pure TS reducer file (e.g.
   `lib/voice/voiceTurnMachine.ts`) implementing the phase set, event set,
   typed IDs (branded string/number types are the natural TS equivalent of
   Swift's wrapper structs — e.g. `type VoiceTurnID = string & { __brand:
   'VoiceTurnID' }`), the deadline table, and the terminal-reason enum from
   §1. This is additive next to `sessionMachine.ts`, not a replacement of it —
   `sessionMachine.ts`'s 4 states can become the *session*-level wrapper
   (mirroring how `RealtimeHubSession` is transport/session-level under the
   turn-level reducer) or be retired in favor of turn-driven state; that's an
   implementation decision for the port PR, not dictated by this extraction.
2. **A `VoiceTurnCoordinator` port** — the atomic-apply-plus-FIFO-drain
   wrapper (§1, "Coordinator-level guarantees"), deadline scheduling
   (`setTimeout`-based, keyed by `{turnID, deadline}` so a canceled timer for
   turn A can never fire against turn B), and the effect-processing hook that
   the voice/PTT wiring subscribes to.
3. **Warm-socket lifecycle on `voiceController.ts`** (or a new sibling
   module) — `ensureWarm()`/keep-open-between-turns/idle-close reconnect with
   strike budget (port `maxReconnectStrikes = 5`, the 60s "survived the idle
   window" reset rule, and the `RealtimeHubCloseClassifier`
   expected-idle-vs-fast-fail distinction) instead of the current
   one-session-per-conversation model. Windows has no sleep/wake zombie-socket
   analog to worry about in the same way (no macOS `NSWorkspace.didWakeNotification`),
   but Windows DOES have an OS sleep/resume event
   (`powerMonitor.on('resume')` in Electron's main process) that should drive
   the equivalent "drop and rebuild the warm socket" defensive reconnect —
   flag this as a real gap, not a Mac-only concern.
4. **System-wide PTT wiring** — a new global-hotkey-driven `beginTurn`/
   `commitTurn`/`cancelTurn` call path (mirroring `PushToTalkManager`'s
   key-down/key-up handlers in §4), independent of whether `VoiceSessionSurface`
   is mounted. This needs a main-process global shortcut (Electron
   `globalShortcut`, already the pattern used by `main/overlay/shortcut.ts`
   for the existing overlay hotkey) that IPCs down/up into the renderer's new
   turn coordinator — analogous to how `main/bar/*` + `main/overlay/*`
   already own hotkey/gesture/window-placement mechanics for the bar.
5. **Barge-in decision + `bargeInStrategy`** — OpenAI in-session cancel vs.
   Gemini session-replace is a per-provider strategy that doesn't exist in
   `openaiSession.ts`/`geminiSession.ts` today; this is required to port
   `beginTurn`'s barge-in branch faithfully.

### Windows files this agent owns that can carry the port

Per the brief's ownership scope (`lib/voice/**`, `lib/ptt/**`, `main/bar/**`,
`main/overlay/**`):
- `lib/voice/voiceTurnMachine.ts` (new) — the reducer port (§1).
- `lib/voice/voiceTurnCoordinator.ts` (new) — the coordinator port (atomic
  apply, deadlines, effects) driving `voiceController.ts`'s existing
  `handle`/session plumbing.
- `lib/voice/voiceController.ts` (existing, extend) — warm-socket
  `ensureWarm`/idle-reconnect/strike-budget logic (§2), and wiring the new
  turn coordinator's effects (start/stop capture, cancel/replace session) to
  the existing `startOpenAiSession`/`startGeminiSession`/`teardown`.
- `lib/ptt/*` stays untouched as the dictation path — it is legitimately
  separate (confirmed above) and is NOT the hub; do not merge it into the
  voice-turn reducer. A NEW system-wide PTT entry point is additive, not a
  rewrite of `ptt/machine.ts`.
- `main/overlay/shortcut.ts` — existing pattern for registering a global
  hotkey + IPC; the new system-wide PTT hotkey should follow this same shape
  rather than inventing a second mechanism.
- `main/bar/window.ts` — where the bar's visual response to voice-turn
  projection changes (listening/thinking/response-active) would hook in, but
  this extraction's scope is capability/state, not the bar's rendering — flag
  for the UI-wiring track, not this doc.

No blocking questions — this was pure extraction from existing source on both
sides.
