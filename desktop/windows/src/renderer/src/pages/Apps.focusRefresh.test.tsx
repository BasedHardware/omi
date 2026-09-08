// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Drive the Apps page's window-focus revalidation. An app enabled out-of-band (the
// web app or another device) must appear on return to the window without an app
// relaunch — the enabled set + installed pool are otherwise only fetched on mount.
// The revalidation reuses load(), so we assert it re-fetches `/v1/apps/enabled` on
// focus, and that the auth / in-flight guards and unmount cleanup hold.

const getMock = vi.fn()
vi.mock('../lib/apiClient', () => ({ omiApi: { get: (...a: unknown[]) => getMock(...a) } }))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

// Signed-in by default; a test flips this to null to exercise the auth guard.
const firebaseMock = { auth: { currentUser: { uid: 'u1' } as { uid: string } | null } }
vi.mock('../lib/firebase', () => firebaseMock)

// Resolve every catalog endpoint with empty data. A never-resolving variant (below)
// keeps the mount load in flight so the loading guard can be exercised.
function stubEndpoints(): void {
  getMock.mockImplementation((url: string) => {
    if (url === '/v1/apps') return Promise.resolve({ data: [] })
    if (url === '/v1/apps/enabled') return Promise.resolve({ data: [] })
    return Promise.resolve({ data: { groups: [] } }) // /v2/apps
  })
}

const enabledCalls = (): number =>
  getMock.mock.calls.filter((c) => c[0] === '/v1/apps/enabled').length

beforeEach(() => {
  getMock.mockReset()
  localStorage.clear()
  // A seeded snapshot makes the page hydrate cache-first (loading starts false), so
  // the mount load resolves without a spinner and a focus fetch is not gated by the
  // loading guard.
  localStorage.setItem('omi.lastSignedInUid', 'u1')
  localStorage.setItem(
    'omi.cache.apps.u1',
    JSON.stringify({ sections: [], allApps: [], installedPool: [], enabled: [] })
  )
  firebaseMock.auth.currentUser = { uid: 'u1' }
})
afterEach(() => {
  cleanup()
  vi.resetModules()
})

async function renderApps(): Promise<void> {
  const { Apps } = await import('./Apps')
  render(
    <MemoryRouter>
      <Apps />
    </MemoryRouter>
  )
}

describe('Apps — revalidates on window focus', () => {
  it('re-fetches the enabled set when the window regains focus', async () => {
    stubEndpoints()
    await renderApps()
    // Mount load runs once.
    await waitFor(() => expect(enabledCalls()).toBe(1))

    window.dispatchEvent(new Event('focus'))
    await waitFor(() => expect(enabledCalls()).toBe(2))
  })

  it('does not revalidate while a load is still in flight (loading guard)', async () => {
    // No snapshot → loading starts true and the mount fetch never resolves, so the
    // page stays in its loading state and the focus handler must skip.
    localStorage.removeItem('omi.cache.apps.u1')
    getMock.mockImplementation(() => new Promise(() => {}))
    await renderApps()
    await waitFor(() => expect(enabledCalls()).toBe(1)) // the in-flight mount load

    window.dispatchEvent(new Event('focus'))
    // No additional fetch — the loading guard held.
    await new Promise((r) => setTimeout(r, 20))
    expect(enabledCalls()).toBe(1)
  })

  it('does not revalidate when signed out (auth guard)', async () => {
    stubEndpoints()
    await renderApps()
    await waitFor(() => expect(enabledCalls()).toBe(1))

    firebaseMock.auth.currentUser = null
    window.dispatchEvent(new Event('focus'))
    await new Promise((r) => setTimeout(r, 20))
    expect(enabledCalls()).toBe(1)
  })

  it('removes the focus listener on unmount', async () => {
    stubEndpoints()
    await renderApps()
    await waitFor(() => expect(enabledCalls()).toBe(1))

    cleanup()
    window.dispatchEvent(new Event('focus'))
    await new Promise((r) => setTimeout(r, 20))
    expect(enabledCalls()).toBe(1)
  })
})
