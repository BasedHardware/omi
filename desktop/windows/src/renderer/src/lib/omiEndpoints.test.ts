import { describe, expect, it } from 'vitest'

describe('managed desktop endpoints', () => {
  it('falls back to production endpoints without build-time environment values', async () => {
    const endpoints = await import('./omiEndpoints')
    expect(endpoints.OMI_API_BASE).toBe('https://api.omi.me')
    expect(endpoints.OMI_DESKTOP_API_BASE).toBe('https://desktop-backend-hhibjajaja-uc.a.run.app')
  })
})
