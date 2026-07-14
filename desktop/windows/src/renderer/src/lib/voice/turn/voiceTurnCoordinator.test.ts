// 1:1 port of macOS `VoiceTurnCoordinatorTests.swift` (14 cases). The Swift test
// names are kept verbatim — each one documents an invariant of the drain/timer
// model, and a renamed test is an invariant nobody can trace back to the
// reference. Windows-only additions (route-aware deadlines, the production
// setTimeout scheduler, throwing-handler recovery) are grouped at the end.
import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  VoiceTurnCoordinator,
  CASCADE_VOICE_TURN_DEADLINES,
  deadlinesForVoiceTurnRoute,
  expandsBarForVoice,
  timeoutVoiceTurnScheduler,
  voiceTurnPhaseLabel,
  voiceTurnRouteLabel,
  type VoiceTurnDeadlineCancellation,
  type VoiceTurnDeadlineScheduling
} from './voiceTurnCoordinator'
import {
  DEFAULT_VOICE_TURN_DEADLINES,
  IDLE_VOICE_TURN_MODEL,
  type VoiceCaptureID,
  type VoiceLeaseID,
  type VoiceSessionID,
  type VoiceTurnEffect,
  type VoiceTurnID,
  type VoiceTurnModel,
  type VoiceTurnRoute,
  type VoiceTurnTerminalRecord,
  type VoiceTurnUIProjection
} from './voiceTurnMachine'

// ---- fixtures -------------------------------------------------------------

let seq = 0
const newTurnID = (): VoiceTurnID => `turn-${++seq}` as VoiceTurnID
const newSessionID = (): VoiceSessionID => `session-${++seq}` as VoiceSessionID
const capture = (n: number): VoiceCaptureID => n as VoiceCaptureID
const lease = (s: string): VoiceLeaseID => s as VoiceLeaseID

/** Port of Swift's `ManualVoiceTurnScheduler` — the fake clock. */
class ManualVoiceTurnScheduler implements VoiceTurnDeadlineScheduling {
  private scheduled: {
    deadline: string
    afterSeconds: number
    fire: () => void
    cancelled: boolean
  }[] = []

  schedule(
    deadline: string,
    afterSeconds: number,
    fire: () => void
  ): VoiceTurnDeadlineCancellation {
    const entry = { deadline, afterSeconds, fire, cancelled: false }
    this.scheduled.push(entry)
    return {
      cancel: () => {
        entry.cancelled = true
      }
    }
  }

  get activeCount(): number {
    return this.scheduled.filter((entry) => !entry.cancelled).length
  }

  /** Fires the oldest live timer for this deadline; a no-op if it was cancelled. */
  fire(deadline: string): void {
    const index = this.scheduled.findIndex(
      (entry) => entry.deadline === deadline && !entry.cancelled
    )
    if (index < 0) return
    const [entry] = this.scheduled.splice(index, 1)
    entry.fire()
  }

  delayFor(deadline: string): number | null {
    return this.scheduled.find((e) => e.deadline === deadline && !e.cancelled)?.afterSeconds ?? null
  }
}

const manual = (): { scheduler: ManualVoiceTurnScheduler; coordinator: VoiceTurnCoordinator } => {
  const scheduler = new ManualVoiceTurnScheduler()
  return {
    scheduler,
    coordinator: new VoiceTurnCoordinator({ scheduler, mintTurnID: newTurnID })
  }
}

/** A fake bar store: the presenter port, recording every projection it is given. */
class RecordingPresenter {
  projections: VoiceTurnUIProjection[] = []
  apply(projection: VoiceTurnUIProjection): void {
    this.projections.push(projection)
  }
  get last(): VoiceTurnUIProjection {
    return this.projections[this.projections.length - 1]
  }
}

/** Port of `RealtimeHubWarmWaitResolutionGate` (PushToTalkManager.swift:40) —
 *  Mac production code that lands on Windows with PR-6's host; inlined here so
 *  PR-2 can port the coordinator test that depends on it. */
