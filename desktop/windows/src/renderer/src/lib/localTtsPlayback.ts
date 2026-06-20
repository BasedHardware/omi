import type { Preferences } from './preferences'
import { getPreferences } from './preferences'

type PlaybackResult = 'skipped' | 'played' | 'failed'

type PlaybackDeps = {
  getPrefs?: () => Preferences
  playAudio?: (audioUrl: string) => Promise<void>
}

let activeAudio: HTMLAudioElement | null = null

export async function speakAssistantText(
  text: string,
  deps: PlaybackDeps = {}
): Promise<PlaybackResult> {
  const cleanText = text.trim()
  const preferences = deps.getPrefs?.() ?? getPreferences()
  if (!cleanText || cleanText.startsWith('Error:')) return 'skipped'
  if (
    !preferences.realtimeVoiceEnabled ||
    (preferences.realtimeVoiceProvider !== 'local-kokoro' &&
      preferences.realtimeVoiceProvider !== 'elevenlabs')
  ) {
    return 'skipped'
  }

  try {
    if (preferences.realtimeVoiceProvider === 'elevenlabs') {
      const status = await window.omi.byokStatus()
      if (!status.providers.elevenlabs.configured) return 'failed'
      const result = await window.omi.elevenLabsTtsSynthesize({
        text: cleanText,
        voiceId: preferences.elevenLabsVoiceId
      })
      await (deps.playAudio ?? playAudioUrl)(result.audioUrl)
      return 'played'
    }

    const status = await window.omi.localTtsStatus()
    if (!status.available && !status.runtime.canInstall) return 'failed'
    const result = await window.omi.localTtsSynthesize({
      text: cleanText,
      voice: preferences.localTtsVoice
    })
    await (deps.playAudio ?? playAudioUrl)(result.audioUrl)
    return 'played'
  } catch (err) {
    console.warn('[local-tts] assistant speech failed:', err instanceof Error ? err.message : err)
    return 'failed'
  }
}

async function playAudioUrl(audioUrl: string): Promise<void> {
  if (typeof Audio === 'undefined') throw new Error('Audio playback is unavailable')
  if (activeAudio) {
    activeAudio.pause()
    activeAudio = null
  }
  const audio = new Audio(audioUrl)
  activeAudio = audio
  await audio.play()
}
