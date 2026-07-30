// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen, act, fireEvent } from '@testing-library/react'
import { DegradedModeNotice } from './DegradedModeNotice'

// The user-facing half of 429-storm degraded mode. Main detects the storm and
// broadcasts backend:degraded; these assertions are the contract that the banner
// shows during a storm, self-clears on recovery, and can be dismissed for the storm.

let fireDegraded: ((d: boolean) => void) | null = null
let initialState = false

function mockOmi(): void {
  fireDegraded = null
  ;(
    window as unknown as {
      omi: {
        backendDegradedState: () => Promise<boolean>
        onBackendDegraded: (cb: (d: boolean) => void) => () => void
      }
    }
  ).omi = {
    backendDegradedState: () => Promise.resolve(initialState),
    onBackendDegraded: (cb) => {
      fireDegraded = cb
      return () => {
        fireDegraded = null
      }
    }
  }
}

async function renderNotice(): Promise<void> {
  await act(async () => {
    render(<DegradedModeNotice />)
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  initialState = false
})
afterEach(() => cleanup())

describe('DegradedModeNotice', () => {
  it('renders nothing when the backend is healthy', async () => {
    mockOmi()
    await renderNotice()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('shows the calm banner on a degraded broadcast and clears on recovery', async () => {
    mockOmi()
    await renderNotice()
    await act(async () => fireDegraded?.(true))
    const notice = screen.getByRole('status')
    expect(notice.textContent).toContain('Omi is catching up')
    expect(notice.textContent).toContain('Syncing will resume automatically')

    await act(async () => fireDegraded?.(false))
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('shows immediately when a storm was already active at mount', async () => {
    initialState = true
    mockOmi()
    await renderNotice()
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('dismiss hides it for the current storm; a later storm shows again', async () => {
    mockOmi()
    await renderNotice()
    await act(async () => fireDegraded?.(true))
    fireEvent.click(screen.getByLabelText('Dismiss'))
    expect(screen.queryByRole('status')).toBeNull()

    // Same storm: no re-broadcast, stays hidden. Recovery then a NEW storm re-shows.
    await act(async () => fireDegraded?.(false))
    await act(async () => fireDegraded?.(true))
    expect(screen.getByRole('status')).toBeTruthy()
  })
})
