// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Keep voiceController's import graph side-effect-free in the test env (these
// siblings are never exercised by playSystemVoice — we only need a clean import).
vi.mock('../analytics', () => ({ trackEvent: vi.fn() }))
vi.mock('./tokenMint', () => ({
  mintRealtimeToken: vi.fn(),
  MintError: class MintError extends Error {}
}))
vi.mock('./usageReport', () => ({ reportRealtimeUsage: vi.fn() }))
vi.mock('./openaiSession', () => ({ startOpenAiSession: vi.fn() }))
vi.mock('./geminiSession', () => ({ startGeminiSession: vi.fn() }))
vi.mock('./tts', () => ({ synthesizeTts: vi.fn(), DEFAULT_TTS_VOICE: 'test-voice' }))

// jsdom does not implement the Web Speech API — provide a controllable mock.
class MockUtterance {
  text: string
  onend: (() => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  constructor(text: string) {
    this.text = text
  }
}
let lastUtterance: MockUtterance | null = null
const speak = vi.fn((u: MockUtterance) => {
  lastUtterance = u
})
const cancel = vi.fn()
const resume = vi.fn()

import { playSystemVoice } from './voiceController'

beforeEach(() => {
  vi.useFakeTimers()
  lastUtterance = null
  speak.mockClear()
  cancel.mockClear()
  resume.mockClear()
  ;(globalThis as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance =
    MockUtterance
  ;(window as unknown as { speechSynthesis: unknown }).speechSynthesis = { speak, cancel, resume }
})
afterEach(() => {
  vi.useRealTimers()
})

// Regression for the C7 spoken-reply hang: Chromium stalls SpeechSynthesis on
// long utterances and never fires `onend`, which (before this guard) left the
// promise pending forever → echo gate + useChat.speaking + the bar orb/keepAlive
// wedged until an app restart.
describe('playSystemVoice — long-utterance hang guard', () => {
  it('resolves via the max-duration watchdog when onend never fires', async () => {
    const p = playSystemVoice('x'.repeat(600)) // 600 chars → 60s backstop
    let resolved = false
    void p.then(() => {
      resolved = true
    })
    expect(speak).toHaveBeenCalledTimes(1)

    // onend never arrives — before the cap the promise stays pending, and the
    // resume() pump keeps Chromium from silently stalling.
    await vi.advanceTimersByTimeAsync(30000)
    expect(resolved).toBe(false)
    expect(resume).toHaveBeenCalled()

    // Past the backstop it cancels the stuck utterance and resolves.
    await vi.advanceTimersByTimeAsync(31000)
    await p
    expect(resolved).toBe(true)
    expect(cancel).toHaveBeenCalled()
  })

  it('resolves promptly on onend and stops the pump/watchdog (no stray cancel)', async () => {
    const p = playSystemVoice('short reply')
    lastUtterance?.onend?.()
    await p

    // After a clean end, no timer should keep firing resume()/cancel().
    resume.mockClear()
    cancel.mockClear()
    await vi.advanceTimersByTimeAsync(130000)
    expect(resume).not.toHaveBeenCalled()
    expect(cancel).not.toHaveBeenCalled()
  })

  it('rejects on a real synth error (not interrupted/canceled)', async () => {
    const p = playSystemVoice('boom')
    lastUtterance?.onerror?.({ error: 'synthesis-failed' })
    await expect(p).rejects.toThrow(/system voice failed/)
  })
})
