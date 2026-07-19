import { describe, it, expect, vi } from 'vitest'
import {
  VoiceTurnHost,
  selectPttRoute,
  type VoiceTurnHostDeps,
  type PttHubAvailability
} from './voiceTurnHost'
import {
  VOICE_TURN_TERMINAL_REASON_RAW,
  type VoiceCaptureID,
  type VoiceLeaseID,
  type VoiceTurnEffect,
  type VoiceTurnID,
  type VoiceTurnRoute,
  type VoiceTurnTerminalReason,
  type VoiceTurnTerminalRecord
} from './voiceTurnMachine'

const T = (s: string): VoiceTurnID => s as unknown as VoiceTurnID
const CAP = (n: number): VoiceCaptureID => n as unknown as VoiceCaptureID
const LEASE = (s: string): VoiceLeaseID => s as unknown as VoiceLeaseID

const ALL_TERMINAL_REASONS: VoiceTurnTerminalReason[] = [
  'success',
  'tooShort',
  'silentRejected',
  'cancelled',
  'interruptedByBargeIn',
  'permissionDenied',
  'captureFailed',
  'transcriptionFailed',
  'providerFailed',
  'providerNoResponse',
  'hubWarmTimeout',
  'deferredCommitTimeout',
  'bargeInReplacementTimeout',
  'toolTimeout',
  'playbackFailed',
  'cleanup'
]

function makeHost(overrides: Partial<VoiceTurnHostDeps> = {}) {
  const spies = {
    disposeCapture: vi.fn(),
    cancelTurn: vi.fn(),
    handoffWarmWaitToCascade: vi.fn(),
    voiceTurnDidTerminate: vi.fn(),
    interruptPlayback: vi.fn(),
    endTurn: vi.fn(() => true),
    applyProjection: vi.fn(),
    restoreSystemAudio: vi.fn(),
    trackEvent: vi.fn()
  }
  const deps: VoiceTurnHostDeps = {
    disposeCapture: spies.disposeCapture,
    hub: {
      cancelTurn: spies.cancelTurn,
      handoffWarmWaitToCascade: spies.handoffWarmWaitToCascade,
      voiceTurnDidTerminate: spies.voiceTurnDidTerminate
    },
    interruptPlayback: spies.interruptPlayback,
    outputCoordinator: { endTurn: spies.endTurn },
    applyProjection: spies.applyProjection,
    restoreSystemAudio: spies.restoreSystemAudio,
    trackEvent: spies.trackEvent,
    ...overrides
  }
  return { host: new VoiceTurnHost(deps), spies }
}

const terminal = (turnID: VoiceTurnID, reason: VoiceTurnTerminalReason): VoiceTurnEffect => {
  const record: VoiceTurnTerminalRecord = { turnID, reason, route: { kind: 'omniSTT' } }
  return { kind: 'terminal', record }
}

describe('selectPttRoute — the pttHubEnabled kill-switch', () => {
  const warmHub: PttHubAvailability = { isAvailable: () => true, isWarm: () => true }
  const coldHub: PttHubAvailability = { isAvailable: () => true, isWarm: () => false }
  const noHub: PttHubAvailability = { isAvailable: () => false, isWarm: () => false }

  it('flag OFF (undefined) ⇒ omniSTT regardless of hub state — the cascade path', () => {
    expect(selectPttRoute(warmHub, {})).toEqual({ kind: 'omniSTT' })
    expect(selectPttRoute(coldHub, {})).toEqual({ kind: 'omniSTT' })
    expect(selectPttRoute(noHub, {})).toEqual({ kind: 'omniSTT' })
  })

  it('flag explicitly false ⇒ omniSTT even with a warm hub', () => {
    expect(selectPttRoute(warmHub, { pttHubEnabled: false })).toEqual({ kind: 'omniSTT' })
  })

  it('flag ON ⇒ hub when warm, hubWarmWait when cold, omniSTT when unavailable', () => {
    expect(selectPttRoute(warmHub, { pttHubEnabled: true })).toEqual({
      kind: 'hub',
      sessionID: null
    })
    expect(selectPttRoute(coldHub, { pttHubEnabled: true })).toEqual({ kind: 'hubWarmWait' })
    expect(selectPttRoute(noHub, { pttHubEnabled: true })).toEqual({ kind: 'omniSTT' })
  })
})

