// FIX 4(a) wiring: loadInsightContext must thread the user's Insight denylist into
// the activity aggregate, so a denylisted app's names/titles never enter the
// Phase-1 prompt — even when Insight triggered on a different, allowed app. The
// SQL-level exclusion itself is proven against a real engine in
// ../../ipc/rewindActivityDenylist.test.ts; here we pin the wiring.
import { describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  rewindActivityAggregate: vi.fn(() => [] as unknown[]),
  recentInsights: vi.fn(() => [] as { advice: string }[]),
  getLatestProfileText: vi.fn(() => null as string | null)
}))

vi.mock('electron', () => ({ net: { fetch: vi.fn() } }))
vi.mock('../core/session', () => ({
  getAbortSignal: () => undefined,
  getBackendSession: () => null
}))
vi.mock('../aiUserProfile/service', () => ({ getLatestProfileText: h.getLatestProfileText }))
vi.mock('../../ipc/db', () => ({
  rewindActivityAggregate: h.rewindActivityAggregate,
  recentInsights: h.recentInsights
}))

import { loadInsightContext } from './context'

describe('loadInsightContext — denylist threading', () => {
  it('forwards the denylist as the aggregate exclusion param', () => {
    const now = new Date('2026-07-15T12:00:00Z')
    const lookbackStartMs = now.getTime() - 600_000
    loadInsightContext({
      frame: { app: 'Terminal', windowTitle: 'zsh' },
      now,
      lookbackStartMs,
      denylist: ['Signal', 'Messages']
    })
    expect(h.rewindActivityAggregate).toHaveBeenCalledWith(lookbackStartMs, now.getTime(), 30, [
      'Signal',
      'Messages'
    ])
  })

  it('forwards an empty denylist unchanged', () => {
    const now = new Date('2026-07-15T12:00:00Z')
    loadInsightContext({
      frame: { app: 'Terminal', windowTitle: null as unknown as string },
      now,
      lookbackStartMs: now.getTime() - 1000,
      denylist: []
    })
    expect(h.rewindActivityAggregate).toHaveBeenCalledWith(
      expect.any(Number),
      now.getTime(),
      30,
      []
    )
  })
})
