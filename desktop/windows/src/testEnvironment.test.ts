import { expect, it } from 'vitest'

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
