import { describe, it, expect } from 'vitest'
import {
  BYOK_PROVIDERS,
  BYOK_HEADER_NAMES,
  withByokHeaders,
  isByokActive,
  byokFingerprint,
  type ByokKeys
} from './byok'

const fullKeys: ByokKeys = {
  openai: 'sk-openai',
  anthropic: 'sk-ant',
  gemini: 'gm-key',
  deepgram: 'dg-key'
}

describe('withByokHeaders', () => {
  it('attaches a header for each non-empty key (full set)', () => {
    const out = withByokHeaders({}, fullKeys)
    expect(out).toEqual({
      'X-BYOK-OpenAI': 'sk-openai',
      'X-BYOK-Anthropic': 'sk-ant',
      'X-BYOK-Gemini': 'gm-key',
      'X-BYOK-Deepgram': 'dg-key'
    })
  })

  it('attaches only the provided providers (partial set)', () => {
    const out = withByokHeaders({}, { openai: 'sk-openai', gemini: 'gm-key' })
    expect(out).toEqual({ 'X-BYOK-OpenAI': 'sk-openai', 'X-BYOK-Gemini': 'gm-key' })
    expect(out['X-BYOK-Anthropic']).toBeUndefined()
  })

  it('trims key values before attaching', () => {
    const out = withByokHeaders({}, { openai: '  sk-openai  ' })
    expect(out['X-BYOK-OpenAI']).toBe('sk-openai')
  })

  it('skips empty and whitespace-only keys', () => {
    const out = withByokHeaders({}, { openai: '', anthropic: '   ', gemini: 'gm' })
    expect(out['X-BYOK-OpenAI']).toBeUndefined()
    expect(out['X-BYOK-Anthropic']).toBeUndefined()
    expect(out['X-BYOK-Gemini']).toBe('gm')
  })

  it('preserves existing headers and returns a new object (no mutation)', () => {
    const headers = { Authorization: 'Bearer abc' }
    const keys: ByokKeys = { openai: 'sk-openai' }
    const out = withByokHeaders(headers, keys)
    expect(out.Authorization).toBe('Bearer abc')
    expect(out['X-BYOK-OpenAI']).toBe('sk-openai')
    // inputs untouched
    expect(headers).toEqual({ Authorization: 'Bearer abc' })
    expect(keys).toEqual({ openai: 'sk-openai' })
    expect(out).not.toBe(headers)
  })
})

describe('isByokActive', () => {
  it('is true only when all four providers have a non-empty key', () => {
    expect(isByokActive(fullKeys)).toBe(true)
  })

  it('is false at 3/4', () => {
    const partial: ByokKeys = { ...fullKeys }
    delete partial.deepgram
    expect(isByokActive(partial)).toBe(false)
  })

  it('is false when a provider key is only whitespace', () => {
    expect(isByokActive({ ...fullKeys, gemini: '   ' })).toBe(false)
  })

  it('is false for an empty map', () => {
    expect(isByokActive({})).toBe(false)
  })

  it('covers exactly the four canonical providers', () => {
    expect(BYOK_PROVIDERS).toEqual(['openai', 'anthropic', 'gemini', 'deepgram'])
    expect(Object.keys(BYOK_HEADER_NAMES).sort()).toEqual([...BYOK_PROVIDERS].sort())
  })
})

describe('byokFingerprint', () => {
  it('produces 64 lowercase hex chars', () => {
    const fp = byokFingerprint('sk-some-key')
    expect(fp).toMatch(/^[a-f0-9]{64}$/)
  })

  it('is deterministic and matches the known SHA-256 of the input', () => {
    // Reference: sha256("abc") = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
    expect(byokFingerprint('abc')).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    )
    expect(byokFingerprint('abc')).toBe(byokFingerprint('abc'))
  })

  it('is whitespace-insensitive (hashes the trimmed key, matching the wire value)', () => {
    const fp = byokFingerprint('  abc  ')
    expect(fp).toBe(byokFingerprint('abc'))
    expect(fp).toMatch(/^[a-f0-9]{64}$/)
  })
})
