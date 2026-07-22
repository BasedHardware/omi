// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, waitFor, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// PR1 (error surfacing): the app-enable/disable toggle used to swallow EVERY failure
// (backend 400 "setup not completed", 403 paid/private, network) into a console.error,
// flipping the row to "Installed" then silently reverting. This suite pins the fix:
// a failed enable/disable raises a real error toast, the row reverts to its prior
// state, and the button is never left stuck busy/disabled.

const getMock = vi.fn()
const postMock = vi.fn()
const toastMock = vi.fn()
vi.mock('../lib/apiClient', () => ({
  omiApi: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a)
  }
}))
vi.mock('../lib/toast', () => ({ toast: (...a: unknown[]) => toastMock(...a) }))

// A minimal catalog item; the grid only needs id/name/category to render a card.
const app = (id: string, name: string): unknown => ({ id, name, category: 'other' })

// Seed a per-uid cold-start snapshot so the grid paints a real card synchronously
// (default view renders `sections`, so the app must live inside a section). The
// revalidating load() still runs; we let it fail so the seeded grid stays on screen.
function seedGrid(): void {
  localStorage.setItem('omi.lastSignedInUid', 'u1')
  const section = {
    capabilityId: 'popular',
    title: 'Other',
    apps: [app('APP1', 'App One')],
    hasMore: false,
    total: 1,
    truncated: false
  }
  localStorage.setItem(
    'omi.cache.apps.u1',
    JSON.stringify({
      sections: [section],
      allApps: [app('APP1', 'App One')],
      installedPool: [app('APP1', 'App One')],
      enabled: []
    })
  )
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  toastMock.mockReset()
  localStorage.clear()
  // Cache-first: a failed revalidation keeps the seeded grid on screen (the card
  // under test), rather than swapping in the full-page "Couldn't load apps".
  getMock.mockRejectedValue(new Error('offline'))
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

// A rejection shaped like an axios error carrying a FastAPI `detail` body.
function httpError(status: number, detail: string): unknown {
  return { response: { status, data: { detail } } }
}

describe('Apps — enable/disable error surfacing (PR1)', () => {
  it('shows an error toast, reverts the row, and does not leave the button stuck busy when enable fails', async () => {
    seedGrid()
    postMock.mockRejectedValue(httpError(403, 'You are not authorized to enable this app'))
    await renderApps()

    // Exact name 'Install' targets the card button, not the "Installed" tab (which
    // a /install/i regex would also match, making the query ambiguous).
    const btn = await screen.findByRole('button', { name: 'Install' })
    fireEvent.click(btn)

    // The enable POST was attempted and an error toast fired.
    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith('/v1/apps/enable', null, {
        params: { app_id: 'APP1' }
      })
    )
    await waitFor(() => expect(toastMock).toHaveBeenCalledTimes(1))
    const [title, opts] = toastMock.mock.calls[0]
    expect(title).toBe('Couldn’t install App One')
    expect((opts as { tone?: string }).tone).toBe('error')
    // A non-"unavailable" 403 detail is NOT surfaced (non-actionable / ambiguous).
    expect((opts as { body?: string }).body).toBeUndefined()

    // The optimistic flip reverted: the row is back to "Install", never stuck on
    // "Installed" and never left disabled/busy.
    await waitFor(() => {
      const after = screen.getByRole('button', { name: 'Install' })
      expect(after.textContent).toContain('Install')
      expect(after.textContent).not.toContain('Installed')
      expect((after as HTMLButtonElement).disabled).toBe(false)
    })
  })

  it('surfaces the backend detail for a user-appropriate "currently unavailable" failure', async () => {
    seedGrid()
    postMock.mockRejectedValue(
      httpError(400, 'This app is currently unavailable. Please try again later.')
    )
    await renderApps()

    const btn = await screen.findByRole('button', { name: 'Install' })
    fireEvent.click(btn)

    await waitFor(() => expect(toastMock).toHaveBeenCalledTimes(1))
    const [title, opts] = toastMock.mock.calls[0]
    expect(title).toBe('Couldn’t install App One')
    expect((opts as { body?: string }).body).toBe(
      'This app is currently unavailable. Please try again later.'
    )
  })
})
