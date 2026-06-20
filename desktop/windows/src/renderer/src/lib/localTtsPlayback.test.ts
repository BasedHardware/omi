import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LocalTtsStatus } from '../../../shared/types'
import type { Preferences } from './preferences'
import { speakAssistantText } from './localTtsPlayback'

const enabledPrefs: Preferences = {
  captionIntervalMs: 2000,
  showRecordingBadge: true,
  reduceMotion: false,
  language: 'en',
  chatHistoryMode: 'infinite',
  chatRuntimeMode: 'auto',
  realtimeVoiceEnabled: true,
  realtimeVoiceProvider: 'local-kokoro',
  localTtsVoice: 'af_heart'
}

const readyStatus: LocalTtsStatus = {
  backend: 'kokoro',
  healthy: true,
  available: true,
  managed: true,
  runtime: {
    kind: 'kokoro-js',
    installState: 'installed',
    model: 'onnx-community/Kokoro-82M-v1.0-ONNX',
    voice: 'af_heart',
    canInstall: true
  },
  checkedAt: 1
}

afterEach(() => {
  vi.restoreAllMocks()
  delete (globalThis as { window?: unknown }).window
})

describe('speakAssistantText', () => {
  it('skips playback when local Kokoro voice is not selected', async () => {
    const localTtsStatus = vi.fn(async () => readyStatus)
    const localTtsSynthesize = vi.fn()
    ;(globalThis as { window?: unknown }).window = {
      omi: { localTtsStatus, localTtsSynthesize }
    }

    const result = await speakAssistantText('hello', {
      getPrefs: () => ({ ...enabledPrefs, realtimeVoiceProvider: 'omi-relay' })
    })

    expect(result).toBe('skipped')
    expect(localTtsStatus).not.toHaveBeenCalled()
    expect(localTtsSynthesize).not.toHaveBeenCalled()
  })

  it('synthesizes assistant text and plays the generated local file URL', async () => {
    const playAudio = vi.fn(async () => undefined)
    const localTtsStatus = vi.fn(async () => readyStatus)
    const localTtsSynthesize = vi.fn(async () => ({
      audioPath: 'C:\\Users\\me\\AppData\\Local\\Omi\\LocalTTS\\audio\\reply.wav',
      audioUrl: 'file:///C:/Users/me/AppData/Local/Omi/LocalTTS/audio/reply.wav',
      mimeType: 'audio/wav' as const
    }))
    ;(globalThis as { window?: unknown }).window = {
      omi: { localTtsStatus, localTtsSynthesize }
    }

    const result = await speakAssistantText(' assistant reply ', {
      getPrefs: () => enabledPrefs,
      playAudio
    })

    expect(result).toBe('played')
    expect(localTtsSynthesize).toHaveBeenCalledWith({
      text: 'assistant reply',
      voice: 'af_heart'
    })
    expect(playAudio).toHaveBeenCalledWith(
      'file:///C:/Users/me/AppData/Local/Omi/LocalTTS/audio/reply.wav'
    )
  })

  it('falls back to text-only when local Kokoro is unavailable', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const localTtsSynthesize = vi.fn()
    ;(globalThis as { window?: unknown }).window = {
      omi: {
        localTtsStatus: vi.fn(async () => ({
          ...readyStatus,
          healthy: false,
          available: false,
          runtime: { ...readyStatus.runtime, installState: 'unsupported', canInstall: false },
          reason: 'unsupported'
        })),
        localTtsSynthesize
      }
    }

    const result = await speakAssistantText('assistant reply', {
      getPrefs: () => enabledPrefs,
      playAudio: vi.fn()
    })

    expect(result).toBe('failed')
    expect(localTtsSynthesize).not.toHaveBeenCalled()
  })

  it('synthesizes assistant text through ElevenLabs when selected', async () => {
    const playAudio = vi.fn(async () => undefined)
    const elevenLabsTtsSynthesize = vi.fn(async () => ({
      audioPath: 'C:\\Users\\me\\AppData\\Local\\Omi\\elevenlabs-tts\\reply.mp3',
      audioUrl: 'file:///C:/Users/me/AppData/Local/Omi/elevenlabs-tts/reply.mp3',
      mimeType: 'audio/mpeg' as const
    }))
    ;(globalThis as { window?: unknown }).window = {
      omi: {
        byokStatus: vi.fn(async () => ({
          activeChatProvider: null,
          providers: {
            openai: { provider: 'openai', configured: false },
            anthropic: { provider: 'anthropic', configured: false },
            gemini: { provider: 'gemini', configured: false },
            openrouter: { provider: 'openrouter', configured: false },
            deepgram: { provider: 'deepgram', configured: false },
            elevenlabs: { provider: 'elevenlabs', configured: true }
          }
        })),
        elevenLabsTtsSynthesize
      }
    }

    const result = await speakAssistantText(' assistant reply ', {
      getPrefs: () => ({
        ...enabledPrefs,
        realtimeVoiceProvider: 'elevenlabs',
        elevenLabsVoiceId: 'voice_123'
      }),
      playAudio
    })

    expect(result).toBe('played')
    expect(elevenLabsTtsSynthesize).toHaveBeenCalledWith({
      text: 'assistant reply',
      voiceId: 'voice_123'
    })
    expect(playAudio).toHaveBeenCalledWith(
      'file:///C:/Users/me/AppData/Local/Omi/elevenlabs-tts/reply.mp3'
    )
  })
})
