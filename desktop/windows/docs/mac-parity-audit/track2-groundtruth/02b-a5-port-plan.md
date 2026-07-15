# Track 2 · A5 — Warm-hub system-wide PTT (VoiceTurn reducer port)
## Implementation spec — build straight from this

Paths: **Windows** = `desktop/windows/src/renderer/src/…`. **Mac ref (READ-ONLY)** = `.worktrees/mac-ref/desktop/macos/Desktop/…` (frozen tag v0.12.72, commit `50d264c94`).

Research basis — read in full: `Sources/FloatingControlBar/VoiceTurnStateMachine.swift` (901 lines), `VoiceTurnCoordinator.swift` (334), `PTTVoiceOutputCoordinator.swift` (96); `Tests/VoiceTurnReducerTests.swift` (38 tests), `Tests/VoiceTurnCoordinatorTests.swift` (14), `Tests/PTTVoiceOutputCoordinatorTests.swift` (12). Windows: `lib/ptt/{machine,constants,gate}.ts`, `hooks/usePushToTalk.ts`, `capture/{PttCaptureHost,pttGraph}.ts`, `lib/voice/{voiceController,sessionMachine,providerSession,openaiSession,geminiSession,echoGate,pcmPlayer}.ts`, `lib/ptt/systemAudioMute.ts`, `components/bar/BarApp.tsx`, `main/bar/gesture.ts`.

`RealtimeHubController.swift` is a **facade** and is **NOT ported** (per brief). Its residual responsibilities are re-specified as a Windows-native module in §C.5.

> ⚠️ **§A below is the authoritative enumeration. Type it out from §A, not from the ground-truth doc, and not from memory of "what a voice state machine usually has."** Every name in §A.3/§A.4/§A.6/§A.7 is a verbatim Swift identifier. Inventing friendlier names (`commitRequested`, `routeResolved`, `responseCompleted`, …) breaks the 1:1 test port and hides the fencing bugs the tests exist to catch.

---

## 0. THE GROUND-TRUTH DOC IS WRONG / INCOMPLETE IN THESE PLACES — the Swift wins

`docs/mac-parity-audit/track2-groundtruth/02-warmhub-voiceturn-statemachine.md` is directionally sound (effects-as-data, FIFO drain, leases, warm-wait buffering, deadline values all check out). **These items are wrong, stale, or omit something load-bearing.**

| # | Doc says | Swift / Windows reality | Consequence if believed |
|---|---|---|---|
| **1** | "`VoiceTurnEvent` (line 241), **25 cases**" | **31 cases** (`VoiceTurnStateMachine.swift:241–336`). The doc's own list below that sentence actually has 31 — the count is just wrong. | Cosmetic, but it means the doc was not counted. Use §A.4. |
| **2** | Fencing section never mentions the **nil-identity rule** | `if let expected = turn.sessionID, sessionID != expected { stale }` (`:585`, `:589`, `:607`, `:611`). Swift `Optional` comparison: once the turn knows an ID, an event carrying **`nil`** is `nil != .some(x)` ⇒ **ALSO STALE**. Proven by `testProviderCallbackMissingKnownIdentityIsDropped`. | **THE BIGGEST TRAP.** The natural TS port (`if (ev.sessionID && ev.sessionID !== turn.sessionID)`) **inverts** this and lets through exactly the stale callback the test exists to catch. See §A.5. |
| **3** | `hubCommitAccepted` row: valid from "`.finalizing`, OR `.awaitingResponse` with deferred/bargeIn deadline pending" | Also requires **`routeMatchesHub(turn.route)`** (`:514`) — and `routeMatchesHub` is true for `.hub(_)` **AND `.hubWarmWait`** (`:783`). So a commit is accepted while the route is still `hubWarmWait`, and the handler then overwrites route → `.hub(sessionID)`. | A port that gates on `route.kind === 'hub'` only will reject a legitimate commit that raced `hubReady`. |
| **4** | Omits two `VoiceTurn` fields entirely | `providerFinished: Bool` (`:174`) and `deadlines: Set<VoiceTurnDeadline>` (`:175`) are **stored on the turn** and are load-bearing: `deadlineFired` is guarded by `turn.deadlines.contains(deadline)` (`:734`), and `providerFinished` is what lets tool/playback drain terminate in **either order**. | Drop either and the turn either never terminates or terminates twice. |
| **5** | Omits that a **terminal** turn still accepts one event | `:420–428`: a terminal turn accepts `deadlineFired(.hintVisibility)` (clears the hint, does not resurrect). `finish`/`cancel` on a terminal turn ⇒ `duplicateTerminalCount += 1` (not stale). Everything else ⇒ stale. | Terminal hint never clears, or a duplicate terminal is miscounted as stale. |
| **6** | Omits `toolStarted` phase behavior from `.playing` | `:623–630`: `toolStarted` sets `phase = .awaitingTools` **even while playing**, and **keeps `activeLease`**. `toolFinished` (`:640–644`) restores `.playing(lease.lane)` if the lease is still held. | Port that guards `toolStarted` to `.awaitingResponse` only drops mid-playback tool calls. |
| **7** | Gap analysis: Windows needs "**system-wide PTT wiring** — a new global-hotkey-driven call path… Electron `globalShortcut`" | **Already ships.** `main/bar/gesture.ts` (`SummonGesture`: `GetAsyncKeyState` sampling, 350 ms hold-vs-tap classify, 5-min stuck-key cap, `endIfActive()` on lock/suspend) → `window.omiBar.onPtt(phase)` → `beginHold()`/`endHold()` in `components/bar/BarApp.tsx`. | Wasted rebuild of a shipped, **more defensive** hotkey layer. **A5 is the turn model + hub route, NOT the gesture.** |
| **8** | "`lib/ptt/*` stays untouched as the dictation path… do not merge it into the voice-turn reducer" | Half right. It must stay as the **cascade transport**, but it cannot stay a **peer state machine**. Mac's `PushToTalkManager` keeps a **derived** `PTTState` via `legacyState(for: phase)` — the reducer is authoritative, the legacy machine is subordinate. | Two peer machines = two sources of truth = the exact bug class this port exists to kill. See §C.2/C.3. |
| **9** | Route case written `hub(sessionID:)` as if required | `case hub(sessionID: VoiceSessionID?)` (`:77`) — **optional**. `PushToTalkManager` emits `.selectRoute(route: .hub(sessionID: nil))` when the hub is already active. | A required-field TS union can't express the shipped call. |

Everything else in the doc (deadline values, terminal-reason list, `terminate()` ordering, the barge-in hub-handoff exception, the FIFO drain, the 256-entry timeline) **verified correct**.

---

## A. The reducer, exactly as Swift defines it

### A.1 Signature (`VoiceTurnStateMachine.swift:374`)

```
VoiceTurnReducer.reduce(_ current: VoiceTurnModel, _ event: VoiceTurnEvent) -> VoiceTurnReduction
                                                                              // { model, effects: [VoiceTurnEffect] }
```
Pure. No timers, no clock, no I/O, no randomness, no ID minting.

```ts
export function reduceVoiceTurn(
  model: VoiceTurnModel,
  event: VoiceTurnEvent,
  deadlines: VoiceTurnDeadlines = DEFAULT_VOICE_TURN_DEADLINES
): { model: VoiceTurnModel; effects: VoiceTurnEffect[] }
```

**CRITICAL — pre-event snapshot semantics.** Swift binds `guard var turn = model.turn` (`:411`) — a **value copy** — then writes through `model.turn?.…`. Guards therefore read the **pre-event** turn even after earlier lines in the same case have mutated `model.turn` (e.g. `toolFinished` at `:637` removes the call ID from `model.turn`, then at `:640` reads `turn.providerFinished` / `turn.activeLease` from the **snapshot**).

TS: make `VoiceTurnModel` and `VoiceTurn` `readonly`, take `const turn = model.turn` once, build a `next` turn immutably, and never re-read `model.turn` inside a case. An object-reference port aliases the two and the guards silently read post-mutation values.

### A.2 Typed IDs (`:5–63`) — brand them

Six distinct wrapper structs. Brand them in TS or the fencing rules become type-invisible and the compiler stops helping:

```ts
declare const brand: unique symbol
type Branded<K extends string, T = string> = T & { readonly [brand]: K }

export type VoiceTurnID     = Branded<'VoiceTurnID'>      // Swift: UUID
export type VoiceCaptureID  = Branded<'VoiceCaptureID', number>  // Swift: UInt64
export type VoiceSessionID  = Branded<'VoiceSessionID'>    // Swift: UUID
export type VoiceResponseID = Branded<'VoiceResponseID'>   // Swift: String (provider-supplied)
export type VoiceToolCallID = Branded<'VoiceToolCallID'>   // Swift: String (provider-supplied)
export type VoiceLeaseID    = Branded<'VoiceLeaseID'>      // Swift: UUID
```

Minting happens in the coordinator/host, **never** in the reducer.

### A.3 State types

**`VoiceTurnIntent`** (`:67`): `'hold' | 'locked' | 'agentFollowUp' | 'automation'`.

**`VoiceTurnRoute`** (`:74`) — orthogonal to phase:
```ts
export type VoiceTurnRoute =
  | { kind: 'undecided' }
  | { kind: 'hubWarmWait' }
  | { kind: 'hub'; sessionID: VoiceSessionID | null }   // ← nullable (:77)
  | { kind: 'omniSTT' }
  | { kind: 'deepgramBatch' }
  | { kind: 'deepgramLive' }
  | { kind: 'agentFollowUp' }
```
`routeMatchesHub(route)` (`:783`) = `kind === 'hub' || kind === 'hubWarmWait'`.

