import { describe, it, expect } from 'vitest'
import {
  categoryCounts,
  categoryLabel,
  describeFilters,
  estimateForgetSeconds,
  filterMemories,
  forgetPreview,
  formatDuration,
  hasActiveFilter,
  isSeenOnce,
  memorySource,
  provenanceChain,
  relatedMemories,
  sourceCounts,
  withinDateRange
} from './memoryProvenance'
import { SCREEN_TAG } from './screenTag'
import { APP_INDEX_TAG } from './memoryCleanup'
import type { Memory, MemoryEvidence } from '../hooks/useMemories'

function mem(id: string, over: Partial<Memory> = {}): Memory {
  return {
    id,
    uid: 'u',
    content: `memory ${id}`,
    created_at: '2026-06-30T12:00:00Z',
    updated_at: '2026-06-30T12:00:00Z',
    ...over
  }
}

function ev(over: Partial<MemoryEvidence> = {}): MemoryEvidence {
  return {
    evidence_id: 'e1',
    source_id: 'conv-1',
    source_type: 'conversation',
    source_signal: 'transcription',
    extractor_id: 'memory_extractor',
    extractor_version: 'v1',
    capture_confidence: 0.8,
    independence_group: 'conv-1',
    redaction_status: 'active',
    created_at: '2026-06-30T11:58:00Z',
    ...over
  }
}

describe('memorySource', () => {
  it('classifies by the desktop provenance tags first', () => {
    expect(memorySource(mem('1', { tags: [SCREEN_TAG] }))).toBe('screen')
    expect(memorySource(mem('2', { tags: [APP_INDEX_TAG] }))).toBe('file-index')
    expect(memorySource(mem('3', { tags: ['gmail/import/note'] }))).toBe('gmail')
    expect(memorySource(mem('4', { tags: ['sticky_notes/import/profile'] }))).toBe('sticky-notes')
  })
  it('classifies manual via manually_added, category, or evidence signal', () => {
    expect(memorySource(mem('1', { manually_added: true }))).toBe('manual')
    expect(memorySource(mem('2', { category: 'manual' }))).toBe('manual')
    expect(memorySource(mem('3', { evidence: [ev({ source_signal: 'manual' })] }))).toBe('manual')
  })
  it('classifies chat, integration, and conversation from the evidence record', () => {
    expect(memorySource(mem('1', { evidence: [ev({ source_type: 'chat_exchange', source_signal: 'direct_user' })] }))).toBe('chat')
    expect(memorySource(mem('2', { evidence: [ev({ source_type: 'integration:x', source_signal: 'integration' })] }))).toBe('integration')
    expect(memorySource(mem('3', { evidence: [ev()] }))).toBe('conversation')
  })
  it('falls back to conversation_id, then app_id, then unknown', () => {
    expect(memorySource(mem('1', { conversation_id: 'c1' }))).toBe('conversation')
    expect(memorySource(mem('2', { app_id: 'some-app' }))).toBe('app')
    expect(memorySource(mem('3'))).toBe('unknown')
  })
  it('prefers a tag over a conflicting evidence record', () => {
    expect(memorySource(mem('1', { tags: [SCREEN_TAG], evidence: [ev()] }))).toBe('screen')
  })
  it('prefers manually_added / category=manual over a conflicting transcription signal', () => {
    // Defense in depth for the create flow: even if the evidence record says
    // 'transcription', an explicit manual marker on the record wins — a
    // user-typed memory must never be labeled "Heard in a conversation".
    expect(memorySource(mem('1', { manually_added: true, evidence: [ev()] }))).toBe('manual')
    expect(memorySource(mem('2', { category: 'manual', evidence: [ev()] }))).toBe('manual')
    expect(
      memorySource(
        mem('3', {
          manually_added: true,
          conversation_id: 'c1',
          evidence: [ev({ source_type: 'conversation', source_signal: 'transcription' })]
        })
      )
    ).toBe('manual')
  })
  it('classifies from the active evidence, skipping a tombstoned first record', () => {
    // A tombstoned evidence[0] must not drive the card's source: the active
    // record classifies, matching what provenanceChain shows in the detail.
    const m = mem('1', {
      evidence: [
        ev({ source_type: 'chat_exchange', source_signal: 'direct_user', redaction_status: 'tombstoned' }),
        ev({ evidence_id: 'e2', source_type: 'conversation', source_signal: 'transcription' })
      ]
    })
    expect(memorySource(m)).toBe('conversation')
  })
})

