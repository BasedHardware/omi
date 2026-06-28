import { describe, it, expect } from 'vitest'
import {
  buildScreenPrompt,
  parseScreenResponse,
  selectWritableCandidates,
  normalizeForDedupe
} from './screenSynthesisPrompt'

describe('buildScreenPrompt', () => {
  it('includes segment app/window and text', () => {
    const p = buildScreenPrompt([{ app: 'Code', windowTitle: 'plan.md', text: 'writing the plan' }])
    expect(p).toContain('Code')
    expect(p).toContain('plan.md')
    expect(p).toContain('writing the plan')
  })
})

describe('parseScreenResponse', () => {
  it('parses fenced JSON', () => {
    const raw = '```json\n{"candidates":[{"text":"User works on omi-windows","confidence":0.9}]}\n```'
    expect(parseScreenResponse(raw)).toEqual([
      { text: 'User works on omi-windows', confidence: 0.9 }
    ])
  })
  it('returns [] on malformed JSON', () => {
    expect(parseScreenResponse('not json at all')).toEqual([])
  })
  it('drops items missing text/confidence', () => {
    expect(
      parseScreenResponse(
        '{"candidates":[{"text":"ok","confidence":0.8},{"text":""},{"confidence":0.9}]}'
      )
    ).toEqual([{ text: 'ok', confidence: 0.8 }])
  })
})

describe('selectWritableCandidates', () => {
  it('keeps only confidence >= threshold, dedupes against seen, and caps', () => {
    const seen = new Set([normalizeForDedupe('Already known fact')])
    const out = selectWritableCandidates(
      [
        { text: 'High conf new', confidence: 0.9 },
        { text: 'low conf', confidence: 0.3 },
        { text: 'already known fact', confidence: 0.95 }, // dup (normalized)
        { text: 'second new', confidence: 0.8 },
        { text: 'third new', confidence: 0.85 }
      ],
      { threshold: 0.7, cap: 2, seen }
    )
    expect(out.map((c) => c.text)).toEqual(['High conf new', 'second new'])
  })
})
