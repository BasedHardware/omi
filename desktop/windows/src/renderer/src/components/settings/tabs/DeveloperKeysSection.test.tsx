// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { DeveloperKeysSection } from './DeveloperKeysSection'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

vi.mock('../../../lib/firebase', () => ({
  auth: { currentUser: { getIdToken: () => Promise.resolve('test-token') } }
}))
vi.mock('../../../lib/billing', () => ({
  fetchSubscription: vi.fn().mockResolvedValue({}),
  fetchChatQuota: vi.fn().mockResolvedValue({})
}))

const validatedProviders = vi.fn()
const enroll = vi.fn()

beforeEach(() => {
  validatedProviders.mockReset()
  enroll.mockReset()
  ;(window as unknown as { omi: unknown }).omi = {
    byokGetAll: vi.fn().mockResolvedValue({ openrouter: 'llm-key', deepgram: 'saved-key' }),
    byokValidatedProviders: validatedProviders,
    byokSet: vi.fn().mockResolvedValue(undefined),
    byokEnroll: enroll
  }
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('DeveloperKeysSection provider-scoped BYOK', () => {
  it('keeps Omi transcription limits visible for LLM-only enrollment, even with a saved Deepgram key', async () => {
    validatedProviders.mockResolvedValue(['openrouter'])
    render(<DeveloperKeysSection />, { wrapper: SettingsSearchProvider })

    expect(await screen.findByText('Chat and AI: BYOK keys active')).not.toBeNull()
    expect(screen.getByText('Transcription: Omi plan allowance')).not.toBeNull()
    expect(
      screen.getByText(/A validated Deepgram key is required for BYOK transcription/)
    ).not.toBeNull()
    expect(screen.getByText(/conversation locks still apply/)).not.toBeNull()
  })

  it('shows Deepgram transcription separately when its current key is enrolled', async () => {
    validatedProviders.mockResolvedValue(['openrouter', 'deepgram'])
    render(<DeveloperKeysSection />, { wrapper: SettingsSearchProvider })

    expect(await screen.findByText('Transcription: Deepgram BYOK')).not.toBeNull()
    expect(screen.getByText('Chat and AI: BYOK keys active')).not.toBeNull()
    expect(screen.queryByText('Transcription: Omi plan allowance')).toBeNull()
  })

  it('explains transcription limits before enrollment', async () => {
    validatedProviders.mockResolvedValue([])
    render(<DeveloperKeysSection />, { wrapper: SettingsSearchProvider })

    expect(await screen.findByText('Bring your own keys')).not.toBeNull()
    expect(screen.getByText('Transcription: Omi plan allowance')).not.toBeNull()
    expect(screen.queryByText('Chat and AI: BYOK keys active')).toBeNull()
  })

  it('returns to Omi transcription allowance when a replacement Deepgram key is rejected', async () => {
    validatedProviders
      .mockResolvedValueOnce(['openrouter', 'deepgram'])
      .mockResolvedValueOnce(['openrouter'])
    enroll.mockResolvedValue({ active: true, results: { deepgram: { ok: false } } })
    render(<DeveloperKeysSection />, { wrapper: SettingsSearchProvider })
    expect(await screen.findByText('Transcription: Deepgram BYOK')).not.toBeNull()

    vi.useFakeTimers()
    fireEvent.change(screen.getByDisplayValue('saved-key'), { target: { value: 'rejected-key' } })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600)
    })

    expect(enroll).toHaveBeenCalledWith('test-token')
    expect(screen.getByText('Transcription: Omi plan allowance')).not.toBeNull()
    expect(screen.getByText('Chat and AI: BYOK keys active')).not.toBeNull()
    expect(screen.queryByText('Transcription: Deepgram BYOK')).toBeNull()
  })
})
