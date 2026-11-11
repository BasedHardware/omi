import { describe, it, expect, vi } from 'vitest'
import { VoicePlaneInvariants, INVARIANT_DUMP_THROTTLE_MS } from './invariants'

function makeChecker(over: { muted?: boolean } = {}) {
  let muted = over.muted ?? false
  let t = 1_000_000
  const deps = {
    isHoldingMute: vi.fn(() => muted),
    restoreSystemAudio: vi.fn(() => {
      muted = false
    }),
    record: vi.fn(),
    dump: vi.fn(),
    now: () => t
  }
  const checker = new VoicePlaneInvariants(deps)
  return {
    checker,
    deps,
    setMuted: (m: boolean) => {
      muted = m
    },
    advance: (ms: number) => {
      t += ms
    }
  }
}

const errSilencer = () => vi.spyOn(console, 'error').mockImplementation(() => {})

describe('INV-VOICE-1 — endpoint mute held while a reply plays', () => {
  it("tonight's bug as an executable invariant: playing + held mute ⇒ record + auto-restore + dump", () => {
    const spy = errSilencer()
    try {
      const h = makeChecker({ muted: true })
      h.checker.checkEvent('turn', { after: 'playing', event: 'playback_started' })
      expect(h.deps.record).toHaveBeenCalledWith('invariant_violation', {
        invariant: 'muted_during_playback'
      })
      expect(h.deps.restoreSystemAudio).toHaveBeenCalledTimes(1)
      expect(h.deps.dump).toHaveBeenCalledWith('invariant:muted_during_playback')
    } finally {
      spy.mockRestore()
    }
  })

  it('healthy path is untouched: playing with no held mute ⇒ nothing fires', () => {
    const h = makeChecker({ muted: false })
    h.checker.checkEvent('turn', { after: 'playing' })
    expect(h.deps.record).not.toHaveBeenCalled()
    expect(h.deps.restoreSystemAudio).not.toHaveBeenCalled()
    expect(h.deps.dump).not.toHaveBeenCalled()
  })

  it('non-playing / non-turn events never even read the mute state', () => {
    const h = makeChecker({ muted: true })
    h.checker.checkEvent('turn', { after: 'recording' })
    h.checker.checkEvent('gesture', { phase: 'down' })
    h.checker.checkEvent('system_audio', { action: 'mute' })
    expect(h.deps.isHoldingMute).not.toHaveBeenCalled()
  })

  it('dumps are throttled; the auto-restore is not', () => {
    const spy = errSilencer()
    try {
      const h = makeChecker({ muted: true })
      h.checker.checkEvent('turn', { after: 'playing' })
      h.setMuted(true) // a second broken turn inside the throttle window
      h.advance(INVARIANT_DUMP_THROTTLE_MS - 1)
      h.checker.checkEvent('turn', { after: 'playing' })
      expect(h.deps.restoreSystemAudio).toHaveBeenCalledTimes(2)
      expect(h.deps.dump).toHaveBeenCalledTimes(1)
      h.setMuted(true)
      h.advance(2)
      h.checker.checkEvent('turn', { after: 'playing' })
      expect(h.deps.dump).toHaveBeenCalledTimes(2)
    } finally {
      spy.mockRestore()
    }
  })

  it('a throwing dep is contained — the checker never breaks the plane', () => {
    const spy = errSilencer()
    try {
      const checker = new VoicePlaneInvariants({
        isHoldingMute: () => true,
        restoreSystemAudio: () => {
          throw new Error('bridge boom')
        },
        record: vi.fn(),
        dump: vi.fn()
      })
      expect(() => checker.checkEvent('turn', { after: 'playing' })).not.toThrow()
    } finally {
      spy.mockRestore()
    }
  })
})
