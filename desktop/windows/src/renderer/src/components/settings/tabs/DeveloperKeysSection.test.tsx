// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { DeveloperKeysSection } from './DeveloperKeysSection'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }))
vi.mock('../../../lib/firebase', () => ({
  auth: { currentUser: { getIdToken } }
}))
vi.mock('../../../lib/billing', () => ({
  fetchSubscription: vi.fn().mockResolvedValue({}),
  fetchChatQuota: vi.fn().mockResolvedValue({})
}))

const validatedProviders = vi.fn()
const enroll = vi.fn()

beforeEach(() => {
  getIdToken.mockReset().mockResolvedValue('test-token')
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

  it('refreshes enrollment after saving a replacement key while signed out', async () => {
    validatedProviders
      .mockResolvedValueOnce(['openrouter', 'deepgram'])
      .mockResolvedValueOnce(['openrouter'])
    getIdToken.mockResolvedValue(undefined)
    render(<DeveloperKeysSection />, { wrapper: SettingsSearchProvider })
    expect(await screen.findByText('Transcription: Deepgram BYOK')).not.toBeNull()

    vi.useFakeTimers()
    fireEvent.change(screen.getByDisplayValue('saved-key'), {
      target: { value: 'replacement-key' }
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600)
    })

    expect(enroll).not.toHaveBeenCalled()
    expect(screen.getByText('Transcription: Omi plan allowance')).not.toBeNull()
    expect(screen.queryByText('Transcription: Deepgram BYOK')).toBeNull()
  })

  it('clears checking and treats enrollment as unknown when its status lookup fails', async () => {
    validatedProviders
      .mockResolvedValueOnce(['openrouter', 'deepgram'])
      .mockRejectedValueOnce(new Error('IPC unavailable'))
    enroll.mockResolvedValue({ active: true, results: { deepgram: { ok: true } } })
    render(<DeveloperKeysSection />, { wrapper: SettingsSearchProvider })
    expect(await screen.findByText('Transcription: Deepgram BYOK')).not.toBeNull()

    vi.useFakeTimers()
    fireEvent.change(screen.getByDisplayValue('saved-key'), {
      target: { value: 'replacement-key' }
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600)
    })

    expect(screen.queryAllByText('Checking…')).toHaveLength(0)
    expect(
      screen.getByText('Transcription status unavailable — reopen settings to check')
    ).not.toBeNull()
    expect(screen.queryByText('Transcription: Deepgram BYOK')).toBeNull()
  })
})
