import { describe, it, expect, vi } from 'vitest'

// captureWindow.ts pulls in @electron-toolkit/utils (real electron ESM) at import;
// stub it so the pure respawn-budget helper is importable in the node suite.
vi.mock('@electron-toolkit/utils', () => ({ is: { dev: false }, electronApp: {}, optimizer: {} }))

import { decideRespawn } from './captureWindow'

// The capture window respawns if it dies, but a persistent crash-loop must not
// flap forever: at most 3 respawns per 60s. decideRespawn is the pure budget.

describe('decideRespawn', () => {
  it('allows a respawn when the window is empty', () => {
    const { allow, times } = decideRespawn([], 100_000)
    expect(allow).toBe(true)
    expect(times).toEqual([])
  })

  it('allows up to 3 respawns inside the 60s window', () => {
    const now = 100_000
    expect(decideRespawn([now - 1000], now).allow).toBe(true)
    expect(decideRespawn([now - 1000, now - 2000], now).allow).toBe(true)
    // A third existing spawn in-window blocks the fourth.
    expect(decideRespawn([now - 1000, now - 2000, now - 3000], now).allow).toBe(false)
  })

  it('prunes spawns older than 60s and allows again', () => {
    const now = 100_000
    const old = [now - 61_000, now - 62_000, now - 70_000]
    const { allow, times } = decideRespawn(old, now)
    expect(allow).toBe(true)
    expect(times).toEqual([]) // all pruned
  })

  it('keeps only in-window spawns in the returned list', () => {
    const now = 100_000
    const { times } = decideRespawn([now - 500, now - 90_000, now - 10_000], now)
    expect(times).toEqual([now - 500, now - 10_000])
  })
})
