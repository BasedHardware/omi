// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AboutTab } from './AboutTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

const getAppVersion = vi.fn()
const getPendingUpdate = vi.fn()
const onUpdateReady = vi.fn()
const checkForUpdates = vi.fn()
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
  whatsNewOpenNotes.mockReset()
  quitApp.mockReset()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    getAppVersion,
    getPendingUpdate,
    onUpdateReady,
    checkForUpdates,
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

  it('surfaces a staged update with a restart affordance', async () => {
    getPendingUpdate.mockResolvedValue({ version: '2.0.0' })
    renderTab()
    await waitFor(() => expect(screen.getByText(/Version 2\.0\.0 is ready/)).toBeTruthy())
    fireEvent.click(screen.getByText('Restart to update'))
    expect(quitApp).toHaveBeenCalled()
  })
})
