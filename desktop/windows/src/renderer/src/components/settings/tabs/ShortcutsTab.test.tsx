// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { ShortcutsTab } from './ShortcutsTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import { getPreferences } from '../../../lib/preferences'

const getRecordHotkey = vi.fn()
const setRecordHotkey = vi.fn()
const setRecordHotkeyEnabled = vi.fn()
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
  getRecordHotkey
    .mockReset()
    .mockResolvedValue({ accelerator: 'Ctrl+Space', registered: true, enabled: true })
  setRecordHotkey.mockReset().mockResolvedValue({ ok: true, registered: true })
  setRecordHotkeyEnabled
    .mockReset()
    .mockResolvedValue({ accelerator: 'Ctrl+Space', registered: false, enabled: false })
  getSummonHotkey.mockReset().mockResolvedValue({ accelerator: 'Shift+Space', registered: true })
  setSummonHotkey.mockReset().mockResolvedValue({ ok: true, registered: true })
  suspendShortcutCapture.mockReset()
  resumeShortcutCapture.mockReset()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    getRecordHotkey,
    setRecordHotkey,
    setRecordHotkeyEnabled,
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

  it('offers an "Off" chip on the Record card only (Summon is coupled to PTT)', async () => {
    renderTab()
    // Exactly one Off chip renders — for the Record card. Summon has none.
    await waitFor(() => expect(screen.getAllByText('Off').length).toBe(1))
  })

  it('turning the record chord off disables it via main and shows the off note', async () => {
    renderTab()
    await waitFor(() => expect(screen.getByText('Off')).toBeTruthy())
    fireEvent.click(screen.getByText('Off'))
    await waitFor(() => expect(setRecordHotkeyEnabled).toHaveBeenCalledWith(false))
    await waitFor(() => expect(screen.getByText('Recording shortcut is off.')).toBeTruthy())
  })

  it('re-enables from Off via the Default chip even when the OS declines the chord', async () => {
    // Start in the "Off" state; the commit reports a conflict (registered=false),
    // which used to wrongly refuse to re-enable. Enabling is user intent — it must
    // decouple from OS registration and surface the "in use" warning instead.
    getRecordHotkey.mockResolvedValue({
      accelerator: 'Ctrl+Space',
      registered: false,
      enabled: false
    })
    setRecordHotkey.mockResolvedValue({ ok: false, registered: false })
    renderTab()
    await waitFor(() => expect(screen.getByText('Recording shortcut is off.')).toBeTruthy())
    // Record is the second card → its Default chip is the second "Default".
    fireEvent.click(screen.getAllByText('Default')[1])
    await waitFor(() => expect(setRecordHotkey).toHaveBeenCalledWith('Ctrl+Space'))
    // No longer "off"; the same conflict note a fresh load shows (enabled,
    // unregistered) — consistent copy, not a second "try another" string.
    await waitFor(() => expect(screen.getByText(/held by another app/)).toBeTruthy())
    expect(screen.queryByText('Recording shortcut is off.')).toBeNull()
  })

  // Regression: recording a CUSTOM record chord the OS declines. Main commits and
  // persists it anyway (intent model, no rollback), so the card must show the same
  // canonical conflict note a fresh load shows — never "try another", which implies
  // nothing was applied while the old working chord has in fact been released.
  it('a declined custom record chord shows "held by another app", not "try another"', async () => {
    setRecordHotkey.mockResolvedValue({ ok: false, registered: false })
    renderTab()
    // Record is the second card → its Custom chip is the second "Custom…".
    await waitFor(() => expect(screen.getAllByText('Custom…').length).toBe(2))
    fireEvent.click(screen.getAllByText('Custom…')[1])
    fireEvent.keyDown(window, { key: 'j', ctrlKey: true })
    await waitFor(() => expect(setRecordHotkey).toHaveBeenCalledWith('CommandOrControl+J'))

    await waitFor(() => expect(screen.getByText(/held by another app/)).toBeTruthy())
    expect(screen.queryByText(/try another/)).toBeNull()
  })

  // The Summon card keeps rollback semantics: ok:false there means main really did
  // NOT rebind, so "try another" (nothing applied) is the correct copy.
  it('a declined custom summon chord still shows "try another" (rollback semantics)', async () => {
    setSummonHotkey.mockResolvedValue({ ok: false, registered: false })
    renderTab()
    await waitFor(() => expect(screen.getAllByText('Custom…').length).toBe(2))
    fireEvent.click(screen.getAllByText('Custom…')[0])
    fireEvent.keyDown(window, { key: 'j', ctrlKey: true })
    await waitFor(() => expect(setSummonHotkey).toHaveBeenCalledWith('CommandOrControl+J'))

    await waitFor(() => expect(screen.getByText(/try another/)).toBeTruthy())
  })
})
