import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./firebase', () => ({ auth: { currentUser: { uid: 'user-123' } } }))

import { trackEvent } from './analytics'

describe('analytics capture contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('sends PostHog identity and Windows enrichment inside properties', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())

    trackEvent('App Launched', { feature: 'voice' })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('https://us.i.posthog.com/i/v0/e/')
    expect(JSON.parse(init?.body as string)).toEqual({
      api_key: 'phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y',
      event: 'App Launched',
      distinct_id: 'user-123',
      properties: {
        feature: 'voice',
        $lib: 'omi-windows',
        $os: 'Windows',
        platform: 'windows'
      }
    })
  })

  it.each(['index.html', 'capture.html', 'glow.html', 'insight-toast.html'])(
    'allows PostHog capture from %s',
    (entry) => {
      const html = readFileSync(resolve(__dirname, '../../', entry), 'utf8')
      expect(html).toMatch(/connect-src[\s\S]*https:\/\/us\.i\.posthog\.com[\s\S]*;/)
    }
  )

  // A VITE_POSTHOG_HOST override used to be honoured here, which sent capture to
  // an origin the renderer CSP does not allow. Assert the runtime behaviour, not
  // the source text: a set override must not reach fetch.
  it('ignores a VITE_POSTHOG_HOST override and posts to the CSP-allowed origin', async () => {
    vi.stubEnv('VITE_POSTHOG_HOST', 'https://not-in-csp.example.com')
    vi.resetModules()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())

    const { trackEvent: trackWithOverride } = await import('./analytics')
    trackWithOverride('App Launched')

    expect(fetchMock.mock.calls[0][0]).toBe('https://us.i.posthog.com/i/v0/e/')
    vi.unstubAllEnvs()
  })
})
