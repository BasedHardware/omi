// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  __resetSuggestionsGenerationForTest,
  classifyContext,
  composeSuggestions,
  LEAD_SUGGESTION,
  parseGeneratedSuggestions,
  readSuggestionsCache,
  refreshHomeSuggestions,
  sanitizeSuggestions,
  suggestionsDayStamp
} from './homeSuggestions'

vi.mock('../persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../apiClient', () => ({ omiApi: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('../agentLLM', () => ({ callAgentLLM: vi.fn() }))
vi.mock('../actionItems', () => ({ fetchAllActionItems: vi.fn() }))

const NOW = new Date('2026-08-16T12:00:00')

beforeEach(() => {
  window.localStorage.clear()
  __resetSuggestionsGenerationForTest()
})

describe('sanitize + compose', () => {
  it('trims, drops overlong and universal questions, and dedupes case-insensitively', () => {
    const out = sanitizeSuggestions([
      '  Follow up with Sam?  ',
      'follow up with sam?',
      'What should I do today?',
      'x'.repeat(73),
      ''
    ])
    expect(out).toEqual(['Follow up with Sam?'])
  })

  it('always leads with the fixed chip and pads to two with the static fallbacks', () => {
    expect(composeSuggestions([])).toEqual([
      LEAD_SUGGESTION,
      'What did I spend my time on this week?',
      "What's the highest-leverage thing I can do next?"
    ])
    expect(composeSuggestions(['Ship the launch plan?'])).toEqual([
      LEAD_SUGGESTION,
      'Ship the launch plan?',
      'What did I spend my time on this week?'
    ])
  })
})

describe('context classification', () => {
  it('all-empty with any failed read is unavailable; all-empty with clean reads is thin', () => {
    expect(classifyContext({ memories: 0, conversations: null, actionItems: 0, goals: 0 })).toBe(
      'unavailable'
    )
    expect(classifyContext({ memories: 0, conversations: 0, actionItems: 0, goals: 0 })).toBe(
      'thin'
    )
    expect(classifyContext({ memories: 3, conversations: null, actionItems: 0, goals: 0 })).toBe(
      'available'
    )
  })
})

describe('generated reply parsing', () => {
  it('reads bare JSON and JSON embedded in prose, and rejects junk', () => {
    expect(parseGeneratedSuggestions('{"questions": ["A?", "B?"]}')).toEqual(['A?', 'B?'])
    expect(parseGeneratedSuggestions('Sure! {"questions": ["A?"]} Hope that helps.')).toEqual([
      'A?'
    ])
    expect(parseGeneratedSuggestions('no json here')).toEqual([])
    expect(parseGeneratedSuggestions('{"questions": "not a list"}')).toEqual([])
  })
})

describe('refresh', () => {
  const deps = (over: Record<string, unknown> = {}) => ({
    get: vi.fn(async (path: string) => {
      if (path === '/v3/memories') return { data: [{ content: 'Knows Sam from the launch' }] }
      if (path === '/v1/conversations') return { data: [] }
      if (path === '/v1/goals/all') return { data: [] }
      throw new Error('unexpected route')
    }) as never,
    fetchActionItems: vi.fn(async () => []) as never,
    generate: vi.fn(async () => '{"questions": ["Ask Sam about the launch?"]}'),
    now: () => NOW,
    ownerId: () => 'uid-1',
    ...over
  })

  it('generates once, caches under the owner and day stamp, and serves the cache after', async () => {
    const d = deps()
    const first = await refreshHomeSuggestions(d)
    expect(first).toEqual(['Ask Sam about the launch?'])
    expect(readSuggestionsCache('uid-1')).toEqual({
      questions: ['Ask Sam about the launch?'],
      dayStamp: suggestionsDayStamp(NOW)
    })
    const second = await refreshHomeSuggestions(d)
    expect(second).toEqual(['Ask Sam about the launch?'])
    expect(d.generate).toHaveBeenCalledTimes(1)
  })

  it('an unavailable context never burns the daily slot or the cache', async () => {
    const d = deps({
      get: vi.fn(async () => {
        throw new Error('down')
      }) as never,
      fetchActionItems: vi.fn(async () => []) as never
    })
    expect(await refreshHomeSuggestions(d)).toEqual([])
    expect(readSuggestionsCache('uid-1')).toBeNull()
    expect(d.generate).not.toHaveBeenCalled()
  })

  it('a thin context caches the empty list without calling the generator', async () => {
    const d = deps({
      get: vi.fn(async () => ({ data: [] })) as never,
      fetchActionItems: vi.fn(async () => []) as never
    })
    expect(await refreshHomeSuggestions(d)).toEqual([])
    expect(readSuggestionsCache('uid-1')).toEqual({
      questions: [],
      dayStamp: suggestionsDayStamp(NOW)
    })
    expect(d.generate).not.toHaveBeenCalled()
  })

  it('drops a generation that finishes after an owner switch', async () => {
    let owner = 'uid-1'
    const d = deps({
      ownerId: () => owner,
      generate: vi.fn(async () => {
        owner = 'uid-2'
        return '{"questions": ["Stale answer?"]}'
      })
    })
    expect(await refreshHomeSuggestions(d)).toEqual([])
    expect(readSuggestionsCache('uid-1')).toBeNull()
    expect(readSuggestionsCache('uid-2')).toBeNull()
  })

  it('a generator failure leaves the cache untouched for a retry next visit', async () => {
    const d = deps({
      generate: vi.fn(async () => {
        throw new Error('llm down')
      })
    })
    expect(await refreshHomeSuggestions(d)).toEqual([])
    expect(readSuggestionsCache('uid-1')).toBeNull()
  })
})
