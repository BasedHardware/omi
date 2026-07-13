// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { ShortcutsTab } from './ShortcutsTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import { getPreferences } from '../../../lib/preferences'

const getRecordHotkey = vi.fn()
const setRecordHotkey = vi.fn()
const getSummonHotkey = vi.fn()
const setSummonHotkey = vi.fn()
const suspendShortcutCapture = vi.fn()
const resumeShortcutCapture = vi.fn()

const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <ShortcutsTab />
    </SettingsSearchProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  getRecordHotkey.mockReset().mockResolvedValue({ accelerator: 'Ctrl+Space', registered: true })
  setRecordHotkey.mockReset().mockResolvedValue({ ok: true, registered: true })
  getSummonHotkey.mockReset().mockResolvedValue({ accelerator: 'Shift+Space', registered: true })
  setSummonHotkey.mockReset().mockResolvedValue({ ok: true, registered: true })
  suspendShortcutCapture.mockReset()
  resumeShortcutCapture.mockReset()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    getRecordHotkey,
    setRecordHotkey,
    getSummonHotkey,
    setSummonHotkey,
    suspendShortcutCapture,
    resumeShortcutCapture
  }
})
afterEach(cleanup)

describe('ShortcutsTab', () => {
  it('renders a card per chord with the current chord as keycaps (summon first)', async () => {
    renderTab()
    await waitFor(() => expect(screen.getByText('Summon hotkey')).toBeTruthy())
    expect(screen.getByText('Record hotkey')).toBeTruthy()
    // Ctrl+Space (record) and Shift+Space (summon) → keycap labels render.
    await waitFor(() => expect(screen.getByText('Ctrl')).toBeTruthy())
    expect(screen.getByText('Shift')).toBeTruthy()
    // Each card carries a Default preset chip + a Custom chip.
    expect(screen.getAllByText('Default').length).toBe(2)
    expect(screen.getAllByText('Custom…').length).toBe(2)
    expect(getRecordHotkey).toHaveBeenCalled()
    expect(getSummonHotkey).toHaveBeenCalled()
  })

  it('warns when a chord is held by another app (registration failed)', async () => {
    getSummonHotkey.mockResolvedValue({ accelerator: 'Shift+Space', registered: false })
    renderTab()
    await waitFor(() => expect(screen.getByText(/held by another app/)).toBeTruthy())
  })

  it('records a custom summon chord, persists it, and re-registers via main', async () => {
    renderTab()
    // Summon is the first card → its Custom chip is the first "Custom…".
    await waitFor(() => expect(screen.getAllByText('Custom…').length).toBe(2))
    fireEvent.click(screen.getAllByText('Custom…')[0])
    // Capturing raw keys → all global chords suspended.
    expect(suspendShortcutCapture).toHaveBeenCalled()
    // Press Ctrl+J → a valid custom accelerator that commits.
    fireEvent.keyDown(window, { key: 'j', ctrlKey: true })
    await waitFor(() => expect(setSummonHotkey).toHaveBeenCalledWith('CommandOrControl+J'))
    // On success the accelerator is mirrored to the legacy pref (startup converge).
    await waitFor(() => expect(getPreferences().overlayShortcut).toBe('CommandOrControl+J'))
  })
})
