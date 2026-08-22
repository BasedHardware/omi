// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen, act, fireEvent } from '@testing-library/react'
import type { RewindCaptureDiagnostics, RewindSettings } from '../../../../shared/types'

import { RewindCaptureNotice } from './RewindCaptureNotice'

const AVAILABLE: RewindCaptureDiagnostics = {
  available: true,
  reason: null,
  likelyMissingLinuxPortal: false
}

const settings = (captureEnabled: boolean): RewindSettings => ({
  captureEnabled,
  intervalMs: 30_000,
  retentionDays: 30,
  excludedApps: [],
  captureQuality: 'standard'
})

function mockOmi(diagnostics: RewindCaptureDiagnostics, captureEnabled: boolean): void {
  ;(
    window as unknown as {
      omi: {
        rewindGetSettings: () => Promise<RewindSettings>
        rewindCaptureDiagnostics: () => Promise<RewindCaptureDiagnostics>
      }
    }
  ).omi = {
    rewindGetSettings: () => Promise.resolve(settings(captureEnabled)),
    rewindCaptureDiagnostics: () => Promise.resolve(diagnostics)
  }
}

async function renderNotice(): Promise<void> {
  await act(async () => {
    render(<RewindCaptureNotice />)
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('RewindCaptureNotice', () => {
  it('renders nothing when capture is available (the overwhelmingly common case)', async () => {
    mockOmi(AVAILABLE, true)
    await renderNotice()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('renders nothing when Rewind is disabled, even if capture would fail', async () => {
    // Showing this to someone who never turned Rewind on would be noise, not help.
    mockOmi(
      { available: false, reason: 'Failed to get sources.', likelyMissingLinuxPortal: true },
      false
    )
    await renderNotice()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('shows the Linux-portal-specific message when likelyMissingLinuxPortal is set', async () => {
    mockOmi(
      { available: false, reason: 'Failed to get sources.', likelyMissingLinuxPortal: true },
      true
    )
    await renderNotice()
    expect(screen.getByText(/screen recording isn't working/i)).toBeTruthy()
    expect(screen.getByText(/xdg-desktop-portal-wlr/i)).toBeTruthy()
  })

  it('shows a generic message with the reason when it is not a Linux-portal case', async () => {
    mockOmi(
      { available: false, reason: 'some other failure', likelyMissingLinuxPortal: false },
      true
    )
    await renderNotice()
    expect(screen.getByText(/some other failure/i)).toBeTruthy()
    expect(screen.queryByText(/xdg-desktop-portal-wlr/i)).toBeNull()
  })

  it('can be dismissed', async () => {
    mockOmi({ available: false, reason: 'x', likelyMissingLinuxPortal: false }, true)
    await renderNotice()
    expect(screen.getByRole('status')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Dismiss'))
    expect(screen.queryByRole('status')).toBeNull()
  })
})
