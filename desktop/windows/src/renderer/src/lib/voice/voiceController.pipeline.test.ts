// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest'

// Keep voiceController's import graph side-effect-free in the test env — only the
// TTS pipeline is exercised here.
vi.mock('../analytics', () => ({ trackEvent: vi.fn() }))
vi.mock('./tokenMint', () => ({
  mintRealtimeToken: vi.fn(),
  MintError: class MintError extends Error {}
}))
vi.mock('./usageReport', () => ({ reportRealtimeUsage: vi.fn() }))
vi.mock('./openaiSession', () => ({ startOpenAiSession: vi.fn() }))
vi.mock('./geminiSession', () => ({ startGeminiSession: vi.fn() }))
vi.mock('./tts', () => ({ synthesizeTts: vi.fn(), DEFAULT_TTS_VOICE: 'test-voice' }))

import { synthesizeTts } from './tts'
import { trackEvent } from '../analytics'
import {
  speakText,
  interruptCurrentResponse,
  stopVoiceSession,
  setVoiceOutputDevice,
  FILLER_PHRASES
} from './voiceController'

// --- controllable Web Speech + Audio + URL doubles --------------------------
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

// When set, the NEXT setSinkId call blocks on this promise — lets a test open
// the barge-in-during-device-selection window in playTtsBlob.
let sinkIdBlocker: { promise: Promise<void>; resolve: () => void } | null = null
class MockAudio {
  src = ''
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  setSinkId = vi.fn(async () => {
    if (sinkIdBlocker) await sinkIdBlocker.promise
  })
  play = vi.fn(async () => {
    audios.push(this as unknown as MockAudio)
  })
  pause = vi.fn()
}
let audios: MockAudio[] = []

const deferred = <T>(): {
  promise: Promise<T>
  resolve: (v: T) => void
  reject: (e: unknown) => void
} => {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}
// Drain microtasks + any 0ms timers.
const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

// A two-chunk reply: a short first sentence (< first-chunk preferred) then a long
// remainder → chunkTts yields exactly two chunks.
const TWO_CHUNK = 'This is the first spoken sentence and it is long enough. ' + 'x'.repeat(400)

const synthMock = synthesizeTts as unknown as Mock

beforeEach(() => {
  lastUtterance = null
  audios = []
  sinkIdBlocker = null
  speak.mockClear()
  cancel.mockClear()
  resume.mockClear()
  synthMock.mockReset()
  ;(trackEvent as unknown as Mock).mockClear()
  ;(globalThis as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance =
    MockUtterance
  ;(globalThis as unknown as { Audio: unknown }).Audio = MockAudio
  ;(window as unknown as { speechSynthesis: unknown }).speechSynthesis = { speak, cancel, resume }
  ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => 'blob:x')
  ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
})

afterEach(() => {
  // Fully reset module singletons (gate + pipeline timers) between tests.
  stopVoiceSession()
})

describe('speakText — chunked pipeline', () => {
  it('begins synthesizing chunk N+1 while chunk N is playing (pipelining)', async () => {
    const d0 = deferred<Blob>()
    const d1 = deferred<Blob>()
    synthMock.mockReturnValueOnce(d0.promise).mockReturnValueOnce(d1.promise)

    const done = speakText(TWO_CHUNK)
    await flush()
    // Only chunk 0 is being synthesized so far; nothing is playing yet.
    expect(synthMock).toHaveBeenCalledTimes(1)
    expect(audios.length).toBe(0)

    d0.resolve(new Blob(['a']))
    await flush()
    // Chunk 0 is now playing AND chunk 1's synthesis was kicked off (pipelined).
    expect(audios.length).toBe(1)
    expect(synthMock).toHaveBeenCalledTimes(2)

    audios[0].onended?.()
    d1.resolve(new Blob(['b']))
    await flush()
    expect(audios.length).toBe(2)
    audios[1].onended?.()
    await done
  })

  it('falls back to the system voice + fallback telemetry when a chunk synth fails', async () => {
    synthMock.mockRejectedValueOnce(new Error('boom')) // single short chunk

    const done = speakText('short reply') // < 40 chars → one chunk, no filler
    await flush()
    expect(trackEvent).toHaveBeenCalledWith(
      'fallback_triggered',
      expect.objectContaining({ component: 'voice_tts', to: 'system_voice', outcome: 'degraded' })
    )
    // System voice spoke the chunk text.
    expect(speak).toHaveBeenCalledTimes(1)
    expect(lastUtterance?.text).toBe('short reply')

    lastUtterance?.onend?.()
    await done
  })
})