class RealtimeHubWarmWaitResolutionGate {
  route: VoiceTurnRoute | null = null
  observe(nextRoute: VoiceTurnRoute | null): boolean {
    const wasWaitingForHub = this.route?.kind === 'hubWarmWait'
    this.route = nextRoute
    return wasWaitingForHub && nextRoute?.kind === 'hub'
  }
}

const terminalsOf = (effects: VoiceTurnEffect[]): VoiceTurnTerminalRecord[] =>
  effects.flatMap((effect) => (effect.kind === 'terminal' ? [effect.record] : []))

// ---- ported Swift cases ---------------------------------------------------

describe('VoiceTurnCoordinator (port of VoiceTurnCoordinatorTests.swift)', () => {
  it('testFakeClockDrivesLockDeadlineAndRealStopCaptureEffect', () => {
    const { scheduler, coordinator } = manual()
    const effects: VoiceTurnEffect[] = []
    coordinator.setEffectHandler((effect) => effects.push(effect))
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'captureStarted', turnID, captureID: capture(1) })
    coordinator.send({ type: 'openLockWindow', turnID })

    scheduler.fire('lockDecision')

    expect(coordinator.model.turn?.phase).toEqual({ kind: 'finalizing' })
    expect(effects).toContainEqual({ kind: 'stopCapture', turnID, captureID: capture(1) })
  })

  it('testCancelledDeadlineCannotMutateLaterTurn', () => {
    const { scheduler, coordinator } = manual()
    const oldTurn = coordinator.begin('hold')
    coordinator.send({ type: 'openLockWindow', turnID: oldTurn })
    const newTurn = coordinator.begin('hold')

    scheduler.fire('lockDecision')

    expect(coordinator.activeTurnID).toBe(newTurn)
    expect(coordinator.model.turn?.phase).toEqual({ kind: 'recording' })
  })

  it('testTimelineReconstructsTurnAndIsBounded', () => {
    const coordinator = new VoiceTurnCoordinator({
      scheduler: new ManualVoiceTurnScheduler(),
      mintTurnID: newTurnID,
      timelineLimit: 4
    })
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'captureStarted', turnID, captureID: capture(1) })
    coordinator.send({ type: 'selectRoute', turnID, route: { kind: 'deepgramBatch' } })
    coordinator.send({ type: 'finalize', turnID })
    coordinator.send({ type: 'transcriptionStarted', turnID })

    const timeline = coordinator.timelineSnapshot()
    expect(timeline).toHaveLength(4)
    expect(timeline[timeline.length - 1].turnID).toBe(turnID)
    expect(timeline[timeline.length - 1].phaseAfter).toEqual({ kind: 'finalizing' })
    expect(timeline[timeline.length - 1].route).toEqual({ kind: 'deepgramBatch' })
  })

  // Windows deviation: Mac asserts against `FloatingControlBarState`. The bar
  // store is PR-6's; the invariant under test is the PROJECTION the presenter
  // port receives, plus Mac's expand rule (`isListening || hint != ""`), which
  // is why the pill stays expanded on a terminal hint.
  it('testPresenterDerivesConsistentListeningThinkingAndTerminalUI', () => {
    const { coordinator } = manual()
    const presenter = new RecordingPresenter()
    coordinator.configure(presenter)
    const turnID = coordinator.begin('hold')
    expect(presenter.last.isListening).toBe(true)
    expect(presenter.last.isThinking).toBe(false)

    coordinator.send({ type: 'selectRoute', turnID, route: { kind: 'deepgramBatch' } })
    coordinator.send({ type: 'finalize', turnID })
    coordinator.send({ type: 'transcriptionStarted', turnID })
    expect(presenter.last.isListening).toBe(false)
    expect(presenter.last.isThinking).toBe(true)
    expect(presenter.last.transcript).toBe('Transcribing…')

    coordinator.send({ type: 'transcriptionFailed', turnID, message: 'fixture' })
    // The capture/listening phase is over, but the pill remains expanded long
    // enough to make the actionable terminal hint visible to the user.
    expect(expandsBarForVoice(presenter.last)).toBe(true)
    expect(presenter.last.isListening).toBe(false)
    expect(presenter.last.isThinking).toBe(false)
    expect(presenter.last.isResponseActive).toBe(false)
    expect(presenter.last.hint).toBe("Couldn't transcribe that — try again")
  })

  it('testTerminalEffectAndCleanupAreExactlyOnce', () => {
    const { coordinator } = manual()
    const terminals: VoiceTurnTerminalRecord[] = []
    coordinator.setEffectHandler((effect) => {
      if (effect.kind === 'terminal') terminals.push(effect.record)
    })
    const turnID = coordinator.begin('hold')

    coordinator.send({ type: 'cancel', turnID, reason: 'cancelled' })
    coordinator.send({ type: 'finish', turnID, reason: 'providerFailed' })

    expect(terminals).toEqual([{ turnID, reason: 'cancelled', route: { kind: 'undecided' } }])
    expect(coordinator.model.duplicateTerminalCount).toBe(1)
  })

  it('testUnscopedPlaybackUsesPresenterButCannotOverrideActivePTTTurn', () => {
    const { coordinator } = manual()
    const presenter = new RecordingPresenter()
    coordinator.configure(presenter)

    coordinator.setUnscopedResponseActive(true)
    expect(presenter.last.isResponseActive).toBe(true)
    coordinator.setUnscopedResponseActive(false)
    expect(presenter.last.isResponseActive).toBe(false)

    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'selectRoute', turnID, route: { kind: 'deepgramBatch' } })
    coordinator.send({ type: 'finalize', turnID })
    coordinator.send({ type: 'transcriptionStarted', turnID })
    coordinator.send({ type: 'transcriptionFinal', turnID, text: 'hello' })
    coordinator.send({
      type: 'providerResponseStarted',
      turnID,
      sessionID: null,
      responseID: null
    })
    expect(presenter.last.isResponseActive).toBe(true)

    coordinator.setUnscopedResponseActive(false)
    expect(presenter.last.isResponseActive).toBe(true)
  })

  it('testSnapshotHandlerReceivesInitialAndSubsequentAuthoritativeModels', () => {
    const { coordinator } = manual()
    const snapshots: VoiceTurnModel[] = []
    coordinator.setSnapshotHandler((model) => snapshots.push(model))

    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'lock', turnID })

    expect(snapshots[0]).toEqual(IDLE_VOICE_TURN_MODEL)
    expect(snapshots[snapshots.length - 1].turn?.phase).toEqual({ kind: 'lockedRecording' })
    expect(snapshots).toHaveLength(3)
  })

  it('testHubReadyTransitionIsConsumedBeforeReentrantSnapshot', () => {
    const { coordinator } = manual()
    const sessionID = newSessionID()
    const gate = new RealtimeHubWarmWaitResolutionGate()
    let resolutions = 0
    coordinator.setSnapshotHandler((model) => {
      if (!gate.observe(model.turn?.route ?? null)) return
      resolutions += 1
      const activeTurnID = coordinator.activeTurnID
      expect(activeTurnID, 'hub-ready transition must retain its active turn').not.toBeNull()
      // The hub controller clears its response glow synchronously on beginTurn,
      // which publishes another snapshot. The consumed transition must not run
      // the warm-wait resolver again.
      coordinator.send({
        type: 'responseActiveChanged',
        turnID: activeTurnID as VoiceTurnID,
        active: false
      })
    })

    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'selectRoute', turnID, route: { kind: 'hubWarmWait' } })
    coordinator.send({ type: 'hubReady', turnID, sessionID })

    expect(resolutions).toBe(1)
    expect(gate.route).toEqual({ kind: 'hub', sessionID })
  })

  it('testSnapshotReentrantEventsDrainFIFOWithoutRecursiveCallbacks', () => {
    const { coordinator } = manual()
    let callbackDepth = 0
    let maximumCallbackDepth = 0
    let queuedRouteSelection = false

    coordinator.setSnapshotHandler((model) => {
      callbackDepth += 1
      maximumCallbackDepth = Math.max(maximumCallbackDepth, callbackDepth)
      try {
        const turn = model.turn
        if (queuedRouteSelection || !turn || turn.phase.kind !== 'recording') return
        queuedRouteSelection = true
        coordinator.send({ type: 'selectRoute', turnID: turn.id, route: { kind: 'deepgramBatch' } })

        expect(
          coordinator.model.turn?.route,
          'a nested event must not mutate the model until the current snapshot returns'
        ).toEqual({ kind: 'undecided' })
      } finally {
        callbackDepth -= 1
      }
    })

    const turnID = coordinator.begin('hold')

    expect(maximumCallbackDepth).toBe(1)
    expect(coordinator.model.turn?.route).toEqual({ kind: 'deepgramBatch' })
    expect(
      coordinator
        .timelineSnapshot()
        .slice(-2)
        .map((entry) => entry.event)
    ).toEqual(['start', 'select_route'])
    expect(coordinator.activeTurnID).toBe(turnID)
  })

  it('testEffectReentrantTerminalEventRunsAfterCurrentEffectReturns', () => {
    const { coordinator } = manual()
    const turnID = coordinator.begin('hold')
    const captureID = capture(91)
    coordinator.send({ type: 'captureStarted', turnID, captureID })

    let callbackDepth = 0
    let maximumCallbackDepth = 0
    let queuedCancellation = false
    const effects: VoiceTurnEffect[] = []
    coordinator.setEffectHandler((effect) => {
      callbackDepth += 1
      maximumCallbackDepth = Math.max(maximumCallbackDepth, callbackDepth)
      effects.push(effect)
      try {
        const isStopCapture =
          effect.kind === 'stopCapture' &&
          effect.turnID === turnID &&
          effect.captureID === captureID
        if (queuedCancellation || !isStopCapture) return
        queuedCancellation = true
        coordinator.send({ type: 'cancel', turnID, reason: 'cancelled' })

        expect(
          coordinator.model.turn?.phase,
          'a nested terminal event must wait until the current effect returns'
        ).toEqual({ kind: 'finalizing' })
      } finally {
        callbackDepth -= 1
      }
    })

    coordinator.send({ type: 'finalize', turnID })

    expect(maximumCallbackDepth).toBe(1)
    expect(coordinator.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'cancelled' })
    expect(terminalsOf(effects)).toEqual([
      { turnID, reason: 'cancelled', route: { kind: 'undecided' } }
    ])
    expect(
      coordinator
        .timelineSnapshot()
        .slice(-2)
        .map((entry) => entry.event)
    ).toEqual(['finalize', 'cancel'])
  })

  it('testResetCancelsOutstandingDeadlinesAndReturnsPresentationToIdle', () => {
    const { scheduler, coordinator } = manual()
    const presenter = new RecordingPresenter()
    coordinator.configure(presenter)
    coordinator.begin('hold')
    expect(presenter.last.isListening).toBe(true)
    expect(scheduler.activeCount).toBeGreaterThan(0)

    coordinator.reset()

    expect(coordinator.activeTurn).toBeNull()
    expect(coordinator.model.turn).toBeNull()
    expect(presenter.last.isListening).toBe(false)
    expect(scheduler.activeCount).toBe(0)
  })

  it('testStaleAndInvalidTransitionsRemainObservableEffects', () => {
    const { coordinator } = manual()
    const effects: VoiceTurnEffect[] = []
    coordinator.setEffectHandler((effect) => effects.push(effect))
    const turnID = coordinator.begin('hold')

    coordinator.send({ type: 'finalize', turnID: newTurnID() })
    coordinator.send({
      type: 'hubCommitAccepted',
      turnID,
      sessionID: newSessionID(),
      responseID: null
    })

    expect(effects.some((effect) => effect.kind === 'staleEventDropped')).toBe(true)
    expect(effects.some((effect) => effect.kind === 'invalidTransition')).toBe(true)
    expect(coordinator.model.staleEventCount).toBe(1)
    expect(coordinator.model.invalidTransitionCount).toBe(1)
  })

  it('testDiagnosticLabelsAreStableAndLowCardinality', () => {
    expect(voiceTurnPhaseLabel({ kind: 'idle' })).toBe('idle')
    expect(voiceTurnPhaseLabel({ kind: 'pendingLockDecision' })).toBe('pending_lock_decision')
    expect(voiceTurnPhaseLabel({ kind: 'recording' })).toBe('recording')
    expect(voiceTurnPhaseLabel({ kind: 'lockedRecording' })).toBe('locked_recording')
    expect(voiceTurnPhaseLabel({ kind: 'finalizing' })).toBe('finalizing')
    expect(voiceTurnPhaseLabel({ kind: 'awaitingResponse' })).toBe('awaiting_response')
    expect(voiceTurnPhaseLabel({ kind: 'awaitingTools' })).toBe('awaiting_tools')
    expect(voiceTurnPhaseLabel({ kind: 'playing', lane: 'filler' })).toBe('playing_filler')
    expect(voiceTurnPhaseLabel({ kind: 'terminal', reason: 'providerFailed' })).toBe(
      'terminal_provider_failed'
    )

    expect(voiceTurnRouteLabel({ kind: 'undecided' })).toBe('undecided')
    expect(voiceTurnRouteLabel({ kind: 'hubWarmWait' })).toBe('hub_warm_wait')
    expect(voiceTurnRouteLabel({ kind: 'hub', sessionID: newSessionID() })).toBe('hub')
    expect(voiceTurnRouteLabel({ kind: 'omniSTT' })).toBe('omni_stt')
    expect(voiceTurnRouteLabel({ kind: 'deepgramBatch' })).toBe('deepgram_batch')
    expect(voiceTurnRouteLabel({ kind: 'deepgramLive' })).toBe('deepgram_live')
    expect(voiceTurnRouteLabel({ kind: 'agentFollowUp' })).toBe('agent_follow_up')
  })

  it('testTimelineNeverStoresAssociatedSpeechPayloads', () => {
    const { coordinator } = manual()
    const marker = 'secret-timeline-marker-442'
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'transcriptChanged', turnID, text: marker })
    coordinator.send({
      type: 'playbackFailed',
      turnID: newTurnID(),
      leaseID: null,
      message: marker
    })

    const events = coordinator.timelineSnapshot().map((entry) => entry.event)
    expect(events).toContain('transcript_changed')
    expect(events).toContain('playback_failed')
    expect(events.join()).not.toContain(marker)
    expect(JSON.stringify(coordinator.timelineSnapshot())).not.toContain(marker)
  })
})