describe('withinDateRange', () => {
  const now = new Date('2026-06-30T18:00:00Z')
  it('always matches "any"', () => {
    expect(withinDateRange('2001-01-01T00:00:00Z', 'any', now)).toBe(true)
  })
  it('matches today only for the same local day', () => {
    expect(withinDateRange(new Date(now.getTime() - 3600_000).toISOString(), 'today', now)).toBe(true)
    expect(withinDateRange(new Date(now.getTime() - 2 * 86_400_000).toISOString(), 'today', now)).toBe(false)
  })
  it('bounds 7 and 30 day windows', () => {
    expect(withinDateRange(new Date(now.getTime() - 6 * 86_400_000).toISOString(), '7d', now)).toBe(true)
    expect(withinDateRange(new Date(now.getTime() - 8 * 86_400_000).toISOString(), '7d', now)).toBe(false)
    expect(withinDateRange(new Date(now.getTime() - 29 * 86_400_000).toISOString(), '30d', now)).toBe(true)
    expect(withinDateRange(new Date(now.getTime() - 31 * 86_400_000).toISOString(), '30d', now)).toBe(false)
  })
  it('rejects an unparseable timestamp instead of matching it', () => {
    expect(withinDateRange('not-a-date', '7d', now)).toBe(false)
  })
})

describe('filterMemories', () => {
  const now = new Date('2026-06-30T18:00:00Z')
  const list = [
    mem('screen-old', { tags: [SCREEN_TAG], content: 'compared CAD tools', created_at: '2026-05-01T10:00:00Z' }),
    mem('screen-new', { tags: [SCREEN_TAG], content: 'compared flight prices', created_at: '2026-06-29T10:00:00Z' }),
    mem('manual-new', { manually_added: true, content: 'allergic to peanuts', created_at: '2026-06-30T08:00:00Z' })
  ]
  it('composes text, source, and date filters (AND)', () => {
    expect(filterMemories(list, { text: 'compared' }, now).map((m) => m.id)).toEqual(['screen-old', 'screen-new'])
    expect(filterMemories(list, { text: 'compared', range: '7d' }, now).map((m) => m.id)).toEqual(['screen-new'])
    expect(filterMemories(list, { source: 'screen', range: '7d' }, now).map((m) => m.id)).toEqual(['screen-new'])
    expect(filterMemories(list, { source: 'manual', text: 'compared' }, now)).toEqual([])
  })
  it('passes everything through with no active filter', () => {
    expect(filterMemories(list, { text: ' ', source: 'all', range: 'any' }, now)).toHaveLength(3)
  })
  it('reports whether any filter is active', () => {
    expect(hasActiveFilter({ text: ' ', source: 'all', range: 'any' })).toBe(false)
    expect(hasActiveFilter({ text: 'x' })).toBe(true)
    expect(hasActiveFilter({ source: 'screen' })).toBe(true)
    expect(hasActiveFilter({ range: '7d' })).toBe(true)
  })
})

describe('describeFilters', () => {
  it('summarizes the active scope in plain language', () => {
    expect(describeFilters({ source: 'screen', range: '7d' })).toBe(
      'Everything from screen capture, last 7 days'
    )
    expect(describeFilters({ text: 'standup' })).toBe('Everything matching "standup"')
  })
  it('is null when nothing is filtered', () => {
    expect(describeFilters({ source: 'all', range: 'any', text: '' })).toBeNull()
  })
})

describe('counts and preview', () => {
  const list = [
    mem('1', { tags: [SCREEN_TAG], category: 'work' }),
    mem('2', { tags: [SCREEN_TAG], category: 'work' }),
    mem('3', { manually_added: true, category: 'core' }),
    mem('4', { conversation_id: 'c1' }) // no category -> 'other'
  ]
  it('groups source counts descending', () => {
    expect(sourceCounts(list)).toEqual([
      { kind: 'screen', count: 2 },
      { kind: 'manual', count: 1 },
      { kind: 'conversation', count: 1 }
    ])
  })
  it('groups category counts descending with a fallback bucket', () => {
    expect(categoryCounts(list)).toEqual([
      { category: 'work', count: 2 },
      { category: 'core', count: 1 },
      { category: 'other', count: 1 }
    ])
    expect(categoryLabel('work')).toBe('Work')
  })
  it('builds the consequence preview from the selection only', () => {
    const preview = forgetPreview(list.slice(0, 3))
    expect(preview.count).toBe(3)
    expect(preview.bySource[0]).toEqual({ kind: 'screen', count: 2 })
    expect(preview.byCategory[0]).toEqual({ category: 'work', count: 2 })
  })
})

