import { describe, it, expect, vi } from 'vitest'
import { SummonGesture, HOLD_THRESHOLD_MS, REPEAT_GAP_MS, MAX_HOLD_MS } from './gesture'

/** Deterministic clock + timer world for the gesture machine. */
function world({
  keyDown = null,
  maxHoldMs
}: { keyDown?: (() => boolean) | null; maxHoldMs?: number } = {}) {
  let now = 0
  const timers: { at: number; fn: () => void; id: number }[] = []
  let nextId = 1
  const events: string[] = []
  const g = new SummonGesture(
    {
      onStart: () => events.push('start'),
      onHoldStart: () => events.push('holdStart'),
      onEnd: (kind) => events.push(`end:${kind}`),
      onCapExceeded: () => events.push('cap')
    },
    {
      sampleKeyDown: keyDown,
      maxHoldMs,
      now: () => now,
      setTimer: (fn, ms) => {
        const id = nextId++
        timers.push({ at: now + ms, fn, id })
        return id
      },
      clearTimer: (h) => {
        const i = timers.findIndex((t) => t.id === h)
        if (i >= 0) timers.splice(i, 1)
      }
    }
  )
  const advance = (ms: number): void => {
    const target = now + ms
    for (;;) {
      timers.sort((a, b) => a.at - b.at)
      const t = timers[0]
      if (!t || t.at > target) break
      timers.shift()
      now = t.at
      t.fn()
    }
    now = target
  }
  return { g, events, advance, now: () => now }
}

