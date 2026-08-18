// The rule that turns a scrub from quadratic into linear. macOS measured the
// difference at 12.3x on a real 18-frame chunk; what is testable without a
// codec is the decision that produces it, which is all of this file.
import { describe, expect, it } from 'vitest'
import { afterExhausted, afterRead, canServe, newCursor, planRead } from './cursorPolicy'

const CHUNK = '2026-08-17/1-2.omichunk'
const OTHER = '2026-08-17/3-4.omichunk'

describe('a fresh cursor', () => {
  it('cannot serve anything', () => {
    expect(canServe(newCursor(), CHUNK, 0)).toBe(false)
  })

  it('reopens for the first read', () => {
    expect(planRead(newCursor(), CHUNK, 7)).toEqual({
      kind: 'reopen',
      chunkPath: CHUNK,
      advanceBy: 7
    })
  })
})

describe('walking forward', () => {
  it('serves the very next frame with a single advance', () => {
    // This is the case that makes sequential playback cheap: one decode step.
    const state = afterRead(newCursor(), { kind: 'reopen', chunkPath: CHUNK, advanceBy: 0 }, 0)
    expect(planRead(state, CHUNK, 1)).toEqual({ kind: 'advance', advanceBy: 0 })
  })

  it('skips ahead without reopening', () => {
    const state = afterRead(newCursor(), { kind: 'reopen', chunkPath: CHUNK, advanceBy: 0 }, 3)
    expect(planRead(state, CHUNK, 9)).toEqual({ kind: 'advance', advanceBy: 5 })
  })

  it('serves the offset it is parked on', () => {
    // The tape parks *before* the next frame, so nextOffset is servable. Off by
    // one here and every sequential read reopens, losing the whole benefit.
    const state = { chunkPath: CHUNK, nextOffset: 4, finished: false }
    expect(canServe(state, CHUNK, 4)).toBe(true)
    expect(planRead(state, CHUNK, 4)).toEqual({ kind: 'advance', advanceBy: 0 })
  })

  it('costs one advance per frame across a whole chunk', () => {
    let state = newCursor()
    let reopens = 0
    for (let offset = 0; offset < 60; offset++) {
      const action = planRead(state, CHUNK, offset)
      if (action.kind === 'reopen') reopens++
      else expect(action.advanceBy).toBe(0)
      state = afterRead(state, action, offset)
    }
    expect(reopens).toBe(1) // only the very first read
  })
})

describe('what forces a reopen', () => {
  it('a backward step', () => {
    // A one-way tape has nothing cheaper available.
    const state = afterRead(newCursor(), { kind: 'reopen', chunkPath: CHUNK, advanceBy: 0 }, 9)
    expect(planRead(state, CHUNK, 4)).toEqual({ kind: 'reopen', chunkPath: CHUNK, advanceBy: 4 })
  })

  it('a different chunk', () => {
    const state = afterRead(newCursor(), { kind: 'reopen', chunkPath: CHUNK, advanceBy: 0 }, 2)
    expect(planRead(state, OTHER, 5)).toEqual({ kind: 'reopen', chunkPath: OTHER, advanceBy: 5 })
  })

  it('a cursor that ran off the end', () => {
    let state = afterRead(newCursor(), { kind: 'reopen', chunkPath: CHUNK, advanceBy: 0 }, 5)
    state = afterExhausted(state)
    expect(canServe(state, CHUNK, 6)).toBe(false)
    expect(planRead(state, CHUNK, 6).kind).toBe('reopen')
  })
})

describe('state bookkeeping', () => {
  it('adopts the chunk it reopened on', () => {
    // Without this a cursor that reopened onto another chunk would still claim
    // the old one and happily "serve" reads from the wrong file.
    const state = afterRead(newCursor(), { kind: 'reopen', chunkPath: OTHER, advanceBy: 3 }, 3)
    expect(state.chunkPath).toBe(OTHER)
    expect(state.nextOffset).toBe(4)
  })

  it('keeps the chunk it was already on when advancing', () => {
    const start = { chunkPath: CHUNK, nextOffset: 2, finished: false }
    const state = afterRead(start, { kind: 'advance', advanceBy: 1 }, 3)
    expect(state.chunkPath).toBe(CHUNK)
    expect(state.nextOffset).toBe(4)
  })

  it('clears the finished flag after a successful read', () => {
    const start = { chunkPath: CHUNK, nextOffset: 9, finished: true }
    const state = afterRead(start, { kind: 'reopen', chunkPath: CHUNK, advanceBy: 0 }, 0)
    expect(state.finished).toBe(false)
  })

  it('rejects a nonsense offset instead of planning for it', () => {
    expect(() => planRead(newCursor(), CHUNK, -1)).toThrow(/non-negative/)
    expect(() => planRead(newCursor(), CHUNK, 1.5)).toThrow(/integer/)
  })
})
