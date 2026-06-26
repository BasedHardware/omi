import { useSettings } from '../stores/settings'

// Spoken replies via the Rust backend's /v1/tts/synthesize (gpt-4o-mini-tts),
// the same endpoint the Mac app uses. The response is 24 kHz mono PCM16, which
// we decode and play through Web Audio.

let ctx: AudioContext | null = null
let current: AudioBufferSourceNode | null = null

const TTS_RATE = 24000

function getCtx(): AudioContext {
  if (!ctx) ctx = new AudioContext()
  return ctx
}

function base64ToInt16(b64: string): Int16Array {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new Int16Array(bytes.buffer, 0, Math.floor(bytes.byteLength / 2))
}

export function stopSpeaking(): void {
  try {
    current?.stop()
  } catch {
    // already stopped
  }
  current = null
}

export async function speak(text: string): Promise<void> {
  const voice = useSettings.getState().settings?.ttsVoice || 'marin'
  const clean = text.replace(/```[\s\S]*?```/g, ' code block ').replace(/[#*_`>]/g, '').slice(0, 1200)
  if (!clean.trim()) return
  try {
    const res = await window.omi.api.requestBinary({
      method: 'POST',
      url: 'v1/tts/synthesize',
      base: 'rust',
      body: JSON.stringify({ text: clean, voice_id: voice })
    })
    if (res.status < 200 || res.status >= 300 || !res.base64) return

    const pcm = base64ToInt16(res.base64)
    const audioCtx = getCtx()
    const buffer = audioCtx.createBuffer(1, pcm.length, TTS_RATE)
    const channel = buffer.getChannelData(0)
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 0x8000

    stopSpeaking()
    const source = audioCtx.createBufferSource()
    source.buffer = buffer
    source.connect(audioCtx.destination)
    source.start()
    current = source
  } catch {
    // TTS is best-effort; stay silent on failure
  }
}
