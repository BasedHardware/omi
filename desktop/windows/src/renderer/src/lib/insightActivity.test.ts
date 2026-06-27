// src/renderer/src/lib/insightActivity.test.ts
import { describe, it, expect } from 'vitest'
import { fromPartial } from '@total-typescript/shoehorn'
import { summarizeActivity } from './insightActivity'
import type { RewindFrame } from '../../../shared/types'

const f = (app: string, windowTitle: string, ocrText: string): RewindFrame =>
  fromPartial({ app, windowTitle, ocrText })

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
})
