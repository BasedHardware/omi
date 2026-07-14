// Pure, event-sourced voice-turn reducer — a 1:1 port of macOS
// `VoiceTurnStateMachine.swift` (VoiceTurnReducer). One turn is the unit of
// identity: every capture, hub session, provider response, tool call and audio
// lease is scoped to it, so a superseded turn's late callbacks are inert.
//
// No timers, no clock, no I/O, no randomness, no ID minting — the coordinator
// owns all of that. `reduceVoiceTurn` is a pure function of (model, event).
//
// Port notes (the traps a "natural" TS translation gets wrong):
//   * Identity fencing is Swift `if let expected = stored, incoming != expected`.
//     Once a turn KNOWS an id, an event carrying `null` is ALSO stale. See
//     `fenceID` — and its two deliberate asymmetric exceptions
//     (`hubCommitAccepted`, `captureFailed`).
//   * Swift binds `guard var turn = model.turn` — a VALUE COPY. Guards read the
//     PRE-EVENT turn even after the model was mutated earlier in the same case.
//     Here `turn` is the caller's (frozen) model.turn and all writes go to a
//     cloned `draft`; never read `draft` where Swift reads `turn`.
//   * `hubWarm` is NON-terminal: it falls back to transcription and the turn
//     CONTINUES.
//   * `terminate()` skips BOTH `cancelHub` and `stopPlayback` when a barge-in
//     supersedes a hub turn, so the successor inherits the live warm socket.
//     Effect emission order is load-bearing: `stopCapture` before `cancelHub`.
//   * `cancel(deadline)` emits only if the deadline was actually held;
//     `schedule(deadline)` always inserts and always emits.

// MARK: - Typed identities

declare const brand: unique symbol
type Branded<K extends string, T = string> = T & { readonly [brand]: K }

/** Swift: `UUID`. */
export type VoiceTurnID = Branded<'VoiceTurnID'>
/** Swift: `UInt64`. */
export type VoiceCaptureID = Branded<'VoiceCaptureID', number>
/** Swift: `UUID`. */
export type VoiceSessionID = Branded<'VoiceSessionID'>
/** Swift: `String` (provider-supplied). */
export type VoiceResponseID = Branded<'VoiceResponseID'>
/** Swift: `String` (provider-supplied). */
export type VoiceToolCallID = Branded<'VoiceToolCallID'>
/** Swift: `UUID`. */
export type VoiceLeaseID = Branded<'VoiceLeaseID'>

// MARK: - State

export type VoiceTurnIntent = 'hold' | 'locked' | 'agentFollowUp' | 'automation'

/** Orthogonal to phase. `hub.sessionID` is nullable — the host emits
 *  `hub(sessionID: null)` when the hub is already active. */
export type VoiceTurnRoute =
  | { kind: 'undecided' }
  | { kind: 'hubWarmWait' }
  | { kind: 'hub'; sessionID: VoiceSessionID | null }
  | { kind: 'omniSTT' }
  | { kind: 'deepgramBatch' }
  | { kind: 'deepgramLive' }
  | { kind: 'agentFollowUp' }

export type VoiceOutputLane =
  | 'nativeRealtime'
  | 'selectedVoiceFallback'
  | 'deterministicAgentAck'
  | 'filler'
  | 'systemVoiceFallback'

/** Swift raw values — these are the telemetry strings. */
export const VOICE_OUTPUT_LANE_RAW: Record<VoiceOutputLane, string> = {
  nativeRealtime: 'native_realtime',
  selectedVoiceFallback: 'selected_voice_fallback',
  deterministicAgentAck: 'deterministic_agent_ack',
  filler: 'filler',
  systemVoiceFallback: 'system_voice_fallback'
}

export type VoiceOutputLease = {
  readonly id: VoiceLeaseID
  readonly turnID: VoiceTurnID
  readonly lane: VoiceOutputLane
}

export type VoiceTurnTerminalReason =
  | 'success'
  | 'tooShort'
  | 'silentRejected'
  | 'cancelled'
  | 'interruptedByBargeIn'
  | 'permissionDenied'
  | 'captureFailed'
  | 'transcriptionFailed'
  | 'providerFailed'
  | 'providerNoResponse'
  | 'hubWarmTimeout'
  | 'deferredCommitTimeout'
  | 'bargeInReplacementTimeout'
  | 'toolTimeout'
  | 'playbackFailed'
  | 'cleanup'

/** Swift raw values — these are the telemetry strings. */
export const VOICE_TURN_TERMINAL_REASON_RAW: Record<VoiceTurnTerminalReason, string> = {
  success: 'success',
  tooShort: 'too_short',
  silentRejected: 'silent_rejected',
  cancelled: 'cancelled',
  interruptedByBargeIn: 'interrupted_by_barge_in',
  permissionDenied: 'permission_denied',
  captureFailed: 'capture_failed',
  transcriptionFailed: 'transcription_failed',
  providerFailed: 'provider_failed',
  providerNoResponse: 'provider_no_response',
  hubWarmTimeout: 'hub_warm_timeout',
  deferredCommitTimeout: 'deferred_commit_timeout',
  bargeInReplacementTimeout: 'barge_in_replacement_timeout',
  toolTimeout: 'tool_timeout',
  playbackFailed: 'playback_failed',
  cleanup: 'cleanup'
}

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

