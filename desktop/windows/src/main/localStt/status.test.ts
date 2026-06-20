import { describe, expect, it, vi } from 'vitest'
import { getLocalSttStatus, localParakeetBaseUrl } from './status'

function okFetch(): typeof fetch {
  return vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ status: 'healthy' }), { status: 200 }))
}

describe('local STT status', () => {
  it('uses the configured local Parakeet URL without trailing slashes', () => {
    expect(localParakeetBaseUrl({ OMI_LOCAL_PARAKEET_URL: 'http://127.0.0.1:9000/' })).toBe(
      'http://127.0.0.1:9000'
    )
  })

  it('is available when health passes and NVIDIA is detected on Windows', async () => {
    const status = await getLocalSttStatus({
      env: { OMI_LOCAL_PARAKEET_URL: 'http://127.0.0.1:9000' },
      platform: 'win32',
      fetchImpl: okFetch(),
      detectNvidiaGpu: async () => true,
      now: () => 123
    })

    expect(status).toMatchObject({
      configuredUrl: 'http://127.0.0.1:9000',
      healthy: true,
      available: true,
      nvidiaAvailable: true,
      checkedAt: 123
    })
  })

  it('blocks auto-local on Windows when NVIDIA is missing', async () => {
    const status = await getLocalSttStatus({
      env: {},
      platform: 'win32',
      fetchImpl: okFetch(),
      detectNvidiaGpu: async () => false
    })

    expect(status.available).toBe(false)
    expect(status.healthy).toBe(true)
    expect(status.reason).toBe('NVIDIA GPU not detected')
  })

  it('fails closed when health does not pass', async () => {
    const status = await getLocalSttStatus({
      env: {},
      platform: 'win32',
      fetchImpl: vi.fn().mockResolvedValue(new Response('', { status: 503 })),
      detectNvidiaGpu: async () => true
    })

    expect(status.available).toBe(false)
    expect(status.healthy).toBe(false)
    expect(status.reason).toContain('Parakeet runtime is not healthy')
  })
})