describe('SummonGesture with key-state sampling', () => {
  it('a tap fires start once and ends as tap on key-up', () => {
    let down = true
    const w = world({ keyDown: () => down })
    w.g.fire()
    expect(w.events).toEqual(['start'])
    w.advance(60)
    down = false
    w.advance(60)
    expect(w.events).toEqual(['start', 'end:tap'])
    expect(w.g.isActive).toBe(false)
  })

  it('HOLD is ONE stable summon: auto-repeat fires never toggle again (the flap bug)', () => {
    let down = true
    const w = world({ keyDown: () => down })
    w.g.fire()
    // OS auto-repeat: initial delay ~500ms then ~30ms repeats, all while held.
    for (let t = 0; t < 2000; t += 30) {
      w.advance(30)
      w.g.fire()
    }
    // Exactly one start, and the hold threshold fired exactly once.
    expect(w.events.filter((e) => e === 'start')).toHaveLength(1)
    expect(w.events.filter((e) => e === 'holdStart')).toHaveLength(1)
    expect(w.events.filter((e) => e.startsWith('end'))).toHaveLength(0)
    down = false
    w.advance(60)
    expect(w.events[w.events.length - 1]).toBe('end:hold')
    // start → holdStart → end:hold, nothing else.
    expect(w.events).toEqual(['start', 'holdStart', 'end:hold'])
  })

  it('holdStart fires at the threshold, not before', () => {
    let down = true
    const w = world({ keyDown: () => down })
    w.g.fire()
    w.advance(HOLD_THRESHOLD_MS - 60)
    expect(w.events).toEqual(['start'])
    w.advance(120)
    expect(w.events).toEqual(['start', 'holdStart'])
    down = false
    w.advance(60)
    expect(w.events).toEqual(['start', 'holdStart', 'end:hold'])
  })

  it('two distinct taps are two gestures', () => {
    let down = true
    const w = world({ keyDown: () => down })
    w.g.fire()
    down = false
    w.advance(60)
    down = true
    w.g.fire()
    down = false
    w.advance(60)
    expect(w.events).toEqual(['start', 'end:tap', 'start', 'end:tap'])
  })

  it('dispose during an active hold ends the gesture, so a start-set suppression is always released (Bug B, case d)', () => {
    // window.ts sets a watchdog-suppression hold in onStart and clears it in
    // onEnd. If a rebind/quit disposes mid-hold, onEnd MUST still fire or the
    // pill would be stuck un-retractable. Model that hold with a boolean.
    let down = true
    let held = false
    let now = 0
    const timers: { fn: () => void; id: number }[] = []
    const g = new SummonGesture(
      {
        onStart: () => (held = true),
        onEnd: () => (held = false)
      },
      {
        sampleKeyDown: () => down,
        now: () => now,
        setTimer: (fn) => {
          timers.push({ fn, id: timers.length + 1 })
          return timers.length
        },
        clearTimer: () => {}
      }
    )
    g.fire()
    now = 500 // held past the threshold — a genuine hold in flight
    expect(held).toBe(true)
    expect(g.isActive).toBe(true)
    g.dispose() // rebind / quit while the key is still physically down
    expect(held).toBe(false)
    expect(g.isActive).toBe(false)
    // A stray sampler tick after dispose must not resurrect the hold.
    down = true
    timers.forEach((t) => t.fn())
    expect(held).toBe(false)
  })

  it('polling only runs during a gesture (zero idle cost)', () => {
    const sample = vi.fn(() => false)
    let now = 0
    const timers: { at: number; fn: () => void; id: number }[] = []
    const g = new SummonGesture(
      { onStart: () => {}, onEnd: () => {} },
      {
        sampleKeyDown: sample,
        now: () => now,
        setTimer: (fn, ms) => {
          timers.push({ at: now + ms, fn, id: timers.length + 1 })
          return timers.length
        },
        clearTimer: () => {}
      }
    )
    expect(timers).toHaveLength(0) // nothing scheduled while idle
    g.fire()
    expect(timers.length).toBeGreaterThan(0)
    now += 40
    timers.shift()!.fn() // key already up → gesture ends
    expect(g.isActive).toBe(false)
    expect(timers).toHaveLength(0) // and nothing remains scheduled
  })

  it('force-ends a hold the sampler never sees released (stuck-visualizer recovery)', () => {
    // The physical key-up is missed — GetAsyncKeyState reads DOWN forever
    // (stale-down after a focus/session transition). Without the cap the gesture
    // never ends, main never sends 'up', and the recording orb sticks (machine.ts
    // WATCHDOG no-ops while `holding`). The cap force-ends it exactly once.
    let down = true
    const w = world({ keyDown: () => down, maxHoldMs: 2000 })
    w.g.fire()
    w.advance(400)
    expect(w.events).toEqual(['start', 'holdStart']) // held past threshold, still down
    w.advance(2000) // cross the cap
    expect(w.events).toEqual(['start', 'holdStart', 'cap', 'end:hold'])
    expect(w.g.isActive).toBe(false)
    // The real key-up finally arrives — it must NOT produce a second end (a
    // double 'up' would desync the renderer).
    down = false
    w.advance(5000)
    expect(w.events).toEqual(['start', 'holdStart', 'cap', 'end:hold'])
  })

  it('endIfActive finalizes an in-flight hold (session lock / suspend), once', () => {
    // powerMonitor lock-screen/suspend end the hold directly: the key-up will
    // never be observed across that transition, so finalize now rather than stick.
    let down = true
    const w = world({ keyDown: () => down })
    w.g.fire()
    w.advance(400) // a genuine hold in flight
    expect(w.events).toEqual(['start', 'holdStart'])
    w.g.endIfActive()
    expect(w.events).toEqual(['start', 'holdStart', 'end:hold'])
    expect(w.g.isActive).toBe(false)
    // A stray sampler tick after must not resurrect it (no second end).
    down = true
    w.advance(1000)
    expect(w.events).toEqual(['start', 'holdStart', 'end:hold'])
  })

  it('endIfActive is a no-op when idle', () => {
    const w = world({ keyDown: () => false })
    w.g.endIfActive()
    expect(w.events).toEqual([])
    expect(w.g.isActive).toBe(false)
  })

  it('MAX_HOLD_MS is 5 minutes (matches the renderer PCM buffer cap with margin)', () => {
    expect(MAX_HOLD_MS).toBe(5 * 60 * 1000)
  })
})

describe('SummonGesture fallback (no key sampler)', () => {
  it('groups auto-repeat fires by gap and classifies a long run as hold', () => {
    const w = world({ keyDown: null })
    w.g.fire()
    for (let t = 0; t < 900; t += 30) {
      w.advance(30)
      w.g.fire()
    }
    expect(w.events).toEqual(['start'])
    w.advance(REPEAT_GAP_MS + 10)
    expect(w.events).toEqual(['start', 'end:hold'])
  })

  it('a single fire ends as tap after the gap', () => {
    const w = world({ keyDown: null })
    w.g.fire()
    w.advance(REPEAT_GAP_MS + 10)
    expect(w.events).toEqual(['start', 'end:tap'])
  })

  it('slow-repeat-delay keyboards do not flap: a second fire within the gap extends the gesture', () => {
    const w = world({ keyDown: null })
    w.g.fire()
    w.advance(1000) // Windows max initial repeat delay
    w.g.fire() // first auto-repeat
    expect(w.events).toEqual(['start']) // no second toggle
  })
})