// ---- Windows-only additions ----------------------------------------------

describe('VoiceTurnCoordinator — route-aware deadlines (decision D2)', () => {
  it('gives the shipped omniSTT cascade its 20s transcription budget, not Mac 12s', () => {
    expect(DEFAULT_VOICE_TURN_DEADLINES.transcription).toBe(12)
    expect(CASCADE_VOICE_TURN_DEADLINES.transcription).toBe(20)
    expect(deadlinesForVoiceTurnRoute({ kind: 'hub', sessionID: null })).toBe(
      DEFAULT_VOICE_TURN_DEADLINES
    )
    expect(deadlinesForVoiceTurnRoute({ kind: 'omniSTT' })).toBe(CASCADE_VOICE_TURN_DEADLINES)

    const { scheduler, coordinator } = manual()
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'selectRoute', turnID, route: { kind: 'omniSTT' } })
    coordinator.send({ type: 'finalize', turnID })
    coordinator.send({ type: 'transcriptionStarted', turnID })

    expect(scheduler.delayFor('transcription')).toBe(20)
  })

  it('arms the CASCADE transcription budget when hub-warm times out mid-turn', () => {
    // The hubWarm deadline hands the buffered PCM to the cascade and the turn
    // SURVIVES — so the transcription deadline it arms in that same reduce must
    // be the cascade's 20s, not the hub route's 12s.
    const { scheduler, coordinator } = manual()
    const effects: VoiceTurnEffect[] = []
    coordinator.setEffectHandler((effect) => effects.push(effect))
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'selectRoute', turnID, route: { kind: 'hubWarmWait' } })
    coordinator.send({ type: 'finalize', turnID })

    scheduler.fire('hubWarm')

    expect(effects).toContainEqual({
      kind: 'fallbackToTranscription',
      turnID,
      reason: 'hubWarmTimeout'
    })
    expect(coordinator.model.turn?.route).toEqual({ kind: 'deepgramBatch' })
    expect(coordinator.model.turn?.phase).toEqual({ kind: 'finalizing' })
    expect(scheduler.delayFor('transcription')).toBe(20)
  })
})

