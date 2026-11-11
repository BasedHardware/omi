// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the Python-backend axios client — the selector's only I/O.
// vi.mock is hoisted above module init, so the fn it references must be created
// in a vi.hoisted() block (also hoisted) to avoid a TDZ ReferenceError.
const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../apiClient', () => ({ omiApi: { get } }))

import {
  refresh,
  refreshIfStale,
  currentPick,
  resolveEffectiveVoiceProvider
} from './autoModelSelector'
import { setPreferences } from '../preferences'

const PICK_DATE_KEY = 'realtimeOmniAutoPickDate'

beforeEach(() => {
  localStorage.clear()
  get.mockReset()
  // Reset the settings-level provider to the default ('auto') each test.
  setPreferences({ voiceProvider: 'auto' })
})

describe('autoModelSelector — core pick', () => {
  it('fetches gptRealtime2, stores it, and resolves to openai under Auto', async () => {
    get.mockResolvedValue({ data: { provider: 'gptRealtime2' } })
    await refresh()
    expect(get).toHaveBeenCalledWith('/v1/auto/model-pick', expect.objectContaining({}))
    expect(currentPick()).toBe('gptRealtime2')
    expect(resolveEffectiveVoiceProvider()).toBe('openai')
  })

  // Regression: this poll is fire-and-forget and swallows every failure, so a
  // dead-session 401 must reject quietly instead of routing the user to Login
  // (apiClient's responseErrorHandler calls forceReauth() unless a request opts
  // out). Without __sessionPreserving, merely STARTING a voice session with a
  // stale token would kick the user to the sign-in screen.
  it('polls with __sessionPreserving so a dead-session 401 never forces reauth', async () => {
    get.mockResolvedValue({ data: { provider: 'geminiFlashLive' } })
    await refresh()
    expect(get).toHaveBeenCalledWith(
      '/v1/auto/model-pick',
      expect.objectContaining({ __sessionPreserving: true, timeout: 15_000 })
    )
  })

  it('fetches geminiFlashLive and resolves to gemini under Auto', async () => {
    get.mockResolvedValue({ data: { provider: 'geminiFlashLive' } })
    await refresh()
    expect(currentPick()).toBe('geminiFlashLive')
    expect(resolveEffectiveVoiceProvider()).toBe('gemini')
  })
})

describe('autoModelSelector — graceful fallback (never clobber a good pick)', () => {
  it('network error with no prior pick defaults to gemini', async () => {
    get.mockRejectedValue(new Error('offline'))
    await refresh()
    expect(currentPick()).toBe('geminiFlashLive')
    expect(resolveEffectiveVoiceProvider()).toBe('gemini')
  })

  it('unknown provider string with no prior pick defaults to gemini', async () => {
    get.mockResolvedValue({ data: { provider: 'someBrandNewModel' } })
    await refresh()
    expect(currentPick()).toBe('geminiFlashLive')
  })

  it('network error keeps the last good pick', async () => {
    get.mockResolvedValueOnce({ data: { provider: 'gptRealtime2' } })
    await refresh()
    get.mockRejectedValueOnce(new Error('offline'))
    await refresh()
    expect(currentPick()).toBe('gptRealtime2') // preserved, not overwritten with the default
  })

  it('junk response keeps the last good pick', async () => {
    get.mockResolvedValueOnce({ data: { provider: 'gptRealtime2' } })
    await refresh()
    get.mockResolvedValueOnce({ data: { provider: 42 } })
    await refresh()
    expect(currentPick()).toBe('gptRealtime2')
  })
})

describe('autoModelSelector — 24h TTL / refreshIfStale', () => {
  it('fires no request when a fresh pick already exists', async () => {
    get.mockResolvedValue({ data: { provider: 'geminiFlashLive' } })
    await refresh() // stamps the pick + date=now
    get.mockClear()
    refreshIfStale()
    expect(get).not.toHaveBeenCalled()
  })

  it('refetches when the cached pick is older than 24h', async () => {
    get.mockResolvedValue({ data: { provider: 'geminiFlashLive' } })
    await refresh()
    // Age the cached timestamp past the 24h TTL.
    localStorage.setItem(PICK_DATE_KEY, String(Date.now() - 25 * 60 * 60 * 1000))
    get.mockClear()
    refreshIfStale()
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('fetches when there is no pick yet', () => {
    refreshIfStale()
    expect(get).toHaveBeenCalledTimes(1)
  })
})

describe('autoModelSelector — a concrete setting bypasses the selector', () => {
  it('returns the pinned provider even when a different Auto pick is cached', async () => {
    get.mockResolvedValue({ data: { provider: 'gptRealtime2' } })
    await refresh() // Auto pick would be 'openai'
    setPreferences({ voiceProvider: 'gemini' })
    expect(resolveEffectiveVoiceProvider()).toBe('gemini')
    setPreferences({ voiceProvider: 'openai' })
    expect(resolveEffectiveVoiceProvider()).toBe('openai')
  })

  it('Auto with no cached pick resolves to gemini', () => {
    expect(resolveEffectiveVoiceProvider()).toBe('gemini')
  })

  // Regression: preferences are a hand-editable localStorage blob with no
  // per-field validation, so an unrecognized value must NOT be passed through as
  // a lane (it would reach the session machine and fail at mint). Unknown = Auto,
  // matching Mac's RealtimeOmniProvider(rawValue:) → nil decode.
  it('treats an unrecognized persisted provider as Auto rather than a lane', async () => {
    get.mockResolvedValue({ data: { provider: 'gptRealtime2' } })
    await refresh()
    setPreferences({ voiceProvider: 'grok' as unknown as 'auto' })
    expect(resolveEffectiveVoiceProvider()).toBe('openai') // the Auto pick, not 'grok'
  })
})