export type VoiceTurnDeadline =
  | 'lockDecision'
  | 'captureStart'
  | 'hubWarm'
  | 'transcription'
  | 'providerResponse'
  | 'pendingTools'
  | 'deferredCommit'
  | 'bargeInReplacement'
  | 'playbackDrain'
  | 'hintVisibility'

/** Swift raw values — these are the telemetry strings. */
export const VOICE_TURN_DEADLINE_RAW: Record<VoiceTurnDeadline, string> = {
  lockDecision: 'lock_decision',
  captureStart: 'capture_start',
  hubWarm: 'hub_warm',
  transcription: 'transcription',
  providerResponse: 'provider_response',
  pendingTools: 'pending_tools',
  deferredCommit: 'deferred_commit',
  bargeInReplacement: 'barge_in_replacement',
  playbackDrain: 'playback_drain',
  hintVisibility: 'hint_visibility'
}

/** The ONLY thing the UI may read. */
export type VoiceTurnUIProjection = {
  readonly isListening: boolean
  readonly isLocked: boolean
  readonly isFollowUp: boolean
  readonly transcript: string
  readonly hint: string
  readonly isThinking: boolean
  readonly isResponseWaiting: boolean
  readonly isResponseActive: boolean
}

export const IDLE_PROJECTION: VoiceTurnUIProjection = {
  isListening: false,
  isLocked: false,
  isFollowUp: false,
  transcript: '',
  hint: '',
  isThinking: false,
  isResponseWaiting: false,
  isResponseActive: false
}

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
  readonly providerFinished: boolean
  readonly deadlines: ReadonlySet<VoiceTurnDeadline>
  readonly projection: VoiceTurnUIProjection
  readonly terminalReason: VoiceTurnTerminalReason | null
}

export type VoiceTurnTerminalRecord = {
  readonly turnID: VoiceTurnID
  readonly reason: VoiceTurnTerminalReason
  readonly route: VoiceTurnRoute
}

export type VoiceTurnModel = {
  readonly turn: VoiceTurn | null
  readonly lastTerminal: VoiceTurnTerminalRecord | null
  readonly staleEventCount: number
  readonly invalidTransitionCount: number
  readonly duplicateTerminalCount: number
}

export const IDLE_VOICE_TURN_MODEL: VoiceTurnModel = {
  turn: null,
  lastTerminal: null,
  staleEventCount: 0,
  invalidTransitionCount: 0,
  duplicateTerminalCount: 0
}

// MARK: - Events

export type VoiceTurnEvent =
  | { type: 'start'; turnID: VoiceTurnID; intent: VoiceTurnIntent }
  | { type: 'openLockWindow'; turnID: VoiceTurnID }
  | { type: 'lock'; turnID: VoiceTurnID }
  | { type: 'finalize'; turnID: VoiceTurnID }
  | { type: 'captureStarted'; turnID: VoiceTurnID; captureID: VoiceCaptureID }
  | {
      type: 'captureFailed'
      turnID: VoiceTurnID
      captureID: VoiceCaptureID | null
      message: string
    }
  | { type: 'selectRoute'; turnID: VoiceTurnID; route: VoiceTurnRoute }
  | { type: 'hubReady'; turnID: VoiceTurnID; sessionID: VoiceSessionID }
  | {
      type: 'hubCommitAccepted'
      turnID: VoiceTurnID
      sessionID: VoiceSessionID
      responseID: VoiceResponseID | null
    }
  | { type: 'hubCommitDeferred'; turnID: VoiceTurnID }
  | { type: 'hubCommitDeferredForReplacement'; turnID: VoiceTurnID }
  | { type: 'transcriptionStarted'; turnID: VoiceTurnID }
  | { type: 'transcriptionFinal'; turnID: VoiceTurnID; text: string }
  | { type: 'transcriptionFailed'; turnID: VoiceTurnID; message: string }
  | {
      type: 'providerResponseStarted'
      turnID: VoiceTurnID
      sessionID: VoiceSessionID | null
      responseID: VoiceResponseID | null
    }
  | {
      type: 'providerTurnFinished'
      turnID: VoiceTurnID
      sessionID: VoiceSessionID | null
      responseID: VoiceResponseID | null
    }
  | { type: 'toolStarted'; turnID: VoiceTurnID; callID: VoiceToolCallID }
  | { type: 'toolFinished'; turnID: VoiceTurnID; callID: VoiceToolCallID }
  | { type: 'playbackStarted'; turnID: VoiceTurnID; lease: VoiceOutputLease }
  | { type: 'playbackDrained'; turnID: VoiceTurnID; leaseID: VoiceLeaseID }
  | {
      type: 'playbackFailed'
      turnID: VoiceTurnID
      leaseID: VoiceLeaseID | null
      message: string
    }
  | { type: 'transcriptChanged'; turnID: VoiceTurnID; text: string }
  | { type: 'hintChanged'; turnID: VoiceTurnID; text: string }
  | { type: 'responseWaitingChanged'; turnID: VoiceTurnID; active: boolean }
  | { type: 'responseActiveChanged'; turnID: VoiceTurnID; active: boolean }
  | { type: 'clearPresentation'; turnID: VoiceTurnID }
  | { type: 'deadlineFired'; turnID: VoiceTurnID; deadline: VoiceTurnDeadline }
  | { type: 'finish'; turnID: VoiceTurnID; reason: VoiceTurnTerminalReason }
  | { type: 'cancel'; turnID: VoiceTurnID; reason: VoiceTurnTerminalReason }
  | { type: 'cleanup' }
  | { type: 'reset' }

