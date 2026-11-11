import { afterEach, expect, it, vi } from 'vitest'

it('pins both API clients to the inert loopback endpoint regardless of .env', () => {
  for (const base of [
    import.meta.env.VITE_OMI_API_BASE,
    import.meta.env.VITE_OMI_DESKTOP_API_BASE
  ]) {
    const url = new URL(base)
    expect(url.origin).toBe('http://127.0.0.1:9')
    expect(url.hostname).not.toMatch(/(^|\.)omi\.me$/i)
  }
})

afterEach(() => {
  vi.unstubAllEnvs()
})

it.each(['0', '', 'true', '1'])('only OMI_E2E=1 selects live configuration (%s)', async (flag) => {
  vi.stubEnv('OMI_E2E', flag)
  vi.stubEnv('VITE_OMI_API_BASE', 'https://sentinel.invalid')
  vi.stubEnv('VITE_OMI_DESKTOP_API_BASE', 'https://desktop-sentinel.invalid')
  vi.resetModules()
  const { default: config } = await import('../vitest.config')
  if (flag === '1') {
    expect(config.test?.setupFiles).toEqual([])
    expect(config.test?.env).toEqual({})
    expect(process.env.VITE_OMI_API_BASE).toBe('https://sentinel.invalid')
    expect(process.env.VITE_OMI_DESKTOP_API_BASE).toBe('https://desktop-sentinel.invalid')
  } else {
    expect(config.test?.setupFiles).toHaveLength(1)
    expect(config.test?.env?.VITE_OMI_API_BASE).toBe('http://127.0.0.1:9')
    expect(config.test?.env?.VITE_FIREBASE_API_KEY).toBe('test-firebase-api-key')
    expect(process.env.VITE_OMI_API_BASE).toBe('http://127.0.0.1:9')
  }
})
