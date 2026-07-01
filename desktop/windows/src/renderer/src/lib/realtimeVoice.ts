import type { Preferences } from './preferences'
import type { LocalTtsStatus } from '../../../shared/types'

export type RealtimeVoiceProvider = NonNullable<Preferences['realtimeVoiceProvider']>

export type RealtimeVoiceReadiness = {
  enabled: boolean
  provider: RealtimeVoiceProvider
  ready: boolean
  label: string
  keyPath: string
  transcriptionPath: string
  reason?: string
}

export function realtimeVoiceReadiness(
  preferences: Preferences,
  localTtsStatus?: LocalTtsStatus | null
): RealtimeVoiceReadiness {
  const provider = preferences.realtimeVoiceProvider ?? 'omi-relay'
  const enabled = !!preferences.realtimeVoiceEnabled
  if (provider === 'local-kokoro') {
    const ready = enabled && Boolean(localTtsStatus?.available)
    return {
      enabled,
      provider,
      ready,
      label: 'Local Kokoro',
      keyPath: 'Local model runtime',
      transcriptionPath: 'Omi /v4/listen remains active for transcription',
      reason: ready
        ? undefined
        : (localTtsStatus?.reason ?? 'Local Kokoro TTS runtime is not ready')
    }
  }
  const relayConfigured = !!import.meta.env.VITE_OMI_REALTIME_VOICE_URL
  return {
    enabled,
    provider,
    ready: enabled && relayConfigured,
    label: 'Omi realtime relay',
    keyPath: 'Omi account session',
    transcriptionPath: 'Omi /v4/listen remains active for transcription',
    reason: relayConfigured ? undefined : 'Realtime relay URL is not configured'
  }
}