/** `cleanup` and `reset` are turn-independent. */
export function turnIDOf(event: VoiceTurnEvent): VoiceTurnID | null {
  return event.type === 'cleanup' || event.type === 'reset' ? null : event.turnID
}

const DIAGNOSTIC_LABELS: Record<VoiceTurnEvent['type'], string> = {
  start: 'start',
  openLockWindow: 'open_lock_window',
  lock: 'lock',
  finalize: 'finalize',
  captureStarted: 'capture_started',
  captureFailed: 'capture_failed',
  selectRoute: 'select_route',
  hubReady: 'hub_ready',
  hubCommitAccepted: 'hub_commit_accepted',
  hubCommitDeferred: 'hub_commit_deferred',
  hubCommitDeferredForReplacement: 'hub_commit_deferred_for_replacement',
  transcriptionStarted: 'transcription_started',
  transcriptionFinal: 'transcription_final',
  transcriptionFailed: 'transcription_failed',
  providerResponseStarted: 'provider_response_started',
  providerTurnFinished: 'provider_turn_finished',
  toolStarted: 'tool_started',
  toolFinished: 'tool_finished',
  playbackStarted: 'playback_started',
  playbackDrained: 'playback_drained',
  playbackFailed: 'playback_failed',
  transcriptChanged: 'transcript_changed',
  hintChanged: 'hint_changed',
  responseWaitingChanged: 'response_waiting_changed',
  responseActiveChanged: 'response_active_changed',
  clearPresentation: 'clear_presentation',
  deadlineFired: 'deadline_fired',
  finish: 'finish',
  cancel: 'cancel',
  cleanup: 'cleanup',
  reset: 'reset'
}

/** A bounded diagnostics label that never includes transcript, hint, or error payloads. */
export function diagnosticLabel(event: VoiceTurnEvent): string {
  return DIAGNOSTIC_LABELS[event.type]
}

// MARK: - Effects

export type VoiceTurnEffect =
  | {
      kind: 'scheduleDeadline'
      turnID: VoiceTurnID
      deadline: VoiceTurnDeadline
      /** Seconds (Swift `TimeInterval`). */
      after: number
    }
  | { kind: 'cancelDeadline'; turnID: VoiceTurnID; deadline: VoiceTurnDeadline }
  | { kind: 'cancelAllDeadlines'; turnID: VoiceTurnID }
  | { kind: 'stopCapture'; turnID: VoiceTurnID; captureID: VoiceCaptureID | null }
  /** Carries the PRE-terminal route — the host needs to know which transport to tear down. */
  | { kind: 'cancelHub'; turnID: VoiceTurnID; route: VoiceTurnRoute }
  | { kind: 'fallbackToTranscription'; turnID: VoiceTurnID; reason: VoiceTurnTerminalReason }
  | { kind: 'stopPlayback'; turnID: VoiceTurnID; leaseID: VoiceLeaseID | null }
  | { kind: 'terminal'; record: VoiceTurnTerminalRecord }
  | { kind: 'staleEventDropped'; turnID: VoiceTurnID | null; event: string }
  | {
      kind: 'invalidTransition'
      turnID: VoiceTurnID | null
      event: string
      phase: VoiceTurnPhase | null
    }

// MARK: - Deadlines (a config struct, not constants — PR-2 passes a route-aware object)

export type VoiceTurnDeadlines = Readonly<Record<VoiceTurnDeadline, number>>

/** SECONDS (Swift `TimeInterval`). */
export const DEFAULT_VOICE_TURN_DEADLINES: VoiceTurnDeadlines = {
  lockDecision: 0.4,
  captureStart: 3,
  hubWarm: 1,
  transcription: 12,
  providerResponse: 20,
  pendingTools: 30,
  deferredCommit: 8,
  bargeInReplacement: 8,
  playbackDrain: 30,
  hintVisibility: 2
}

// MARK: - Derived predicates

export function isRecording(phase: VoiceTurnPhase): boolean {
  return (
    phase.kind === 'recording' ||
    phase.kind === 'lockedRecording' ||
    phase.kind === 'pendingLockDecision'
  )
}

