import { describe, expect, it } from 'vitest'
import {
  buildRewindSearchQuery,
  escapeRewindSearchLikeToken,
  REWIND_SEARCH_TOKEN_LIMIT,
  tokenizeRewindSearchQuery
} from './rewindSearchQuery'

describe('rewindSearchQuery', () => {
  it('normalizes whitespace and caps the number of SQL terms', () => {
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

  it('escapes LIKE wildcards and the escape character itself', () => {
    expect(escapeRewindSearchLikeToken('100%_done\\today')).toBe('100\\%\\_done\\\\today')
  })

  it('builds an all-token search across OCR text, app, and window title', () => {
    const sql = buildRewindSearchQuery('visual studio')

    expect(sql?.where).toBe(
      "(ocr_text LIKE ? ESCAPE '\\' OR window_title LIKE ? ESCAPE '\\' OR app LIKE ? ESCAPE '\\') AND (ocr_text LIKE ? ESCAPE '\\' OR window_title LIKE ? ESCAPE '\\' OR app LIKE ? ESCAPE '\\')"
    )
    expect(sql?.params).toEqual(Array(3).fill('%visual%').concat(Array(3).fill('%studio%')))
  })

  it('treats percent and underscore as literal search characters', () => {
    const sql = buildRewindSearchQuery('100% done_')

    expect(sql?.params).toEqual(Array(3).fill('%100\\%%').concat(Array(3).fill('%done\\_%')))
  })

  it('returns null for an empty query', () => {
    expect(buildRewindSearchQuery('   ')).toBeNull()
  })
})
