export type WindowsUpdateChannel = 'stable' | 'beta'
type FetchUpdateFeed = (input: string, init?: RequestInit) => Promise<Response>

type WindowsUpdateFeedResponse = {
  requested_channel?: unknown
  served_channel?: unknown
  feed_url?: unknown
}

const WINDOWS_FEED_PATH =
  /^\/BasedHardware\/omi\/releases\/download\/v?\d+\.\d+(?:\.\d+)?(?:\+\d+)?-windows\/$/

function parseFeedResponse(payload: unknown, requestedChannel: WindowsUpdateChannel): string {
  if (typeof payload !== 'object' || payload === null) {
    throw new Error('Windows update feed response is not an object')
  }
  const response = payload as WindowsUpdateFeedResponse
  if (response.requested_channel !== requestedChannel) {
    throw new Error('Windows update feed response does not match the requested channel')
  }
  if (response.served_channel !== 'stable' && response.served_channel !== 'beta') {
    throw new Error('Windows update feed response has an invalid served channel')
  }
  if (requestedChannel === 'stable' && response.served_channel !== 'stable') {
    throw new Error('Stable Windows updates cannot fall through to beta')
  }
  if (typeof response.feed_url !== 'string') {
    throw new Error('Windows update feed response is missing feed_url')
  }

  let feedUrl: URL
  try {
    feedUrl = new URL(response.feed_url)
  } catch {
    throw new Error('Windows update feed response contains an invalid feed_url')
  }
  if (
    feedUrl.origin !== 'https://github.com' ||
    feedUrl.username !== '' ||
    feedUrl.password !== '' ||
    feedUrl.search !== '' ||
    feedUrl.hash !== '' ||
    !WINDOWS_FEED_PATH.test(feedUrl.pathname)
  ) {
    throw new Error('Windows update feed response contains an untrusted feed_url')
  }
  return feedUrl.toString()
}

export async function resolveWindowsUpdateFeedUrl(
  apiBase: string,
  channel: WindowsUpdateChannel,
  fetchImpl: FetchUpdateFeed = fetch
): Promise<string> {
  const endpoint = new URL(`${apiBase.replace(/\/+$/, '')}/v2/desktop/update-feed/windows`)
  endpoint.searchParams.set('channel', channel)
  const response = await fetchImpl(endpoint.toString(), {
    headers: { Accept: 'application/json' },
    cache: 'no-store'
  })
  if (!response.ok) {
    throw new Error(`Windows update feed resolution failed (${response.status})`)
  }
  return parseFeedResponse(await response.json(), channel)
}

type ResolveFeed = (channel: WindowsUpdateChannel) => Promise<string>
type ApplyFeed = (feedUrl: string) => void

/**
 * Resolves an immutable feed before every update check. Concurrent checks share
 * one resolution request, and a response for a channel the user just left can
 * never overwrite the newly selected channel.
 */
export class WindowsUpdateFeedSelector {
  private selectedChannel: WindowsUpdateChannel
  private configuredChannel: WindowsUpdateChannel | null = null
  private configuredUrl: string | null = null
  private readonly inFlight = new Map<WindowsUpdateChannel, Promise<string>>()

  constructor(
    initialChannel: WindowsUpdateChannel,
    private readonly resolveFeed: ResolveFeed,
    private readonly applyFeed: ApplyFeed
  ) {
    this.selectedChannel = initialChannel
  }

  select(channel: WindowsUpdateChannel): void {
    this.selectedChannel = channel
  }

  async prepareSelected(): Promise<void> {
    while (true) {
      const channel = this.selectedChannel
      const feedUrl = await this.resolveOnce(channel)

      if (this.selectedChannel !== channel) {
        if (this.configuredChannel === this.selectedChannel) return
        continue
      }
      if (this.configuredChannel !== channel || this.configuredUrl !== feedUrl) {
        this.applyFeed(feedUrl)
        this.configuredChannel = channel
        this.configuredUrl = feedUrl
      }
      return
    }
  }

  private async resolveOnce(channel: WindowsUpdateChannel): Promise<string> {
    const existing = this.inFlight.get(channel)
    if (existing) return existing

    const request = this.resolveFeed(channel)
    this.inFlight.set(channel, request)
    try {
      return await request
    } finally {
      if (this.inFlight.get(channel) === request) this.inFlight.delete(channel)
    }
  }
}