Windows mapping: `hub` + `hubWarmWait` are **net-new** (this feature). `omniSTT` ≈ the shipped `/v2/voice-message/transcribe` cascade. `deepgramBatch` / `deepgramLive` have **no Windows producer** — keep the cases anyway (free; keeps the ported tests faithful — `hubWarm` firing sets route to `deepgramBatch` at `:753`). See **D5**.

**`VoiceOutputLane`** (`:84`, raw values matter for telemetry):
`nativeRealtime` = `"native_realtime"` · `selectedVoiceFallback` = `"selected_voice_fallback"` · `deterministicAgentAck` = `"deterministic_agent_ack"` · `filler` = `"filler"` · `systemVoiceFallback` = `"system_voice_fallback"`.

**`VoiceOutputLease`** (`:92`): `{ id: VoiceLeaseID; turnID: VoiceTurnID; lane: VoiceOutputLane }` — value-equal.

**`VoiceTurnTerminalReason`** — **16** cases (`:98`), raw values are the telemetry strings:
`success` · `tooShort`=`too_short` · `silentRejected`=`silent_rejected` · `cancelled` · `interruptedByBargeIn`=`interrupted_by_barge_in` · `permissionDenied`=`permission_denied` · `captureFailed`=`capture_failed` · `transcriptionFailed`=`transcription_failed` · `providerFailed`=`provider_failed` · `providerNoResponse`=`provider_no_response` · `hubWarmTimeout`=`hub_warm_timeout` · `deferredCommitTimeout`=`deferred_commit_timeout` · `bargeInReplacementTimeout`=`barge_in_replacement_timeout` · `toolTimeout`=`tool_timeout` · `playbackFailed`=`playback_failed` · `cleanup`

**`VoiceTurnPhase`** (`:117`) — 9 cases:
```ts
export type VoiceTurnPhase =
  | { kind: 'idle' }
  | { kind: 'pendingLockDecision' }
  | { kind: 'recording' }
  | { kind: 'lockedRecording' }
  | { kind: 'finalizing' }
  | { kind: 'awaitingResponse' }
  | { kind: 'awaitingTools' }
  | { kind: 'playing'; lane: VoiceOutputLane }
  | { kind: 'terminal'; reason: VoiceTurnTerminalReason }
```
Derived **functions**, not stored fields:
- `isRecording(p)` (`:128`) = `recording | lockedRecording | pendingLockDecision`
- `isTerminal(p)` (`:132`) = `kind === 'terminal'`
- `acceptsProviderOutput(p)` (`:788`) = `awaitingResponse | awaitingTools | playing` — **and nothing else**. This is what stops a stray provider callback from mutating a turn that is still capturing mic audio.

**`VoiceTurnDeadline`** (`:138`) — 10, string-valued: `lock_decision`, `capture_start`, `hub_warm`, `transcription`, `provider_response`, `pending_tools`, `deferred_commit`, `barge_in_replacement`, `playback_drain`, `hint_visibility`.

**`VoiceTurnUIProjection`** (`:151`) — the **only** thing the UI may read:
```ts
export type VoiceTurnUIProjection = {
  readonly isListening: boolean       // default false
  readonly isLocked: boolean
  readonly isFollowUp: boolean
  readonly transcript: string         // default ''
  readonly hint: string               // default ''
  readonly isThinking: boolean
  readonly isResponseWaiting: boolean
  readonly isResponseActive: boolean
}
export const IDLE_PROJECTION: VoiceTurnUIProjection = { …all false / '' }   // Swift: .idle (:161)
```

**`VoiceTurn`** (`:164`) — **every field, none optional-by-omission**:
```ts
export type VoiceTurn = {
  readonly id: VoiceTurnID
  readonly intent: VoiceTurnIntent
  readonly phase: VoiceTurnPhase
  readonly route: VoiceTurnRoute
  readonly captureID: VoiceCaptureID | null
  readonly sessionID: VoiceSessionID | null
  readonly responseID: VoiceResponseID | null
  readonly pendingToolCallIDs: ReadonlySet<VoiceToolCallID>
  readonly activeLease: VoiceOutputLease | null
  readonly providerFinished: boolean          // ← doc omits this
  readonly deadlines: ReadonlySet<VoiceTurnDeadline>   // ← doc omits this
  readonly projection: VoiceTurnUIProjection
  readonly terminalReason: VoiceTurnTerminalReason | null
}
```
**Constructor** (`:179`) — `newVoiceTurn(id, intent)`:
- `phase` = `intent === 'locked' ? lockedRecording : recording`
- `route` = `intent === 'agentFollowUp' ? agentFollowUp : undecided`
- `pendingToolCallIDs` = ∅, `providerFinished` = false, `deadlines` = ∅
- `projection` = `{ isListening: true, isLocked: intent==='locked', isFollowUp: intent==='agentFollowUp', transcript:'', hint:'', isThinking:false, isResponseWaiting:false, isResponseActive:false }`

**`VoiceTurnTerminalRecord`** (`:199`): `{ turnID, reason, route }` (route defaults `undecided`).

**`VoiceTurnModel`** (`:215`):
```ts
export type VoiceTurnModel = {
  readonly turn: VoiceTurn | null
  readonly lastTerminal: VoiceTurnTerminalRecord | null
  readonly staleEventCount: number
  readonly invalidTransitionCount: number
  readonly duplicateTerminalCount: number
}
export const IDLE_VOICE_TURN_MODEL: VoiceTurnModel = { turn: null, lastTerminal: null, staleEventCount: 0, invalidTransitionCount: 0, duplicateTerminalCount: 0 }
```

### A.4 The 31 events — VERBATIM Swift names (`:241–336`)

**Use these names.** Every one carries a `turnID` except `cleanup` and `reset` (`:295` returns `nil` for both).

| # | Event (Swift name) | Payload |
|---|---|---|
| 1 | `start` | `turnID, intent` |
| 2 | `openLockWindow` | `turnID` |
| 3 | `lock` | `turnID` |
| 4 | `finalize` | `turnID` |
| 5 | `captureStarted` | `turnID, captureID` |
| 6 | `captureFailed` | `turnID, captureID: VoiceCaptureID?, message: String` |
| 7 | `selectRoute` | `turnID, route` |
| 8 | `hubReady` | `turnID, sessionID` |
| 9 | `hubCommitAccepted` | `turnID, sessionID, responseID: VoiceResponseID?` |
| 10 | `hubCommitDeferred` | `turnID` |
| 11 | `hubCommitDeferredForReplacement` | `turnID` |
| 12 | `transcriptionStarted` | `turnID` |
| 13 | `transcriptionFinal` | `turnID, text` |
| 14 | `transcriptionFailed` | `turnID, message` |
| 15 | `providerResponseStarted` | `turnID, sessionID: VoiceSessionID?, responseID: VoiceResponseID?` |
| 16 | `providerTurnFinished` | `turnID, sessionID: VoiceSessionID?, responseID: VoiceResponseID?` |
| 17 | `toolStarted` | `turnID, callID` |
| 18 | `toolFinished` | `turnID, callID` |
| 19 | `playbackStarted` | `turnID, lease: VoiceOutputLease` |
| 20 | `playbackDrained` | `turnID, leaseID` |
| 21 | `playbackFailed` | `turnID, leaseID: VoiceLeaseID?, message` |
| 22 | `transcriptChanged` | `turnID, text` |
| 23 | `hintChanged` | `turnID, text` |
| 24 | `responseWaitingChanged` | `turnID, active: Bool` |
| 25 | `responseActiveChanged` | `turnID, active: Bool` |
| 26 | `clearPresentation` | `turnID` |
| 27 | `deadlineFired` | `turnID, deadline` |
| 28 | `finish` | `turnID, reason` |
| 29 | `cancel` | `turnID, reason` |
| 30 | `cleanup` | *(none — turn-independent)* |
| 31 | `reset` | *(none — turn-independent)* |

`diagnosticLabel` (`:301`) is a **payload-free** snake_case literal per case (`"capture_started"`, `"hub_commit_deferred_for_replacement"`, …). It must **never** contain transcript, hint, message, or ID text. Two Swift tests assert this — **port both**.

TS:
```ts
export type VoiceTurnEvent =
  | { type: 'start'; turnID: VoiceTurnID; intent: VoiceTurnIntent }
  | { type: 'captureFailed'; turnID: VoiceTurnID; captureID: VoiceCaptureID | null; message: string }
  | { type: 'providerResponseStarted'; turnID: VoiceTurnID; sessionID: VoiceSessionID | null; responseID: VoiceResponseID | null }
  | { type: 'cleanup' }
  | { type: 'reset' }
  // … 26 more
export function turnIDOf(e: VoiceTurnEvent): VoiceTurnID | null
export function diagnosticLabel(e: VoiceTurnEvent): string
```

### A.5 Fencing — four levels. This is the entire point of the port.

**Level 0 — turn-independent events, handled BEFORE any guard, in this order (`:378–409`):**

1. **`start`** (`:378`):
   - if an active **non-terminal** turn exists → `terminate(interruptedByBargeIn)` **first** (emits its full effect list, incl. `cancelAllDeadlines(oldTurnID)`);
   - else if a **terminal** turn still holds deadlines → emit `cancelAllDeadlines(oldTurnID)`;
   - then `model.turn = newVoiceTurn(turnID, intent)`; **reset all three anomaly counters to 0**; `schedule(captureStart, 3s)`. Return.
2. **`cleanup`** (`:392`): if a turn exists → `terminate(cleanup)`. Return.
3. **`reset`** (`:399`): if turn is `null` or terminal → cancel its deadlines (if any) and set `turn = null`. If **non-terminal** → `invalidTransition` (does **not** clear the turn). Return.