export function isTerminal(phase: VoiceTurnPhase): boolean {
  return phase.kind === 'terminal'
}

/** The guard that stops a stray provider callback from mutating a turn that is
 *  still capturing mic audio. */
export function acceptsProviderOutput(phase: VoiceTurnPhase): boolean {
  return (
    phase.kind === 'awaitingResponse' || phase.kind === 'awaitingTools' || phase.kind === 'playing'
  )
}

export function routeMatchesHub(route: VoiceTurnRoute): boolean {
  return route.kind === 'hub' || route.kind === 'hubWarmWait'
}

/** Pure — ported verbatim from Swift. NOTE: `permissionDenied` deliberately gets
 *  NO hint (mirrors macOS); do not "fix" it here. */
export function terminalHint(reason: VoiceTurnTerminalReason): string | null {
  switch (reason) {
    case 'tooShort':
      return 'Hold longer to record'
    case 'captureFailed':
      return 'Microphone unavailable — try again'
    case 'transcriptionFailed':
      return "Couldn't transcribe that — try again"
    case 'providerFailed':
    case 'providerNoResponse':
    case 'deferredCommitTimeout':
    case 'bargeInReplacementTimeout':
    case 'toolTimeout':
      return 'Voice response failed — try again'
    case 'playbackFailed':
      return 'Audio playback failed'
    case 'success':
    case 'silentRejected':
    case 'cancelled':
    case 'interruptedByBargeIn':
    case 'permissionDenied':
    case 'hubWarmTimeout':
    case 'cleanup':
      return null
  }
}

export function projectionOf(model: VoiceTurnModel): VoiceTurnUIProjection {
  return model.turn?.projection ?? IDLE_PROJECTION
}

// MARK: - Internal equality (Swift value semantics)

function phasesEqual(a: VoiceTurnPhase, b: VoiceTurnPhase): boolean {
  if (a.kind !== b.kind) return false
  if (a.kind === 'playing' && b.kind === 'playing') return a.lane === b.lane
  if (a.kind === 'terminal' && b.kind === 'terminal') return a.reason === b.reason
  return true
}

function routesEqual(a: VoiceTurnRoute, b: VoiceTurnRoute): boolean {
  if (a.kind !== b.kind) return false
  if (a.kind === 'hub' && b.kind === 'hub') return a.sessionID === b.sessionID
  return true
}

function leasesEqual(a: VoiceOutputLease, b: VoiceOutputLease): boolean {
  return a.id === b.id && a.turnID === b.turnID && a.lane === b.lane
}

/**
 * Swift `if let expected = stored, incoming != expected { stale }`.
 *
 * - unknown stored  → accept (and adopt whatever arrived).
 * - known stored    → incoming must match EXACTLY; a `null` incoming is STALE
 *   (`nil != .some(x)` in Swift). This is what drops a provider callback that
 *   lost its identity — do NOT rewrite as `incoming && incoming !== stored`.
 */
function fenceID<T>(stored: T | null, incoming: T | null): boolean {
  if (stored === null) return true
  return incoming === stored
}

// MARK: - Mutable draft (Swift's `model` — distinct from the `turn` value copy)

type MutableProjection = { -readonly [K in keyof VoiceTurnUIProjection]: VoiceTurnUIProjection[K] }

type MutableTurn = {
  id: VoiceTurnID
  intent: VoiceTurnIntent
  phase: VoiceTurnPhase
  route: VoiceTurnRoute
  captureID: VoiceCaptureID | null
  sessionID: VoiceSessionID | null
  responseID: VoiceResponseID | null
  pendingToolCallIDs: Set<VoiceToolCallID>
  activeLease: VoiceOutputLease | null
  providerFinished: boolean
  deadlines: Set<VoiceTurnDeadline>
  projection: MutableProjection
  terminalReason: VoiceTurnTerminalReason | null
}

type MutableModel = {
  turn: MutableTurn | null
  lastTerminal: VoiceTurnTerminalRecord | null
  staleEventCount: number
  invalidTransitionCount: number
  duplicateTerminalCount: number
}

function cloneTurn(turn: VoiceTurn): MutableTurn {
  return {
    id: turn.id,
    intent: turn.intent,
    phase: turn.phase,
    route: turn.route,
    captureID: turn.captureID,
    sessionID: turn.sessionID,
    responseID: turn.responseID,
    pendingToolCallIDs: new Set(turn.pendingToolCallIDs),
    activeLease: turn.activeLease,
    providerFinished: turn.providerFinished,
    deadlines: new Set(turn.deadlines),
    projection: { ...turn.projection },
    terminalReason: turn.terminalReason
  }
}

function newVoiceTurn(id: VoiceTurnID, intent: VoiceTurnIntent): MutableTurn {
  return {
    id,
    intent,
    phase: intent === 'locked' ? { kind: 'lockedRecording' } : { kind: 'recording' },
    route: intent === 'agentFollowUp' ? { kind: 'agentFollowUp' } : { kind: 'undecided' },
    captureID: null,
    sessionID: null,
    responseID: null,
    pendingToolCallIDs: new Set(),
    activeLease: null,
    providerFinished: false,
    deadlines: new Set(),
    projection: {
      isListening: true,
      isLocked: intent === 'locked',
      isFollowUp: intent === 'agentFollowUp',
      transcript: '',
      hint: '',
      isThinking: false,
      isResponseWaiting: false,
      isResponseActive: false
    },
    terminalReason: null
  }
}

