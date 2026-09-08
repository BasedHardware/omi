import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { LiveServerMessage } from '@google/genai'
import type { VoicePlayer } from './pcmPlayer'
import type { ProviderSessionCallbacks } from './providerSession'

// geminiSession pulls the AudioWorklet/mic graph transitively (pcmPlayer imports
// a `?worker&url` asset, capture pulls Web Audio). Stub the heavy bits so the
// pure message-handler logic is testable in the node env — base64ToBytes stays a
// real passthrough so we can assert the enqueued payload.
vi.mock('@google/genai', () => ({ GoogleGenAI: vi.fn(), Modality: { AUDIO: 'audio' } }))
vi.mock('../apiClient', () => ({ desktopApi: { post: vi.fn() } }))
vi.mock('../audio', () => ({ acquireMicStream: vi.fn() }))
vi.mock('../capture/pipelineHandle', () => ({ makePipelineHandle: vi.fn() }))
vi.mock('../capture/pcmPipeline', () => ({ createPcmPipeline: vi.fn() }))
vi.mock('./pcmPlayer', () => ({
  createVoicePlayer: vi.fn(),
  int16ToBase64: vi.fn(),
  base64ToBytes: (s: string) => new TextEncoder().encode(s)
}))

import { createGeminiMessageHandler } from './geminiSession'

function makePlayer(): VoicePlayer & Record<string, ReturnType<typeof vi.fn>> {
  return {
    enqueuePcm16: vi.fn(),
    flush: vi.fn(),
    clear: vi.fn(),
    setSinkId: vi.fn(),
    close: vi.fn()
  } as VoicePlayer & Record<string, ReturnType<typeof vi.fn>>
}

function makeCb(): ProviderSessionCallbacks {
  return {
    onConnected: vi.fn(),
    onFatal: vi.fn(),
    onSpeakingStart: vi.fn(),
    onSpeakingEnd: vi.fn(),
    onUtterance: vi.fn(),
    onUsage: vi.fn()
  }
}

// Message builders for the Gemini Live serverContent shape the handler reads.
const audio = (data: string): LiveServerMessage =>
  ({
    serverContent: { modelTurn: { parts: [{ inlineData: { data, mimeType: 'audio/pcm' } }] } }
  }) as unknown as LiveServerMessage
const interrupted = (): LiveServerMessage =>
  ({ serverContent: { interrupted: true } }) as unknown as LiveServerMessage
const turnComplete = (): LiveServerMessage =>
  ({ serverContent: { turnComplete: true } }) as unknown as LiveServerMessage

describe('createGeminiMessageHandler barge-in gate', () => {
  let player: ReturnType<typeof makePlayer>
  let cb: ProviderSessionCallbacks
  let handle: (msg: LiveServerMessage) => void

  beforeEach(() => {
    player = makePlayer()
    cb = makeCb()
    handle = createGeminiMessageHandler({ isStopped: () => false, getPlayer: () => player, cb })
  })

  it('REGRESSION: drops the interrupted generation trailing audio, resumes on the next turn', () => {
    // Generation 1 audio → enqueued.
    handle(audio('g1-chunk-a'))
    expect(player.enqueuePcm16).toHaveBeenCalledTimes(1)

    // Barge-in: player flushed AND the gate closes.
    handle(interrupted())
    expect(player.clear).toHaveBeenCalledTimes(1)

    // Trailing audio for the SAME (now interrupted) generation, arriving in a
    // LATER message — the bug: player.clear() already ran, so pre-fix this got
    // re-enqueued and bled stale audio over the user. Must be dropped now.
    handle(audio('g1-trailing'))
    expect(player.enqueuePcm16).toHaveBeenCalledTimes(1) // still 1 — dropped

    // Turn boundary closes the interrupted generation and re-opens the gate.
    handle(turnComplete())

    // Generation 2 (the reply to the user's barge-in) must play again.
    handle(audio('g2-chunk-a'))
    expect(player.enqueuePcm16).toHaveBeenCalledTimes(2)
    expect(player.enqueuePcm16).toHaveBeenLastCalledWith(new TextEncoder().encode('g2-chunk-a'))
  })

  it('does not gate audio for an uninterrupted generation', () => {
    handle(audio('chunk-a'))
    handle(audio('chunk-b'))
    handle(turnComplete())
    handle(audio('next-turn'))
    expect(player.enqueuePcm16).toHaveBeenCalledTimes(3)
    expect(player.clear).not.toHaveBeenCalled()
  })

  it('drops trailing audio delivered in the same message as the interrupt', () => {
    handle(audio('g1'))
    // Interrupt + trailing parts in one serverContent payload.
    handle({
      serverContent: {
        interrupted: true,
        modelTurn: { parts: [{ inlineData: { data: 'raced', mimeType: 'audio/pcm' } }] }
      }
    } as unknown as LiveServerMessage)
    expect(player.clear).toHaveBeenCalledTimes(1)
    expect(player.enqueuePcm16).toHaveBeenCalledTimes(1) // 'raced' dropped
  })

  it('re-arms the gate even when interrupt and turnComplete share a message', () => {
    handle(audio('g1'))
    handle({
      serverContent: { interrupted: true, turnComplete: true }
    } as unknown as LiveServerMessage)
    // This message: cleared, gate closed then re-opened by turnComplete.
    expect(player.clear).toHaveBeenCalledTimes(1)
    // Next generation plays normally.
    handle(audio('g2'))
    expect(player.enqueuePcm16).toHaveBeenCalledTimes(2)
  })

  it('ignores messages once the session is stopped', () => {
    let stopped = false
    const h = createGeminiMessageHandler({ isStopped: () => stopped, getPlayer: () => player, cb })
    stopped = true
    h(audio('after-stop'))
    expect(player.enqueuePcm16).not.toHaveBeenCalled()
  })
})