**Level 1 — top-of-reduce turn guard (`:411–418`):**
```
if (model.turn == null)            -> stale
if (turnIDOf(event) !== turn.id)   -> stale
```
`stale` = `staleEventCount += 1` + effect `staleEventDropped(turnID: event.turnID, event: label)`. **No state mutation.** This is the single choke point that makes a superseded turn's late callbacks inert.

**Level 2 — terminal-phase special case (`:420–436`):**
- `deadlineFired(hintVisibility)` **and the turn still holds that deadline** → remove it, set `projection.hint = ''`, return. (The **only** event a terminal turn accepts.)
- `finish` / `cancel` → `duplicateTerminalCount += 1`, dropped (**not** stale).
- everything else → `stale`.

**Level 3 — per-event nested identity guards. THE TRAP.**

Swift (`:585`, `:589`, `:607`, `:611`, `:518`):
```swift
if let expected = turn.sessionID, sessionID != expected { return stale }
```
`sessionID` here is `VoiceSessionID?`. If the turn already knows a session and the event carries **`nil`**, Swift evaluates `nil != .some(x)` ⇒ `true` ⇒ **STALE**. Confirmed by `testProviderCallbackMissingKnownIdentityIsDropped`.

The natural TS port is **BACKWARDS** and lets exactly that callback through:
```ts
if (ev.sessionID && ev.sessionID !== turn.sessionID) return stale   // ❌ WRONG
```

Correct — one helper, used at **every** ID-carrying handler:
```ts
/** Swift `if let expected = stored, incoming != expected { stale }` semantics.
 *  unknown-stored  -> accept (and adopt).
 *  known-stored    -> incoming must match EXACTLY; `null` incoming is STALE. */
function fenceID<T>(stored: T | null, incoming: T | null): boolean {
  if (stored == null) return true
  return incoming === stored
}
```
⚠️ **Two deliberate exceptions where Swift is NOT symmetric — do not "fix" them:**
- `hubCommitAccepted` (`:518`): `guard turn.sessionID == nil || turn.sessionID == sessionID` — here the event's `sessionID` is **non-optional**, so this is a plain equality fence.
- `captureFailed` (`:484`): `if let expected = turn.captureID, let captureID, expected != captureID { stale }` — **both** must be non-nil to be stale. A `captureFailed` with a `nil` captureID is **accepted** (a failure before capture ever started). Opposite of the provider rule.

### A.6 Every transition, exactly (`:438–778`)

Ordering below is the Swift switch order. "→ stale/invalid" means the guard fails and the reducer returns with **no state change**.

| Event | Guard (else) | Effects & state change |
|---|---|---|
| `openLockWindow` `:439` | `phase == recording` (else **invalid**) | phase→`pendingLockDecision`; `isListening=true`, `isLocked=false`; `schedule(lockDecision, 0.4s)` |
| `lock` `:450` | `phase == recording \|\| pendingLockDecision` (else **invalid**) | `cancel(lockDecision)`; phase→`lockedRecording`; `intent='locked'`; `isListening=true`, `isLocked=true` |
| `finalize` `:461` | `isRecording(phase)` (else **invalid**) | `cancel(lockDecision)`, `cancel(captureStart)`; phase→`finalizing`; `isListening=false`, `isLocked=false`, `isThinking=true`; effect **`stopCapture(turnID, turn.captureID)`** |
| `captureStarted` `:474` | `isRecording(phase)` (else **stale + `stopCapture(captureID)`** — kills the orphan capture) | `cancel(captureStart)`; `turn.captureID = captureID` |
| `captureFailed` `:483` | both IDs non-nil and different ⇒ **stale** | `terminate(captureFailed)` |
| `selectRoute` `:490` | `isRecording(phase) \|\| phase == finalizing` (else **invalid**) | `turn.route = route`; if `route == hubWarmWait` → `schedule(hubWarm, 1s)` |
| `hubReady` `:500` | `turn.route == hubWarmWait` (else **stale**) | `cancel(hubWarm)`; `route = hub(sessionID)`; `turn.sessionID = sessionID` |
| `hubCommitAccepted` `:509` | `(phase == finalizing) \|\| (phase == awaitingResponse && deadlines ∋ deferredCommit ∪ bargeInReplacement)` **AND** `routeMatchesHub(route)` (else **invalid**); then `turn.sessionID == nil \|\| == sessionID` (else **stale**) | `route = hub(sessionID)`; `sessionID`, `responseID` set; phase→`awaitingResponse`; `isThinking=true`, `isResponseWaiting=true`; `cancel(deferredCommit)`, `cancel(bargeInReplacement)`; `schedule(providerResponse, 20s)` |
| `hubCommitDeferred` `:532` | `phase == finalizing` **AND** `routeMatchesHub` (else **invalid**) | phase→`awaitingResponse`; `isThinking=true`, `isResponseWaiting=true`; `schedule(deferredCommit, 8s)` |
| `hubCommitDeferredForReplacement` `:542` | same guard | phase→`awaitingResponse`; same projection; `schedule(bargeInReplacement, 8s)` |
| `transcriptionStarted` `:556` | `phase == finalizing` (else **invalid**) | `isThinking=true`; `transcript = "Transcribing…"`; `schedule(transcription, 12s)` |
| `transcriptionFinal` `:565` | `phase == finalizing` (else **stale**) | `cancel(transcription)`; phase→`awaitingResponse`; `transcript = text`; `isThinking=true`, `isResponseWaiting=true`; `schedule(providerResponse, 20s)` |
| `transcriptionFailed` `:577` | **none** (any non-terminal phase) | `terminate(transcriptionFailed)` |
| `providerResponseStarted` `:580` | `acceptsProviderOutput(phase)` (else **invalid**); then `fenceID(turn.sessionID, ev.sessionID)` and `fenceID(turn.responseID, ev.responseID)` (else **stale**) | `cancel(providerResponse)`, `cancel(deferredCommit)`, `cancel(bargeInReplacement)`; adopt `sessionID ?? existing`, `responseID ?? existing`; `isThinking=false`, `isResponseWaiting=false`, `isResponseActive=true`. **Phase unchanged.** |
| `providerTurnFinished` `:602` | same guards | `providerFinished = true`; cancel the same 3 deadlines; **if `activeLease == null` AND `pendingToolCallIDs` empty → `terminate(success)`**, else stay |
| `toolStarted` `:623` | `acceptsProviderOutput(phase)` (else **invalid**) | `pendingToolCallIDs += callID`; **phase→`awaitingTools`** (even from `playing`; `activeLease` is kept); `schedule(pendingTools, 30s)` |
| `toolFinished` `:632` | `pendingToolCallIDs ∋ callID` (else **stale**) | remove; **if now empty:** `cancel(pendingTools)`; then — `providerFinished && activeLease == null` → `terminate(success)`; else `activeLease != null` → phase→`playing(lease.lane)`; else → phase→`awaitingResponse` + `schedule(providerResponse, 20s)` |
| `playbackStarted` `:651` | `acceptsProviderOutput(phase)` (else **invalid**); `lease.turnID == turn.id` (else **stale**); a **different** already-active lease (else **invalid** — a real bug, not staleness) | `cancel(providerResponse)`; `activeLease = lease`; phase→`playing(lease.lane)`; `isThinking=false`, `isResponseWaiting=false`, `isResponseActive=true`; `schedule(playbackDrain, 30s)` |
| `playbackDrained` `:672` | `turn.activeLease?.id == leaseID` (else **stale**) | `cancel(playbackDrain)`; `activeLease = null`; then — `providerFinished && no pending tools` → `terminate(success)`; else pending tools → phase→`awaitingTools`, `isResponseActive=false`, `isResponseWaiting=false`; else → phase→`awaitingResponse`, `isResponseActive=false`, **`isResponseWaiting=true`**, `schedule(providerResponse, 20s)` |
| `playbackFailed` `:693` | if `leaseID != nil` it must equal the active lease (else **stale**); a `nil` leaseID always applies | `terminate(playbackFailed)` |
| `transcriptChanged` `:700` | none | `projection.transcript = text` |
| `hintChanged` `:703` | none | `projection.hint = text`; if `text === ''` → `cancel(hintVisibility)`, else `schedule(hintVisibility, 2s)` |
| `responseWaitingChanged` `:711` | none | `isResponseWaiting = active`; **`isThinking = active`** (both) |
| `responseActiveChanged` `:715` | none | `isResponseActive = active`; if `active` → `isThinking=false`, `isResponseWaiting=false` |
| `clearPresentation` `:722` | none | projection → all-false/empty; `cancel(hintVisibility)` |
| `deadlineFired` `:733` | `turn.deadlines ∋ deadline` (else **stale**) | remove it, then per-deadline (§A.7) |
| `finish` / `cancel` `:773` | none (non-terminal) | `terminate(reason)` |

**`deadlineFired` dispatch (`:739–771`):**

