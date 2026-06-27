import { describe, it, expect } from 'vitest'
import { extractJSONObject } from './extractJson'

describe('extractJSONObject', () => {
  it('returns a bare object unchanged', () => {
    expect(extractJSONObject('{"a":1}')).toBe('{"a":1}')
  })

  it('drops a leading preamble and trailing prose so the result parses', () => {
    const out = extractJSONObject('Here you go: {"memories":[]} Hope that helps!')
    expect(JSON.parse(out)).toEqual({ memories: [] })
  })

  it('strips a ```json code fence', () => {
    const out = extractJSONObject('```json\n{"a":1}\n```')
    expect(JSON.parse(out)).toEqual({ a: 1 })
  })

  it('ignores braces inside string values', () => {
    const out = extractJSONObject('{"text":"a } b"} trailing words')
    expect(JSON.parse(out)).toEqual({ text: 'a } b' })
  })

  it('falls back to slice-to-end for an unterminated object', () => {
    expect(extractJSONObject('prefix {"a":1')).toBe('{"a":1')
  })
})
