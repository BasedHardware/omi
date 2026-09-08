// @vitest-environment jsdom
// A9: both provider lanes must receive the SAME assembled system instruction,
// and building it must never block session start on a network fetch.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { get, startOpenAiSession, startGeminiSession, mintRealtimeToken } = vi.hoisted(() => ({
  get: vi.fn(),
  startOpenAiSession: vi.fn(),
  startGeminiSession: vi.fn(),
  mintRealtimeToken: vi.fn()
}))

vi.mock('../analytics', () => ({ trackEvent: vi.fn() }))
vi.mock('../firebase', () => ({ auth: { currentUser: { uid: 'u1', displayName: 'Ada' } } }))
vi.mock('../apiClient', () => ({ omiApi: { get } }))
vi.mock('./tokenMint', () => ({
  mintRealtimeToken,
  MintError: class MintError extends Error {},
  OPENAI_REALTIME_MODEL: 'test-openai',
  GEMINI_LIVE_MODEL: 'test-gemini'
}))
vi.mock('./usageReport', () => ({ reportRealtimeUsage: vi.fn() }))
vi.mock('./openaiSession', () => ({ startOpenAiSession }))
vi.mock('./geminiSession', () => ({ startGeminiSession }))
vi.mock('./tts', () => ({ synthesizeTts: vi.fn(), DEFAULT_TTS_VOICE: 'test-voice' }))

import { startVoiceSession, stopVoiceSession } from './voiceController'
import { refreshAboutUserCard, resetAboutUserCard, whenAboutUserCardSettled } from './aboutUser'
import { setPreferences } from './../preferences'

const handle = { stop: vi.fn(), setMuted: vi.fn(), setOutputDevice: vi.fn(), sendUserText: vi.fn() }

beforeEach(() => {
  get.mockReset()
  startOpenAiSession.mockReset().mockResolvedValue(handle)
  startGeminiSession.mockReset().mockResolvedValue(handle)
  mintRealtimeToken.mockReset().mockResolvedValue({ token: 't' })
  resetAboutUserCard()
  localStorage.clear()
  setPreferences({ voiceLanguages: undefined })
})

afterEach(() => stopVoiceSession())

describe('startVoiceSession — system instruction', () => {
  // The card build fires TWO network reads (memories + action items). If session
  // start awaited either of them, a hung backend would hang push-to-talk — so the
  // hot path reads the CACHE synchronously and only kicks the refresh.
  it('starts even while the about_user fetches never resolve', async () => {
    get.mockReturnValue(new Promise(() => {}))
    await startVoiceSession('openai')
    expect(startOpenAiSession).toHaveBeenCalledTimes(1)
    const { instructions } = startOpenAiSession.mock.calls[0][0]
    expect(instructions).toContain('You are Omi, a fast spoken-voice assistant')
    expect(instructions).toContain('Current local datetime:')
    // Nothing cached yet → no card, rather than a card that falsely claims Omi
    // knows nothing about the user. (The routing rule still names the tag.)
    expect(instructions).not.toContain('What Omi knows about them:')
  })

  it('feeds the cached card and the voice-language preference to BOTH lanes', async () => {
    get.mockResolvedValue({
      data: [{ content: 'Ships fast.', created_at: '2026-07-01T00:00:00Z' }]
    })
    refreshAboutUserCard()
    await whenAboutUserCardSettled()
    setPreferences({ voiceLanguages: ['ru', 'en'] })

    await startVoiceSession('openai')
    stopVoiceSession()
    await startVoiceSession('gemini')

    const openai = startOpenAiSession.mock.calls[0][0].instructions
    const gemini = startGeminiSession.mock.calls[0][0].instructions
    // Identical apart from the wall-clock line each session stamps at start.
    const withoutClock = (s: string): string => s.replace(/Current local datetime:.*\n/, '')
    expect(withoutClock(openai)).toBe(withoutClock(gemini))
    for (const text of [openai, gemini]) {
      expect(text).toContain('<about_user>')
      expect(text).toContain('Name: Ada')
      expect(text).toContain('- Ships fast.')
      expect(text).toContain('The user speaks ONLY these languages: Russian, English')
    }
  })
})