| Deadline | Default (`:359`) | Terminal? | Behavior |
|---|---|---|---|
| `lockDecision` | **0.4 s** | no | must still be `pendingLockDecision` (else **stale**) → phase→`finalizing`; `isListening=false`, `isThinking=true`; effect `stopCapture(turn.captureID)` |
| `captureStart` | **3 s** | yes | `terminate(captureFailed)` |
| `hubWarm` | **1 s** | **NO** | effect `fallbackToTranscription(turnID, reason: hubWarmTimeout)`; `route = deepgramBatch`; **if phase is still `finalizing` → `schedule(transcription, 12s)`**. **The turn CONTINUES.** The single most important non-terminal deadline in the system. |
| `transcription` | **12 s** | yes | `terminate(transcriptionFailed)` |
| `providerResponse` | **20 s** | yes | `terminate(providerNoResponse)` |
| `pendingTools` | **30 s** | yes | `terminate(toolTimeout)` |
| `deferredCommit` | **8 s** | yes | `terminate(deferredCommitTimeout)` |
| `bargeInReplacement` | **8 s** | yes | `terminate(bargeInReplacementTimeout)` |
| `playbackDrain` | **30 s** | yes | `terminate(playbackFailed)` |
| `hintVisibility` | **2 s** | no | `projection.hint = ''` |

`Deadlines` is a **config struct, not constants** (`:359`) — port as an injectable object so tests can shorten it and D2 can vary it per route:
```ts
export const DEFAULT_VOICE_TURN_DEADLINES = {
  lockDecision: 0.4, captureStart: 3, hubWarm: 1, transcription: 12,
  providerResponse: 20, pendingTools: 30, deferredCommit: 8,
  bargeInReplacement: 8, playbackDrain: 30, hintVisibility: 2
} as const   // SECONDS (Swift TimeInterval)
```

**Deadline helpers — get these exactly right:**
- `schedule(d, after)` (`:797`): **always** inserts into `turn.deadlines` and **always** emits `scheduleDeadline`. Re-scheduling an already-held deadline is legal and **resets the timer** (the coordinator cancels the old handle first). `hintChanged` relies on this.
- `cancel(d)` (`:808`): emits `cancelDeadline` **only if the deadline was actually present** (`Set.remove` returned non-nil). A port that unconditionally emits will produce spurious effects and break `testTerminalEffectAndCleanupAreExactlyOnce`-style counting.

### A.7 `terminate()` — the single terminal path (`:817–878`)

```
if isTerminal(turn.phase)   -> duplicateTerminalCount += 1; RETURN (no effects)
record = { turnID, reason, route: turn.route }

if (turn.captureID != null || isRecording(turn.phase) || turn.phase == finalizing)
    emit stopCapture(turnID, turn.captureID)

preservesHubForBargeInHandoff = (reason == interruptedByBargeIn) && (route.kind == 'hub')

if (!preservesHubForBargeInHandoff)  emit cancelHub(turnID, turn.route)
if (turn.activeLease != null && !preservesHubForBargeInHandoff)
                                     emit stopPlayback(turnID, lease.id)
emit cancelAllDeadlines(turnID)
emit terminal(record)

turn.deadlines = ∅ ; turn.pendingToolCallIDs = ∅ ; turn.activeLease = null
turn.terminalReason = reason ; turn.phase = terminal(reason) ; turn.projection = IDLE

hint = terminalHint(reason)                    // table below
if (hint != null) {
    turn.projection.hint = hint
    turn.deadlines += hintVisibility           // inserted DIRECTLY, not via schedule()
    emit scheduleDeadline(turnID, hintVisibility, 2s)
}
model.turn = turn ; model.lastTerminal = record
```

**The emission ORDER is load-bearing** — `stopCapture` **before** `cancelHub`, or a trailing PCM chunk revives the socket. Preserve it exactly.

**`preservesHubForBargeInHandoff` (`:831`) is the feature.** When a barge-in supersedes a turn that was on the **hub** route, `terminate()` **skips `cancelHub` AND `stopPlayback`** so the successor turn inherits the live warm socket. Get this wrong and every barge-in tears the hub down — i.e. warm-hub PTT does not exist. Covered by `testHubBargeInPreservesProviderRuntimeForAtomicHandoff`.

**`terminalHint(reason)` (`:850`) — a pure function. Port verbatim:**

| Reason | Hint |
|---|---|
| `tooShort` | `"Hold longer to record"` |
| `captureFailed` | `"Microphone unavailable — try again"` |
| `transcriptionFailed` | `"Couldn't transcribe that — try again"` |
| `providerFailed`, `providerNoResponse`, `deferredCommitTimeout`, `bargeInReplacementTimeout`, `toolTimeout` | `"Voice response failed — try again"` |
| `playbackFailed` | `"Audio playback failed"` |
| `success`, `silentRejected`, `cancelled`, `interruptedByBargeIn`, **`permissionDenied`**, `hubWarmTimeout`, `cleanup` | **`nil` — no hint** |

⚠️ Note `permissionDenied` gets **no** hint in Swift (`:863`), even though it reads like it should share `captureFailed`'s. **Do not "fix" this** — port it as-is and let a Windows-side hint (if wanted) be a separate, explicit decision.

### A.8 Effects (`VoiceTurnEffect`, `:338`)

```ts
export type VoiceTurnEffect =
  | { kind: 'scheduleDeadline'; turnID: VoiceTurnID; deadline: VoiceTurnDeadline; after: number }  // seconds
  | { kind: 'cancelDeadline'; turnID: VoiceTurnID; deadline: VoiceTurnDeadline }
  | { kind: 'cancelAllDeadlines'; turnID: VoiceTurnID }
  | { kind: 'stopCapture'; turnID: VoiceTurnID; captureID: VoiceCaptureID | null }
  | { kind: 'cancelHub'; turnID: VoiceTurnID; route: VoiceTurnRoute }              // ← carries the OLD route
  | { kind: 'fallbackToTranscription'; turnID: VoiceTurnID; reason: VoiceTurnTerminalReason }
  | { kind: 'stopPlayback'; turnID: VoiceTurnID; leaseID: VoiceLeaseID | null }
  | { kind: 'terminal'; record: VoiceTurnTerminalRecord }                          // { turnID, reason, route }
  | { kind: 'staleEventDropped'; turnID: VoiceTurnID | null; event: string }       // event = diagnosticLabel
  | { kind: 'invalidTransition'; turnID: VoiceTurnID | null; event: string; phase: VoiceTurnPhase | null }
```
`cancelHub` carrying the **pre-terminal** route is deliberate — `testHubTerminalCleanupCarriesOldRouteInEffectPayload` asserts it; the host needs to know *which* transport to tear down.

### A.9 PR-1 module surface

`lib/voice/turn/voiceTurnMachine.ts` exports every type above plus `reduceVoiceTurn`, `IDLE_VOICE_TURN_MODEL`, `DEFAULT_VOICE_TURN_DEADLINES`, `IDLE_PROJECTION`, `projectionOf(model)`, `diagnosticLabel(event)`, `turnIDOf(event)`, `isRecording`, `isTerminal`, `acceptsProviderOutput`, `routeMatchesHub`, `terminalHint`.
Imports **nothing but types**. Contains **no `Date.now()`**, no `setTimeout`, no IPC, no `crypto.randomUUID()`.

---

## B. The coordinator contract (`VoiceTurnCoordinator.swift`)

Port to `lib/voice/turn/voiceTurnCoordinator.ts` as a **class**, one instance in the owning renderer (§C.1) — **not** a module global. (Mac gets away with `@MainActor` singletons; Windows has three renderers.)

### B.1 FIFO, non-reentrant — operationally (`send()`, `:154–170`)

```ts
send(event: VoiceTurnEvent): void {
  this.pending.push(event)
  if (this.draining) return            // ← the ENTIRE non-reentrancy rule
  this.draining = true
  try {
    for (let i = 0; i < this.pending.length; i++) this.apply(this.pending[i])
  } finally {
    this.pending.length = 0            // Swift: removeAll(keepingCapacity:) inside a `defer`
    this.draining = false
  }
}
```

- **Index-based loop, NOT `shift()`.** The array is *expected* to grow during iteration — that growth **is** the mechanism.
- Swift clears + unsets the flag in a `defer`, so a thrown effect handler still leaves the coordinator drainable. The TS `finally` must do the same, or one throwing handler wedges PTT permanently.

**Can an effect enqueue another event mid-drain? YES — and it must not recurse.**
A `send()` called from inside an **effect handler** or a **snapshot handler** appends to `pending` and returns immediately (`draining` is still true); the outer loop reaches it at the next index. **Call-stack depth stays 1.** `testEffectReentrantTerminalEventRunsAfterCurrentEffectReturns` and `testSnapshotReentrantEventsDrainFIFOWithoutRecursiveCallbacks` assert depth-1 + ordering — **port both.**

**Events arriving mid-drain** (deadline fires, IPC, provider callback) take the identical path: strict FIFO append to the same `pending` array, reduced only after the in-flight event is **fully published** (B.2). No event is ever reduced against a half-applied model.

### B.2 Atomic apply (`apply()`, `:178–186`)

For **one** event, strictly in this order:

1. `reduceVoiceTurn(this.model, event)` → `{ model, effects }`
2. **assign `this.model`** — the new model is visible to everything below
3. append a `VoiceTurnTimelineEntry` to the ring buffer (cap **256**, `:119`; fields: `sequence, turnID, event label, phaseBefore, phaseAfter, route, terminalReason, staleEventCount, invalidTransitionCount` — all low-cardinality labels, **never payloads**)
4. `process(effects)` — **in emission order**
5. `presenter.apply(projectionOf(this.model))`
6. `snapshotHandler(this.model)`

An event is **fully published** (model + effects + UI + snapshot) before the next is reduced. That is precisely what makes a nested `send` safe: it observes a consistent world.

### B.3 `process()` (`:219–257`) — effects vs. state transitions

**State transitions are the reducer's job. The coordinator owns only timers + diagnostics:**

