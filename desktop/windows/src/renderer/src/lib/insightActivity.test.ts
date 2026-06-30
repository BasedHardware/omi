// src/renderer/src/lib/insightActivity.test.ts
import { describe, it, expect } from 'vitest'
import { summarizeActivity } from './insightActivity'
import type { RewindFrame } from '../../../shared/types'

const f = (app: string, windowTitle: string, ocrText: string): RewindFrame =>
  ({ id: 0, ts: 0, app, windowTitle, processName: app.toLowerCase(), ocrText, imagePath: '', width: 0, height: 0, indexed: 1 }) as RewindFrame

describe('summarizeActivity', () => {
  it('groups by app/window, dedupes identical OCR, and budgets length', () => {
    const out = summarizeActivity(
      [
        f('Code', 'plan.md', 'writing the plan'),
        f('Code', 'plan.md', 'writing the plan'),
        f('Code', 'plan.md', 'adding tests'),
        f('Chrome', 'Docs', 'reading api docs')
      ],
      10_000
    )
    expect(out).toContain('Code')
    expect(out).toContain('plan.md')
    expect(out).toContain('writing the plan')
    expect(out).toContain('adding tests')
    expect(out).toContain('Chrome')
  })
  it('returns empty string for no usable frames', () => {
    expect(summarizeActivity([f('Code', 'x', '   ')], 10_000)).toBe('')
  })
  it('keeps a truncated first block when it exceeds the budget', () => {
    const out = summarizeActivity([f('Code', 'plan.md', 'x'.repeat(500))], 40)
    expect(out.length).toBeGreaterThan(0)
    expect(out.length).toBeLessThanOrEqual(40)
    expect(out.startsWith('## ')).toBe(true)
  })

  // Bug #2: frames arrive oldest-first (listRewindFrames is ORDER BY ts). When the
  // budget can't hold everything, the summary must keep the MOST RECENT activity
  // (what the user is doing now) and drop the oldest — otherwise the proactive
  // insight is generated about a screen from up to an hour ago.
  it('keeps the most recent activity and drops the oldest when over budget', () => {
    const old = 'OLD_' + 'o'.repeat(120)
    const mid = 'MID_' + 'm'.repeat(120)
    const now = 'NOW_' + 'n'.repeat(120)
    const out = summarizeActivity(
      [f('OldApp', 'old', old), f('MidApp', 'mid', mid), f('NowApp', 'now', now)],
      300 // fits ~2 of the 3 blocks
    )
    expect(out).toContain('NOW_') // current screen is always present
    expect(out).not.toContain('OLD_') // oldest is dropped first
  })

  // The kept blocks must still read oldest→newest so the model sees the current
  // screen LAST (as "now"), not in reverse.
  it('emits kept blocks in chronological order (current screen last)', () => {
    const mid = 'MID_' + 'm'.repeat(120)
    const now = 'NOW_' + 'n'.repeat(120)
    const out = summarizeActivity(
      [f('MidApp', 'mid', mid), f('NowApp', 'now', now)],
      10_000 // both fit
    )
    expect(out.indexOf('MID_')).toBeLessThan(out.indexOf('NOW_'))
  })
})
