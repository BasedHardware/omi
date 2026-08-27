// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  refreshByokKeys,
  resetByokKeys,
  withByokHeadersIfActive,
  isByokActiveCached,
  hasTranscriptionByokCached,
  llmByokValidatedCached
} from './byokKeys'
import type { ByokKeys, ByokProvider } from '../../../shared/byok'

const FULL: ByokKeys = { openai: 'sk-o', anthropic: 'sk-a', gemini: 'gm', deepgram: 'dg' }

async function loadCache(keys: ByokKeys, validated: ByokProvider[] = []): Promise<void> {
  ;(window as unknown as { omi: unknown }).omi = {
    byokGetAll: vi.fn().mockResolvedValue(keys),
    byokValidatedProviders: vi.fn().mockResolvedValue(validated)
  }
  await refreshByokKeys()
}

describe('withByokHeadersIfActive', () => {
  beforeEach(async () => {
    await loadCache({}) // reset cache to empty between tests
  })

  it('attaches all four X-BYOK-* headers when the cached set is complete', async () => {
    await loadCache(FULL)
    expect(isByokActiveCached()).toBe(true)
    const out = withByokHeadersIfActive({ Authorization: 'Bearer t' })
    expect(out).toEqual({
      Authorization: 'Bearer t',
      'X-BYOK-OpenAI': 'sk-o',
      'X-BYOK-Anthropic': 'sk-a',
      'X-BYOK-Gemini': 'gm',
      'X-BYOK-Deepgram': 'dg'
    })
  })

  it('attaches configured LLM keys for a partial set', async () => {
    await loadCache({ openai: 'sk-o', anthropic: 'sk-a', gemini: 'gm' })
    expect(isByokActiveCached()).toBe(true)
    const out = withByokHeadersIfActive({ Authorization: 'Bearer t' })
    expect(out).toEqual({
      Authorization: 'Bearer t',
      'X-BYOK-OpenAI': 'sk-o',
      'X-BYOK-Anthropic': 'sk-a',
      'X-BYOK-Gemini': 'gm'
    })
  })

  it('stops attaching after the keys are cleared (refresh on byok:changed)', async () => {
    await loadCache(FULL)
    expect(withByokHeadersIfActive({})['X-BYOK-OpenAI']).toBe('sk-o')
    await loadCache({}) // user cleared all keys → cache reloads empty
    expect(isByokActiveCached()).toBe(false)
    expect(withByokHeadersIfActive({})).toEqual({})
  })

  it('does not mutate the input headers object', async () => {
    await loadCache(FULL)
    const input = { Authorization: 'Bearer t' }
    const out = withByokHeadersIfActive(input)
    expect(input).toEqual({ Authorization: 'Bearer t' })
    expect(out).not.toBe(input)
  })

  it('resetByokKeys empties the cache synchronously so no X-BYOK is attached after sign-out', async () => {
    await loadCache(FULL, ['deepgram'])
    expect(isByokActiveCached()).toBe(true)
    expect(hasTranscriptionByokCached()).toBe(true)
    resetByokKeys() // sign-out teardown
    expect(isByokActiveCached()).toBe(false)
    expect(hasTranscriptionByokCached()).toBe(false)
    expect(withByokHeadersIfActive({ Authorization: 'Bearer t' })).toEqual({
      Authorization: 'Bearer t'
    })
  })
})

describe('validated capability cache', () => {
  beforeEach(async () => {
    await loadCache({}) // reset cache to empty between tests
  })

  it('suppresses transcription quota only on validated Deepgram enrollment, not key presence', async () => {
    // Configured-but-rejected Deepgram: key present in the store, evidence absent.
    await loadCache(FULL, [])
    expect(hasTranscriptionByokCached()).toBe(false)

    // Backend accepted the Deepgram fingerprint.
    await loadCache(FULL, ['openai', 'deepgram'])
    expect(hasTranscriptionByokCached()).toBe(true)

    // Key rotated after enrollment → no longer validated until re-enrollment.
    await loadCache(FULL, ['openai'])
    expect(hasTranscriptionByokCached()).toBe(false)
  })

  it('reports LLM activation only from validated providers', async () => {
    await loadCache(FULL, ['deepgram']) // Deepgram-only never unlocks the LLM plan
    expect(llmByokValidatedCached()).toBe(false)

    await loadCache(FULL, ['gemini'])
    expect(llmByokValidatedCached()).toBe(true)
  })
})