// MARK: - Reducer

export type VoiceTurnReduction = {
  model: VoiceTurnModel
  effects: VoiceTurnEffect[]
}

/** ALWAYS inserts and ALWAYS emits — re-scheduling a held deadline resets the
 *  timer (the coordinator cancels the old handle first). `hintChanged` relies on it. */
function schedule(
  deadline: VoiceTurnDeadline,
  after: number,
  model: MutableModel,
  effects: VoiceTurnEffect[]
): void {
  const turn = model.turn
  if (turn === null) return
  turn.deadlines.add(deadline)
  effects.push({ kind: 'scheduleDeadline', turnID: turn.id, deadline, after })
}

/** Emits `cancelDeadline` ONLY if the deadline was actually held (Swift
 *  `Set.remove` returning non-nil). Unconditional emission breaks exactly-once
 *  effect counting. */
function cancel(
  deadline: VoiceTurnDeadline,
  model: MutableModel,
  effects: VoiceTurnEffect[]
): void {
  const turn = model.turn
  if (turn === null) return
  if (!turn.deadlines.delete(deadline)) return
  effects.push({ kind: 'cancelDeadline', turnID: turn.id, deadline })
}

function stale(model: MutableModel, event: VoiceTurnEvent, effects: VoiceTurnEffect[]): void {
  model.staleEventCount += 1
  effects.push({
    kind: 'staleEventDropped',
    turnID: turnIDOf(event),
    event: diagnosticLabel(event)
  })
}

function invalid(model: MutableModel, event: VoiceTurnEvent, effects: VoiceTurnEffect[]): void {
  model.invalidTransitionCount += 1
  effects.push({
    kind: 'invalidTransition',
    turnID: turnIDOf(event),
    event: diagnosticLabel(event),
    phase: model.turn?.phase ?? null
  })
}

/** The single terminal path. Effect emission ORDER is load-bearing:
 *  `stopCapture` BEFORE `cancelHub`, or a trailing PCM chunk revives the socket. */
function terminate(
  model: MutableModel,
  reason: VoiceTurnTerminalReason,
  effects: VoiceTurnEffect[],
  deadlines: VoiceTurnDeadlines
): void {
  const turn = model.turn
  if (turn === null) return
  if (isTerminal(turn.phase)) {
    model.duplicateTerminalCount += 1
    return
  }

  const record: VoiceTurnTerminalRecord = { turnID: turn.id, reason, route: turn.route }

  if (turn.captureID !== null || isRecording(turn.phase) || turn.phase.kind === 'finalizing') {
    effects.push({ kind: 'stopCapture', turnID: turn.id, captureID: turn.captureID })
  }

  // THE warm-hub feature: a barge-in that supersedes a turn on the hub route
  // hands the live socket to the successor — no cancelHub, no stopPlayback.
  const preservesHubForBargeInHandoff =
    reason === 'interruptedByBargeIn' && turn.route.kind === 'hub'

  if (!preservesHubForBargeInHandoff) {
    effects.push({ kind: 'cancelHub', turnID: turn.id, route: turn.route })
  }
  if (turn.activeLease !== null && !preservesHubForBargeInHandoff) {
    effects.push({ kind: 'stopPlayback', turnID: turn.id, leaseID: turn.activeLease.id })
  }
  effects.push({ kind: 'cancelAllDeadlines', turnID: turn.id })
  effects.push({ kind: 'terminal', record })

  turn.deadlines.clear()
  turn.pendingToolCallIDs.clear()
  turn.activeLease = null
  turn.terminalReason = reason
  turn.phase = { kind: 'terminal', reason }
  turn.projection = { ...IDLE_PROJECTION }

  const hint = terminalHint(reason)
  if (hint !== null) {
    turn.projection.hint = hint
    // Inserted DIRECTLY, not via schedule().
    turn.deadlines.add('hintVisibility')
    effects.push({
      kind: 'scheduleDeadline',
      turnID: turn.id,
      deadline: 'hintVisibility',
      after: deadlines.hintVisibility
    })
  }

  model.lastTerminal = record
}

