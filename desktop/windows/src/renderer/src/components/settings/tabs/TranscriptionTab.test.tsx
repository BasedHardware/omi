// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { TranscriptionTab } from './TranscriptionTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import { getPreferences } from '../../../lib/preferences'

// The tab syncs the chosen language to the backend via the shared helper; stub it
// so the test is hermetic (no firebase/axios/network at import time).
const syncLanguage = vi.fn().mockResolvedValue(undefined)
vi.mock('../../../lib/userProfile', () => ({
  syncLanguage: (...a: unknown[]) => syncLanguage(...a)
}))

const vocab = vi.hoisted(() => ({
  fetchVocabulary: vi.fn(),
  saveVocabulary: vi.fn()
}))
vi.mock('../../../lib/transcriptionVocabulary', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/transcriptionVocabulary')>()
  return { ...actual, fetchVocabulary: vocab.fetchVocabulary, saveVocabulary: vocab.saveVocabulary }
})

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
  vocab.fetchVocabulary.mockReset().mockResolvedValue([])
  vocab.saveVocabulary.mockReset().mockResolvedValue(undefined)
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

  it('offers Brazilian Portuguese and persists its regional code (#7461)', () => {
    renderTab()
    const dropdown = screen.getByRole('combobox')
    expect(Array.from(dropdown.querySelectorAll('option')).map((o) => o.textContent)).toContain(
      'Portuguese (Brazil)'
    )
    fireEvent.change(dropdown, { target: { value: 'pt-BR' } })
    expect(getPreferences().language).toBe('pt-BR')
    expect(syncLanguage).toHaveBeenCalledWith('pt-BR')
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

describe('TranscriptionTab — custom vocabulary', () => {
  const input = (): HTMLInputElement =>
    screen.getByRole('textbox', { name: 'Add a vocabulary word' }) as HTMLInputElement

  it('shows the saved terms and adds typed ones on Enter (comma lists too)', async () => {
    vocab.fetchVocabulary.mockResolvedValue(['Omi'])
    renderTab()
    expect(await screen.findByText('Omi')).toBeTruthy()

    fireEvent.change(input(), { target: { value: 'Callie, OpenAI' } })
    fireEvent.keyDown(input(), { key: 'Enter' })

    expect(vocab.saveVocabulary).toHaveBeenCalledWith(['Omi', 'Callie', 'OpenAI'])
    expect(screen.getByText('Callie')).toBeTruthy()
    expect(input().value).toBe('')
  })

  it('removes a term with its × button', async () => {
    vocab.fetchVocabulary.mockResolvedValue(['Omi', 'Callie'])
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove Callie' }))
    expect(vocab.saveVocabulary).toHaveBeenCalledWith(['Omi'])
    expect(screen.queryByText('Callie')).toBeNull()
  })

  it('never saves when the saved list could not be loaded', async () => {
    vocab.fetchVocabulary.mockRejectedValue(new Error('offline'))
    renderTab()
    expect(await screen.findByText(/Couldn’t load your vocabulary/)).toBeTruthy()
    expect(screen.queryByRole('textbox', { name: 'Add a vocabulary word' })).toBeNull()
    expect(vocab.saveVocabulary).not.toHaveBeenCalled()
  })

  it('retries a failed load', async () => {
    vocab.fetchVocabulary.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(['Omi'])
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Omi')).toBeTruthy()
    expect(vocab.fetchVocabulary).toHaveBeenCalledTimes(2)
  })

  it('reverts the optimistic change when saving fails', async () => {
    vocab.fetchVocabulary.mockResolvedValue(['Omi'])
    vocab.saveVocabulary.mockRejectedValue(new Error('500'))
    renderTab()
    await screen.findByText('Omi')
    fireEvent.change(input(), { target: { value: 'Callie' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    // The save was attempted and the term shown optimistically, so the check below
    // observes a real revert rather than an add that never happened.
    expect(vocab.saveVocabulary).toHaveBeenCalledWith(['Omi', 'Callie'])
    expect(screen.getByText('Callie')).toBeTruthy()
    await waitFor(() => expect(screen.queryByText('Callie')).toBeNull())
    expect(screen.getByText('Omi')).toBeTruthy()
  })

  it('a failed earlier save does not undo a newer one that succeeded', async () => {
    vocab.fetchVocabulary.mockResolvedValue(['Omi'])
    let failFirst: (e: Error) => void = () => {}
    vocab.saveVocabulary
      .mockImplementationOnce(() => new Promise<void>((_, reject) => (failFirst = reject)))
      .mockResolvedValueOnce(undefined)
    renderTab()
    await screen.findByText('Omi')
    fireEvent.change(input(), { target: { value: 'Callie' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    fireEvent.change(input(), { target: { value: 'OpenAI' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(vocab.saveVocabulary).toHaveBeenLastCalledWith(['Omi', 'Callie', 'OpenAI'])
    failFirst(new Error('500'))
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.getByText('Callie')).toBeTruthy()
    expect(screen.getByText('OpenAI')).toBeTruthy()
  })

  it('does not add a term on the Enter that confirms an IME composition', async () => {
    vocab.fetchVocabulary.mockResolvedValue([])
    renderTab()
    await waitFor(() => expect(input().disabled).toBe(false))
    fireEvent.change(input(), { target: { value: 'にほん' } })
    fireEvent.keyDown(input(), { key: 'Enter', isComposing: true })
    expect(vocab.saveVocabulary).not.toHaveBeenCalled()
    expect(input().value).toBe('にほん')
  })

  it('says the list is full at the limit instead of silently ignoring input', async () => {
    vocab.fetchVocabulary.mockResolvedValue(Array.from({ length: 100 }, (_, i) => `term${i}`))
    renderTab()
    expect(await screen.findByText(/100\/100 • Remove a word to add another/)).toBeTruthy()
    expect(input().disabled).toBe(true)
  })
})