describe('VoiceTurnCoordinator — production scheduler', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('fires deadlineFired through setTimeout at the scheduled delay', () => {
    vi.useFakeTimers()
    const coordinator = new VoiceTurnCoordinator({
      scheduler: timeoutVoiceTurnScheduler,
      mintTurnID: newTurnID
    })
    coordinator.begin('hold') // arms captureStart at 3s

    vi.advanceTimersByTime(2999)
    expect(coordinator.model.turn?.phase).toEqual({ kind: 'recording' })

    vi.advanceTimersByTime(1)
    expect(coordinator.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'captureFailed' })
  })

  it('re-arming a held deadline cancels the prior handle', () => {
    // `hintChanged` re-schedules `hintVisibility` on every hint. If the coordinator
    // kept the old handle, it would fire 2s after the FIRST hint — clearing the
    // second hint early and delivering a `deadlineFired` the reducer counts stale.
    vi.useFakeTimers()
    const coordinator = new VoiceTurnCoordinator({
      scheduler: timeoutVoiceTurnScheduler,
      mintTurnID: newTurnID
    })
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'captureStarted', turnID, captureID: capture(3) })
    coordinator.send({ type: 'hintChanged', turnID, text: 'first' })

    vi.advanceTimersByTime(1500)
    coordinator.send({ type: 'hintChanged', turnID, text: 'second' })
    vi.advanceTimersByTime(1500) // the first handle's 2s window has now elapsed

    expect(coordinator.projection.hint).toBe('second')
    expect(coordinator.model.staleEventCount).toBe(0)

    vi.advanceTimersByTime(500) // 2s after the second hint
    expect(coordinator.projection.hint).toBe('')
  })

  it('a cancelled deadline never fires', () => {
    vi.useFakeTimers()
    const coordinator = new VoiceTurnCoordinator({
      scheduler: timeoutVoiceTurnScheduler,
      mintTurnID: newTurnID
    })
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'captureStarted', turnID, captureID: capture(7) }) // cancels captureStart

    vi.advanceTimersByTime(10_000)

    expect(coordinator.model.turn?.phase).toEqual({ kind: 'recording' })
    expect(coordinator.activeTurnID).toBe(turnID)
  })
})

