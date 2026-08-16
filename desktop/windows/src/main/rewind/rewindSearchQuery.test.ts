import { describe, expect, it } from 'vitest'
import {
  buildRewindFtsMatch,
  expandRewindSearchWord,
  REWIND_SEARCH_QUERY_CHAR_LIMIT,
  REWIND_SEARCH_TOKEN_LIMIT,
  splitCamelCase,
  splitOnDigits,
  tokenizeRewindSearchQuery
} from './rewindSearchQuery'

describe('rewindSearchQuery — tokenizer', () => {
  it('normalizes whitespace and caps the number of tokens', () => {
    expect(tokenizeRewindSearchQuery('  visual   studio  code ')).toEqual([
      'visual',
      'studio',
      'code'
    ])
    const many = Array.from({ length: REWIND_SEARCH_TOKEN_LIMIT + 3 }, (_, i) => `term${i}`).join(
      ' '
    )
    expect(tokenizeRewindSearchQuery(many)).toHaveLength(REWIND_SEARCH_TOKEN_LIMIT)
  })

  it('limits scanned query text before tokenizing large inputs', () => {
    const huge = `${'a'.repeat(REWIND_SEARCH_QUERY_CHAR_LIMIT + 20)} tail`
    expect(tokenizeRewindSearchQuery(huge)).toEqual(['a'.repeat(REWIND_SEARCH_QUERY_CHAR_LIMIT)])
  })

  it('does not let leading whitespace consume the query text cap', () => {
    const padded = `${' '.repeat(REWIND_SEARCH_QUERY_CHAR_LIMIT + 20)}visual studio`
    expect(tokenizeRewindSearchQuery(padded)).toEqual(['visual', 'studio'])
  })
})

describe('rewindSearchQuery — compound splitting', () => {
  it('splits camelCase on uppercase boundaries, dropping <2-char parts', () => {
    expect(splitCamelCase('ActivityPerformance')).toEqual(['Activity', 'Performance'])
    // Leading single-cap fragment "A" is dropped (length < 2).
    expect(splitCamelCase('AButton')).toEqual(['Button'])
    expect(splitCamelCase('lowercase')).toEqual(['lowercase'])
  })

  it('splits on digit/non-digit boundaries, dropping <2-char parts', () => {
    expect(splitOnDigits('test123')).toEqual(['test', '123'])
    // "v2" -> ["v", "2"] both dropped (length < 2).
    expect(splitOnDigits('v2')).toEqual([])
    expect(splitOnDigits('plain')).toEqual(['plain'])
  })
})

describe('rewindSearchQuery — FTS5 MATCH builder', () => {
  it('quotes a single token as an FTS5 prefix phrase', () => {
    expect(expandRewindSearchWord('visual')).toBe('"visual"*')
    expect(buildRewindFtsMatch('visual studio')).toBe('"visual"* "studio"*')
  })

  it('expands camelCase into an OR of prefix terms (original first, deduped, ordered)', () => {
    expect(buildRewindFtsMatch('ActivityPerformance')).toBe(
      '("ActivityPerformance"* OR "Activity"* OR "Performance"*)'
    )
  })

  it('expands digit boundaries into an OR of prefix terms', () => {
    expect(buildRewindFtsMatch('test123')).toBe('("test123"* OR "test"* OR "123"*)')
  })

  it('AND-joins multiple tokens (space is implicit AND in FTS5)', () => {
    expect(buildRewindFtsMatch('pelican reservoir')).toBe('"pelican"* "reservoir"*')
  })

  it('escapes embedded double quotes so MATCH syntax cannot be broken', () => {
    // A literal " is doubled inside the phrase; the surrounding grammar is intact.
    expect(buildRewindFtsMatch('foo"bar')).toBe('"foo""bar"*')
    // Parens / operators from user input are neutralized by quoting.
    expect(buildRewindFtsMatch('a) OR b(')).toBe('"a)"* "OR"* "b("*')
  })

  it('drops pure-punctuation tokens and returns null for an empty query', () => {
    expect(buildRewindFtsMatch('   ')).toBeNull()
    expect(buildRewindFtsMatch('!!! @@')).toBeNull()
    // One punctuation token dropped, the real one kept.
    expect(buildRewindFtsMatch('!!! budget')).toBe('"budget"*')
  })
})
