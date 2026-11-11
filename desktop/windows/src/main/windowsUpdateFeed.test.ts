import { describe, expect, it, vi } from 'vitest'
import {
  resolveWindowsUpdateFeedUrl,
  WindowsUpdateFeedSelector,
  type WindowsUpdateChannel
} from './windowsUpdateFeed'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  })
}

function deferred<T>(): {
  promise: Promise<T>
  resolve: (value: T) => void
} {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('resolveWindowsUpdateFeedUrl', () => {
  it('requests the selected channel and accepts only an immutable Windows release feed', async () => {
    const fetchImpl = vi.fn(async (_input: string | URL | Request, _init?: RequestInit) =>
      jsonResponse({
        requested_channel: 'beta',
        served_channel: 'stable',
        version: '1.0.1',
        feed_url: 'https://github.com/BasedHardware/omi/releases/download/v1.0.1-windows/'
      })
    )

    await expect(
      resolveWindowsUpdateFeedUrl('https://api.omi.me/', 'beta', fetchImpl as typeof fetch)
    ).resolves.toBe('https://github.com/BasedHardware/omi/releases/download/v1.0.1-windows/')
    expect(String(fetchImpl.mock.calls[0][0])).toBe(
      'https://api.omi.me/v2/desktop/update-feed/windows?channel=beta'
    )
    expect(fetchImpl.mock.calls[0][1]).toMatchObject({
      headers: { Accept: 'application/json' },
      cache: 'no-store'
    })
  })

  it('rejects stable-to-beta, wrong-platform, and untrusted feeds', async () => {
    const betaForStable = vi.fn(async () =>
      jsonResponse({
        requested_channel: 'stable',
        served_channel: 'beta',
        feed_url: 'https://github.com/BasedHardware/omi/releases/download/v1.0.19-windows/'
      })
    ) as typeof fetch
    await expect(
      resolveWindowsUpdateFeedUrl('https://api.omi.me', 'stable', betaForStable)
    ).rejects.toThrow('Stable Windows updates cannot fall through to beta')

    const macFeed = vi.fn(async () =>
      jsonResponse({
        requested_channel: 'stable',
        served_channel: 'stable',
        feed_url: 'https://github.com/BasedHardware/omi/releases/download/v0.12.123+12123-macos/'
      })
    ) as typeof fetch
    await expect(
      resolveWindowsUpdateFeedUrl('https://api.omi.me', 'stable', macFeed)
    ).rejects.toThrow('untrusted feed_url')

    const untrusted = vi.fn(async () =>
      jsonResponse({
        requested_channel: 'beta',
        served_channel: 'beta',
        feed_url: 'https://example.com/v1.0.19-windows/'
      })
    ) as typeof fetch
    await expect(
      resolveWindowsUpdateFeedUrl('https://api.omi.me', 'beta', untrusted)
    ).rejects.toThrow('untrusted feed_url')
  })

  it('surfaces resolution failures without reading an error body', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ detail: 'internal' }, 503)) as typeof fetch
    await expect(
      resolveWindowsUpdateFeedUrl('https://api.omi.me', 'stable', fetchImpl)
    ).rejects.toThrow('Windows update feed resolution failed (503)')
  })
})

describe('WindowsUpdateFeedSelector', () => {
  it('refreshes before later checks but does not reapply an unchanged feed', async () => {
    const resolveFeed = vi.fn(async () => {
      return 'https://github.com/BasedHardware/omi/releases/download/v1.0.1-windows/'
    })
    const applyFeed = vi.fn()
    const selector = new WindowsUpdateFeedSelector('stable', resolveFeed, applyFeed)

    await selector.prepareSelected()
    await selector.prepareSelected()

    expect(resolveFeed).toHaveBeenCalledTimes(2)
    expect(applyFeed).toHaveBeenCalledTimes(1)
  })

  it('never applies a stale channel response after a live channel switch', async () => {
    const stable = deferred<string>()
    const beta = deferred<string>()
    const resolveFeed = vi.fn((channel: WindowsUpdateChannel) => {
      return channel === 'stable' ? stable.promise : beta.promise
    })
    const applyFeed = vi.fn()
    const selector = new WindowsUpdateFeedSelector('stable', resolveFeed, applyFeed)

    const staleCheck = selector.prepareSelected()
    selector.select('beta')
    const betaCheck = selector.prepareSelected()

    beta.resolve('https://github.com/BasedHardware/omi/releases/download/v1.0.19-windows/')
    await betaCheck
    stable.resolve('https://github.com/BasedHardware/omi/releases/download/v1.0.1-windows/')
    await staleCheck

    expect(applyFeed).toHaveBeenCalledTimes(1)
    expect(applyFeed).toHaveBeenCalledWith(
      'https://github.com/BasedHardware/omi/releases/download/v1.0.19-windows/'
    )
  })
})
