// src/renderer/src/lib/insightGate.test.ts
import { describe, it, expect } from 'vitest'
import { selectInsight } from './insightGate'
import type { InsightPayload } from '../../../shared/types'

const ins = (headline: string, confidence: number): InsightPayload => ({
  headline, advice: 'a', reasoning: '', category: 'other', sourceApp: 'X', confidence
})

describe('selectInsight', () => {
  it('drops below threshold', () => {
    expect(selectInsight(ins('h', 0.5), { threshold: 0.75, recentHeadlines: [] })).toBeNull()
  })
  it('drops a near-duplicate of a recent headline', () => {
    expect(
      selectInsight(ins('Use a Debugger', 0.9), { threshold: 0.75, recentHeadlines: ['use a debugger'] })
    ).toBeNull()
  })
  it('passes a confident new insight', () => {
    expect(selectInsight(ins('Fresh idea', 0.8), { threshold: 0.75, recentHeadlines: ['other'] })).not.toBeNull()
  })
  it('passes null through', () => {
    expect(selectInsight(null, { threshold: 0.75, recentHeadlines: [] })).toBeNull()
  })
})
