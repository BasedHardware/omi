// src/main/ipc/deepgramTts.ts
// Deepgram Text-to-Speech via REST API
import { ipcMain } from 'electron'

const DEEPGRAM_TTS_URL = 'https://api.deepgram.com/v1/speak'

export type DeepgramTtsOptions = {
  text: string
  voice?: string //aura-asteria-en, aura-athena-en, etc.
  encoding?: 'mp3' | 'wav' | 'pcm' | 'opus' | 'flac'
  container?: 'mp3' | 'wav' | 'none'
  sampleRate?: number
}

export type DeepgramTtsResult = {
  ok: boolean
  audio?: ArrayBuffer
  contentType?: string
  error?: string
}

// Popular Deepgram Aura voices
export const DEEPGRAM_VOICES = [
  { id: 'aura-asteria-en', name: 'Asteria (Female, Natural)', lang: 'en' },
  { id: 'aura-athena-en', name: 'Athena (Female, Warm)', lang: 'en' },
  { id: 'aura-arcas-en', name: 'Arcas (Male, Confident)', lang: 'en' },
  { id: 'aura-orpheus-en', name: 'Orpheus (Male, Authoritative)', lang: 'en' },
  { id: 'aura-helios-en', name: 'Helios (Male, Friendly)', lang: 'en' },
  { id: 'aura-luna-en', name: 'Luna (Female, Soft)', lang: 'en' }
] as const

let deepgramApiKey = ''

export function setDeepgramTtsApiKey(key: string): void {
  deepgramApiKey = key
}

export async function synthesizeSpeech(options: DeepgramTtsOptions): Promise<DeepgramTtsResult> {
  if (!deepgramApiKey) {
    return { ok: false, error: 'Deepgram API key not configured' }
  }

  if (!options.text || !options.text.trim()) {
    return { ok: false, error: 'No text provided' }
  }

  try {
    const params = new URLSearchParams({
      model: 'aura-asteria-en',
      encoding: options.encoding || 'mp3'
    })

    if (options.voice) params.set('model', options.voice)
    if (options.sampleRate) params.set('sample_rate', String(options.sampleRate))

    const url = `${DEEPGRAM_TTS_URL}?${params.toString()}`

    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Token ${deepgramApiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text: options.text })
    })

    if (!res.ok) {
      const errorText = await res.text().catch(() => 'Unknown error')
      return { ok: false, error: `Deepgram TTS failed (${res.status}): ${errorText}` }
    }

    const arrayBuffer = await res.arrayBuffer()
    const contentType = res.headers.get('content-type') || 'audio/mpeg'

    return { ok: true, audio: arrayBuffer, contentType }
  } catch (e) {
    return { ok: false, error: `Deepgram TTS error: ${(e as Error).message}` }
  }
}

export function registerDeepgramTtsHandlers(): void {
  ipcMain.handle('deepgram-tts:synthesize', async (_e, options: DeepgramTtsOptions) => {
    const result = await synthesizeSpeech(options)
    if (!result.ok) {
      return { ok: false, error: result.error }
    }
    // Convert ArrayBuffer to Uint8Array for IPC transfer
    return {
      ok: true,
      audio: result.audio ? Array.from(new Uint8Array(result.audio)) : undefined,
      contentType: result.contentType
    }
  })

  ipcMain.handle('deepgram-tts:voices', async () => {
    return DEEPGRAM_VOICES
  })
}
