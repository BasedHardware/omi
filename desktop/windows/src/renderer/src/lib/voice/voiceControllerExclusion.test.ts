// @vitest-environment jsdom
//
// Regression for the "two/three voices at once" bug (2026-07-20): a `fromVoice`
// cascade reply (`speakText`) played simultaneously with the realtime hub voice
// when a hub tool call degraded. The fix routes both lanes through
// `audibleOutputArbiter`: while a realtime lane is audible, `speakText` must DROP
// its spoken output (Mac denies the TTS lease while a realtime turn owns it).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('../analytics', () => ({ trackEvent: vi.fn() }))
vi.mock('./tokenMint', () => ({
  mintRealtimeToken: vi.fn(),
  MintError: class MintError extends Error {}
}))
vi.mock('./usageReport', () => ({ reportRealtimeUsage: vi.fn() }))
vi.mock('./openaiSession', () => ({ startOpenAiSession: vi.fn() }))
vi.mock('./geminiSession', () => ({ startGeminiSession: vi.fn() }))
// A single small chunk so speakText takes the direct synth→play path.
vi.mock('./ttsChunker', () => ({ chunkTts: (t: string) => (t.trim() ? [t] : []) }))
const { synthesizeTts } = vi.hoisted(() => ({ synthesizeTts: vi.fn() }))
vi.mock('./tts', () => ({ synthesizeTts, DEFAULT_TTS_VOICE: 'v' }))

import { speakText } from './voiceController'
import {
  beginRealtimeAudible,
  endRealtimeAudible,
  __resetAudibleArbiterForTests
} from './audibleOutputArbiter'

beforeEach(() => {
  synthesizeTts.mockReset()
  synthesizeTts.mockResolvedValue(new Blob(['x'], { type: 'audio/mpeg' }))
  // voiceController registers its real resetTtsPipeline as the stop hook at import;
  // re-import isn't needed — just clear the realtime-speaker set between tests.
  __resetAudibleArbiterForTests()
  // jsdom lacks the capture bridge + Audio playback; stub what speakText touches.
  ;(window as unknown as { omi?: unknown }).omi = { captureCommand: vi.fn() }
  ;(globalThis as unknown as { Audio: unknown }).Audio = class {
    src = ''
    onended: (() => void) | null = null
    onerror: (() => void) | null = null
    setSinkId = vi.fn(async () => {})
    play = vi.fn(async () => {
      // Resolve the playback wait immediately so the test doesn't hang.
      this.onended?.()
    })
    pause = vi.fn()
  }
  ;(globalThis.URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(
    () => 'blob:x'
  )
  ;(globalThis.URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
})
afterEach(() => {
  __resetAudibleArbiterForTests()
})

describe('speakText — single-audible-owner exclusion', () => {
  it('DROPS the cascade reply (no synthesis) while a realtime lane is audible', async () => {
    const token = beginRealtimeAudible()
    await speakText('the duplicate spoken answer')
    expect(synthesizeTts).not.toHaveBeenCalled()
    endRealtimeAudible(token)
  })

  it('speaks normally when no realtime lane is audible (cascade route unaffected)', async () => {
    await speakText('a normal cascade reply')
    expect(synthesizeTts).toHaveBeenCalledTimes(1)
  })

  it('resumes speaking once the realtime lane has ended', async () => {
    const token = beginRealtimeAudible()
    await speakText('suppressed')
    expect(synthesizeTts).not.toHaveBeenCalled()
    endRealtimeAudible(token)
    await speakText('now allowed')
    expect(synthesizeTts).toHaveBeenCalledTimes(1)
  })
})
