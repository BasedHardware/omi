import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./firebase', () => ({ auth: { currentUser: { uid: 'user-123' } } }))

describe('analytics capture contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.resetModules()
    vi.stubGlobal('window', {
      omi: { getAppVersion: vi.fn(async () => ({ name: 'Omi', version: '1.2.3' })) }
    })
  })

  it('sends PostHog identity and Windows enrichment inside properties', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
    const { trackEvent: trackWithContext } = await import('./analytics')

    trackWithContext('App Launched', { feature: 'voice' })

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
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
        platform: 'windows',
        app_version: '1.2.3'
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

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    expect(fetchMock.mock.calls[0][0]).toBe('https://us.i.posthog.com/i/v0/e/')
    vi.unstubAllEnvs()
  })

  it('preserves lifecycle order while app-version context resolves', async () => {
    let resolveVersion: ((value: { name: string; version: string }) => void) | undefined
    const getAppVersion = vi.fn(
      () =>
        new Promise<{ name: string; version: string }>((resolve) => {
          resolveVersion = resolve
        })
    )
    vi.stubGlobal('window', { omi: { getAppVersion } })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
    const { trackEvent: trackOrdered } = await import('./analytics')

    trackOrdered('Transcription Started')
    trackOrdered('Transcription Ended')
    expect(fetchMock).not.toHaveBeenCalled()

    await vi.waitFor(() => expect(getAppVersion).toHaveBeenCalledOnce())
    resolveVersion?.({ name: 'Omi', version: '1.2.3' })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls.map(([, init]) => JSON.parse(init?.body as string).event)).toEqual([
      'Transcription Started',
      'Transcription Ended'
    ])
    expect(getAppVersion).toHaveBeenCalledOnce()
  })
})
