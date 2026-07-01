import { describe, expect, it } from 'vitest'
import type { LocalTtsStatus } from '../../../shared/types'
import type { Preferences } from './preferences'
import { realtimeVoiceReadiness } from './realtimeVoice'

const basePreferences: Preferences = {
  captionIntervalMs: 2000,
  showRecordingBadge: true,
  reduceMotion: false,
  language: 'en',
  chatHistoryMode: 'infinite',
  realtimeVoiceProvider: 'omi-relay'
}

const readyLocalTts: LocalTtsStatus = {
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

describe('realtimeVoiceReadiness', () => {
  it('keeps voice disabled until the user opts in', () => {
    const readiness = realtimeVoiceReadiness(basePreferences)
    expect(readiness.enabled).toBe(false)
    expect(readiness.ready).toBe(false)
    expect(readiness.transcriptionPath).toContain('/v4/listen')
  })

  it('routes local Kokoro readiness without BYOK state', () => {
    const readiness = realtimeVoiceReadiness(
      {
        ...basePreferences,
        realtimeVoiceEnabled: true,
        realtimeVoiceProvider: 'local-kokoro'
      },
      readyLocalTts
    )

    expect(readiness.ready).toBe(true)
    expect(readiness.label).toBe('Local Kokoro')
    expect(readiness.keyPath).toBe('Local model runtime')
  })

  it('does not report local Kokoro ready before the runtime is available', () => {
    const readiness = realtimeVoiceReadiness({
      ...basePreferences,
      realtimeVoiceEnabled: true,
      realtimeVoiceProvider: 'local-kokoro'
    })

    expect(readiness.ready).toBe(false)
    expect(readiness.reason).toBe('Local Kokoro TTS runtime is not ready')
  })

  it('reports the relay as unavailable when no relay URL is configured', () => {
    const readiness = realtimeVoiceReadiness({
      ...basePreferences,
      realtimeVoiceEnabled: true,
      realtimeVoiceProvider: 'omi-relay'
    })

    expect(readiness.ready).toBe(false)
    expect(readiness.reason).toBe('Realtime relay URL is not configured')
  })
})
