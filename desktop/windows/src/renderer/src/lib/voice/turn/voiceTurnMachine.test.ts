// 1:1 port of macOS `VoiceTurnReducerTests.swift` (38 cases). The Swift test
// names are kept verbatim — each one documents an invariant of the turn model,
// and a renamed test is an invariant nobody can trace back to the reference.
import { describe, it, expect } from 'vitest'
import {
  reduceVoiceTurn,
  routeMatchesHub,
  IDLE_VOICE_TURN_MODEL,
  IDLE_PROJECTION,
  diagnosticLabel,
  type VoiceTurnModel,
  type VoiceTurnEvent,
  type VoiceTurnEffect,
  type VoiceTurnReduction,
  type VoiceTurnID,
  type VoiceCaptureID,
  type VoiceSessionID,
  type VoiceResponseID,
  type VoiceToolCallID,
  type VoiceLeaseID,
  type VoiceOutputLease,
  type VoiceTurnRoute
} from './voiceTurnMachine'

// ---- fixtures -------------------------------------------------------------
// The reducer never mints IDs; tests do (as the coordinator will).

let seq = 0
const newTurnID = (): VoiceTurnID => `turn-${++seq}` as VoiceTurnID
const newSessionID = (): VoiceSessionID => `session-${++seq}` as VoiceSessionID
const newLeaseID = (): VoiceLeaseID => `lease-${++seq}` as VoiceLeaseID
const capture = (n: number): VoiceCaptureID => n as VoiceCaptureID
const response = (s: string): VoiceResponseID => s as VoiceResponseID
const tool = (s: string): VoiceToolCallID => s as VoiceToolCallID

const reduce = (model: VoiceTurnModel, event: VoiceTurnEvent): VoiceTurnReduction =>
  reduceVoiceTurn(model, event)

const IDLE = IDLE_VOICE_TURN_MODEL

const isTerminalEffect = (e: VoiceTurnEffect): boolean => e.kind === 'terminal'

const lease = (turnID: VoiceTurnID, lane: VoiceOutputLease['lane']): VoiceOutputLease => ({
  id: newLeaseID(),
  turnID,
  lane
})

const hub = (sessionID: VoiceSessionID | null): VoiceTurnRoute => ({ kind: 'hub', sessionID })

/** The Swift fixture: a hub turn parked in `awaitingResponse` after a commit. */
function awaitingHubResponse(): {
  model: VoiceTurnModel
  turnID: VoiceTurnID
  sessionID: VoiceSessionID
  responseID: VoiceResponseID
} {
  const turnID = newTurnID()
  const sessionID = newSessionID()
  const responseID = response('response')
  let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
  model = reduce(model, { type: 'selectRoute', turnID, route: hub(sessionID) }).model
  model = reduce(model, { type: 'finalize', turnID }).model
  model = reduce(model, { type: 'hubCommitAccepted', turnID, sessionID, responseID }).model
  return { model, turnID, sessionID, responseID }
}

function representativeActiveModels(): VoiceTurnModel[] {
  const turnID = newTurnID()
  const sessionID = newSessionID()
  const responseID = response('response')
  const recording = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
  const pending = reduce(recording, { type: 'openLockWindow', turnID }).model
  const locked = reduce(recording, { type: 'lock', turnID }).model
  const finalizing = reduce(recording, { type: 'finalize', turnID }).model
  let awaiting = reduce(recording, { type: 'selectRoute', turnID, route: hub(sessionID) }).model
  awaiting = reduce(awaiting, { type: 'finalize', turnID }).model
  awaiting = reduce(awaiting, { type: 'hubCommitAccepted', turnID, sessionID, responseID }).model
  const tools = reduce(awaiting, { type: 'toolStarted', turnID, callID: tool('tool') }).model
  const playing = reduce(awaiting, {
    type: 'playbackStarted',
    turnID,
    lease: lease(turnID, 'nativeRealtime')
  }).model
  return [recording, pending, locked, finalizing, awaiting, tools, playing]
}

// ---- tests ----------------------------------------------------------------