describe('VoiceTurnCoordinator — drain robustness', () => {
  it('a throwing effect handler does not wedge the drain (Swift `defer`)', () => {
    const { coordinator } = manual()
    coordinator.setEffectHandler(() => {
      throw new Error('handler blew up')
    })

    expect(() => coordinator.begin('hold')).toThrow('handler blew up')

    // The queue was cleared and the draining flag unset, so PTT still works.
    coordinator.setEffectHandler(null)
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'lock', turnID })
    expect(coordinator.model.turn?.phase).toEqual({ kind: 'lockedRecording' })
  })

  it('a terminated turn ignores late transport callbacks', () => {
    const { coordinator } = manual()
    const effects: VoiceTurnEffect[] = []
    const turnID = coordinator.begin('hold')
    coordinator.send({ type: 'cancel', turnID, reason: 'cancelled' })
    coordinator.setEffectHandler((effect) => effects.push(effect))

    coordinator.send({ type: 'transcriptionFinal', turnID, text: 'too late' })
    coordinator.send({ type: 'playbackDrained', turnID, leaseID: lease('l1') })

    expect(coordinator.activeTurnID).toBeNull()
    expect(coordinator.model.turn?.phase).toEqual({ kind: 'terminal', reason: 'cancelled' })
    expect(terminalsOf(effects)).toEqual([])
    expect(coordinator.model.staleEventCount).toBe(2)
  })
})
