import { describe, it, expect } from 'vitest'
import {
  sanitizeWorkstreamTag,
  liveTag,
  selectPooledFacts,
  selectRecentContextFacts,
  relativeAge,
  workstreamPromptSection,
  recentContextPromptSection,
  type PoolFact
} from './workstreamPooling'

const NOW = 1_760_000_000_000
const HOUR = 60 * 60 * 1000

const fact = (over: Partial<PoolFact> = {}): PoolFact => ({
  factID: 'f1',
  bucketID: 'b1',
  appName: 'Code',
  statement: 'A validated statement.',
  notifyWorthiness: 0.7,
  createdAt: NOW - HOUR,
  ...over
})

describe('sanitizeWorkstreamTag', () => {
  it('kebab-cases and enforces the 2-32 window', () => {
    expect(sanitizeWorkstreamTag('  Omi Port ')).toBe('omi-port')
    expect(sanitizeWorkstreamTag('a__b--c')).toBe('a-b-c')
    expect(sanitizeWorkstreamTag('-x-')).toBeNull()
    expect(sanitizeWorkstreamTag('a')).toBeNull()
    expect(sanitizeWorkstreamTag('x'.repeat(33))).toBeNull()
  })

  it('rejects the unknown abstention', () => {
    expect(sanitizeWorkstreamTag('unknown')).toBeNull()
    expect(sanitizeWorkstreamTag('UNKNOWN')).toBeNull()
  })
})

describe('liveTag', () => {
  it('any own-visit tag wins outright', () => {
    expect(liveTag(new Map([['alpha', 1]]), new Map([['beta', 10]]))).toBe('alpha')
  })

  it('bucket majority stands in only at >=3 tagged facts and >=80% share', () => {
    expect(
      liveTag(
        new Map(),
        new Map([
          ['alpha', 4],
          ['beta', 1]
        ])
      )
    ).toBe('alpha')
    expect(
      liveTag(
        new Map(),
        new Map([
          ['alpha', 3],
          ['beta', 1]
        ])
      )
    ).toBeNull()
    expect(liveTag(new Map(), new Map([['alpha', 2]]))).toBeNull()
    expect(liveTag(new Map(), new Map())).toBeNull()
  })
})

describe('selectPooledFacts', () => {
  it('applies the worthiness floor, scaffolding filter, and score ordering', () => {
    const facts = [
      fact({ factID: 'low', notifyWorthiness: 0.2 }),
      fact({ factID: 'scaffold', statement: 'Proposed fact: nothing real.' }),
      fact({ factID: 'old-high', notifyWorthiness: 0.9, createdAt: NOW - 48 * HOUR }),
      fact({ factID: 'fresh-mid', notifyWorthiness: 0.5, createdAt: NOW })
    ]
    // fresh-mid scores 0.5 + 1.0 = 1.5; old-high scores 0.9 + ~0.004.
    expect(selectPooledFacts(facts, NOW).map((f) => f.factID)).toEqual(['fresh-mid', 'old-high'])
  })

  it('caps per bucket at 3 and total at 8', () => {
    const facts: PoolFact[] = []
    for (let bucket = 0; bucket < 4; bucket++) {
      for (let i = 0; i < 5; i++) {
        facts.push(
          fact({
            factID: `b${bucket}-f${i}`,
            bucketID: `bucket-${bucket}`,
            createdAt: NOW - i * 1000
          })
        )
      }
    }
    const selected = selectPooledFacts(facts, NOW)
    expect(selected.length).toBe(8)
    const perBucket = new Map<string, number>()
    for (const f of selected) perBucket.set(f.bucketID, (perBucket.get(f.bucketID) ?? 0) + 1)
    for (const count of perBucket.values()) expect(count).toBeLessThanOrEqual(3)
  })

  it('recent-context variant: floor 0.6, window 15 min, one per bucket, max 3', () => {
    const facts = [
      fact({ factID: 'in-window', notifyWorthiness: 0.7, createdAt: NOW - 10 * 60 * 1000 }),
      fact({ factID: 'same-bucket', notifyWorthiness: 0.9, createdAt: NOW - 5 * 60 * 1000 }),
      fact({ factID: 'too-old', notifyWorthiness: 0.9, createdAt: NOW - 20 * 60 * 1000 }),
      fact({ factID: 'too-weak', notifyWorthiness: 0.5, createdAt: NOW - 60 * 1000 })
    ]
    const selected = selectRecentContextFacts(facts, NOW)
    expect(selected.length).toBe(1)
    expect(selected[0].factID).toBe('same-bucket')
  })
})

describe('relativeAge', () => {
  it('buckets s/m/h/d exactly', () => {
    expect(relativeAge(30 * 1000)).toBe('30s ago')
    expect(relativeAge(5 * 60 * 1000)).toBe('5m ago')
    expect(relativeAge(3 * HOUR)).toBe('3h ago')
    expect(relativeAge(49 * HOUR)).toBe('2d ago')
  })
})

describe('prompt sections', () => {
  it('renders the non-citable intro and clamped item lines', () => {
    const section = workstreamPromptSection(
      'omi-port',
      [fact({ appName: 'A'.repeat(40), statement: 'S'.repeat(400) })],
      NOW
    )
    expect(section).toContain('== RELATED WORKSTREAM CONTEXT (omi-port) ==')
    expect(section).toContain('not citable — never place them in bucket_entry_refs or fact_ids')
    const line = section?.split('\n').at(-1) as string
    expect(line.startsWith(`- [${'A'.repeat(24)}, 1h ago] ${'S'.repeat(300)}`)).toBe(true)
    expect(line.length).toBe(2 + 1 + 24 + 2 + 6 + 2 + 300)
  })

  it('recent-context header names the 15-minute window; empty lists render nothing', () => {
    expect(recentContextPromptSection([fact()], NOW)).toContain(
      '== RECENT CONTEXT FROM OTHER WINDOWS (last 15 min) =='
    )
    expect(workstreamPromptSection('t', [], NOW)).toBeNull()
    expect(recentContextPromptSection([], NOW)).toBeNull()
  })
})