describe('speakText — filler', () => {
  it('plays a filler before the first real audio and cancels it when audio arrives', async () => {
    const d0 = deferred<Blob>()
    const d1 = deferred<Blob>()
    synthMock.mockReturnValueOnce(d0.promise).mockReturnValueOnce(d1.promise)

    const done = speakText(TWO_CHUNK)
    await flush()
    // Filler is speaking; no real audio yet.
    expect(speak).toHaveBeenCalledTimes(1)
    expect(FILLER_PHRASES).toContain(lastUtterance?.text)
    expect(audios.length).toBe(0)
    expect(cancel).not.toHaveBeenCalled()

    d0.resolve(new Blob(['a']))
    await flush()
    // First real audio arrived → filler cancelled, and it never speaks again.
    expect(cancel).toHaveBeenCalledTimes(1)
    expect(audios.length).toBe(1)
    speak.mockClear()

    audios[0].onended?.()
    d1.resolve(new Blob(['b']))
    await flush()
    audios[1].onended?.()
    await done
    expect(speak).not.toHaveBeenCalled() // no filler after real audio
  })

  it('does not play a filler for a short single-chunk reply (preserves prior behavior)', async () => {
    synthMock.mockResolvedValueOnce(new Blob(['a']))
    const done = speakText('short reply')
    await flush()
    expect(speak).not.toHaveBeenCalled()
    expect(audios.length).toBe(1)
    audios[0].onended?.()
    await done
  })
})

describe('interruptCurrentResponse — barge-in', () => {
  it('stops playback, cancels the filler, resolves the reply, and a later speak works', async () => {
    const d0 = deferred<Blob>()
    const d1 = deferred<Blob>()
    synthMock.mockReturnValueOnce(d0.promise).mockReturnValueOnce(d1.promise)

    const done = speakText(TWO_CHUNK)
    await flush()
    d0.resolve(new Blob(['a']))
    await flush()
    expect(audios.length).toBe(1) // chunk 0 playing

    interruptCurrentResponse()
    await flush()
    expect(audios[0].pause).toHaveBeenCalled() // playback stopped
    expect(cancel).toHaveBeenCalled() // filler cancelled
    await done // resolves promptly (→ useChat.speaking clears → orb glow clears)

    // A subsequent reply still works after an interrupt.
    synthMock.mockResolvedValueOnce(new Blob(['b']))
    const done2 = speakText('hello again')
    await flush()
    expect(audios.length).toBe(2)
    audios[1].onended?.()
    await done2
  })

  it('a barge-in during output-device selection never starts stale audio', async () => {
    // A non-default output device forces playTtsBlob's setSinkId await — the one
    // window where an interrupt could land after the chunk resolved but before
    // playback starts. The element must never play (stale audio) after barge-in.
    await setVoiceOutputDevice('device-1')
    try {
      const gate = deferred<void>()
      sinkIdBlocker = { promise: gate.promise, resolve: () => gate.resolve() }
      synthMock.mockResolvedValueOnce(new Blob(['a'])) // single short chunk, no filler

      const done = speakText('short reply')
      await flush() // synth resolved → playTtsBlob now blocked inside setSinkId
      expect(audios.length).toBe(0) // not playing yet — still selecting the sink

      interruptCurrentResponse() // barge-in DURING device selection
      gate.resolve() // sink selection completes only after the interrupt
      await flush()

      expect(audios.length).toBe(0) // stale audio never started
      await done // resolves promptly → orb glow clears
    } finally {
      await setVoiceOutputDevice('') // restore module sinkId for other tests
    }
  })
})
