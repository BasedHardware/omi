import { describe, it, expect } from 'vitest'
import {
  PROVIDERS,
  REGION_ORDER,
  getProvider,
  getModel,
  providersByRegion,
  localProviders,
  cloudProviders
} from './providers'

describe('provider registry', () => {
  it('has unique provider ids', () => {
    const ids = PROVIDERS.map((p) => p.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('ships the local providers (LM Studio + Ollama) with no key required', () => {
    const local = localProviders()
    expect(local.map((p) => p.id).sort()).toEqual(['lmstudio', 'ollama'])
    for (const p of local) expect(p.requiresApiKey).toBe(false)
  })

  it('every cloud provider needs a key except custom', () => {
    for (const p of cloudProviders()) {
      if (p.id === 'custom') continue
      expect(p.requiresApiKey).toBe(true)
    }
  })

  it('every provider has a valid region in the known order', () => {
    for (const p of PROVIDERS) expect(REGION_ORDER).toContain(p.region)
  })

  it('OpenAI-compatible providers expose a base URL (except custom which the user fills in)', () => {
    for (const p of PROVIDERS) {
      if (p.id === 'custom') continue
      expect(p.baseUrl).toMatch(/^https?:\/\//)
    }
  })

  it('groups providers by region and omits empty groups', () => {
    const groups = providersByRegion()
    expect(groups.length).toBeGreaterThan(0)
    expect(groups[0].region).toBe('local')
    for (const g of groups) expect(g.providers.length).toBeGreaterThan(0)
  })

  it('DeepSeek is text-only (no vision capability anywhere)', () => {
    const ds = getProvider('deepseek')
    expect(ds).toBeDefined()
    for (const m of ds!.models) expect(m.capabilities).not.toContain('vision')
  })

  it('Ollama Cloud models all carry the -cloud tag', () => {
    const oc = getProvider('ollama-cloud')
    expect(oc).toBeDefined()
    for (const m of oc!.models) expect(m.id.endsWith('-cloud')).toBe(true)
  })

  it('resolves a model by provider + id', () => {
    expect(getModel('anthropic', 'claude-opus-4-8')?.label).toBe('Claude Opus 4.8')
    expect(getModel('openai', 'does-not-exist')).toBeUndefined()
  })
})
