import { describe, expect, it } from 'vitest'
import {
  COPY,
  corpusCountLabel,
  failedCorpora,
  isEmptyResult,
  isTotalFailure,
  searchPhase
} from './searchCopy'
import { CORPUS_LABELS, emptyResults, type SearchResults, type SearchSlice } from './runSearch'

const slice = (over: Partial<SearchSlice> = {}): SearchSlice => ({
  hits: [],
  total: 0,
  failed: false,
  atLeast: false,
  ...over
})

const hits = (n: number): SearchSlice['hits'] =>
  Array.from({ length: n }, (_v, i) => ({
    kind: 'memory' as const,
    id: String(i),
    title: `hit ${i}`,
    detail: '',
    timestamp: i
  }))

const results = (over: Partial<SearchResults> = {}): SearchResults => ({
  ...emptyResults('lease'),
  ...over
})

describe('corpusCountLabel', () => {
  it('says nothing matched when nothing did', () => {
    expect(corpusCountLabel(slice())).toBe('No matches')
  })

  it('names a failure instead of showing it as an empty result', () => {
    // An empty list here would read as "you have nothing about that", which is a
    // different and much worse claim than "this could not be searched".
    expect(corpusCountLabel(slice({ failed: true }))).toBe('Could not be searched')
  })

  it('gives the exact count when everything is on screen', () => {
    expect(corpusCountLabel(slice({ hits: hits(1), total: 1 }))).toBe('1 match')
    expect(corpusCountLabel(slice({ hits: hits(4), total: 4 }))).toBe('4 matches')
  })

  it('says how much it is not showing when the list is capped', () => {
    expect(corpusCountLabel(slice({ hits: hits(20), total: 300 }))).toBe('Showing 20 of 300')
  })

  it('marks a lower-bound total so it is never read as exact', () => {
    // The conversation endpoint reports pages, not rows, so this total is a
    // floor and must not be presented as a count.
    expect(corpusCountLabel(slice({ hits: hits(20), total: 41, atLeast: true }))).toBe(
      'Showing 20 of 41+'
    )
  })

  it('groups thousands so a large number stays readable', () => {
    expect(corpusCountLabel(slice({ hits: hits(20), total: 3741 }))).toBe('Showing 20 of 3,741')
  })

  it('never claims fewer matches than the hits it is showing', () => {
    // A stale or wrong total must not produce "Showing 20 of 3".
    expect(corpusCountLabel(slice({ hits: hits(20), total: 3 }))).toBe('20 matches')
  })
})

describe('result predicates', () => {
  it('treats a result with no hits anywhere as empty', () => {
    expect(isEmptyResult(results())).toBe(true)
    expect(isEmptyResult(results({ tasks: slice({ hits: hits(1), total: 1 }) }))).toBe(false)
  })

  it('does not call a result empty when a corpus failed', () => {
    // Something might well match in the corpus that could not be reached.
    expect(isEmptyResult(results({ conversations: slice({ failed: true }) }))).toBe(false)
  })

  it('recognises a total failure and lists which corpora failed', () => {
    const all = results({
      conversations: slice({ failed: true }),
      memories: slice({ failed: true }),
      tasks: slice({ failed: true }),
      screen: slice({ failed: true })
    })
    expect(isTotalFailure(all)).toBe(true)
    expect(failedCorpora(all)).toEqual(['conversations', 'memories', 'tasks', 'screen'])

    const partial = results({ conversations: slice({ failed: true }) })
    expect(isTotalFailure(partial)).toBe(false)
    expect(failedCorpora(partial)).toEqual(['conversations'])
  })
})

describe('searchPhase', () => {
  const base = { input: '', searching: false, results: null as SearchResults | null }

  it('prompts on an empty box', () => {
    expect(searchPhase(base)).toEqual({ kind: 'prompt' })
    expect(searchPhase({ ...base, input: '   ' })).toEqual({ kind: 'prompt' })
  })

  it('asks for more characters before searching', () => {
    expect(searchPhase({ ...base, input: 'l' })).toEqual({ kind: 'tooShort' })
  })

  it('shows searching while a request is open', () => {
    expect(searchPhase({ ...base, input: 'lease', searching: true })).toEqual({ kind: 'searching' })
  })

  it('keeps showing searching until the first result arrives', () => {
    // results === null means nothing has come back yet. Rendering "nothing
    // found" here would tell someone their data is missing when it simply has
    // not arrived.
    expect(searchPhase({ ...base, input: 'lease', searching: false })).toEqual({
      kind: 'searching'
    })
  })

  it('prefers searching over empty when a newer request is open', () => {
    expect(searchPhase({ input: 'lease', searching: true, results: results() })).toEqual({
      kind: 'searching'
    })
  })

  it('reports empty against the text that was searched, not the live input', () => {
    // The box may already say "leaseh" while these results are for "lease".
    expect(
      searchPhase({ input: 'leaseh', searching: false, results: results({ query: 'lease' }) })
    ).toEqual({ kind: 'empty', query: 'lease' })
  })

  it('calls it unavailable when nothing could be searched', () => {
    const dead = results({
      conversations: slice({ failed: true }),
      memories: slice({ failed: true }),
      tasks: slice({ failed: true }),
      screen: slice({ failed: true })
    })
    expect(searchPhase({ input: 'lease', searching: false, results: dead })).toEqual({
      kind: 'unavailable'
    })
  })

  it('shows results when any corpus has one', () => {
    expect(
      searchPhase({
        input: 'lease',
        searching: false,
        results: results({ memories: slice({ hits: hits(2), total: 2 }) })
      })
    ).toEqual({ kind: 'results' })
  })
})

describe('COPY', () => {
  it('names the searched text in the empty message', () => {
    expect(COPY.empty('lease')).toBe('Nothing matches “lease”.')
  })

  it('names every corpus that failed in the partial warning', () => {
    expect(COPY.partial(['conversations'], CORPUS_LABELS)).toBe(
      'Conversations could not be searched, so these results are incomplete.'
    )
    expect(COPY.partial(['conversations', 'screen'], CORPUS_LABELS)).toBe(
      'Conversations and Screen could not be searched, so these results are incomplete.'
    )
  })
})
