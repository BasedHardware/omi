import type { ByokStatus, LocalTtsStatus, RealtimeVoiceProvider } from '../../../shared/types'
import type { Preferences } from './preferences'

export type { RealtimeVoiceProvider } from '../../../shared/types'

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
  byokStatus: ByokStatus | null,
  localTtsStatus: LocalTtsStatus | null = null
): RealtimeVoiceReadiness {
  const provider = preferences.realtimeVoiceProvider ?? 'omi-relay'
  const enabled = !!preferences.realtimeVoiceEnabled
  if (provider === 'local-kokoro') {
    const canRun = !!localTtsStatus?.available || !!localTtsStatus?.runtime.canInstall
    return {
      enabled,
      provider,
      ready: enabled && canRun,
      label: 'Local Kokoro',
      keyPath: 'On-device Kokoro-82M',
      transcriptionPath: 'Omi /v4/listen remains active for transcription',
      reason: canRun
        ? localTtsStatus?.available
          ? undefined
          : 'Kokoro installs on first spoken reply'
        : (localTtsStatus?.reason ?? 'Local Kokoro TTS unavailable')
    }
  }
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
