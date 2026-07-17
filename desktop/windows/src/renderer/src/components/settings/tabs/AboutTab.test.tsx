// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AboutTab } from './AboutTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

const getAppVersion = vi.fn()
const getPendingUpdate = vi.fn()
const onUpdateReady = vi.fn()
const checkForUpdates = vi.fn()
const getBetaUpdatesOptIn = vi.fn()
const setBetaUpdatesOptIn = vi.fn()
const whatsNewOpenNotes = vi.fn()
const quitApp = vi.fn()

const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <AboutTab />
    </SettingsSearchProvider>
  )
}

beforeEach(() => {
  getAppVersion.mockReset().mockResolvedValue({ name: 'Omi', version: '1.2.3' })
  getPendingUpdate.mockReset().mockResolvedValue(null)
  onUpdateReady.mockReset().mockReturnValue(() => {})
  checkForUpdates.mockReset().mockResolvedValue({ status: 'up-to-date', version: '1.2.3' })
  getBetaUpdatesOptIn.mockReset().mockResolvedValue(false)
  setBetaUpdatesOptIn.mockReset().mockResolvedValue(true)
  whatsNewOpenNotes.mockReset()
  quitApp.mockReset()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    getAppVersion,
    getPendingUpdate,
    onUpdateReady,
    checkForUpdates,
    getBetaUpdatesOptIn,
    setBetaUpdatesOptIn,
    whatsNewOpenNotes,
    quitApp
  }
})
afterEach(cleanup)

describe('AboutTab', () => {
  it('shows the real app version', async () => {
    renderTab()
    await waitFor(() => expect(screen.getByText('Version 1.2.3')).toBeTruthy())
  })

  it('opens release notes via the existing IPC', async () => {
    renderTab()
    fireEvent.click(screen.getByText('Release notes'))
    expect(whatsNewOpenNotes).toHaveBeenCalled()
  })

  it('checks for updates and reports the result', async () => {
    renderTab()
    fireEvent.click(screen.getByText('Check for updates'))
    expect(checkForUpdates).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByText(/latest version \(1\.2\.3\)/)).toBeTruthy())
  })

  it('opts into beta updates, persists the choice, and kicks a check', async () => {
    renderTab()
    const toggle = await screen.findByRole('switch', { name: 'Receive beta updates' })
    // Disabled until the persisted value loads; enabled once it resolves (false).
    await waitFor(() => expect((toggle as HTMLButtonElement).disabled).toBe(false))
    expect(toggle.getAttribute('aria-checked')).toBe('false')

    fireEvent.click(toggle)
    await waitFor(() => expect(setBetaUpdatesOptIn).toHaveBeenCalledWith(true))
    // Opting in surfaces a newer beta immediately (also re-checks in main).
    expect(checkForUpdates).toHaveBeenCalled()
    await waitFor(() => expect(toggle.getAttribute('aria-checked')).toBe('true'))
  })

  it('reflects an already-on beta opt-in on mount', async () => {
    getBetaUpdatesOptIn.mockResolvedValue(true)
    renderTab()
    const toggle = await screen.findByRole('switch', { name: 'Receive beta updates' })
    await waitFor(() => expect(toggle.getAttribute('aria-checked')).toBe('true'))
  })

  it('surfaces a staged update with a restart affordance', async () => {
    getPendingUpdate.mockResolvedValue({ version: '2.0.0' })
    renderTab()
    await waitFor(() => expect(screen.getByText(/Version 2\.0\.0 is ready/)).toBeTruthy())
    fireEvent.click(screen.getByText('Restart to update'))
    expect(quitApp).toHaveBeenCalled()
  })
})
