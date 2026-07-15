// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  refreshByokKeys,
  withByokHeadersIfActive,
  isByokActiveCached
} from './byokKeys'
import type { ByokKeys } from '../../../shared/byok'

const FULL: ByokKeys = { openai: 'sk-o', anthropic: 'sk-a', gemini: 'gm', deepgram: 'dg' }

async function loadCache(keys: ByokKeys): Promise<void> {
  ;(window as unknown as { omi: unknown }).omi = { byokGetAll: vi.fn().mockResolvedValue(keys) }
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

  it('attaches nothing for a partial set (all-or-none)', async () => {
    await loadCache({ openai: 'sk-o', anthropic: 'sk-a', gemini: 'gm' })
    expect(isByokActiveCached()).toBe(false)
    const out = withByokHeadersIfActive({ Authorization: 'Bearer t' })
    expect(out).toEqual({ Authorization: 'Bearer t' })
    expect(out['X-BYOK-OpenAI']).toBeUndefined()
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
})