describe('VoiceTurnHost — effect mapping', () => {
  it('stopCapture disposes the capture window mic capture', () => {
    const { host, spies } = makeHost()
    host.effectHandler({ kind: 'stopCapture', turnID: T('a'), captureID: CAP(7) })
    expect(spies.disposeCapture).toHaveBeenCalledWith(T('a'), CAP(7))
    expect(spies.disposeCapture).toHaveBeenCalledTimes(1)
  })

  // 2026-07-18 muted-reply regression: the A4 helper mutes the DEFAULT OUTPUT
  // ENDPOINT — the same device the hub reply plays through. Restoring only on
  // `terminal` kept the speakers muted for the ENTIRE hub reply (terminal fires
  // after playback drains), so every reply was inaudible while all internal
  // signals read healthy. The restore must ride capture end.
  it('stopCapture restores system audio (before any reply playback can start)', () => {
    const { host, spies } = makeHost()
    host.effectHandler({ kind: 'stopCapture', turnID: T('a'), captureID: CAP(7) })
    expect(spies.restoreSystemAudio).toHaveBeenCalledTimes(1)
  })

  it('A4: stopCapture then terminal for the SAME turn ⇒ exactly one restore', () => {
    // terminate() emits this exact pair back-to-back; the turn-ID guard must
    // collapse it to a single restore.
    const { host, spies } = makeHost()
    host.effectHandler({ kind: 'stopCapture', turnID: T('a'), captureID: CAP(7) })
    host.effectHandler(terminal(T('a'), 'success'))
    expect(spies.restoreSystemAudio).toHaveBeenCalledTimes(1)
  })

  it('cancelHub calls hubController.cancelTurn(turnID) (route dropped)', () => {
    const { host, spies } = makeHost()
    const route: VoiceTurnRoute = { kind: 'hub', sessionID: null }
    host.effectHandler({ kind: 'cancelHub', turnID: T('a'), route })
    expect(spies.cancelTurn).toHaveBeenCalledWith(T('a'))
    expect(spies.cancelTurn).toHaveBeenCalledTimes(1)
  })

  it('stopPlayback interrupts the current response for the lease', () => {
    const { host, spies } = makeHost()
    host.effectHandler({ kind: 'stopPlayback', turnID: T('a'), leaseID: LEASE('L1') })
    expect(spies.interruptPlayback).toHaveBeenCalledWith(LEASE('L1'))
  })

  it('the five coordinator-owned effects are no-ops in the host', () => {
    const { host, spies } = makeHost()
    const ignored: VoiceTurnEffect[] = [
      { kind: 'scheduleDeadline', turnID: T('a'), deadline: 'transcription', after: 12 },
      { kind: 'cancelDeadline', turnID: T('a'), deadline: 'transcription' },
      { kind: 'cancelAllDeadlines', turnID: T('a') },
      { kind: 'staleEventDropped', turnID: T('a'), event: 'capture_started' },
      { kind: 'invalidTransition', turnID: T('a'), event: 'lock', phase: null }
    ]
    for (const eff of ignored) expect(() => host.effectHandler(eff)).not.toThrow()
    // No subsystem call fired for any of them.
    for (const spy of Object.values(spies)) expect(spy).not.toHaveBeenCalled()
  })

  it('broadcasts the projection through the presenter', () => {
    const { host, spies } = makeHost()
    const projection = {
      isListening: true,
      isLocked: false,
      isFollowUp: false,
      transcript: '',
      hint: '',
      isThinking: false,
      isResponseWaiting: false,
      isResponseActive: false
    }
    host.presenter.apply(projection)
    expect(spies.applyProjection).toHaveBeenCalledWith(projection)
  })
})

