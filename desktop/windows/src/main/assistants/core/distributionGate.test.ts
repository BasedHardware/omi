// The gate that decides whether a new frame is worth an assistant's (paid,
// cloud, battery-burning) look at all.
import { describe, expect, it } from 'vitest'
import {
  DEBOUNCE_MS,
  FALLBACK_MS,
  MESSAGING_FALLBACK_MS,
  distributionDecision,
  fallbackIntervalMs
} from './distributionGate'

const T0 = 1_700_000_000_000

const at = (
  now: number,
  over: { contextChanged?: boolean; app?: string; lastDistributedAt?: number | null } = {}
): ReturnType<typeof distributionDecision> =>
  distributionDecision({
    contextChanged: over.contextChanged ?? false,
    app: over.app ?? 'Visual Studio Code',
    now,
    lastDistributedAt: over.lastDistributedAt === undefined ? T0 : over.lastDistributedAt
  })

describe('fallbackIntervalMs', () => {
  it('is 60s normally and 15s in a messaging app', () => {
    expect(fallbackIntervalMs('Visual Studio Code')).toBe(FALLBACK_MS)
    expect(fallbackIntervalMs('Slack')).toBe(MESSAGING_FALLBACK_MS)
    expect(fallbackIntervalMs('WhatsApp')).toBe(MESSAGING_FALLBACK_MS)
    expect(fallbackIntervalMs('Discord')).toBe(MESSAGING_FALLBACK_MS)
  })
})

describe('distributionDecision', () => {
  it('flushes the first frame ever', () => {
    expect(at(T0, { lastDistributedAt: null })).toBe('flushNow')
  })

  it('debounces a context change so rapid app-hopping settles first', () => {
    expect(at(T0 + 1_000, { contextChanged: true })).toBe('scheduleDebounce')
    expect(DEBOUNCE_MS).toBe(3_000)
  })

  it('skips an unchanged context until the fallback elapses', () => {
    expect(at(T0 + 3_000)).toBe('skip')
    expect(at(T0 + 59_999)).toBe('skip')
    expect(at(T0 + 60_000)).toBe('flushNow')
  })

  it('uses the 15s fallback in a messaging app (replies arrive without a context change)', () => {
    expect(at(T0 + 14_999, { app: 'Slack' })).toBe('skip')
    expect(at(T0 + 15_000, { app: 'Slack' })).toBe('flushNow')
  })

  // The scenario this gate exists for: the user edits one file for ten minutes.
  // Capture writes a row roughly every second (the pHash keeps moving), so every
  // 3s tick sees a NEW frame id with NO context change. Without the gate that is
  // ~200 analyze() calls — and a vision assistant would ship ~200 screenshots.
  it('turns 10 minutes of typing in one window into ~10 distributions, not ~200', () => {
    let lastDistributedAt: number | null = T0
    let distributions = 0
    let ticks = 0
    for (let now = T0 + 3_000; now <= T0 + 600_000; now += 3_000) {
      ticks += 1
      const decision = distributionDecision({
        contextChanged: false,
        app: 'Visual Studio Code',
        now,
        lastDistributedAt
      })
      if (decision === 'flushNow') {
        distributions += 1
        lastDistributedAt = now
      }
    }
    expect(ticks).toBe(200) // what an ungated coordinator would have analyzed
    expect(distributions).toBe(10) // one per 60s fallback
  })
})
