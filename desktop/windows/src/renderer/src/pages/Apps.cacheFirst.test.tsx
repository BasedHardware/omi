// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, waitFor, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// The Apps page hydrates from a per-uid cold-start snapshot and revalidates. The
// error render is a FULL-PAGE replacement (not a banner), so a failed revalidation
// must NOT swap the just-hydrated cached grid for "Couldn't load apps" — it must
// keep the grid on screen. A true load failure with NO cache still shows the error.

const getMock = vi.fn()
vi.mock('../lib/apiClient', () => ({ omiApi: { get: (...a: unknown[]) => getMock(...a) } }))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

const app = (id: string): unknown => ({ id, name: id, category: 'other' })

beforeEach(() => {
  getMock.mockReset()
  localStorage.clear()
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

describe('Apps — cache-first failure path', () => {
  it('keeps the cached grid and suppresses the full-page error on a failed revalidation', async () => {
    localStorage.setItem('omi.lastSignedInUid', 'u1')
    localStorage.setItem(
      'omi.cache.apps.u1',
      JSON.stringify({
        sections: [],
        allApps: [app('CACHED')],
        installedPool: [app('CACHED')],
        enabled: []
      })
    )
    // Every fetch fails (offline cold start). /v2/apps has no .catch, so load() rejects.
    getMock.mockRejectedValue(new Error('offline'))
    await renderApps()

    // The fetch is attempted and fails...
    await waitFor(() => expect(getMock).toHaveBeenCalled())
    // ...but the grid (its search box) stays on screen — no full-page error swap.
    await waitFor(() => expect(screen.queryByPlaceholderText('Search apps…')).not.toBeNull())
    expect(screen.queryByText('Couldn’t load apps')).toBeNull()
  })

  it('shows the full-page error when a load fails with NO cached data', async () => {
    localStorage.setItem('omi.lastSignedInUid', 'u1') // no snapshot
    getMock.mockRejectedValue(new Error('offline'))
    await renderApps()

    await waitFor(() => expect(screen.queryByText('Couldn’t load apps')).not.toBeNull())
    // The grid is not shown when there's genuinely nothing cached.
    expect(screen.queryByPlaceholderText('Search apps…')).toBeNull()
  })
})