- `scheduleDeadline` → `deadlineCancellations[{turnID,deadline}]?.cancel()` **first**, then `scheduler.schedule(seconds, () => { delete handle; this.send({type:'deadlineFired', turnID, deadline}) })` (`:259`)
- `cancelDeadline` → cancel + drop that one handle
- `cancelAllDeadlines` → cancel + drop **every** handle whose key's `turnID` matches
- `terminal` → `recordVoiceTurnTerminal(reason, route, staleEventCount, invalidTransitionCount)`
- `staleEventDropped` / `invalidTransition` → `recordVoiceTurnAnomaly(kind, phase, route)` + a bounded log

**Then EVERY effect — including those five — is forwarded to `effectHandler`.** The coordinator does **no I/O beyond timers**; the host does all real work.

Deadline fencing falls out for free: the key is `{turnID, deadline}`, so a cancelled handle can never fire into a later turn — and even a rogue timer that does fire is rejected by the reducer's Level-1 guard. `testCancelledDeadlineCannotMutateLaterTurn` — port it.

Scheduler is **injected**:
```ts
export type DeadlineScheduler = {
  schedule(seconds: number, fire: () => void): { cancel(): void }
}
```
Tests inject a manual clock; production wraps `setTimeout`.

### B.4 Remaining coordinator API