describe('VoiceTurnReducer', () => {
  it('testHappyHubTurnTransitionsThroughPlaybackAndTerminatesExactlyOnce', () => {
    const turnID = newTurnID()
    const captureID = capture(7)
    const sessionID = newSessionID()
    const responseID = response('response-1')
    const activeLease = lease(turnID, 'nativeRealtime')
    let model = IDLE

    model = reduce(model, { type: 'start', turnID, intent: 'hold' }).model
    expect(model.turn?.phase).toEqual({ kind: 'recording' })
    expect(model.turn?.projection.isListening).toBe(true)

    model = reduce(model, { type: 'captureStarted', turnID, captureID }).model
    model = reduce(model, { type: 'selectRoute', turnID, route: hub(sessionID) }).model
    model = reduce(model, { type: 'finalize', turnID }).model
    expect(model.turn?.phase).toEqual({ kind: 'finalizing' })

    model = reduce(model, { type: 'hubCommitAccepted', turnID, sessionID, responseID }).model
    expect(model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(model.turn?.projection.isResponseWaiting).toBe(true)

    model = reduce(model, { type: 'providerResponseStarted', turnID, sessionID, responseID }).model
    expect(model.turn?.projection.isThinking).toBe(false)

    model = reduce(model, { type: 'playbackStarted', turnID, lease: activeLease }).model
    expect(model.turn?.phase).toEqual({ kind: 'playing', lane: 'nativeRealtime' })
    expect(model.turn?.activeLease).toEqual(activeLease)

    model = reduce(model, { type: 'providerTurnFinished', turnID, sessionID, responseID }).model

    const drained = reduce(model, { type: 'playbackDrained', turnID, leaseID: activeLease.id })
    expect(drained.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'success' })
    expect(drained.model.lastTerminal).toEqual({
      turnID,
      reason: 'success',
      route: hub(sessionID)
    })
    expect(drained.effects.filter(isTerminalEffect)).toHaveLength(1)

    const duplicate = reduce(drained.model, { type: 'finish', turnID, reason: 'success' })
    expect(duplicate.model.duplicateTerminalCount).toBe(1)
    expect(duplicate.effects.some(isTerminalEffect)).toBe(false)
  })

  it('testQuickTapLockWindowCanBecomeLockedRecording', () => {
    const turnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model

    model = reduce(model, { type: 'openLockWindow', turnID }).model
    expect(model.turn?.phase).toEqual({ kind: 'pendingLockDecision' })
    expect(model.turn?.deadlines.has('lockDecision')).toBe(true)

    const locked = reduce(model, { type: 'lock', turnID })
    expect(locked.model.turn?.phase).toEqual({ kind: 'lockedRecording' })
    expect(locked.model.turn?.intent).toBe('locked')
    expect(locked.model.turn?.projection.isLocked).toBe(true)
    expect(locked.effects).toContainEqual({
      kind: 'cancelDeadline',
      turnID,
      deadline: 'lockDecision'
    })
  })

  it('testLockWindowDeadlineFinalizesAndStopsCapture', () => {
    const turnID = newTurnID()
    const captureID = capture(8)
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'captureStarted', turnID, captureID }).model
    model = reduce(model, { type: 'openLockWindow', turnID }).model

    const result = reduce(model, { type: 'deadlineFired', turnID, deadline: 'lockDecision' })

    expect(result.model.turn?.phase).toEqual({ kind: 'finalizing' })
    expect(result.effects).toContainEqual({ kind: 'stopCapture', turnID, captureID })
  })

  it('testLateCaptureStartAfterFinalizationIsStoppedAndCannotResurrectTurn', () => {
    const turnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'finalize', turnID }).model
    const lateCaptureID = capture(99)

    const result = reduce(model, { type: 'captureStarted', turnID, captureID: lateCaptureID })

    expect(result.model.turn?.phase).toEqual({ kind: 'finalizing' })
    expect(result.model.turn?.captureID).toBeNull()
    expect(result.model.staleEventCount).toBe(1)
    expect(result.effects).toContainEqual({
      kind: 'stopCapture',
      turnID,
      captureID: lateCaptureID
    })
  })

  it('testOldTurnEventsAreDroppedAfterBargeInStartsNewTurn', () => {
    const oldTurnID = newTurnID()
    const newTurn = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID: oldTurnID, intent: 'hold' }).model

    const bargeIn = reduce(model, { type: 'start', turnID: newTurn, intent: 'hold' })
    model = bargeIn.model
    expect(model.turn?.id).toBe(newTurn)
    expect(model.lastTerminal).toEqual({
      turnID: oldTurnID,
      reason: 'interruptedByBargeIn',
      route: { kind: 'undecided' }
    })

    const stale = reduce(model, { type: 'transcriptionFinal', turnID: oldTurnID, text: 'old' })
    expect(stale.model.turn?.id).toBe(newTurn)
    expect(stale.model.turn?.projection.transcript).toBe('')
    expect(stale.model.staleEventCount).toBe(1)
  })

  it('testHubBargeInPreservesProviderRuntimeForAtomicHandoff', () => {
    const oldTurnID = newTurnID()
    const newTurn = newTurnID()
    const sessionID = newSessionID()
    let model = reduce(IDLE, { type: 'start', turnID: oldTurnID, intent: 'hold' }).model
    model = reduce(model, {
      type: 'selectRoute',
      turnID: oldTurnID,
      route: hub(sessionID)
    }).model

    const result = reduce(model, { type: 'start', turnID: newTurn, intent: 'hold' })

    expect(result.model.lastTerminal?.route).toEqual(hub(sessionID))
    expect(result.effects).not.toContainEqual({
      kind: 'cancelHub',
      turnID: oldTurnID,
      route: hub(sessionID)
    })
    expect(result.effects.some((e) => e.kind === 'stopPlayback' && e.turnID === oldTurnID)).toBe(
      false
    )
  })

  it('testHubWarmTimeoutFallsBackWithoutTerminatingOrDroppingTurn', () => {
    const turnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'selectRoute', turnID, route: { kind: 'hubWarmWait' } }).model
    model = reduce(model, { type: 'finalize', turnID }).model

    const timedOut = reduce(model, { type: 'deadlineFired', turnID, deadline: 'hubWarm' })

    expect(timedOut.model.turn?.route).toEqual({ kind: 'deepgramBatch' })
    expect(timedOut.model.turn?.phase).toEqual({ kind: 'finalizing' })
    expect(timedOut.model.turn?.terminalReason).toBeNull()
    expect(timedOut.effects).toContainEqual({
      kind: 'fallbackToTranscription',
      turnID,
      reason: 'hubWarmTimeout'
    })
  })

  it('testHubReadyCancelsWarmDeadlineAndPreservesRecording', () => {
    const turnID = newTurnID()
    const sessionID = newSessionID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'selectRoute', turnID, route: { kind: 'hubWarmWait' } }).model

    const ready = reduce(model, { type: 'hubReady', turnID, sessionID })

    expect(ready.model.turn?.route).toEqual(hub(sessionID))
    expect(ready.model.turn?.sessionID).toBe(sessionID)
    expect(ready.model.turn?.phase).toEqual({ kind: 'recording' })
    expect(ready.effects).toContainEqual({ kind: 'cancelDeadline', turnID, deadline: 'hubWarm' })
  })

  it('testDeferredCommitTimeoutTerminatesWithTypedReason', () => {
    const turnID = newTurnID()
    const sessionID = newSessionID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'selectRoute', turnID, route: hub(sessionID) }).model
    model = reduce(model, { type: 'finalize', turnID }).model
    model = reduce(model, { type: 'hubCommitDeferred', turnID }).model

    const result = reduce(model, { type: 'deadlineFired', turnID, deadline: 'deferredCommit' })

    expect(result.model.turn?.phase).toEqual({
      kind: 'terminal',
      reason: 'deferredCommitTimeout'
    })
    expect(result.model.lastTerminal?.reason).toBe('deferredCommitTimeout')
  })

  it('testBargeInReplacementCommitHasDistinctDeadlineAndCanResumeOnFreshSession', () => {
    const turnID = newTurnID()
    const oldSessionID = newSessionID()
    const replacementSessionID = newSessionID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'selectRoute', turnID, route: hub(oldSessionID) }).model
    model = reduce(model, { type: 'finalize', turnID }).model

    const deferred = reduce(model, { type: 'hubCommitDeferredForReplacement', turnID })
    expect(deferred.model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(deferred.model.turn?.deadlines.has('bargeInReplacement')).toBe(true)
    expect(deferred.model.turn?.deadlines.has('deferredCommit')).toBe(false)

    // `selectRoute` set the route's sessionID but never the TURN's sessionID, so
    // the fence still admits a fresh replacement session.
    const accepted = reduce(deferred.model, {
      type: 'hubCommitAccepted',
      turnID,
      sessionID: replacementSessionID,
      responseID: null
    })
    expect(accepted.model.turn?.sessionID).toBe(replacementSessionID)
    expect(accepted.model.turn?.deadlines.has('bargeInReplacement')).toBe(false)
    expect(accepted.model.turn?.deadlines.has('providerResponse')).toBe(true)
    expect(accepted.effects).toContainEqual({
      kind: 'cancelDeadline',
      turnID,
      deadline: 'bargeInReplacement'
    })
  })

  it('testBargeInReplacementDeadlineTerminatesWithTypedReason', () => {
    const turnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'selectRoute', turnID, route: hub(null) }).model
    model = reduce(model, { type: 'finalize', turnID }).model
    model = reduce(model, { type: 'hubCommitDeferredForReplacement', turnID }).model

    const result = reduce(model, { type: 'deadlineFired', turnID, deadline: 'bargeInReplacement' })

    expect(result.model.turn?.phase).toEqual({
      kind: 'terminal',
      reason: 'bargeInReplacementTimeout'
    })
    expect(result.model.lastTerminal?.reason).toBe('bargeInReplacementTimeout')
  })

  it('testProviderNoResponseDeadlineTerminatesAndShowsActionableHint', () => {
    const { model, turnID } = awaitingHubResponse()

    const result = reduce(model, { type: 'deadlineFired', turnID, deadline: 'providerResponse' })

    expect(result.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'providerNoResponse' })
    expect(result.model.turn?.projection.isListening).toBe(false)
    expect(result.model.turn?.projection.isThinking).toBe(false)
    expect(result.model.turn?.projection.isResponseActive).toBe(false)
    expect(result.model.turn?.projection.hint).toBe('Voice response failed — try again')
    expect(result.model.turn?.deadlines.has('hintVisibility')).toBe(true)
  })

  it('testProviderEventFromReplacedSessionIsDropped', () => {
    const { model, turnID, responseID } = awaitingHubResponse()
    const staleSession = newSessionID()

    const result = reduce(model, {
      type: 'providerResponseStarted',
      turnID,
      sessionID: staleSession,
      responseID
    })

    expect(result.model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(result.model.staleEventCount).toBe(1)
  })

  it('testProviderEventFromReplacedResponseIsDropped', () => {
    const { model, turnID, sessionID } = awaitingHubResponse()

    const result = reduce(model, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID: response('stale')
    })

    expect(result.model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(result.model.staleEventCount).toBe(1)
  })

  // THE nil-identity fence. A callback that lost its identity is stale, NOT accepted.
  it('testProviderCallbackMissingKnownIdentityIsDropped', () => {
    const { model, turnID } = awaitingHubResponse()

    const started = reduce(model, {
      type: 'providerResponseStarted',
      turnID,
      sessionID: null,
      responseID: null
    })
    const finished = reduce(model, {
      type: 'providerTurnFinished',
      turnID,
      sessionID: null,
      responseID: null
    })

    expect(started.model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(started.model.staleEventCount).toBe(1)
    expect(finished.model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(finished.model.staleEventCount).toBe(1)
  })

  it('testProviderCanFinishSuccessfullyWithoutStartingPlayback', () => {
    const { model, turnID, sessionID, responseID } = awaitingHubResponse()

    const result = reduce(model, { type: 'providerTurnFinished', turnID, sessionID, responseID })

    expect(result.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'success' })
    expect(result.model.lastTerminal?.reason).toBe('success')
  })

  it('testToolCompletionKeepsTurnOpenUntilEveryToolFinishes', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    const first = tool('first')
    const second = tool('second')
    model = reduce(model, { type: 'toolStarted', turnID, callID: first }).model
    model = reduce(model, { type: 'toolStarted', turnID, callID: second }).model

    model = reduce(model, { type: 'toolFinished', turnID, callID: first }).model
    expect(model.turn?.phase).toEqual({ kind: 'awaitingTools' })
    expect(model.turn?.pendingToolCallIDs).toEqual(new Set([second]))

    const finished = reduce(model, { type: 'toolFinished', turnID, callID: second })
    expect(finished.model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(finished.model.turn?.pendingToolCallIDs.size).toBe(0)
    expect(finished.effects).toContainEqual({
      kind: 'cancelDeadline',
      turnID,
      deadline: 'pendingTools'
    })
    expect(finished.model.turn?.deadlines.has('providerResponse')).toBe(true)
  })

  it('testProviderFinishDuringToolWaitTerminatesAfterLastToolAndOnlyThen', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    const callID = tool('pending')
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    model = reduce(model, { type: 'toolStarted', turnID, callID }).model

    const providerFinished = reduce(model, {
      type: 'providerTurnFinished',
      turnID,
      sessionID,
      responseID
    })
    expect(providerFinished.model.turn?.phase).toEqual({ kind: 'awaitingTools' })
    expect(providerFinished.model.lastTerminal).toBeNull()

    const toolFinished = reduce(providerFinished.model, { type: 'toolFinished', turnID, callID })
    expect(toolFinished.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'success' })
    expect(toolFinished.model.lastTerminal?.reason).toBe('success')
  })

  it('testToolAndPlaybackCanDrainInEitherOrderWithoutClosingEarly', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    const callID = tool('tool')
    const activeLease = lease(turnID, 'nativeRealtime')
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    model = reduce(model, { type: 'playbackStarted', turnID, lease: activeLease }).model
    model = reduce(model, { type: 'toolStarted', turnID, callID }).model
    model = reduce(model, { type: 'providerTurnFinished', turnID, sessionID, responseID }).model

    const drained = reduce(model, { type: 'playbackDrained', turnID, leaseID: activeLease.id })
    expect(drained.model.turn?.phase).toEqual({ kind: 'awaitingTools' })
    expect(drained.model.lastTerminal).toBeNull()

    const finished = reduce(drained.model, { type: 'toolFinished', turnID, callID })
    expect(finished.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'success' })
  })

  it('testProviderOutputCannotMutateRecordingTurnBeforeCommit', () => {
    const turnID = newTurnID()
    const activeLease = lease(turnID, 'nativeRealtime')
    const recording = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model

    const started = reduce(recording, {
      type: 'providerResponseStarted',
      turnID,
      sessionID: newSessionID(),
      responseID: null
    })
    const playback = reduce(recording, { type: 'playbackStarted', turnID, lease: activeLease })

    expect(started.model.turn?.phase).toEqual({ kind: 'recording' })
    expect(started.model.invalidTransitionCount).toBe(1)
    expect(playback.model.turn?.phase).toEqual({ kind: 'recording' })
    expect(playback.model.turn?.activeLease).toBeNull()
    expect(playback.model.invalidTransitionCount).toBe(1)
  })

  it('testPendingToolDeadlineTerminates', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    model = reduce(model, { type: 'toolStarted', turnID, callID: tool('slow') }).model

    const result = reduce(model, { type: 'deadlineFired', turnID, deadline: 'pendingTools' })

    expect(result.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'toolTimeout' })
  })

  it('testCaptureTranscriptionAndPlaybackDeadlinesHaveDistinctTerminalReasons', () => {
    const captureTurnID = newTurnID()
    const capturing = reduce(IDLE, { type: 'start', turnID: captureTurnID, intent: 'hold' }).model
    expect(
      reduce(capturing, { type: 'deadlineFired', turnID: captureTurnID, deadline: 'captureStart' })
        .model.turn?.phase
    ).toEqual({ kind: 'terminal', reason: 'captureFailed' })

    const transcriptionTurnID = newTurnID()
    let transcribing = reduce(IDLE, {
      type: 'start',
      turnID: transcriptionTurnID,
      intent: 'hold'
    }).model
    transcribing = reduce(transcribing, {
      type: 'selectRoute',
      turnID: transcriptionTurnID,
      route: { kind: 'deepgramBatch' }
    }).model
    transcribing = reduce(transcribing, { type: 'finalize', turnID: transcriptionTurnID }).model
    transcribing = reduce(transcribing, {
      type: 'transcriptionStarted',
      turnID: transcriptionTurnID
    }).model
    expect(
      reduce(transcribing, {
        type: 'deadlineFired',
        turnID: transcriptionTurnID,
        deadline: 'transcription'
      }).model.turn?.phase
    ).toEqual({ kind: 'terminal', reason: 'transcriptionFailed' })

    const { model: awaiting, turnID: playbackTurnID } = awaitingHubResponse()
    const activeLease = lease(playbackTurnID, 'nativeRealtime')
    const playing = reduce(awaiting, {
      type: 'playbackStarted',
      turnID: playbackTurnID,
      lease: activeLease
    }).model
    expect(
      reduce(playing, {
        type: 'deadlineFired',
        turnID: playbackTurnID,
        deadline: 'playbackDrain'
      }).model.turn?.phase
    ).toEqual({ kind: 'terminal', reason: 'playbackFailed' })
  })

  it('testPlaybackFailureRequiresMatchingLeaseAndShowsErrorHint', () => {
    const { model: awaiting, turnID } = awaitingHubResponse()
    const activeLease = lease(turnID, 'selectedVoiceFallback')
    const playing = reduce(awaiting, { type: 'playbackStarted', turnID, lease: activeLease }).model

    const stale = reduce(playing, {
      type: 'playbackFailed',
      turnID,
      leaseID: newLeaseID(),
      message: 'stale'
    })
    expect(stale.model.turn?.phase).toEqual({ kind: 'playing', lane: 'selectedVoiceFallback' })
    expect(stale.model.staleEventCount).toBe(1)

    const failed = reduce(playing, {
      type: 'playbackFailed',
      turnID,
      leaseID: activeLease.id,
      message: 'fixture'
    })
    expect(failed.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'playbackFailed' })
    expect(failed.model.turn?.projection.hint).toBe('Audio playback failed')
  })

  it('testCompetingPlaybackLeaseIsRejectedAsInvalidTransition', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    const native = lease(turnID, 'nativeRealtime')
    const fallback = lease(turnID, 'selectedVoiceFallback')
    model = reduce(model, { type: 'playbackStarted', turnID, lease: native }).model

    const result = reduce(model, { type: 'playbackStarted', turnID, lease: fallback })

    expect(result.model.turn?.activeLease).toEqual(native)
    expect(result.model.invalidTransitionCount).toBe(1)
  })

  it('testStalePlaybackDrainCannotFinishCurrentLease', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    const activeLease = lease(turnID, 'nativeRealtime')
    model = reduce(model, { type: 'playbackStarted', turnID, lease: activeLease }).model

    const result = reduce(model, { type: 'playbackDrained', turnID, leaseID: newLeaseID() })

    expect(result.model.turn?.phase).toEqual({ kind: 'playing', lane: 'nativeRealtime' })
    expect(result.model.turn?.activeLease).toEqual(activeLease)
    expect(result.model.staleEventCount).toBe(1)
  })

  it('testProviderTurnDoneWaitsForMatchingPlaybackDrain', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    const activeLease = lease(turnID, 'nativeRealtime')
    model = reduce(model, { type: 'playbackStarted', turnID, lease: activeLease }).model

    const providerDone = reduce(model, {
      type: 'providerTurnFinished',
      turnID,
      sessionID,
      responseID
    })

    expect(providerDone.model.turn?.phase).toEqual({ kind: 'playing', lane: 'nativeRealtime' })
    expect(providerDone.model.turn?.providerFinished).toBe(true)
    expect(providerDone.model.lastTerminal).toBeNull()

    const drained = reduce(providerDone.model, {
      type: 'playbackDrained',
      turnID,
      leaseID: activeLease.id
    })
    expect(drained.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'success' })
  })

  it('testPlaybackDrainBeforeProviderDoneReturnsToAwaitingResponse', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    const activeLease = lease(turnID, 'nativeRealtime')
    model = reduce(model, { type: 'playbackStarted', turnID, lease: activeLease }).model

    const drained = reduce(model, { type: 'playbackDrained', turnID, leaseID: activeLease.id })

    expect(drained.model.turn?.phase).toEqual({ kind: 'awaitingResponse' })
    expect(drained.model.lastTerminal).toBeNull()
    expect(drained.model.turn?.deadlines.has('providerResponse')).toBe(true)
  })

  it('testCleanupFromEveryNonIdlePhaseConvergesToTerminalThenReset', () => {
    for (const model of representativeActiveModels()) {
      const cleaned = reduce(model, { type: 'cleanup' })
      expect(cleaned.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'cleanup' })
      expect(cleaned.model.turn?.projection).toEqual(IDLE_PROJECTION)
      expect(cleaned.effects.some(isTerminalEffect)).toBe(true)

      const reset = reduce(cleaned.model, { type: 'reset' })
      expect(reset.model.turn).toBeNull()
      expect(reset.model.lastTerminal?.reason).toBe('cleanup')
    }
  })

  it('testInvalidTransitionDoesNotMutateTurn', () => {
    const turnID = newTurnID()
    const model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model

    const result = reduce(model, {
      type: 'hubCommitAccepted',
      turnID,
      sessionID: newSessionID(),
      responseID: response('unexpected')
    })

    expect(result.model.turn).toEqual(model.turn)
    expect(result.model.invalidTransitionCount).toBe(1)
  })

  it('testDeferredCommitCannotSkipFinalization', () => {
    const turnID = newTurnID()
    let recording = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    recording = reduce(recording, { type: 'selectRoute', turnID, route: hub(null) }).model

    const generic = reduce(recording, { type: 'hubCommitDeferred', turnID })
    const replacement = reduce(recording, { type: 'hubCommitDeferredForReplacement', turnID })

    expect(generic.model.turn?.phase).toEqual({ kind: 'recording' })
    expect(generic.model.invalidTransitionCount).toBe(1)
    expect(replacement.model.turn?.phase).toEqual({ kind: 'recording' })
    expect(replacement.model.invalidTransitionCount).toBe(1)
  })

  it('testHubTerminalCleanupCarriesOldRouteInEffectPayload', () => {
    const turnID = newTurnID()
    const route = hub(newSessionID())
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'selectRoute', turnID, route }).model

    const cancelled = reduce(model, { type: 'cancel', turnID, reason: 'cancelled' })

    expect(cancelled.effects).toContainEqual({ kind: 'cancelHub', turnID, route })
    expect(routeMatchesHub(route)).toBe(true)
    expect(routeMatchesHub({ kind: 'deepgramBatch' })).toBe(false)
  })

  it('testHintDeadlineOnlyClearsTheCurrentTurnHint', () => {
    const turnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'hintChanged', turnID, text: 'Hold longer' }).model

    const cleared = reduce(model, { type: 'deadlineFired', turnID, deadline: 'hintVisibility' })

    expect(cleared.model.turn?.projection.hint).toBe('')
  })

  it('testTerminalHintDeadlineClearsHintWithoutResurrectingTurn', () => {
    const turnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'finish', turnID, reason: 'tooShort' }).model
    expect(model.turn?.projection.hint).toBe('Hold longer to record')

    const cleared = reduce(model, { type: 'deadlineFired', turnID, deadline: 'hintVisibility' })

    expect(cleared.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'tooShort' })
    expect(cleared.model.turn?.projection.hint).toBe('')
  })

  it('testSemanticPresentationEventsUpdateProjectionWithoutOwningIO', () => {
    const { model: starting, turnID } = awaitingHubResponse()
    let model = reduce(starting, { type: 'transcriptChanged', turnID, text: 'hello' }).model
    model = reduce(model, { type: 'hintChanged', turnID, text: 'working' }).model
    model = reduce(model, { type: 'responseWaitingChanged', turnID, active: true }).model
    expect(model.turn?.projection.transcript).toBe('hello')
    expect(model.turn?.projection.hint).toBe('working')
    expect(model.turn?.projection.isThinking).toBe(true)

    model = reduce(model, { type: 'responseActiveChanged', turnID, active: true }).model
    expect(model.turn?.projection.isResponseActive).toBe(true)
    expect(model.turn?.projection.isResponseWaiting).toBe(false)
    expect(model.turn?.projection.isThinking).toBe(false)

    const cleared = reduce(model, { type: 'hintChanged', turnID, text: '' })
    expect(cleared.model.turn?.projection.hint).toBe('')
    expect(cleared.effects).toContainEqual({
      kind: 'cancelDeadline',
      turnID,
      deadline: 'hintVisibility'
    })
  })

  it('testRandomizedStaleEventsNeverChangeActiveTurnIdentityOrTerminalizeIt', () => {
    const activeTurnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID: activeTurnID, intent: 'hold' }).model
    const initialStaleCount = model.staleEventCount

    for (let index = 0; index < 250; index++) {
      const staleID = newTurnID()
      let event: VoiceTurnEvent
      switch (index % 5) {
        case 0:
          event = { type: 'finalize', turnID: staleID }
          break
        case 1:
          event = { type: 'transcriptionFinal', turnID: staleID, text: 'stale' }
          break
        case 2:
          event = { type: 'toolFinished', turnID: staleID, callID: tool(`${index}`) }
          break
        case 3:
          event = { type: 'playbackDrained', turnID: staleID, leaseID: newLeaseID() }
          break
        default:
          event = { type: 'deadlineFired', turnID: staleID, deadline: 'providerResponse' }
      }
      model = reduce(model, event).model
      expect(model.turn?.id).toBe(activeTurnID)
      expect(model.turn?.phase.kind).not.toBe('terminal')
    }

    expect(model.staleEventCount).toBe(initialStaleCount + 250)
  })

  it('testClearPresentationIsARealReducerTransition', () => {
    const turnID = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'transcriptChanged', turnID, text: 'private words' }).model
    model = reduce(model, { type: 'responseActiveChanged', turnID, active: true }).model

    const cleared = reduce(model, { type: 'clearPresentation', turnID })

    expect(cleared.model.turn?.projection).toEqual(IDLE_PROJECTION)
    expect(cleared.model.turn?.phase).toEqual({ kind: 'recording' })
  })

  it('testDiagnosticLabelsNeverContainSpeechOrErrorPayloads', () => {
    const marker = 'secret-marker-9381'
    const turnID = newTurnID()
    const events: VoiceTurnEvent[] = [
      { type: 'transcriptChanged', turnID, text: marker },
      { type: 'transcriptionFinal', turnID, text: marker },
      { type: 'playbackFailed', turnID, leaseID: null, message: marker },
      { type: 'captureFailed', turnID, captureID: null, message: marker }
    ]

    for (const event of events) {
      expect(diagnosticLabel(event)).not.toContain(marker)
      const stale = reduce(IDLE, event)
      const last = stale.effects[stale.effects.length - 1]
      expect(last?.kind).toBe('staleEventDropped')
      if (last?.kind !== 'staleEventDropped') throw new Error('expected stale diagnostic effect')
      expect(last.event).toBe(diagnosticLabel(event))
      expect(last.event).not.toContain(marker)
    }
  })

  it('testNewTurnResetsPerTurnAnomalyCounters', () => {
    const turnA = newTurnID()
    let model = reduce(IDLE, { type: 'start', turnID: turnA, intent: 'hold' }).model
    model = reduce(model, { type: 'finalize', turnID: newTurnID() }).model
    model = reduce(model, {
      type: 'hubCommitAccepted',
      turnID: turnA,
      sessionID: newSessionID(),
      responseID: null
    }).model
    expect(model.staleEventCount).toBe(1)
    expect(model.invalidTransitionCount).toBe(1)

    const turnB = newTurnID()
    model = reduce(model, { type: 'start', turnID: turnB, intent: 'hold' }).model

    expect(model.turn?.id).toBe(turnB)
    expect(model.staleEventCount).toBe(0)
    expect(model.invalidTransitionCount).toBe(0)
    expect(model.duplicateTerminalCount).toBe(0)
  })

  // --- PORT GUARD (beyond the Swift 38) -----------------------------------
  // Swift `cancel(_:)` emits only when `Set.remove` returned non-nil. A port
  // that emits unconditionally produces spurious `cancelDeadline` effects for
  // deadlines that were never held. On macOS the coordinator suite catches this
  // (`testTerminalEffectAndCleanupAreExactlyOnce`); no reducer test does, so the
  // trap would survive until PR-2. Pinned here at the layer that owns it.
  it('cancelEmitsNothingForADeadlineTheTurnDoesNotHold', () => {
    const turnID = newTurnID()
    // `finalize` cancels BOTH lockDecision and captureStart, but a plain hold
    // only ever armed captureStart.
    const model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    expect(model.turn?.deadlines.has('lockDecision')).toBe(false)
    expect(model.turn?.deadlines.has('captureStart')).toBe(true)

    const finalized = reduce(model, { type: 'finalize', turnID })

    const cancels = finalized.effects.filter((e) => e.kind === 'cancelDeadline')
    expect(cancels).toEqual([{ kind: 'cancelDeadline', turnID, deadline: 'captureStart' }])
  })

  // Swift's `terminate()` binds `guard var turn = model.turn` — the MUTATED model,
  // NOT the pre-event snapshot every other guard reads. `playbackDrained` nulls
  // `activeLease` BEFORE calling terminate, so a successful drain must emit NO
  // `stopPlayback` — the lease already drained itself; stopping it again would
  // tear down the next turn's playback. A port that snapshots the lease pre-event
  // (the natural reading of the "guards read pre-event" rule) emits a spurious
  // one. No Swift reducer test pins this; pinned here.
  it('successfulPlaybackDrainTerminatesWithoutEmittingStopPlayback', () => {
    const { model: starting, turnID, sessionID, responseID } = awaitingHubResponse()
    let model = reduce(starting, {
      type: 'providerResponseStarted',
      turnID,
      sessionID,
      responseID
    }).model
    const activeLease = lease(turnID, 'nativeRealtime')
    model = reduce(model, { type: 'playbackStarted', turnID, lease: activeLease }).model
    model = reduce(model, { type: 'providerTurnFinished', turnID, sessionID, responseID }).model

    const drained = reduce(model, { type: 'playbackDrained', turnID, leaseID: activeLease.id })

    expect(drained.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'success' })
    expect(drained.effects.filter((e) => e.kind === 'stopPlayback')).toEqual([])

    // Control: a lease that is STILL active at terminate time DOES get stopped.
    const cancelled = reduce(model, { type: 'cancel', turnID, reason: 'cancelled' })
    expect(cancelled.effects).toContainEqual({
      kind: 'stopPlayback',
      turnID,
      leaseID: activeLease.id
    })
  })

  // Effect emission ORDER inside terminate() is load-bearing: `stopCapture` must
  // precede `cancelHub`, or a trailing PCM chunk can revive the socket the
  // reducer just asked the host to tear down. Order is invisible to
  // `toContainEqual`, so it needs its own assertion.
  it('terminateEmitsStopCaptureBeforeCancelHub', () => {
    const turnID = newTurnID()
    const captureID = capture(11)
    let model = reduce(IDLE, { type: 'start', turnID, intent: 'hold' }).model
    model = reduce(model, { type: 'captureStarted', turnID, captureID }).model
    model = reduce(model, { type: 'selectRoute', turnID, route: hub(newSessionID()) }).model

    const cancelled = reduce(model, { type: 'cancel', turnID, reason: 'cancelled' })

    const order = cancelled.effects
      .map((e) => e.kind)
      .filter((k) => k === 'stopCapture' || k === 'cancelHub')
    expect(order).toEqual(['stopCapture', 'cancelHub'])
  })
})