describe('VoiceTurnHost — fallbackToTranscription keeps the turn alive, no double emit', () => {
  it('hands the warm-wait buffer to the cascade and does NOT terminate or emit', () => {
    const { host, spies } = makeHost()
    host.effectHandler({
      kind: 'fallbackToTranscription',
      turnID: T('a'),
      reason: 'hubWarmTimeout'
    })
    expect(spies.handoffWarmWaitToCascade).toHaveBeenCalledWith(T('a'))
    // The turn continues — nothing terminal fires from the host here.
    expect(spies.endTurn).not.toHaveBeenCalled()
    expect(spies.voiceTurnDidTerminate).not.toHaveBeenCalled()
    expect(spies.restoreSystemAudio).not.toHaveBeenCalled()
    // The controller owns the `degraded` telemetry; the host must stay silent.
    expect(spies.trackEvent).not.toHaveBeenCalled()
  })
})

describe('VoiceTurnHost — terminal', () => {
  it('ends the lease, releases hub per-turn state, and restores system audio', () => {
    const { host, spies } = makeHost()
    host.effectHandler(terminal(T('a'), 'success'))
    expect(spies.endTurn).toHaveBeenCalledWith(T('a'))
    expect(spies.voiceTurnDidTerminate).toHaveBeenCalledWith(T('a'))
    expect(spies.restoreSystemAudio).toHaveBeenCalledTimes(1)
  })

  it('A4: EVERY one of the 16 terminal reasons ⇒ exactly one restore', () => {
    for (const reason of ALL_TERMINAL_REASONS) {
      const { host, spies } = makeHost()
      host.effectHandler(terminal(T('turn'), reason))
      expect(spies.restoreSystemAudio, `restore for ${reason}`).toHaveBeenCalledTimes(1)
    }
  })

  it('A4: a repeated terminal for the SAME turn restores only once', () => {
    const { host, spies } = makeHost()
    host.effectHandler(terminal(T('a'), 'success'))
    host.effectHandler(terminal(T('a'), 'success'))
    expect(spies.restoreSystemAudio).toHaveBeenCalledTimes(1)
  })

  it('a new turn gets its own single restore', () => {
    const { host, spies } = makeHost()
    host.effectHandler(terminal(T('a'), 'success'))
    host.effectHandler(terminal(T('b'), 'cancelled'))
    expect(spies.restoreSystemAudio).toHaveBeenCalledTimes(2)
  })

  it('emits an `exhausted` fallback ONLY for the no-path-left provider/warm terminals', () => {
    const exhausted: VoiceTurnTerminalReason[] = [
      'providerFailed',
      'providerNoResponse',
      'hubWarmTimeout'
    ]
    for (const reason of exhausted) {
      const { host, spies } = makeHost()
      host.effectHandler(terminal(T('a'), reason))
      expect(spies.trackEvent, `emit for ${reason}`).toHaveBeenCalledWith('fallback_triggered', {
        component: 'ptt_cascade',
        from: 'hub',
        to: 'none',
        reason: VOICE_TURN_TERMINAL_REASON_RAW[reason],
        outcome: 'exhausted'
      })
      expect(spies.trackEvent).toHaveBeenCalledTimes(1)
    }
  })

  it('does NOT emit fallback telemetry for a clean success or a hard non-hub failure', () => {
    for (const reason of ['success', 'cancelled', 'transcriptionFailed', 'tooShort'] as const) {
      const { host, spies } = makeHost()
      host.effectHandler(terminal(T('a'), reason))
      expect(spies.trackEvent, `no emit for ${reason}`).not.toHaveBeenCalled()
    }
  })
})
