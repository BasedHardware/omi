export type TTSVoice = {
  name: string
  lang: string
  localService: boolean
}

export type TTSSettings = {
  enabled: boolean
  rate: number // 0.5 - 2.0, default 1.0
  pitch: number // 0.0 - 2.0, default 1.0
  volume: number // 0.0 - 1.0, default 1.0
  voiceName: string | null // null = system default
}

let isSpeaking = false
let onSpeakingChange: ((speaking: boolean) => void) | null = null

function getSynthesis(): SpeechSynthesis | null {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    return window.speechSynthesis
  }
  return null
}

export function getAvailableVoices(): TTSVoice[] {
  const synth = getSynthesis()
  if (!synth) return []

  const voices = synth.getVoices()
  return voices.map((v) => ({
    name: v.name,
    lang: v.lang,
    localService: v.localService
  }))
}

export function getPreferredVoice(settings: TTSSettings): SpeechSynthesisVoice | null {
  const synth = getSynthesis()
  if (!synth) return null

  const voices = synth.getVoices()

  // If a specific voice is configured, try to find it
  if (settings.voiceName) {
    const match = voices.find((v) => v.name === settings.voiceName)
    if (match) return match
  }

  // Otherwise, prefer a natural English voice
  const preferred = voices.find(
    (v) =>
      v.lang.startsWith('en') &&
      (v.name.includes('Natural') || v.name.includes('Enhanced') || v.name.includes('Premium'))
  )
  if (preferred) return preferred

  // Fall back to first English voice
  return voices.find((v) => v.lang.startsWith('en')) || voices[0] || null
}

export function speak(
  text: string,
  settings: TTSSettings,
  callbacks?: { onEnd?: () => void; onError?: (error: string) => void }
): void {
  const synth = getSynthesis()
  if (!synth || !text.trim()) {
    callbacks?.onEnd?.()
    return
  }

  // Cancel any current speech
  stop()

  const utterance = new SpeechSynthesisUtterance(text)
  const voice = getPreferredVoice(settings)

  if (voice) {
    utterance.voice = voice
  }

  utterance.rate = Math.max(0.5, Math.min(2.0, settings.rate))
  utterance.pitch = Math.max(0.0, Math.min(2.0, settings.pitch))
  utterance.volume = Math.max(0.0, Math.min(1.0, settings.volume))

  utterance.onstart = () => {
    isSpeaking = true
    onSpeakingChange?.(true)
  }

  utterance.onend = () => {
    isSpeaking = false
    onSpeakingChange?.(false)
    callbacks?.onEnd?.()
  }

  utterance.onerror = (event) => {
    // 'canceled' is expected when we call stop()
    if (event.error !== 'canceled') {
      console.error('[tts] error:', event.error)
      callbacks?.onError?.(event.error)
    }
    isSpeaking = false
    onSpeakingChange?.(false)
    callbacks?.onEnd?.()
  }

  synth.speak(utterance)
}

export function stop(): void {
  const synth = getSynthesis()
  if (synth) {
    synth.cancel()
  }
  isSpeaking = false
  onSpeakingChange?.(false)
}

export function isTTSSpeaking(): boolean {
  return isSpeaking
}

export function setOnSpeakingChange(cb: ((speaking: boolean) => void) | null): void {
  onSpeakingChange = cb
}

// Resume speech synthesis after user interaction (Chrome autoplay policy)
export function resumeAfterInteraction(): void {
  const synth = getSynthesis()
  if (synth) {
    synth.resume()
  }
}
