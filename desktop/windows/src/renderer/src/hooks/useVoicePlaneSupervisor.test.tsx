// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import {
  useVoicePlaneSupervisor,
  SUPERVISOR_FIRE_CHIP,
  PLANE_RESET_CHIP,
  LOCAL_IDLE_TERMINAL_MS,
  type VoicePlaneSupervisorSignals
} from './useVoicePlaneSupervisor'
import { VOICE_SUPERVISOR_TIMEOUT_MS } from '../lib/voice/supervisor/voicePlaneSupervisor'

vi.mock('../lib/analytics', () => ({ trackEvent: vi.fn() }))
import { trackEvent } from '../lib/analytics'

type PttCb = (phase: 'down' | 'up') => void
type ResetCb = (payload: { trigger: string }) => void

let pttCb: PttCb | null = null
let resetCb: ResetCb | null = null
const resetVoicePlane = vi.fn()
const voiceFlightRecord = vi.fn()

const baseSignals = (
  over: Partial<VoicePlaneSupervisorSignals> = {}
): VoicePlaneSupervisorSignals => ({
  hubActive: false,
  hubResponseActive: false,
  hubHint: '',
  hubSeq: 0,
  pttRecording: false,
  pttTranscribing: false,
  pttHint: null,
  pttError: null,
  chatStatus: 'idle',
  ...over
})

beforeEach(() => {
  vi.useFakeTimers()
  pttCb = null
  resetCb = null
  resetVoicePlane.mockClear()
  voiceFlightRecord.mockClear()
  vi.mocked(trackEvent).mockClear()
  ;(window as unknown as { omiBar: unknown }).omiBar = {
    onPtt: (cb: PttCb) => {
      pttCb = cb
      return () => {
        pttCb = null
      }
    }
  }
  ;(window as unknown as { omi: unknown }).omi = {
    resetVoicePlane,
    voiceFlightRecord,
    onVoicePlaneReset: (cb: ResetCb) => {
      resetCb = cb
      return () => {
        resetCb = null
      }
    }
  }
})

afterEach(() => {
  vi.useRealTimers()
})

const press = (): void => act(() => pttCb?.('down'))
const release = (): void => act(() => pttCb?.('up'))
const elapse = (): void => void act(() => vi.advanceTimersByTime(VOICE_SUPERVISOR_TIMEOUT_MS + 1))

describe('useVoicePlaneSupervisor — fires on a never-terminal turn', () => {
  it('hub-lane hold with NO terminal ⇒ chip + resetVoicePlane + shared fallback event', () => {
    const { result } = renderHook((s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s), {
      initialProps: baseSignals({ hubActive: true })
    })
    press()
    release()
    elapse()
    expect(resetVoicePlane).toHaveBeenCalledWith('supervisor_timeout')
    expect(result.current.chip).toBe(SUPERVISOR_FIRE_CHIP)
    expect(trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'realtime_hub',
      from: 'hub',
      to: 'rebuilt',
      reason: 'other',
      outcome: 'degraded'
    })
  })

  it('local-lane hold reports the ptt_cascade component', () => {
    renderHook((s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s), {
      initialProps: baseSignals({ pttRecording: true })
    })
    press()
    release()
    elapse()
    expect(trackEvent).toHaveBeenCalledWith(
      'fallback_triggered',
      expect.objectContaining({ component: 'ptt_cascade' })
    )
  })
})

describe('useVoicePlaneSupervisor — inert on healthy / non-turn activity', () => {
  it('a TAP (no live turn at release) never arms — no fire, no reset', () => {
    renderHook((s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s), {
      initialProps: baseSignals() // neither hubActive nor pttRecording
    })
    press()
    release()
    elapse()
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })

  it('reply playback starting disarms (healthy hub turn)', () => {
    const { rerender } = renderHook(
      (s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s),
      { initialProps: baseSignals({ hubActive: true }) }
    )
    press()
    release()
    rerender(baseSignals({ hubActive: true, hubResponseActive: true }))
    elapse()
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })

  it('a visible hint disarms (tooShort-style guidance is a terminal)', () => {
    const { rerender } = renderHook(
      (s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s),
      { initialProps: baseSignals({ hubActive: true }) }
    )
    press()
    release()
    rerender(baseSignals({ hubHint: 'Hold longer to record' }))
    elapse()
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })

  it('the chat pipeline leaving idle disarms (cascade text commit)', () => {
    const { rerender } = renderHook(
      (s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s),
      { initialProps: baseSignals({ pttRecording: true }) }
    )
    press()
    release()
    rerender(baseSignals({ chatStatus: 'sending' }))
    elapse()
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })

  it('noteCancel (Esc abort) swallows the trailing release', () => {
    const { result } = renderHook((s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s), {
      initialProps: baseSignals({ hubActive: true })
    })
    press()
    act(() => result.current.noteCancel())
    release() // hubActive may still read true here (state lag) — must not arm
    elapse()
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })
})

