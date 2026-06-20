import { describe, expect, it } from 'vitest'
import type { ByokStatus, LocalTtsStatus } from '../../../shared/types'
import type { Preferences } from './preferences'
import { realtimeVoiceReadiness } from './realtimeVoice'

const basePreferences: Preferences = {
  captionIntervalMs: 2000,
  showRecordingBadge: true,
  reduceMotion: false,
  language: 'en',
  chatHistoryMode: 'infinite',
  chatRuntimeMode: 'auto',
  realtimeVoiceProvider: 'omi-relay'
}

const byokStatus: ByokStatus = {
  activeChatProvider: null,
  providers: {
    openai: { provider: 'openai', configured: true },
    anthropic: { provider: 'anthropic', configured: false },
    gemini: { provider: 'gemini', configured: false },
    deepgram: { provider: 'deepgram', configured: false }
  }
}

const localTtsStatus: LocalTtsStatus = {
  backend: 'kokoro',
  healthy: false,
  available: false,
  managed: true,
  runtime: {
    kind: 'kokoro-js',
    installState: 'not_installed',
    model: 'onnx-community/Kokoro-82M-v1.0-ONNX',
    voice: 'af_heart',
    canInstall: true
  },
  checkedAt: 1
}

describe('realtimeVoiceReadiness', () => {
  it('keeps voice disabled until the user opts in', () => {
    const readiness = realtimeVoiceReadiness(basePreferences, byokStatus)
    expect(readiness.enabled).toBe(false)
    expect(readiness.ready).toBe(false)
    expect(readiness.transcriptionPath).toContain('/v4/listen')
  })

  it('uses the OpenAI BYOK key path when selected', () => {
    const readiness = realtimeVoiceReadiness(
      {
        ...basePreferences,
        realtimeVoiceEnabled: true,
        realtimeVoiceProvider: 'openai-byok'
      },
      byokStatus
    )
    expect(readiness.ready).toBe(true)
    expect(readiness.keyPath).toBe('OpenAI BYOK key')
  })

  it('reports a missing OpenAI key without affecting transcription', () => {
    const readiness = realtimeVoiceReadiness(
      {
        ...basePreferences,
        realtimeVoiceEnabled: true,
        realtimeVoiceProvider: 'openai-byok'
      },
      null
    )
    expect(readiness.ready).toBe(false)
    expect(readiness.reason).toBe('OpenAI key is not saved')
    expect(readiness.transcriptionPath).toContain('/v4/listen')
  })

  it('uses local Kokoro TTS readiness when selected', () => {
    const readiness = realtimeVoiceReadiness(
      {
        ...basePreferences,
        realtimeVoiceEnabled: true,
        realtimeVoiceProvider: 'local-kokoro'
      },
      byokStatus,
      localTtsStatus
    )
    expect(readiness.ready).toBe(true)
    expect(readiness.keyPath).toBe('On-device Kokoro-82M')
    expect(readiness.reason).toBe('Kokoro installs on first spoken reply')
    expect(readiness.transcriptionPath).toContain('/v4/listen')
  })

  it('reports local Kokoro unavailable without blocking transcription', () => {
    const readiness = realtimeVoiceReadiness(
      {
        ...basePreferences,
        realtimeVoiceEnabled: true,
        realtimeVoiceProvider: 'local-kokoro'
      },
      byokStatus,
      {
        ...localTtsStatus,
        runtime: { ...localTtsStatus.runtime, installState: 'unsupported', canInstall: false },
        reason: 'unsupported'
      }
    )
    expect(readiness.ready).toBe(false)
    expect(readiness.reason).toBe('unsupported')
    expect(readiness.transcriptionPath).toContain('/v4/listen')
  })
})
