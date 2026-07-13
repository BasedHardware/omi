// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Tasks Major #1 (pagination): the page fetched with a hard `limit: 300` and
// never looked at `has_more`, so a user with more than 300 action items lost
// everything past the cap. Fix: page at 100 following `has_more` until it's
// false (backend/routers/action_items.py get_action_items returns has_more).
//
// Tasks Major #2 (staleness): the page cached items at module scope and only
// ever fetched once per app session (a `cache.loaded` guard skipped every
// later mount), with no window-focus refresh — unlike the Home task widget.
// Fix: refetch on every mount (stale-while-revalidate) and on window focus.

const getMock = vi.fn()
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: (...args: unknown[]) => getMock(...args) }
}))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

function actionItemsPage(ids: string[], hasMore: boolean): { data: unknown } {
  return {
    data: {
      action_items: ids.map((id) => ({ id, description: id, completed: false })),
      has_more: hasMore
    }
  }
}

beforeEach(() => {
  getMock.mockReset()
})

afterEach(() => {
  cleanup()
  vi.resetModules()
})

describe('Tasks — pagination (has_more, page size 100)', () => {
  it('follows has_more across pages instead of stopping at one 300-cap request', async () => {
    const page1 = Array.from({ length: 100 }, (_, i) => `a${i}`)
    const page2 = Array.from({ length: 100 }, (_, i) => `b${i}`)
    const page3 = Array.from({ length: 50 }, (_, i) => `c${i}`)
    getMock.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/v1/conversations') return Promise.resolve({ data: [] })
      const offset = (config?.params?.offset as number) ?? 0
      if (offset === 0) return Promise.resolve(actionItemsPage(page1, true))
      if (offset === 100) return Promise.resolve(actionItemsPage(page2, true))
      if (offset === 200) return Promise.resolve(actionItemsPage(page3, false))
      throw new Error(`unexpected offset ${offset}`)
    })

    const { Tasks } = await import('./Tasks')
    render(
      <MemoryRouter>
        <Tasks />
      </MemoryRouter>
    )

    await waitFor(() =>
      expect(getMock.mock.calls.filter((c) => c[0] === '/v1/action-items')).toHaveLength(3)
    )

    // Every page-1 request must ask for 100, never the old hard 300.
    const actionItemCalls = getMock.mock.calls.filter((c) => c[0] === '/v1/action-items')
    for (const call of actionItemCalls) {
      expect((call[1] as { params: { limit: number } }).params.limit).toBe(100)
    }

    // All 250 items across 3 pages surfaced, not just the first page.
    await waitFor(() => expect(document.body.textContent).toContain('250 open'))
  })
})

describe('Tasks — freshness on mount + window focus', () => {
  it('refetches on every mount, not only once per session', async () => {
    getMock.mockImplementation((url: string) => {
      if (url === '/v1/conversations') return Promise.resolve({ data: [] })
      return Promise.resolve(actionItemsPage([], false))
    })

    const { Tasks } = await import('./Tasks')
    const first = render(
      <MemoryRouter>
        <Tasks />
      </MemoryRouter>
    )
    await waitFor(() => expect(getMock).toHaveBeenCalled())
    const callsAfterFirstMount = getMock.mock.calls.filter(
      (c) => c[0] === '/v1/action-items'
    ).length
    expect(callsAfterFirstMount).toBeGreaterThan(0)
    first.unmount()

    getMock.mockClear()
    render(
      <MemoryRouter>
        <Tasks />
      </MemoryRouter>
    )
    // A second, later mount (simulating a revisit) must issue its own fetch —
    // the old module-level `cache.loaded` guard made this a no-op after the
    // first-ever mount of the session.
    await waitFor(() =>
      expect(getMock.mock.calls.filter((c) => c[0] === '/v1/action-items').length).toBeGreaterThan(
        0
      )
    )
  })

  it('refetches when the window regains focus', async () => {
    getMock.mockImplementation((url: string) => {
      if (url === '/v1/conversations') return Promise.resolve({ data: [] })
      return Promise.resolve(actionItemsPage([], false))
    })

    const { Tasks } = await import('./Tasks')
    render(
      <MemoryRouter>
        <Tasks />
      </MemoryRouter>
    )
    await waitFor(() => expect(getMock).toHaveBeenCalled())
    getMock.mockClear()

    window.dispatchEvent(new Event('focus'))

    await waitFor(() =>
      expect(getMock.mock.calls.filter((c) => c[0] === '/v1/action-items').length).toBeGreaterThan(
        0
      )
    )
  })
})
