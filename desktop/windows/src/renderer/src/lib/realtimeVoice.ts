import type { ByokStatus } from '../../../shared/types'
import type { Preferences } from './preferences'

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
  byokStatus: ByokStatus | null
): RealtimeVoiceReadiness {
  const provider = preferences.realtimeVoiceProvider ?? 'omi-relay'
  const enabled = !!preferences.realtimeVoiceEnabled
  if (provider === 'openai-byok') {
    const configured = !!byokStatus?.providers.openai.configured
    return {
      enabled,
      provider,
      ready: enabled && configured,
      label: 'OpenAI Realtime',
      keyPath: 'OpenAI BYOK key',
      transcriptionPath: 'Omi /v4/listen remains active for transcription',
      reason: configured ? undefined : 'OpenAI key is not saved'
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