export function reduceVoiceTurn(
  current: VoiceTurnModel,
  event: VoiceTurnEvent,
  deadlines: VoiceTurnDeadlines = DEFAULT_VOICE_TURN_DEADLINES
): VoiceTurnReduction {
  const model: MutableModel = {
    turn: current.turn === null ? null : cloneTurn(current.turn),
    lastTerminal: current.lastTerminal,
    staleEventCount: current.staleEventCount,
    invalidTransitionCount: current.invalidTransitionCount,
    duplicateTerminalCount: current.duplicateTerminalCount
  }
  const effects: VoiceTurnEffect[] = []

  // Level 0 — turn-independent events, before any guard.

  if (event.type === 'start') {
    const active = model.turn
    if (active !== null && !isTerminal(active.phase)) {
      terminate(model, 'interruptedByBargeIn', effects, deadlines)
    } else if (active !== null && active.deadlines.size > 0) {
      effects.push({ kind: 'cancelAllDeadlines', turnID: active.id })
    }
    model.turn = newVoiceTurn(event.turnID, event.intent)
    model.staleEventCount = 0
    model.invalidTransitionCount = 0
    model.duplicateTerminalCount = 0
    schedule('captureStart', deadlines.captureStart, model, effects)
    return { model, effects }
  }

  if (event.type === 'cleanup') {
    if (model.turn !== null) {
      terminate(model, 'cleanup', effects, deadlines)
    }
    return { model, effects }
  }

  if (event.type === 'reset') {
    if (model.turn === null || isTerminal(model.turn.phase)) {
      if (model.turn !== null && model.turn.deadlines.size > 0) {
        effects.push({ kind: 'cancelAllDeadlines', turnID: model.turn.id })
      }
      model.turn = null
    } else {
      invalid(model, event, effects)
    }
    return { model, effects }
  }

  // Level 1 — turn guard. `turn` is the PRE-EVENT snapshot (Swift's value copy);
  // every guard below reads it, never `model.turn`.
  const turn = current.turn
  if (turn === null) {
    stale(model, event, effects)
    return { model, effects }
  }
  if (event.turnID !== turn.id) {
    stale(model, event, effects)
    return { model, effects }
  }

  // The mutable twin of `turn` — every WRITE goes here, every GUARD reads `turn`.
  const draft = model.turn as MutableTurn

  // Level 2 — a terminal turn accepts exactly one event.
  if (isTerminal(turn.phase)) {
    if (
      event.type === 'deadlineFired' &&
      event.deadline === 'hintVisibility' &&
      turn.deadlines.has('hintVisibility')
    ) {
      draft.deadlines.delete('hintVisibility')
      draft.projection.hint = ''
      return { model, effects }
    }
    if (event.type === 'finish' || event.type === 'cancel') {
      model.duplicateTerminalCount += 1
    } else {
      stale(model, event, effects)
    }
    return { model, effects }
  }

  // Level 3 — per-event guards.

  switch (event.type) {
    case 'openLockWindow': {
      if (turn.phase.kind !== 'recording') {
        invalid(model, event, effects)
        return { model, effects }
      }
      draft.phase = { kind: 'pendingLockDecision' }
      draft.projection.isListening = true
      draft.projection.isLocked = false
      schedule('lockDecision', deadlines.lockDecision, model, effects)
      break
    }

    case 'lock': {
      if (turn.phase.kind !== 'recording' && turn.phase.kind !== 'pendingLockDecision') {
        invalid(model, event, effects)
        return { model, effects }
      }
      cancel('lockDecision', model, effects)
      draft.phase = { kind: 'lockedRecording' }
      draft.intent = 'locked'
      draft.projection.isListening = true
      draft.projection.isLocked = true
      break
    }

    case 'finalize': {
      if (!isRecording(turn.phase)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      cancel('lockDecision', model, effects)
      cancel('captureStart', model, effects)
      draft.phase = { kind: 'finalizing' }
      draft.projection.isListening = false
      draft.projection.isLocked = false
      draft.projection.isThinking = true
      effects.push({ kind: 'stopCapture', turnID: turn.id, captureID: turn.captureID })
      break
    }

    case 'captureStarted': {
      if (!isRecording(turn.phase)) {
        // Kill the orphan capture — it can never reach this turn.
        stale(model, event, effects)
        effects.push({ kind: 'stopCapture', turnID: turn.id, captureID: event.captureID })
        return { model, effects }
      }
      cancel('captureStart', model, effects)
      draft.captureID = event.captureID
      break
    }

    case 'captureFailed': {
      // Asymmetric on purpose: BOTH ids must be non-null to be stale. A failure
      // before capture ever started (null captureID) is ACCEPTED.
      if (
        turn.captureID !== null &&
        event.captureID !== null &&
        turn.captureID !== event.captureID
      ) {
        stale(model, event, effects)
        return { model, effects }
      }
      terminate(model, 'captureFailed', effects, deadlines)
      break
    }

    case 'selectRoute': {
      if (!isRecording(turn.phase) && turn.phase.kind !== 'finalizing') {
        invalid(model, event, effects)
        return { model, effects }
      }
      draft.route = event.route
      if (event.route.kind === 'hubWarmWait') {
        schedule('hubWarm', deadlines.hubWarm, model, effects)
      }
      break
    }

    case 'hubReady': {
      if (turn.route.kind !== 'hubWarmWait') {
        stale(model, event, effects)
        return { model, effects }
      }
      cancel('hubWarm', model, effects)
      draft.route = { kind: 'hub', sessionID: event.sessionID }
      draft.sessionID = event.sessionID
      break
    }

    case 'hubCommitAccepted': {
      const isDeferredCommit =
        turn.phase.kind === 'awaitingResponse' &&
        (turn.deadlines.has('deferredCommit') || turn.deadlines.has('bargeInReplacement'))
      if (!(turn.phase.kind === 'finalizing' || isDeferredCommit) || !routeMatchesHub(turn.route)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      // Asymmetric on purpose: the event's sessionID is non-optional here, so
      // this is a plain equality fence, not `fenceID`.
      if (!(turn.sessionID === null || turn.sessionID === event.sessionID)) {
        stale(model, event, effects)
        return { model, effects }
      }
      draft.route = { kind: 'hub', sessionID: event.sessionID }
      draft.sessionID = event.sessionID
      draft.responseID = event.responseID
      draft.phase = { kind: 'awaitingResponse' }
      draft.projection.isThinking = true
      draft.projection.isResponseWaiting = true
      cancel('deferredCommit', model, effects)
      cancel('bargeInReplacement', model, effects)
      schedule('providerResponse', deadlines.providerResponse, model, effects)
      break
    }

    case 'hubCommitDeferred': {
      if (turn.phase.kind !== 'finalizing' || !routeMatchesHub(turn.route)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      draft.phase = { kind: 'awaitingResponse' }
      draft.projection.isThinking = true
      draft.projection.isResponseWaiting = true
      schedule('deferredCommit', deadlines.deferredCommit, model, effects)
      break
    }

    case 'hubCommitDeferredForReplacement': {
      if (turn.phase.kind !== 'finalizing' || !routeMatchesHub(turn.route)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      draft.phase = { kind: 'awaitingResponse' }
      draft.projection.isThinking = true
      draft.projection.isResponseWaiting = true
      schedule('bargeInReplacement', deadlines.bargeInReplacement, model, effects)
      break
    }

    case 'transcriptionStarted': {
      if (turn.phase.kind !== 'finalizing') {
        invalid(model, event, effects)
        return { model, effects }
      }
      draft.projection.isThinking = true
      draft.projection.transcript = 'Transcribing…'
      schedule('transcription', deadlines.transcription, model, effects)
      break
    }

    case 'transcriptionFinal': {
      if (turn.phase.kind !== 'finalizing') {
        stale(model, event, effects)
        return { model, effects }
      }
      cancel('transcription', model, effects)
      draft.phase = { kind: 'awaitingResponse' }
      draft.projection.transcript = event.text
      draft.projection.isThinking = true
      draft.projection.isResponseWaiting = true
      schedule('providerResponse', deadlines.providerResponse, model, effects)
      break
    }

    case 'transcriptionFailed': {
      terminate(model, 'transcriptionFailed', effects, deadlines)
      break
    }

    case 'providerResponseStarted': {
      if (!acceptsProviderOutput(turn.phase)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      if (
        !fenceID(turn.sessionID, event.sessionID) ||
        !fenceID(turn.responseID, event.responseID)
      ) {
        stale(model, event, effects)
        return { model, effects }
      }
      cancel('providerResponse', model, effects)
      cancel('deferredCommit', model, effects)
      cancel('bargeInReplacement', model, effects)
      draft.sessionID = event.sessionID ?? turn.sessionID
      draft.responseID = event.responseID ?? turn.responseID
      draft.projection.isThinking = false
      draft.projection.isResponseWaiting = false
      draft.projection.isResponseActive = true
      // Phase deliberately unchanged.
      break
    }

    case 'providerTurnFinished': {
      if (!acceptsProviderOutput(turn.phase)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      if (
        !fenceID(turn.sessionID, event.sessionID) ||
        !fenceID(turn.responseID, event.responseID)
      ) {
        stale(model, event, effects)
        return { model, effects }
      }
      draft.providerFinished = true
      cancel('providerResponse', model, effects)
      cancel('deferredCommit', model, effects)
      cancel('bargeInReplacement', model, effects)
      if (turn.activeLease === null && turn.pendingToolCallIDs.size === 0) {
        terminate(model, 'success', effects, deadlines)
      }
      break
    }

    case 'toolStarted': {
      if (!acceptsProviderOutput(turn.phase)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      draft.pendingToolCallIDs.add(event.callID)
      // Even from `playing` — and `activeLease` is kept.
      draft.phase = { kind: 'awaitingTools' }
      schedule('pendingTools', deadlines.pendingTools, model, effects)
      break
    }

    case 'toolFinished': {
      if (!turn.pendingToolCallIDs.has(event.callID)) {
        stale(model, event, effects)
        return { model, effects }
      }
      draft.pendingToolCallIDs.delete(event.callID)
      if (draft.pendingToolCallIDs.size === 0) {
        cancel('pendingTools', model, effects)
        if (turn.providerFinished && turn.activeLease === null) {
          terminate(model, 'success', effects, deadlines)
        } else if (turn.activeLease !== null) {
          draft.phase = { kind: 'playing', lane: turn.activeLease.lane }
        } else {
          draft.phase = { kind: 'awaitingResponse' }
          schedule('providerResponse', deadlines.providerResponse, model, effects)
        }
      }
      break
    }

    case 'playbackStarted': {
      if (!acceptsProviderOutput(turn.phase)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      if (event.lease.turnID !== turn.id) {
        stale(model, event, effects)
        return { model, effects }
      }
      // A DIFFERENT already-active lease is a real bug, not staleness.
      if (turn.activeLease !== null && !leasesEqual(turn.activeLease, event.lease)) {
        invalid(model, event, effects)
        return { model, effects }
      }
      cancel('providerResponse', model, effects)
      draft.activeLease = event.lease
      draft.phase = { kind: 'playing', lane: event.lease.lane }
      draft.projection.isThinking = false
      draft.projection.isResponseWaiting = false
      draft.projection.isResponseActive = true
      schedule('playbackDrain', deadlines.playbackDrain, model, effects)
      break
    }

    case 'playbackDrained': {
      if (turn.activeLease === null || turn.activeLease.id !== event.leaseID) {
        stale(model, event, effects)
        return { model, effects }
      }
      cancel('playbackDrain', model, effects)
      draft.activeLease = null
      if (turn.providerFinished && turn.pendingToolCallIDs.size === 0) {
        terminate(model, 'success', effects, deadlines)
      } else if (turn.pendingToolCallIDs.size > 0) {
        draft.phase = { kind: 'awaitingTools' }
        draft.projection.isResponseActive = false
        draft.projection.isResponseWaiting = false
      } else {
        draft.phase = { kind: 'awaitingResponse' }
        draft.projection.isResponseActive = false
        draft.projection.isResponseWaiting = true
        schedule('providerResponse', deadlines.providerResponse, model, effects)
      }
      break
    }

    case 'playbackFailed': {
      // A null leaseID always applies.
      if (event.leaseID !== null && turn.activeLease?.id !== event.leaseID) {
        stale(model, event, effects)
        return { model, effects }
      }
      terminate(model, 'playbackFailed', effects, deadlines)
      break
    }

    case 'transcriptChanged': {
      draft.projection.transcript = event.text
      break
    }

    case 'hintChanged': {
      draft.projection.hint = event.text
      if (event.text === '') {
        cancel('hintVisibility', model, effects)
      } else {
        schedule('hintVisibility', deadlines.hintVisibility, model, effects)
      }
      break
    }

    case 'responseWaitingChanged': {
      draft.projection.isResponseWaiting = event.active
      draft.projection.isThinking = event.active
      break
    }

    case 'responseActiveChanged': {
      draft.projection.isResponseActive = event.active
      if (event.active) {
        draft.projection.isThinking = false
        draft.projection.isResponseWaiting = false
      }
      break
    }

    case 'clearPresentation': {
      draft.projection = { ...IDLE_PROJECTION }
      cancel('hintVisibility', model, effects)
      break
    }

    case 'deadlineFired': {
      if (!turn.deadlines.has(event.deadline)) {
        stale(model, event, effects)
        return { model, effects }
      }
      draft.deadlines.delete(event.deadline)
      switch (event.deadline) {
        case 'lockDecision': {
          if (turn.phase.kind !== 'pendingLockDecision') {
            stale(model, event, effects)
            return { model, effects }
          }
          draft.phase = { kind: 'finalizing' }
          draft.projection.isListening = false
          draft.projection.isThinking = true
          effects.push({ kind: 'stopCapture', turnID: turn.id, captureID: turn.captureID })
          break
        }
        case 'captureStart':
          terminate(model, 'captureFailed', effects, deadlines)
          break
        case 'hubWarm': {
          // NON-TERMINAL. The turn continues on the cascade.
          effects.push({
            kind: 'fallbackToTranscription',
            turnID: turn.id,
            reason: 'hubWarmTimeout'
          })
          draft.route = { kind: 'deepgramBatch' }
          if (turn.phase.kind === 'finalizing') {
            schedule('transcription', deadlines.transcription, model, effects)
          }
          break
        }
        case 'transcription':
          terminate(model, 'transcriptionFailed', effects, deadlines)
          break
        case 'providerResponse':
          terminate(model, 'providerNoResponse', effects, deadlines)
          break
        case 'pendingTools':
          terminate(model, 'toolTimeout', effects, deadlines)
          break
        case 'deferredCommit':
          terminate(model, 'deferredCommitTimeout', effects, deadlines)
          break
        case 'bargeInReplacement':
          terminate(model, 'bargeInReplacementTimeout', effects, deadlines)
          break
        case 'playbackDrain':
          terminate(model, 'playbackFailed', effects, deadlines)
          break
        case 'hintVisibility':
          draft.projection.hint = ''
          break
      }
      break
    }

    case 'finish':
    case 'cancel': {
      terminate(model, event.reason, effects, deadlines)
      break
    }
  }

  return { model, effects }
}

// Re-exported for callers that need structural equality on the sum types.
export { phasesEqual, routesEqual, leasesEqual }
