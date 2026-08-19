import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const analyticsAuth = vi.hoisted(() => ({
  currentUser: { uid: 'user-123' } as { uid: string } | null
}))
const getWindowsDeviceIdHash = vi.hoisted(() => vi.fn(async () => 'a1b2c3d4'))

vi.mock('./firebase', () => ({ auth: analyticsAuth }))
vi.mock('./clientDevice', () => ({ getWindowsDeviceIdHash }))

describe('analytics capture contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.resetModules()
    analyticsAuth.currentUser = { uid: 'user-123' }
    getWindowsDeviceIdHash.mockReset().mockResolvedValue('a1b2c3d4')
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

  it('uses a stable, hashed install identity before sign-in', async () => {
    analyticsAuth.currentUser = null
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
    const { trackEvent: trackAnonymous } = await import('./analytics')

    trackAnonymous('Sign In Started')

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const body = JSON.parse(fetchMock.mock.calls[0][1]?.body as string)
    expect(body.distinct_id).toBe('windows_a1b2c3d4')
  })

  it('never collapses device-hash failures into one shared anonymous person', async () => {
    analyticsAuth.currentUser = null
    getWindowsDeviceIdHash.mockRejectedValueOnce(new Error('unavailable'))
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
    const { trackEvent: trackAnonymous } = await import('./analytics')

    trackAnonymous('Sign In Started')

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const body = JSON.parse(fetchMock.mock.calls[0][1]?.body as string)
    expect(body.distinct_id).toMatch(/^windows_[0-9a-f-]{36}$/)
    expect(body.distinct_id).not.toBe('anonymous')
  })

  it('rotates the anonymous identity after sign-out on a shared installation', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
    const analytics = await import('./analytics')

    analytics.trackSignedOut('user-123')
    analyticsAuth.currentUser = null
    analytics.trackEvent('Sign In Started')

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(init?.body as string))
    expect(bodies[0].distinct_id).toBe('user-123')
    expect(bodies[1].distinct_id).toMatch(/^windows_[0-9a-f-]{36}$/)
    expect(bodies[1].distinct_id).not.toBe('windows_a1b2c3d4')
  })

  it('builds bounded macOS-compatible product payloads without raw content', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
    const analytics = await import('./analytics')

    analytics.trackHowDidYouHear('private free-form source')
    analytics.trackOnboardingCompleted()
    analytics.trackOnboardingStepCompleted(7, 'Microphone', true)
    analytics.trackSignInStarted('apple')
    analytics.trackSignInCompleted('apple')
    analytics.trackSignInFailed(
      'google',
      new Error('Token exchange failed (500): secret.person@example.com')
    )
    analytics.trackSignedOut('signed-out-user')
    analytics.trackPermissionRequested('microphone')
    analytics.trackPermissionGranted('screen_capture_opt_in')
    analytics.trackPermissionDenied('automation_consent')
    analytics.trackPermissionSkipped('microphone')
    analytics.trackMemoryCreated(12.9)
    analytics.trackChatMessageSent({
      messageLength: -10,
      hasSelectedAppContext: true,
      source: 'desktop_voice'
    })
    analytics.trackPageViewed('conversation-detail')
    analytics.trackAppEnabled('APP With Spaces', 'Chat Assistants')
    analytics.trackAppDisabled('APP With Spaces', 'Chat Assistants')
    analytics.trackAppDetailViewed('APP With Spaces', 'Chat Assistants')

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(18))
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(init?.body as string))
    const byEvent = Object.fromEntries(bodies.map((body) => [body.event, body]))
    expect(byEvent.$identify).toMatchObject({
      distinct_id: 'user-123',
      properties: { $anon_distinct_id: 'windows_a1b2c3d4' }
    })
    expect(bodies.findIndex((body) => body.event === '$identify')).toBeLessThan(
      bodies.findIndex((body) => body.event === 'Sign In Completed')
    )
    expect(byEvent['Onboarding How Did You Hear'].properties).toMatchObject({
      source: 'unknown',
      is_referral: false
    })
    expect(byEvent['Onboarding Step Microphone_Skipped Completed'].properties.step).toBe(7)
    expect(byEvent['Sign In Failed'].properties).toMatchObject({
      provider: 'google',
      error: 'token_exchange_failed',
      error_class: 'token_exchange_failed'
    })
    expect(byEvent['Signed Out'].distinct_id).toBe('signed-out-user')
    expect(byEvent['Permission Granted'].properties.permission).toBe('screen_capture_opt_in')
    expect(byEvent['Memory Created'].properties).toMatchObject({
      source: 'desktop',
      duration_seconds: 12
    })
    expect(byEvent['Chat Message Sent'].properties).toMatchObject({
      message_length: 0,
      has_selected_app_context: true,
      source: 'desktop_voice'
    })
    expect(byEvent['Page Viewed'].properties.page).toBe('conversation-detail')
    expect(byEvent['App Enabled'].properties).toMatchObject({
      app_id: 'app_with_spaces',
      category: 'chat_assistants'
    })
    expect(JSON.stringify(bodies)).not.toContain('secret.person@example.com')
    expect(JSON.stringify(bodies)).not.toContain('private free-form source')
  })

  it('swallows property serialization failures', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
    const { trackEvent: trackUnsafe } = await import('./analytics')

    trackUnsafe('Unsafe input', { value: 1n })

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(fetchMock).not.toHaveBeenCalled()
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
