import { describe, expect, it } from 'vitest'
import type { ByokStatus } from '../../../shared/types'
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
})
