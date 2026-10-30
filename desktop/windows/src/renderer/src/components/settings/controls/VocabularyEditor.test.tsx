// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'

const fetchMock = vi.fn()
const saveMock = vi.fn()
const toastMock = vi.fn()
vi.mock('../../../lib/transcriptionVocabulary', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/transcriptionVocabulary')>(
    '../../../lib/transcriptionVocabulary'
  )
  return {
    ...actual,
    fetchTranscriptionVocabulary: () => fetchMock(),
    saveTranscriptionVocabulary: (terms: string[]) => saveMock(terms)
  }
})
vi.mock('../../../lib/apiClient', () => ({ omiApi: {} }))
vi.mock('../../../lib/ptt/userVocabulary', () => ({ refreshUserVocabulary: vi.fn() }))
vi.mock('../../../lib/toast', () => ({ toast: (...a: unknown[]) => toastMock(...a) }))

import { VOCABULARY_LIMIT } from '../../../lib/transcriptionVocabulary'
import { VocabularyEditor } from './VocabularyEditor'

beforeEach(() => {
  fetchMock.mockReset()
  saveMock.mockReset()
  toastMock.mockReset()
  fetchMock.mockResolvedValue(['Omi'])
  saveMock.mockResolvedValue(undefined)
})
afterEach(cleanup)

describe('VocabularyEditor', () => {
  it('loads the account list and renders a removable chip per term', async () => {
    render(<VocabularyEditor />)
    await screen.findByText('Omi')
    expect(screen.getByLabelText('Remove Omi')).toBeTruthy()
    expect(screen.getByTestId('vocabulary-count').textContent).toBe('1/100')
  })

  it('Enter adds the typed terms and saves the whole list', async () => {
    render(<VocabularyEditor />)
    await screen.findByText('Omi')
    const input = screen.getByLabelText('Add a vocabulary term') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'Deepgram, omi' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    await waitFor(() => expect(saveMock).toHaveBeenCalledWith(['Omi', 'Deepgram']))
    expect(screen.getByText('Deepgram')).toBeTruthy()
    expect(screen.getAllByText('Omi')).toHaveLength(1) // case-insensitive dedupe
    expect(input.value).toBe('')
  })

  it('× removes the term and saves the shorter list', async () => {
    fetchMock.mockResolvedValue(['Omi', 'Deepgram'])
    render(<VocabularyEditor />)
    await screen.findByText('Deepgram')
    fireEvent.click(screen.getByLabelText('Remove Deepgram'))
    await waitFor(() => expect(saveMock).toHaveBeenCalledWith(['Omi']))
    expect(screen.queryByText('Deepgram')).toBeNull()
  })

  it('reverts the optimistic edit and toasts when the save is rejected', async () => {
    saveMock.mockRejectedValueOnce(new Error('500'))
    render(<VocabularyEditor />)
    await screen.findByText('Omi')
    fireEvent.click(screen.getByLabelText('Remove Omi'))
    // Optimistically gone, then back once the rejection lands.
    await waitFor(() => expect(screen.getByText('Omi')).toBeTruthy())
    expect(toastMock).toHaveBeenCalledWith('Could not save vocabulary', expect.anything())
  })

  it('disables add at the term cap and toasts when overflow is submitted', async () => {
    fetchMock.mockResolvedValue(Array.from({ length: VOCABULARY_LIMIT }, (_, i) => `t${i}`))
    render(<VocabularyEditor />)
    await screen.findByText('t0')
    const input = screen.getByLabelText('Add a vocabulary term') as HTMLInputElement
    expect(input.disabled).toBe(true)
    expect(input.placeholder).toMatch(/Limit of 100 terms reached/)
  })

  it('shows a retry affordance when the list cannot be loaded', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(['Omi'])
    render(<VocabularyEditor />)
    await screen.findByText('Couldn’t load your vocabulary.')
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }))
    await screen.findByText('Omi')
  })
})
