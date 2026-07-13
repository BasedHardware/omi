// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { TranscriptionTab } from './TranscriptionTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import { getPreferences } from '../../../lib/preferences'

// The tab syncs the chosen language to the backend via the shared helper; stub it
// so the test is hermetic (no firebase/axios/network at import time).
const syncLanguage = vi.fn().mockResolvedValue(undefined)
vi.mock('../../../lib/userProfile', () => ({
  syncLanguage: (...a: unknown[]) => syncLanguage(...a)
}))

const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <TranscriptionTab />
    </SettingsSearchProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  syncLanguage.mockClear()
})
afterEach(cleanup)

describe('TranscriptionTab', () => {
  it('defaults to single-language mode with the language dropdown visible', () => {
    renderTab()
    // Default language is English (not the multi sentinel) → single card selected.
    expect(
      screen.getByRole('radio', { name: /Single language/ }).getAttribute('aria-checked')
    ).toBe('true')
    expect(screen.getByRole('combobox')).toBeTruthy()
  })

  it('changes the single language: persists the preference and syncs the backend', () => {
    renderTab()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'es' } })
    expect(getPreferences().language).toBe('es')
    expect(syncLanguage).toHaveBeenCalledWith('es')
  })

  it('auto-detect maps to the multi sentinel and hides the dropdown', () => {
    renderTab()
    fireEvent.click(screen.getByText('Auto-detect (multi-language)'))
    expect(getPreferences().language).toBe('multi')
    expect(syncLanguage).toHaveBeenCalledWith('multi')
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('toggles the local VAD gate preference (on by default)', () => {
    renderTab()
    const toggle = screen.getByRole('switch', { name: 'Local VAD gate' })
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    fireEvent.click(toggle)
    expect(getPreferences().vadGateEnabled).toBe(false)
  })
})