describe('estimateForgetSeconds / formatDuration', () => {
  it('paces small batches at ~1.1s each', () => {
    expect(estimateForgetSeconds(0)).toBe(0)
    expect(estimateForgetSeconds(10)).toBeCloseTo(11)
    expect(estimateForgetSeconds(60)).toBeCloseTo(66)
  })
  it('paces past the hourly cap at ~1/minute', () => {
    expect(estimateForgetSeconds(61)).toBeCloseTo(126)
    expect(estimateForgetSeconds(120)).toBeCloseTo(66 + 60 * 60)
  })
  it('formats durations honestly', () => {
    expect(formatDuration(30)).toBe('under a minute')
    expect(formatDuration(300)).toBe('about 5 minutes')
    expect(formatDuration(3600)).toBe('about 1 hour')
    expect(formatDuration(5400)).toBe('about 1 h 30 min')
  })
})

describe('isSeenOnce', () => {
  it('is true only when the server flagged single_source', () => {
    expect(isSeenOnce(mem('1', { uncertainty_reasons: ['single_source'] }))).toBe(true)
    expect(isSeenOnce(mem('2', { uncertainty_reasons: ['stale'] }))).toBe(false)
    expect(isSeenOnce(mem('3'))).toBe(false) // field absent -> no marker, never guessed
  })
})

describe('provenanceChain', () => {
  it('renders the shortest honest chain for a bare legacy memory', () => {
    const steps = provenanceChain(mem('1'))
    expect(steps).toHaveLength(1)
    expect(steps[0]).toMatchObject({ kind: 'capture', title: 'Origin not recorded', at: '2026-06-30T12:00:00Z' })
    expect(steps[0].sub).toBeUndefined()
  })
  it('adds conversation, extraction, and corroboration steps only when backed by data', () => {
    const m = mem('1', {
      conversation_id: 'c1',
      capture_confidence: 0.8,
      evidence: [
        ev({ client_device_id: 'LAPTOP-A9' }),
        ev({ evidence_id: 'e2', independence_group: 'conv-2', created_at: '2026-07-01T09:20:00Z' })
      ]
    })
    const steps = provenanceChain(m)
    expect(steps.map((s) => s.kind)).toEqual(['capture', 'conversation', 'extraction', 'corroboration'])
    expect(steps[0].sub).toBe('Device: LAPTOP-A9')
    expect(steps[1].conversationId).toBe('c1')
    expect(steps[2].sub).toBe('memory_extractor v1 · capture confidence 0.80')
    expect(steps[3].title).toBe('Confirmed 1 more time')
    expect(steps[3].sub).toContain('2 independent sources')
    expect(steps[3].at).toBe('2026-07-01T09:20:00Z')
  })
  it('omits the extraction step when the extractor is unknown', () => {
    const m = mem('1', { evidence: [ev({ extractor_id: 'unknown', extractor_version: 'unknown' })] })
    expect(provenanceChain(m).map((s) => s.kind)).toEqual(['capture'])
  })
  it('omits capture confidence when the field is missing', () => {
    const m = mem('1', { evidence: [ev()] })
    const extraction = provenanceChain(m).find((s) => s.kind === 'extraction')
    expect(extraction?.sub).toBe('memory_extractor v1')
  })
  it('ignores tombstoned evidence for corroboration', () => {
    const m = mem('1', {
      evidence: [ev(), ev({ evidence_id: 'e2', redaction_status: 'tombstoned' })]
    })
    expect(provenanceChain(m).some((s) => s.kind === 'corroboration')).toBe(false)
  })
  it('picks the chronologically latest corroboration timestamp, not the lexicographically last', () => {
    // created_at values can carry timezone offsets, so a raw string sort can
    // pick an earlier instant. Sort by parsed time so the true latest wins:
    // 08:00Z is later than 09:00+05:00 (04:00Z) yet sorts earlier as a string.
    const m = mem('1', {
      evidence: [
        ev({ created_at: '2026-07-01T08:00:00Z' }),
        ev({ evidence_id: 'e2', created_at: '2026-07-01T09:00:00+05:00' })
      ]
    })
    const step = provenanceChain(m).find((s) => s.kind === 'corroboration')
    expect(step?.at).toBe('2026-07-01T08:00:00Z')
  })
})

describe('relatedMemories', () => {
  const list = [
    mem('a', { conversation_id: 'c1' }),
    mem('b', { conversation_id: 'c1' }),
    mem('c', { conversation_id: 'c2' }),
    mem('d')
  ]
  it('returns other memories from the same conversation', () => {
    expect(relatedMemories(list, list[0]).map((m) => m.id)).toEqual(['b'])
  })
  it('is empty when the memory has no conversation', () => {
    expect(relatedMemories(list, list[3])).toEqual([])
  })
})