- **`begin(intent, id = mintTurnID())`** (`:145`) — if the current turn is **terminal**, `send(reset)` **first**, then `send(start)`. Returns the id. This is the **only** place a `VoiceTurnID` is manufactured for a real PTT press.
- **`activeTurnID` / `activeTurn`** (`:127`) — **`null` whenever the turn is terminal.** Hosts must never treat a terminal turn as active. (A7c's `canReplaceSession` is built on this — §E.)
- **`projection`** (`:129`) — `model.turn?.projection ?? IDLE_PROJECTION`.
- **`setUnscopedResponseActive(active)`** (`:199`) — **no-op if a turn is active.** Lets non-PTT chat playback drive the pill without a turn. Windows needs this: the Home chat surface and A1's chunked bar TTS both play audio outside a PTT turn. `testUnscopedPlaybackUsesPresenterButCannotOverrideActivePTTTurn`.
- **`reset()`** (`:207`) — `send(cleanup)` + `send(reset)` (two separate drains), cancel every outstanding handle, apply `IDLE_PROJECTION`.
- **`timelineSnapshot()`** — diagnostics export.
- **`PTTBarPresenter`** (`:48–87`) — projection → bar state. Key derived rule: **expand-for-voice = `isListening || hint !== ''`**, and the expand/collapse call fires **only on a change** of that boolean. On Windows this is an orb/bar store update, not a new component.

---

## C. Mapping onto Windows

### C.1 Window ownership — decide once, everything follows (**decision D1**)

Three renderers matter:
- **bar** — gesture + orb (`BarApp.tsx`, `usePushToTalk`)
- **main** — `voiceController` (session machine, token mint, A1 chunked TTS, `interruptCurrentResponse`), `pcmPlayer`, chat send, auth
- **capture window** — owns the mic graph; `PttCaptureHost` routes `ptt-chunk` / `ptt-levels` / `ptt-capped` / `ptt-drained` / `ptt-error` back to the **`ownerId`** that issued the command (`captureEmit(event, ownerId)`)

**RECOMMENDATION: the coordinator + hub live in the MAIN window renderer.**
- `voiceController.ts`, the A1 TTS pipeline, `interruptCurrentResponse()`, `pcmPlayer`, chat send and the auth/token mint are **all already there**. A bar-owned hub would need every one of them over IPC.
- The bar→main hop already exists and ships today: `window.omiBar.interruptTts()`.
- The capture window streams PCM to **whichever window issued the command** — so main can own hub audio with **zero capture-layer changes**.

**Cost:** the orb's `ptt-levels` must still reach the bar. Cheapest fix: `captureEmit(event, ownerId)` already takes an owner — add a **levels-only fan-out to a second owner**. (Alternative: the bar keeps issuing capture commands and main receives PCM via a main-process relay — strictly more code.)

Under this design the bar is a thin driver: `beginHold()` / `endHold()` → IPC → `coordinator.begin('hold')` / `send(finalize)`; the projection is broadcast back for the orb + hint.

### C.2 What the reducer now OWNS

- **Turn identity** (`VoiceTurnID`) and every ID scoped to it.
- **Phase.** `lib/ptt/machine.ts`'s `idle|holding|draining|streamFinalize|batching` becomes a **derived transport state** — exactly what Mac does (`PushToTalkManager.legacyState(for: phase)`).
- **Terminal reasons + hints.** The machine's `showHint` / `showError` effects are **deleted**; `terminal(record)` + `terminalHint(reason)` replace them.
- **Turn-killing deadlines.** `WATCHDOG_MS` (25 s) and `BATCH_TIMEOUT_MS` (20 s) collapse onto the reducer's `transcription` deadline — **one timer owns turn death** (see **D2** for the value). `STREAM_FINALIZE_DEADLINE_MS` (3 s) **stays** as a transport-internal timer that reports failure by emitting `transcriptionFailed` — it has no turn-level meaning.
- **Barge-in.** Today: `onHoldStart: () => window.omiBar.interruptTts()` (A1). After A5: `coordinator.begin('hold')` → reducer terminates the prior turn `interruptedByBargeIn` → `stopPlayback(leaseID)` effect → host calls `voiceController.interruptCurrentResponse(leaseID)`. **Same function, now turn- and lease-fenced.** Strictly better; nothing is lost.
- **Output leases** (§C.4 / A1).

### C.3 What `lib/ptt/*` KEEPS (do not regress)

`lib/ptt/machine.ts` **survives** as the **cascade transport sequencer** under the `omniSTT` route. It keeps: capture start/drain sequencing, `DRAIN_MS` (300), buffer-cap handling (`MAX_BUFFER_BYTES` = 4.5 min), `gateDecision` (`too-short` / `dead-mic` / `silent`), stream-vs-batch selection, and the `/v2/voice-message/transcribe` call (`BATCH_TRANSCRIBE_PATH`, `batchTranscribeParams` — A2's `keywords` param intact).
`lib/ptt/constants.ts` and `lib/ptt/gate.ts` are **unchanged**.

Effect / verdict re-targeting — **real Swift event names**:

| `PttEffect` / verdict today | after A5 |
|---|---|
| `commit(text)` | → event **`transcriptionFinal(turnID, text)`** |
| `setLiveText(text)` | → event **`transcriptChanged(turnID, text)`** |
| start of the batch/stream request | → event **`transcriptionStarted(turnID)`** (this is what arms the `transcription` deadline) |
| `showError(message)` | → event **`transcriptionFailed(turnID, message)`** — the reducer supplies the hint |
| gate `too-short` | → event **`finish(turnID, 'tooShort')`** (hint: "Hold longer to record") |
| gate `silent` | → event **`finish(turnID, 'silentRejected')`** (**no hint** — matches today's silent discard) |
| gate `dead-mic` | → event **`finish(turnID, 'captureFailed')`** (hint: "Microphone unavailable — try again") |
| `showHint('too-long')` | **stays local** — a non-terminal warning about an ongoing hold; the reducer has no case for it and its `hintVisibility` is 2 s vs. `TOO_LONG_HINT_MS` 4 s. See **D6**. |
| `captureEnded` | → event **`captureStarted`**/nothing; capture **stop** is now an *effect* (`stopCapture`), not an event. Report actual stop as a no-op or drop it. |
| RELEASE (key-up) | → event **`finalize(turnID)`** |
| CANCEL | → event **`cancel(turnID, 'cancelled')`** |
| `startCapture` / `startDrain` / `stopCapture` / `startStream` / `stopStream` / `startBatch` / `abortBatch` / `sendFinalize` / `startVocabulary` | unchanged transport effects |
| `armWatchdog` | **DELETED** — the reducer's `transcription` deadline replaces it |

### C.4 Shipped Track-2 behaviors — OWN vs. LEAVE IN PLACE

| Feature | Today | After A5 | Risk |
|---|---|---|---|
| **A1** — chunked bar TTS + cross-window barge-in interrupt | `voiceController.ts`: `runChunkedTts`, `speakText`, `playSystemVoice`, `FILLER_PHRASES`/`startFiller`/`cancelFiller`, `resetTtsPipeline`, `interruptCurrentResponse()`; bar calls `window.omiBar.interruptTts()` on hold-start | **Reducer OWNS the turn-level half.** Playback becomes **lease-holding lanes**: `speakText` → `selectedVoiceFallback`; `playSystemVoice` → `systemVoiceFallback`; filler → `filler` (the **only** lane that yields — `fillerCanYield`); hub audio → `nativeRealtime`; A10 ack → `deterministicAgentAck` (sets `providerOutputSuppressed`). Playback start/drain/fail emit `playbackStarted(lease)` / `playbackDrained(leaseID)` / `playbackFailed(leaseID)`. `interruptCurrentResponse(leaseID)` is driven by the `stopPlayback` effect. Non-PTT chat TTS keeps working via `setUnscopedResponseActive(true)`. | **HIGHEST.** The `leaseID` must thread through `runChunkedTts`'s abort controller (`currentTtsAbort`), or a barge-in cancels the **successor** turn's audio. **PR 3 lands leases + tests BEFORE any wiring.** |
| **A4** — system-audio mute (`lib/ptt/systemAudioMute.ts`) | keyed on `PttEffect['kind']`: `startCapture` → mute (pref-gated `pttMuteSystemAudio`), `startDrain`/`stopCapture` → restore (unconditional); driven from `usePushToTalk`; unmount → unconditional `restoreSystemAudio()` | **STAYS — but must also fire on the hub route** (hub turns capture the mic too). Re-key `systemAudioActionFor` to the **turn** boundary: mute at capture start; restore on the reducer's `stopCapture` effect **and** unconditionally on `terminal`. Keep the pref gate. Keep "RESTORE IS UNCONDITIONAL". **Keep the explicit deviation comment at `systemAudioMute.ts:19–24` — do NOT add Mac's restore-before-TTS hook**; it stays correct because `terminate()` provably emits `stopCapture` before `stopPlayback`/playback ever starts. | **Medium.** Easy to ship a hub turn that never unmutes. **Required test: every one of the 16 terminal reasons ⇒ exactly one restore.** |
| **A6** — Gemini `interruptedTurnActive` trailing-audio gate (`geminiSession.ts`, `createGeminiMessageHandler`) | drops post-interrupt PCM until `turnComplete` | **LEAVE EXACTLY WHERE IT IS.** It is a *provider-protocol* concern (Gemini keeps streaming a cancelled generation) that sits **below** the reducer. The reducer's fencing is turn-level and fences a **different thing**. **Do not "simplify" it away on the grounds that the reducer now fences turns.** | Low, if respected. |
| **A7a/b** — device-change capture rebuild + silent-mic escalation ladder | `usePushToTalk` `DeadMicPolicy`/`applyDeadMicTurn` (rebuild at 2 consecutive silent turns, escalate at 3); capture window `rebuildWarmGraph('silent_mic', false)` | **STAYS.** Feed it from the reducer's terminal reason (`silentRejected` / `captureFailed`) instead of the local gate result, so it counts **hub** turns too. | Low. |
| **A8** — auto model selection | `resolveEffectiveVoiceProvider` / autoModelSelector; `VoiceProviderSetting = 'auto' \| VoiceProvider` | **STAYS.** The hub asks it **once at warm time**; the resolved provider becomes part of the hub session identity (`VoiceSessionID`). | Low. |
| **A9** — session system instructions + about_user card | session-config builder | **STAYS.** Applied via `session.update` at warm time — **once per warm socket, not per turn.** ⚠️ **Flag for A9's owner:** if the about_user card changes mid-session, the hub must re-`session.update` or re-warm, else a long-lived warm socket serves stale grounding. (Mac solves this with `reconnectWarmSessionIfSeedStale()`; that mechanism is **A7c**, not A5.) | Low. |

### C.5 What the (unported) `RealtimeHubController` facade still requires Windows to provide

New module `lib/voice/hub/hubController.ts` — Windows-native, providing **only**:

1. **`ensureWarm(): Promise<VoiceSessionID>`** — mint token (A8-resolved provider), open socket, apply A9 instructions, configure **manual turn detection**. **Idempotent** (no-op if already warm on the same provider).
2. **`beginTurn(turnID)` / `appendAudio(pcm)` / `commitTurn(turnID)` / `cancelTurn(turnID, route)`** — the four primitives the reducer's effects drive.
3. **Warm-wait buffering** — PCM captured while the socket is still connecting is **buffered**, flushed on `hubReady`; on the **1 s `hubWarm` deadline** the buffer is handed to the cascade (`fallbackToTranscription`) and **the turn CONTINUES — it does not die.** This is the only piece of the facade with real logic. **Unit-test it.**
4. **`voiceTurnDidTerminate(turnID)`** — release per-turn provider state, **keep the socket**.
5. **Session lifecycle events out** — `hubDidConnect(sessionID)`, `hubDidError({ reason, aliveForMs })`. **This is the A7c seam** (§E).

**Provider protocol:**

- **OpenAI Realtime over WebSocket** (not WebRTC — see **D3**):
  - warm-time: `session.update { turn_detection: null }` (**PTT controls turns, not server VAD**)
  - per turn: `input_audio_buffer.append` (while held) → on release `input_audio_buffer.commit` → `response.create`
  - barge-in: `response.cancel` + `conversation.item.truncate` (Mac's `.inSessionCancel` strategy)
  - browser/Electron WS auth via subprotocols `["realtime", "openai-insecure-api-key.<ephemeral client_secret>"]`
  - ephemeral secrets are short-lived **for establishing** the connection → **mint fresh on each `ensureWarm`, not per turn**
- **Gemini Live — manual activity detection** (Mac's `.replaceSession` barge-in strategy):
  - connect with `realtimeInputConfig.automaticActivityDetection.disabled: true`
  - per turn: `sendRealtimeInput({ activityStart: {} })` … `sendRealtimeInput({ activityEnd: {} })`
  - Gemini has no reliable in-session cancel of a streaming reply ⇒ barge-in **replaces the session** — which is exactly why `hubCommitDeferredForReplacement` + `bargeInReplacement` (8 s) exist in the reducer, distinct from `hubCommitDeferred` + `deferredCommit` (8 s).

### C.6 The cutover seam + kill-switch

**Route selection is the seam.** The **host** (never the reducer) picks the route and emits `selectRoute`:

```ts
const route: VoiceTurnRoute =
  prefs.pttHubEnabled && hub.isAvailable()
    ? (hub.isWarm() ? { kind: 'hub', sessionID: null } : { kind: 'hubWarmWait' })
    : { kind: 'omniSTT' }
coordinator.send({ type: 'selectRoute', turnID, route })
```
(The `hub(sessionID: null)` shape is exactly what `PushToTalkManager` emits when the hub is already active — hence the nullable field in §A.3.)

- `omniSTT` drives today's cascade end-to-end (byte-for-byte the shipped path, now under the reducer's turn model).
- `hubWarmWait` → `hub` drives the new lane.

**Kill-switch = the `pttHubEnabled` preference, default OFF.** Flipping it off at runtime restores merged behavior with **no restart** — the next `selectRoute` picks `omniSTT`.

---

## D. Sub-PR breakdown (ordered, independently landable)

### PR 1 — pure reducer + ported Swift tests. **Zero wiring, zero behavior change.**
**Files:** `lib/voice/turn/voiceTurnMachine.ts`, `…/voiceTurnMachine.test.ts`
**Scope:** everything in §A. Nothing imports it yet.
**Tests:** port all **38** `VoiceTurnReducerTests` cases 1:1, keeping the Swift names (they document the invariant):
`testHappyHubTurnTransitionsThroughPlaybackAndTerminatesExactlyOnce` · `testQuickTapLockWindowCanBecomeLockedRecording` · `testLockWindowDeadlineFinalizesAndStopsCapture` · `testLateCaptureStartAfterFinalizationIsStoppedAndCannotResurrectTurn` · `testOldTurnEventsAreDroppedAfterBargeInStartsNewTurn` · **`testHubBargeInPreservesProviderRuntimeForAtomicHandoff`** · **`testHubWarmTimeoutFallsBackWithoutTerminatingOrDroppingTurn`** · `testHubReadyCancelsWarmDeadlineAndPreservesRecording` · `testDeferredCommitTimeoutTerminatesWithTypedReason` · `testBargeInReplacementCommitHasDistinctDeadlineAndCanResumeOnFreshSession` · `testBargeInReplacementDeadlineTerminatesWithTypedReason` · `testProviderNoResponseDeadlineTerminatesAndShowsActionableHint` · `testProviderEventFromReplacedSessionIsDropped` · `testProviderEventFromReplacedResponseIsDropped` · **`testProviderCallbackMissingKnownIdentityIsDropped`** (the nil-ID trap, §A.5) · `testProviderCanFinishSuccessfullyWithoutStartingPlayback` · `testToolCompletionKeepsTurnOpenUntilEveryToolFinishes` · `testProviderFinishDuringToolWaitTerminatesAfterLastToolAndOnlyThen` · `testToolAndPlaybackCanDrainInEitherOrderWithoutClosingEarly` · `testProviderOutputCannotMutateRecordingTurnBeforeCommit` · `testPendingToolDeadlineTerminates` · `testCaptureTranscriptionAndPlaybackDeadlinesHaveDistinctTerminalReasons` · `testPlaybackFailureRequiresMatchingLeaseAndShowsErrorHint` · `testCompetingPlaybackLeaseIsRejectedAsInvalidTransition` · `testStalePlaybackDrainCannotFinishCurrentLease` · `testProviderTurnDoneWaitsForMatchingPlaybackDrain` · `testPlaybackDrainBeforeProviderDoneReturnsToAwaitingResponse` · `testCleanupFromEveryNonIdlePhaseConvergesToTerminalThenReset` · `testInvalidTransitionDoesNotMutateTurn` · `testDeferredCommitCannotSkipFinalization` · `testHubTerminalCleanupCarriesOldRouteInEffectPayload` · `testHintDeadlineOnlyClearsTheCurrentTurnHint` · `testTerminalHintDeadlineClearsHintWithoutResurrectingTurn` · `testSemanticPresentationEventsUpdateProjectionWithoutOwningIO` · `testRandomizedStaleEventsNeverChangeActiveTurnIdentityOrTerminalizeIt` · `testClearPresentationIsARealReducerTransition` · `testDiagnosticLabelsNeverContainSpeechOrErrorPayloads` · `testNewTurnResetsPerTurnAnomalyCounters`
**Verification:** `pnpm test` (hermetic, node). **Correctness is won here.**

### PR 2 — coordinator + injected scheduler
**Files:** `lib/voice/turn/voiceTurnCoordinator.ts`, `…/voiceTurnCoordinator.test.ts`
**Scope:** everything in §B. Still unwired.
**Tests:** port all **14** `VoiceTurnCoordinatorTests`:
`testFakeClockDrivesLockDeadlineAndRealStopCaptureEffect` · **`testCancelledDeadlineCannotMutateLaterTurn`** · `testTimelineReconstructsTurnAndIsBounded` · `testPresenterDerivesConsistentListeningThinkingAndTerminalUI` · `testTerminalEffectAndCleanupAreExactlyOnce` · `testUnscopedPlaybackUsesPresenterButCannotOverrideActivePTTTurn` · `testSnapshotHandlerReceivesInitialAndSubsequentAuthoritativeModels` · `testHubReadyTransitionIsConsumedBeforeReentrantSnapshot` · **`testSnapshotReentrantEventsDrainFIFOWithoutRecursiveCallbacks`** · **`testEffectReentrantTerminalEventRunsAfterCurrentEffectReturns`** · `testResetCancelsOutstandingDeadlinesAndReturnsPresentationToIdle` · `testStaleAndInvalidTransitionsRemainObservableEffects` · `testDiagnosticLabelsAreStableAndLowCardinality` · `testTimelineNeverStoresAssociatedSpeechPayloads`
**Verification:** hermetic.

### PR 3 — output leases (touches A1, **additively**)
**Files:** `lib/voice/turn/voiceOutputCoordinator.ts` (+ test); `lib/voice/voiceController.ts` (additive param only)
**Scope:** port `PTTVoiceOutputCoordinator.swift` verbatim — `beginTurn` / `endTurn` / `interrupt` / `acquire(lane, turnID)` / `release(lease)` / `snapshot()`, **all turn-ID fenced** (`.staleTurn` when the turnID doesn't match; `.denied(active:)` when another lane holds it; same-lane `acquire` is **idempotent**). `deterministicAgentAck` sets `providerOutputSuppressed = true`. `VoiceOutputHandoffPolicy.fillerCanYield(active, to:, turnID:)` — filler yields to any non-filler lane on the **same** turn, and nothing else does.
`voiceController`'s playback paths gain an **optional `leaseID` (default `null` = today's behavior)**.
**Tests:** port all **12** `PTTVoiceOutputCoordinatorTests` (`testEveryPTTAudibleLaneCompetesForTheSameLease`, `testFillerIsTheOnlyLaneThatYieldsToRealOutputOnTheSameTurn`, `testDeterministicAckSuppressesProviderOutputForTurn`, `testStaleReleaseCannotClearCurrentLease`, `testStaleTurnCannotAcquireOrEndCurrentTurn`, `testReleaseRequiresExactLeaseIdentity`, `testInterruptRequiresCurrentTurnAndRevokesLease`, `testSameLaneAcquireIsIdempotent`, `testLateNativeAudioIsDeniedAfterFallbackLease`, `testFallbackCannotStartAfterNativeRealtimeLease`, `testAudioPlayerMustActuallyStartBeforePlaybackOwnsLease`, `testFillerCarriesTextIntoSystemVoiceFallback`). **A1's existing tests must stay green.**
**Verification:** hermetic. Still unwired.

### PR 4 — hub session lanes (no reducer yet)
**Files:** `lib/voice/hub/hubSession.ts` (interface), `openaiHubSession.ts` (WS + manual turn detection), `geminiHubSession.ts` (manual activity detection)
**Scope:** the provider frame sequences in §C.5. **Reuses the capture window's PCM and the existing `pcmPlayer` — no new audio graph.**
**Tests:** hermetic, against a **fake WebSocket** — assert exact frame sequences: `turn_detection: null` at warm; `append` → `commit` → `response.create`; `response.cancel` + `conversation.item.truncate` on barge-in; `activityStart` / `activityEnd` on Gemini.
**Real-app:** dev-only "warm + one turn" harness behind the flag, exercised with a real mic.

### PR 5 — hub controller
**Files:** `lib/voice/hub/hubController.ts` (+ test)
**Scope:** `ensureWarm` (A8 provider + A9 instructions), warm-wait PCM buffer + flush, the four turn primitives, `voiceTurnDidTerminate`, and the connect/error surface A7c will consume.
**Tests:** warm-wait buffer — flush on `hubReady` · hand-off to the cascade on the 1 s timeout (**turn survives**) · discard on cancel. Hermetic.
**Verification:** still not wired to the UI.

### PR 6 — wiring + cutover, behind `pttHubEnabled` (**default OFF**)
**Files:** new `lib/voice/turn/voiceTurnHost.ts` (**the only new file that touches shipped paths**); edits to `lib/ptt/machine.ts` (drop `showHint`/`showError`/`armWatchdog`), `hooks/usePushToTalk.ts` (verdicts sourced from reducer terminals), `lib/ptt/systemAudioMute.ts` (hub-route mute/restore), `capture/PttCaptureHost.ts` (levels fan-out — pending **D1**)
**Scope:** the host maps every effect to a real call —
`stopCapture` → capture-window dispose · `cancelHub` → `hubController.cancelTurn(turnID, route)` · `fallbackToTranscription` → hand the warm-wait buffer to the cascade **and keep the turn alive** · `stopPlayback` → `voiceController.interruptCurrentResponse(leaseID)` · `terminal` → `voiceOutputCoordinator.endTurn` + `hubController.voiceTurnDidTerminate` + A4 restore + cleanup · `scheduleDeadline`/`cancelDeadline`/`cancelAllDeadlines`/`staleEventDropped`/`invalidTransition` → **ignored by the host** (the coordinator already handled them).
Broadcasts the projection to the bar. Derives `lib/ptt/machine.ts`'s transport phase under the `omniSTT` route.
**Verification — REAL APP, BOTH FLAG STATES:**
- **OFF** → shipped cascade byte-for-byte. Regression-check A1 barge-in, A4 mute/restore (**every terminal reason ⇒ exactly one restore**), A6 gate, A7 ladder, A2 keywords still on the wire.
- **ON** → hold / speak / release / spoken reply on the warm hub; **barge-in mid-reply keeps the socket** (assert no `cancelHub` effect); hub-warm timeout **silently falls back to the cascade mid-turn**.
- Live E2E reuses the existing `pnpm test:e2e:ptt` auth-extraction pattern (self-fetches the token from the running app — **never ask Chris for tokens**).

### PR 7 (post-soak, optional) — flip the default
One-line pref change + telemetry review. **Keep the kill-switch.**

### Fallback telemetry (AGENTS.md contract — required; do NOT invent new counters)
- `fallbackToTranscription` effect → `recordFallback({ component: 'ptt_cascade', from: 'hub', to: 'omni_stt', reason: 'hub_warm_timeout', outcome: 'degraded' })`
- terminal `providerFailed` / `providerNoResponse` / `hubWarmTimeout` with no path left → `outcome: 'exhausted'`
- the existing openai↔gemini mint fallback **already emits** — **do not duplicate it**
- do **not** add a new `*_fallback_total` counter

---

## E. Risks + decisions I need from you (the orchestrator)

### Windows is AHEAD of Mac — do NOT drag it backward
1. **Capture-window warm mic graph** (pre-roll ring + `backfillMs`, so the 350 ms hold threshold costs no speech; `MIC_IDLE_RELEASE_MS` / `MIC_TAP_RELEASE_MS` linger policy) has **no Mac equivalent**. The reducer must **not** own capture — keep the IPC capture client; `captureStarted` / `captureFailed` are **reports**, `stopCapture` is the only command.
2. **A4's deterministic restore points.** `systemAudioMute.ts:19–24` is right: Windows restores at deterministic PTT-END effects and therefore needs **no** restore-before-TTS hook. Mac adds one only because its teardown isn't deterministic. **Do not port Mac's extra restore.**
3. **A6's trailing-audio gate** is Windows-side hardening below the reducer. **Keep it.**
4. **Gesture layer** (`SummonGesture`: stuck-key cap, `endIfActive()` on lock/suspend) is **more defensive than Mac's**. Keep it; the reducer sits above it. (The ground-truth doc says this is missing — it isn't. §0 item 7.)

### Where Mac assumes an affordance Windows lacks
- `@MainActor` global singletons → Windows has three renderers, so ownership must be **explicit** (D1). This is the port's biggest structural translation cost.
- Mac can hold the mic open cheaply; on Windows a continuously-open mic **lights the OS privacy indicator** → **D3**.
- `systemDidWake` (`NSWorkspace.didWakeNotification`) → the Windows equivalent is `powerMonitor.on('resume')` in main. A7c's problem — but **A5 must lay the hook point**.

### DECISIONS — I will not guess these

- **D1 — Who owns the coordinator + hub?**
  **Recommend: the MAIN window**, with the capture window fanning `ptt-levels` out to the bar as a second owner. The alternative (bar owns it) drags the entire TTS / chat / token surface across IPC.

- **D2 — Transcription deadline conflict.**
  Mac `transcription = 12 s`; Windows ships `BATCH_TIMEOUT_MS = 20 s` and `WATCHDOG_MS = 25 s`.
  **Recommend:** reducer default **12 s on the hub route**, **20 s on the `omniSTT` route** (pass a route-aware `Deadlines` object — it is already a config struct), so **no shipped cascade turn dies sooner than it does today**. Blindly porting 12 s is a user-visible regression on slow batch transcription.

- **D3 — The OpenAI hub lane must be WebSocket + PCM, NOT the shipped WebRTC lane.**
  `openaiSession.ts` uses `OpenAIRealtimeWebRTC` + `acquireMicStream`, which **holds the mic open for the life of the warm session** → the Windows mic indicator would be lit whenever the app is warm (privacy regression). The hub lane must be **WS**, feeding the capture window's existing PCM into `pcmPlayer` (this is also what Mac does). The WebRTC lane **stays** for the continuous Home voice surface.
  **This is the single biggest scoping call in A5.**

- **D4 — Warm-socket cost / idle policy.**
  A warm hub holds a provider socket + a minted key open across idle time. Mac accepts this.
  **Recommend an idle release** (~60 s of inactivity → drop the socket; re-warm on the next key-down — the 1 s `hubWarm` deadline plus warm-wait buffering makes the cold start invisible). **Needs a number from you.**

- **D5 — Keep `deepgramBatch` / `deepgramLive` in the TS route union?**
  **Recommend yes** — free, and required for faithfulness: the `hubWarm` deadline literally sets `route = deepgramBatch` (`:753`). No Windows producer emits `deepgramLive`.

- **D6 — The `too-long` hint has no reducer home.**
  It is a **non-terminal warning** about an ongoing hold, and Windows shows it for 4 s (`TOO_LONG_HINT_MS`) vs. the reducer's fixed 2 s `hintVisibility`.
  **Recommend:** keep it entirely in the transport/UI layer (unchanged), *not* routed through `hintChanged`. Cheap, zero regression. Say if you'd rather unify.

- **D7 — `permissionDenied` gets NO hint in Swift** (`:863`) even though `captureFailed` does.
  **Recommend:** port as-is (faithful), and if Windows wants a hint there, add it as an explicit Windows deviation with a comment — not silently.

### What A5 must EXPOSE so A7c (reconnect / failover / wake) can be built on top
*(Build the seam, not the feature. **A7c is NOT planned here.**)*

Windows today has **no reconnect at all**: a fatal session error just surfaces a manual "Try again" (`sessionMachine.ts`, `error.retryable`). Mac has a proactive **1.5 s re-warm**, `maxReconnectStrikes = 5`, a `systemDidWake` refresh guarded by `canReplaceSession`, and **one-hop openai↔gemini failover**.

A5 ships these hooks, **unused**:

1. **`VoiceSessionID` as a first-class, reducer-fenced identity** — A7c's session-replace correctness depends **entirely** on it (§A.5 Level 3).
2. **`hubController.on('connected', sessionID)` / `on('error', { reason, aliveForMs })`** — `aliveForMs` is what lets A7c distinguish a flapping socket (**strike**) from a long-lived one (**reset strikes**; Mac's rule: survived > 60 s ⇒ healthy).
3. **`hubController.teardownSession(reason)` + idempotent `ensureWarm()`** — a re-warm is teardown-then-warm; **both must be safe to call at any turn phase**.
4. **`canReplaceSession()`** — true **only when `coordinator.activeTurnID == null`**. Wake-refresh and provider failover must **never** yank the socket mid-turn. Expose it in A5 even though nothing calls it yet.
5. **A `powerMonitor.on('resume')` main→renderer message already plumbed to a no-op host handler** — so A7c is a body change, not new IPC.
6. **`hubCommitDeferredForReplacement` + `bargeInReplacement` (8 s)** — already in the reducer; the **turn-level** half of session replacement. A7c drives the **session-level** half.

**Explicitly NOT in A5:** retry timers, strike counters, failover policy, wake handling, `reconnectWarmSessionIfSeedStale`.

---

## Net file inventory

**New:**
- `lib/voice/turn/voiceTurnMachine.ts` (+ `.test.ts`) — PR 1
- `lib/voice/turn/voiceTurnCoordinator.ts` (+ `.test.ts`) — PR 2
- `lib/voice/turn/voiceOutputCoordinator.ts` (+ `.test.ts`) — PR 3
- `lib/voice/hub/{hubSession, openaiHubSession, geminiHubSession}.ts` (+ tests) — PR 4
- `lib/voice/hub/hubController.ts` (+ test) — PR 5
- `lib/voice/turn/voiceTurnHost.ts` — PR 6

**Modified (shipped code):**
- `lib/voice/voiceController.ts` — additive `leaseID` param (PR 3)
- `lib/ptt/machine.ts` — drop `showHint` / `showError` / `armWatchdog` (PR 6)
- `hooks/usePushToTalk.ts` — verdicts sourced from reducer terminals (PR 6)
- `lib/ptt/systemAudioMute.ts` — hub-route mute/restore (PR 6)
- `capture/PttCaptureHost.ts` — levels fan-out (PR 6, pending D1)

All PR-6 changes sit behind the `pttHubEnabled` kill-switch, default OFF.

---

# A5 — Orchestrator decisions (BINDING). Ruled 2026-07-14.

These resolve §E of `a5-port-plan.md`. Implementers follow these; do not re-litigate.

## D1 — Coordinator + hub live in the MAIN window renderer. ACCEPTED.
`voiceController`, the A1 chunked-TTS pipeline, `interruptCurrentResponse()`, `pcmPlayer`, chat send, and the auth/token mint are all already in main. A bar-owned hub would drag every one of them across IPC. The capture window already streams PCM to whichever window issued the command, so main can own hub audio with **zero capture-layer changes**.
**Cost accepted:** `ptt-levels` must fan out to the bar for the orb. Implement as a levels-only second owner in `captureEmit(event, ownerId)`. Do NOT relay PCM through main.

## D2 — Route-aware deadlines. ACCEPTED (12 s hub / 20 s omniSTT).
`Deadlines` is already a config struct — pass a route-aware object. Hub route uses Mac's 12 s `transcription`; the shipped `omniSTT` cascade keeps **20 s** (today's `BATCH_TIMEOUT_MS`).
**Rationale:** blindly porting 12 s would kill slow batch transcriptions that succeed today — a user-visible regression. Faithfulness to Mac must never make Windows worse than it already is.

## D3 — The OpenAI hub lane is WebSocket + capture-window PCM. NOT WebRTC. ACCEPTED — this is the most important call in A5.
The shipped `openaiSession.ts` (`OpenAIRealtimeWebRTC` + `acquireMicStream`) holds the **mic open for the life of the warm session**. On a warm hub that means the **Windows mic privacy indicator is lit the entire time the app is warm** — the app would look like it's always listening. That is an unacceptable privacy/trust regression and is disqualifying on its own, independent of any latency argument.
The hub lane MUST be WS, fed by the capture window's existing PCM (mic opens only while a turn is held) and played through the existing `pcmPlayer`. This is also what Mac does.
**The shipped WebRTC lane STAYS** for the continuous Home voice surface — do not remove or refactor it.

## D4 — Warm-socket idle policy: release after **180 s** idle, and warm eagerly on bar summon.
- **Idle release: 180 s** (named constant, flag-gated, tunable). Rationale: it survives natural conversational pauses and back-to-back turns — the exact shape warm-hub exists to serve — while bounding the cost of an idle open socket + minted ephemeral key. It also roughly matches Gemini's own ~2.5-min idle close, so **we** control teardown instead of being surprised by the provider's.
- **Eager `ensureWarm()` on bar summon** (a strong intent signal). This is what makes the *first* press warm without holding a socket 24/7.
- A cold press degrades **gracefully, never worse than today**: warm-wait buffering + the 1 s `hubWarm` deadline hands the buffer to the cascade and **the turn survives**. Worst case = today's behavior.
- Revisit the number from telemetry after soak. PR 6 ships default-OFF, so this is cheap to tune.

## D5 — Keep `deepgramBatch` / `deepgramLive` in the route union. ACCEPTED.
Free, and required for faithfulness: the `hubWarm` deadline literally sets `route = deepgramBatch` (`:753`). No Windows producer emits `deepgramLive` — that's fine.

## D6 — The `too-long` hint stays in the transport/UI layer. ACCEPTED.
Non-terminal warning about an ongoing hold; Windows shows it 4 s (`TOO_LONG_HINT_MS`) vs. the reducer's fixed 2 s `hintVisibility`. Do NOT route it through `hintChanged`. Zero regression, no reducer case needed.

## D7 — `permissionDenied` gets NO hint. Port as-is. ACCEPTED.
Port `terminalHint` verbatim (Swift `:863`). Do **not** silently add a Windows hint inside the reducer — that would desync the ported tests and hide a deliberate Mac choice.
**Follow-up (NOT A5):** verify Windows surfaces mic-permission-denied to the user *somewhere* (the mic-consent path). If it doesn't, that's a real UX gap — file it as its own item; do not smuggle a fix into the reducer.

## Standing constraints carried into every A5 PR
- **A6's Gemini trailing-audio gate stays exactly where it is.** It's a provider-protocol concern *below* the reducer, fencing a different thing. Do not "simplify" it away because the reducer now fences turns.
- **A4's deviation comment (`systemAudioMute.ts:19–24`) stays.** Windows restores at deterministic PTT-END effects and needs **no** restore-before-TTS hook. Do not port Mac's extra restore.
- **The shipped gesture layer (`SummonGesture`) is NOT rebuilt.** It's already more defensive than Mac's (stuck-key cap, `endIfActive()` on lock/suspend). A5 is the turn model + hub route, not the gesture. (The ground-truth doc is wrong about this — §0 item 7.)
- **The capture-window warm mic graph (pre-roll ring / `backfillMs`) has no Mac equivalent — keep it.** The reducer must NOT own capture: `captureStarted`/`captureFailed` are *reports*; `stopCapture` is the only command.
- **A9 stale-grounding (noted, not fixed in A5):** a long-lived warm socket bakes the about_user card at warm time, so it can serve stale grounding. D4's 180 s idle release bounds the staleness window. The real fix is A7c's `reconnectWarmSessionIfSeedStale` — out of A5 scope.
- **Fallback telemetry:** use the shared helper per AGENTS.md (`ptt_cascade`, `hub`→`omni_stt`, `hub_warm_timeout`, `degraded`/`exhausted`). Do NOT invent a new `*_fallback_total` counter, and do NOT duplicate the existing openai↔gemini mint fallback event.