describe('useVoicePlaneSupervisor — audit M1: silent holds are legit, not wedges', () => {
  it('a silent HUB hold (quiet silentRejected discard: active drops, no hint) never fires', () => {
    const { rerender } = renderHook(
      (s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s),
      { initialProps: baseSignals({ hubActive: true }) }
    )
    press()
    release()
    // The reducer discards the silent turn: terminal silentRejected — NO hint,
    // NO playback, chat untouched. The only observable is active → false.
    rerender(baseSignals({ hubActive: false }))
    elapse()
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })

  it('a genuinely WEDGED hub turn (active stays latched, no transitions) still fires', () => {
    renderHook((s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s), {
      initialProps: baseSignals({ hubActive: true })
    })
    press()
    release()
    elapse()
    expect(resetVoicePlane).toHaveBeenCalledTimes(1)
  })

  it('a silent LOCAL hold (machine reconciles to full idle, no hint) never fires', () => {
    const { rerender } = renderHook(
      (s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s),
      { initialProps: baseSignals({ pttRecording: true }) }
    )
    press()
    release()
    // Silent gate: recording drops and transcription never starts.
    rerender(baseSignals({ pttRecording: false, pttTranscribing: false }))
    elapse() // covers the idle debounce AND the full window
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })

  it('the release commit-split (recording↓ then transcribing↑ a beat later) does NOT satisfy the contract', () => {
    const { rerender } = renderHook(
      (s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s),
      { initialProps: baseSignals({ pttRecording: true }) }
    )
    press()
    release()
    // Momentary both-false frame between React commits…
    rerender(baseSignals({ pttRecording: false, pttTranscribing: false }))
    act(() => vi.advanceTimersByTime(LOCAL_IDLE_TERMINAL_MS - 100))
    // …then the real transcription starts (inside the debounce): the watch must
    // still be armed, and a machine that then WEDGES in transcribing fires.
    rerender(baseSignals({ pttTranscribing: true }))
    elapse()
    expect(resetVoicePlane).toHaveBeenCalledTimes(1)
  })
})

describe('useVoicePlaneSupervisor — audit M2: progress restarts the clock', () => {
  it('a healthy multi-round tool turn (transitions keep arriving) outlives several windows without firing', () => {
    const { rerender } = renderHook(
      (s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s),
      { initialProps: baseSignals({ hubActive: true, hubSeq: 1 }) }
    )
    press()
    release()
    // Three windows' worth of wall time, each punctuated by an observed
    // reducer transition (tool round start/finish) before the deadline.
    for (let seq = 2; seq <= 4; seq++) {
      act(() => vi.advanceTimersByTime(VOICE_SUPERVISOR_TIMEOUT_MS - 1000))
      rerender(baseSignals({ hubActive: true, hubSeq: seq }))
    }
    expect(resetVoicePlane).not.toHaveBeenCalled()
    // Then the turn truly stalls: no more transitions ⇒ the watch runs out.
    elapse()
    expect(resetVoicePlane).toHaveBeenCalledTimes(1)
  })
})

describe('useVoicePlaneSupervisor — external plane reset', () => {
  it('cancels the local hold, disarms, and shows the reset chip', () => {
    const cancelLocal = vi.fn()
    const { result } = renderHook((s: VoicePlaneSupervisorSignals) => useVoicePlaneSupervisor(s), {
      initialProps: baseSignals({ pttRecording: true, cancelLocal })
    })
    press()
    release()
    act(() => resetCb?.({ trigger: 'context_menu' }))
    expect(cancelLocal).toHaveBeenCalledTimes(1)
    expect(result.current.chip).toBe(PLANE_RESET_CHIP)
    elapse()
    expect(resetVoicePlane).not.toHaveBeenCalled()
  })
})
