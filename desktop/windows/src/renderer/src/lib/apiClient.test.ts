// responseErrorHandler 401 path: force-refresh once + retry, else route to
// reauth. ./firebase and ./authSession are mocked so no real Firebase SDK loads.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type RefreshOutcome = { status: 'ok'; token: string } | { status: 'dead' } | { status: 'transient' }

const h = vi.hoisted(() => ({
  refreshIdToken: vi.fn<() => Promise<RefreshOutcome>>(),
  forceReauth: vi.fn(async () => {})
}))

vi.mock('./firebase', () => ({ auth: { currentUser: null } }))
vi.mock('./authSession', () => ({
  refreshIdToken: h.refreshIdToken,
  forceReauth: h.forceReauth
}))

import { responseErrorHandler } from './apiClient'

// A stand-in axios instance: records the retried request and echoes success.
function fakeClient() {
  const calls: Array<{ headers: Record<string, unknown> }> = []
  const client = vi.fn(async (config: { headers: Record<string, unknown> }) => {
    calls.push(config)
    return { status: 200, data: 'ok', config }
  })
  return { client: client as unknown as never, calls }
}

type ErrorArg = Parameters<typeof responseErrorHandler>[1]

function err401(extra: Record<string, unknown> = {}): ErrorArg {
  return { config: { headers: {}, ...extra }, response: { status: 401 } } as unknown as ErrorArg
}

beforeEach(() => {
  h.refreshIdToken.mockReset()
  h.forceReauth.mockClear()
})
afterEach(() => vi.restoreAllMocks())

describe('responseErrorHandler — 401 handling', () => {
  it('force-refreshes once and retries with the fresh token', async () => {
    h.refreshIdToken.mockResolvedValue({ status: 'ok', token: 'fresh-token' })
    const { client, calls } = fakeClient()
    const error = err401()

    const res = await responseErrorHandler(client, error)

    expect(h.refreshIdToken).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(1)
    expect(calls[0].headers.Authorization).toBe('Bearer fresh-token')
    expect((res as { data: string }).data).toBe('ok')
    expect(h.forceReauth).not.toHaveBeenCalled()
  })

  it('routes to reauth when the refresh is dead (permanent failure / no user)', async () => {
    h.refreshIdToken.mockResolvedValue({ status: 'dead' })
    const { client, calls } = fakeClient()

    await expect(responseErrorHandler(client, err401())).rejects.toBeDefined()

    expect(h.forceReauth).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(0) // no retry
  })

  it('does NOT reauth on a TRANSIENT refresh failure (network blip) — keeps the session', async () => {
    h.refreshIdToken.mockResolvedValue({ status: 'transient' })
    const { client, calls } = fakeClient()

    await expect(responseErrorHandler(client, err401())).rejects.toBeDefined()

    expect(h.forceReauth).not.toHaveBeenCalled() // the whole point — no sign-out on a blip
    expect(calls).toHaveLength(0) // no retry; caller retries later
  })

  it('routes to reauth (no second refresh) when the refreshed token is ALSO rejected', async () => {
    h.refreshIdToken.mockResolvedValue({ status: 'ok', token: 'fresh-token' })
    const { client } = fakeClient()
    // First pass marks __reauthTried + retries; the retried request 401s again →
    // same config comes back through the handler.
    const error = err401()
    await responseErrorHandler(client, error)
    h.refreshIdToken.mockClear()

    await expect(responseErrorHandler(client, error)).rejects.toBeDefined()

    expect(h.refreshIdToken).not.toHaveBeenCalled() // already tried once
    expect(h.forceReauth).toHaveBeenCalledTimes(1)
  })

  it('__sessionPreserving refreshes + retries but never forces reauth on death', async () => {
    h.refreshIdToken.mockResolvedValue({ status: 'dead' })
    const { client } = fakeClient()

    await expect(
      responseErrorHandler(client, err401({ __sessionPreserving: true }))
    ).rejects.toBeDefined()

    expect(h.refreshIdToken).toHaveBeenCalledTimes(1) // still attempts the refresh
    expect(h.forceReauth).not.toHaveBeenCalled() // background poller: no sign-in kick
  })

  it('does not touch a 401 flagged __noRetry', async () => {
    const { client } = fakeClient()
    await expect(responseErrorHandler(client, err401({ __noRetry: true }))).rejects.toBeDefined()
    expect(h.refreshIdToken).not.toHaveBeenCalled()
    expect(h.forceReauth).not.toHaveBeenCalled()
  })

  it('passes a non-retryable status (404) straight through as a rejection', async () => {
    const { client, calls } = fakeClient()
    await expect(
      responseErrorHandler(client, {
        config: { headers: {} },
        response: { status: 404 }
      } as unknown as ErrorArg)
    ).rejects.toBeDefined()
    expect(calls).toHaveLength(0)
    expect(h.forceReauth).not.toHaveBeenCalled()
  })
})
