// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, waitFor, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Apps } from './Apps'

// PR1 (error surfacing): the app-enable/disable toggle used to swallow EVERY failure
// (backend 400 "setup not completed", 403 paid/private, network) into a console.error,
// flipping the row to "Installed" then silently reverting. This suite pins the fix:
// a failed enable/disable raises a real error toast, the row reverts to its prior
// state, and the button is never left stuck busy/disabled.

const telemetry = vi.hoisted(() => ({
  trackAppEnabled: vi.fn(),
  trackAppDisabled: vi.fn(),
  trackAppDetailViewed: vi.fn()
}))
const { getMock, postMock, toastMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  toastMock: vi.fn()
}))
vi.mock('../lib/apiClient', () => ({
  omiApi: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a)
  }
}))
vi.mock('../lib/toast', () => ({ toast: (...a: unknown[]) => toastMock(...a) }))
vi.mock('../lib/analytics', () => telemetry)

// A minimal catalog item; the grid only needs id/name/category to render a card.
const app = (id: string, name: string): unknown => ({ id, name, category: 'other' })

// Seed a per-uid cold-start snapshot so the grid paints a real card synchronously
// (default view renders `sections`, so the app must live inside a section). The
// revalidating load() still runs; we let it fail so the seeded grid stays on screen.
function seedGrid(isEnabled = false): void {
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
      enabled: isEnabled ? ['APP1'] : []
    })
  )
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  toastMock.mockReset()
  telemetry.trackAppEnabled.mockReset()
  telemetry.trackAppDisabled.mockReset()
  telemetry.trackAppDetailViewed.mockReset()
  localStorage.clear()
  // Cache-first: a failed revalidation keeps the seeded grid on screen (the card
  // under test), rather than swapping in the full-page "Couldn't load apps".
  getMock.mockRejectedValue(new Error('offline'))
})
afterEach(() => {
  cleanup()
})

function renderApps(): void {
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
  it('records successful enable, disable, and detail actions without the app name', async () => {
    seedGrid()
    postMock.mockResolvedValue({ data: {} })
    const first = render(
      <MemoryRouter>
        <Apps />
      </MemoryRouter>
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Install' }))
    await waitFor(() =>
      expect(telemetry.trackAppEnabled).toHaveBeenCalledExactlyOnceWith('APP1', 'other')
    )
    expect(JSON.stringify(telemetry.trackAppEnabled.mock.calls)).not.toContain('App One')
    first.unmount()

    seedGrid(true)
    renderApps()
    const installedButtons = await screen.findAllByRole('button', { name: 'Installed' })
    fireEvent.click(installedButtons[installedButtons.length - 1])
    await waitFor(() =>
      expect(telemetry.trackAppDisabled).toHaveBeenCalledExactlyOnceWith('APP1', 'other')
    )

    fireEvent.click(screen.getByText('App One'))
    expect(telemetry.trackAppDetailViewed).toHaveBeenCalledExactlyOnceWith('APP1', 'other')
  })

  it('shows an error toast, reverts the row, and does not leave the button stuck busy when enable fails', async () => {
    seedGrid()
    postMock.mockRejectedValue(httpError(403, 'You are not authorized to enable this app'))
    renderApps()

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
    renderApps()

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
