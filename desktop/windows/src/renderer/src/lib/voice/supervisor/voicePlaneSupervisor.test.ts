import { describe, it, expect, vi } from 'vitest'
import { VoicePlaneSupervisor, VOICE_SUPERVISOR_TIMEOUT_MS } from './voicePlaneSupervisor'

/** Manual timer: fire() simulates the timeout elapsing. */
function makeSupervisor(over: { timeoutMs?: number } = {}) {
  const onFire = vi.fn()
  const record = vi.fn()
  let armed: { fire: () => void; cancelled: boolean } | null = null
  const sup = new VoicePlaneSupervisor({
    onFire,
    record,
    timeoutMs: over.timeoutMs,
    schedule: (fire) => {
      const entry = { fire, cancelled: false }
      armed = entry
      return {
        cancel: () => {
          entry.cancelled = true
          if (armed === entry) armed = null
        }
      }
    }
  })
  const elapse = (): void => {
    const entry = armed
    armed = null
    if (entry && !entry.cancelled) entry.fire()
  }
  return { sup, onFire, record, elapse }
}

describe('VoicePlaneSupervisor — fires on a never-terminal turn', () => {
  it('press → release → NO terminal within the window ⇒ exactly one fire with the lane', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('hub')
    expect(h.sup.armed).toBe(true)
    h.elapse()
    expect(h.onFire).toHaveBeenCalledTimes(1)
    expect(h.onFire).toHaveBeenCalledWith({ lane: 'hub' })
    expect(h.sup.armed).toBe(false)
    // A second elapse cannot double-fire.
    h.elapse()
    expect(h.onFire).toHaveBeenCalledTimes(1)
  })

  it('the default window outlasts the longest observable-event GAP in a healthy turn (45 s release watchdog → hint)', () => {
    // NOT a total-turn bound — multi-round tool turns legitimately run longer;
    // noteProgress restarts the clock on every observed transition. The window
    // only needs to exceed the longest silent gap a healthy turn can produce.
    expect(VOICE_SUPERVISOR_TIMEOUT_MS).toBeGreaterThan(45_000)
  })
})

describe('VoicePlaneSupervisor — observed progress restarts the clock (audit M2)', () => {
  it('a slow multi-round tool turn that keeps making transitions never fires', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('hub')
    // Round 1 tool call, round 2 tool call, response — each observed transition
    // re-arms; the PRIOR window's timer must be cancelled, not left to fire.
    h.sup.noteProgress('hub')
    h.sup.noteProgress('hub')
    h.sup.noteProgress('hub')
    h.elapse() // only the LATEST armed window can elapse
    expect(h.onFire).toHaveBeenCalledTimes(1) // the final window did run out…
    h.elapse()
    expect(h.onFire).toHaveBeenCalledTimes(1) // …but no stale timer double-fires
  })

  it('progress for the WRONG lane does not touch the watch', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('local')
    h.sup.noteProgress('hub') // hub transitions while a LOCAL watch is armed
    expect(h.sup.armed).toBe(true)
  })

  it('progress with nothing armed is a no-op', () => {
    const h = makeSupervisor()
    h.sup.noteProgress('hub')
    expect(h.sup.armed).toBe(false)
  })
})

describe('VoicePlaneSupervisor — lane-scoped terminals (audit M1)', () => {
  it("a lane-scoped terminal only clears its own lane's watch", () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('local')
    h.sup.noteTerminal('turn_reconciled', 'hub') // hub reconciled ≠ local outcome
    expect(h.sup.armed).toBe(true)
    h.sup.noteTerminal('local_idle', 'local')
    expect(h.sup.armed).toBe(false)
  })
})

describe('VoicePlaneSupervisor — inert on healthy turns', () => {
  it('a terminal (reply playback) before the window disarms — no fire ever', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('hub')
    h.sup.noteTerminal('playback')
    expect(h.sup.armed).toBe(false)
    h.elapse()
    expect(h.onFire).not.toHaveBeenCalled()
  })

  it('a SLOW but completing turn (terminal just before the deadline) never fires', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('local')
    // …55 s of legitimate slow work (cascade batch + chat), then the terminal:
    h.sup.noteTerminal('chat_status')
    h.elapse()
    expect(h.onFire).not.toHaveBeenCalled()
  })

  it('a visible hint/error is a terminal too (tooShort etc.)', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('hub')
    h.sup.noteTerminal('hint')
    h.elapse()
    expect(h.onFire).not.toHaveBeenCalled()
  })

  it('a terminal with nothing armed is a no-op (no stray records)', () => {
    const h = makeSupervisor()
    h.sup.noteTerminal('playback')
    expect(h.record).not.toHaveBeenCalled()
  })
})

describe('VoicePlaneSupervisor — supersede / cancel / reset edges', () => {
  it('a new press supersedes a pending watch (the barge-in path)', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('hub')
    h.sup.notePress() // barge-in: old watch dropped, new turn owns the contract
    expect(h.sup.armed).toBe(false)
    h.elapse()
    expect(h.onFire).not.toHaveBeenCalled()
    h.sup.noteRelease('hub')
    h.elapse()
    expect(h.onFire).toHaveBeenCalledTimes(1)
  })

  it('an abort disarms AND swallows the trailing release (state-lag race)', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteCancel() // Esc mid-hold
    // The physical key-up still arrives, and cross-window state may still read
    // "turn live" for a beat — the release must NOT arm on the dead turn.
    h.sup.noteRelease('hub')
    expect(h.sup.armed).toBe(false)
    h.elapse()
    expect(h.onFire).not.toHaveBeenCalled()
    // The NEXT press-and-release owes a terminal again.
    h.sup.notePress()
    h.sup.noteRelease('hub')
    expect(h.sup.armed).toBe(true)
  })

  it('dispose() cancels the pending watch and refuses new arms', () => {
    const h = makeSupervisor()
    h.sup.notePress()
    h.sup.noteRelease('local')
    h.sup.dispose()
    h.elapse()
    expect(h.onFire).not.toHaveBeenCalled()
    h.sup.notePress()
    h.sup.noteRelease('local')
    expect(h.sup.armed).toBe(false)
  })

  it('a throwing record tap never breaks the supervisor', () => {
    const onFire = vi.fn()
    const sup = new VoicePlaneSupervisor({
      onFire,
      record: () => {
        throw new Error('tap boom')
      },
      schedule: (fire) => {
        fire()
        return { cancel: () => {} }
      }
    })
    expect(() => {
      sup.notePress()
      sup.noteRelease('hub')
    }).not.toThrow()
    expect(onFire).toHaveBeenCalledTimes(1)
  })
})
