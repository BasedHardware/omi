import { app } from 'electron'
import { mkdir, readdir, rm, stat, writeFile } from 'fs/promises'
import { randomUUID } from 'crypto'
import { join } from 'path'
import { pathToFileURL } from 'url'
import type {
  ElevenLabsTtsSynthesizeRequest,
  ElevenLabsTtsSynthesizeResult
} from '../../shared/types'
import { loadByokKey } from '../byok/store'

type FetchLike = typeof fetch

export type ElevenLabsTtsOptions = {
  fetchImpl?: FetchLike
  now?: () => number
  audioDir?: string
}

const DEFAULT_VOICE_ID = 'JBFqnCBsd6RMkjVDRZzb'
const DEFAULT_MODEL_ID = 'eleven_multilingual_v2'
const DEFAULT_OUTPUT_FORMAT = 'mp3_44100_128'
const MAX_TTS_CHARS = 4000
const AUDIO_RETENTION_MS = 24 * 60 * 60 * 1000

function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, ' ').slice(0, MAX_TTS_CHARS)
}

function normalizeToken(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim()
  return trimmed || fallback
}

function audioRoot(options: ElevenLabsTtsOptions): string {
  return options.audioDir ?? join(app.getPath('userData'), 'elevenlabs-tts')
}

async function cleanupOldAudio(dir: string, now: () => number): Promise<void> {
  const cutoff = now() - AUDIO_RETENTION_MS
  const entries = await readdir(dir, { withFileTypes: true }).catch(() => [])
  await Promise.all(
    entries
      .filter((entry) => entry.isFile() && entry.name.endsWith('.mp3'))
      .map(async (entry) => {
        const path = join(dir, entry.name)
        const info = await stat(path).catch(() => null)
        if (info && info.mtimeMs < cutoff) await rm(path, { force: true })
      })
  )
}

export async function synthesizeWithElevenLabs(
  request: ElevenLabsTtsSynthesizeRequest,
  options: ElevenLabsTtsOptions = {}
): Promise<ElevenLabsTtsSynthesizeResult> {
  const key = loadByokKey('elevenlabs')
  if (!key) throw new Error('Save an ElevenLabs key before using ElevenLabs TTS')

  const text = normalizeText(request.text)
  if (!text) throw new Error('Text is required for ElevenLabs TTS')

  const voiceId = encodeURIComponent(normalizeToken(request.voiceId, DEFAULT_VOICE_ID))
  const modelId = normalizeToken(request.modelId, DEFAULT_MODEL_ID)
  const outputFormat = encodeURIComponent(
    normalizeToken(request.outputFormat, DEFAULT_OUTPUT_FORMAT)
  )
  const fetchImpl = options.fetchImpl ?? fetch
  const response = await fetchImpl(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}?output_format=${outputFormat}`,
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'xi-api-key': key
      },
      body: JSON.stringify({
        text,
        model_id: modelId
      })
    }
  )
  if (!response.ok) {
    throw new Error(`ElevenLabs TTS failed with HTTP ${response.status}`)
  }

  const dir = audioRoot(options)
  await mkdir(dir, { recursive: true })
  await cleanupOldAudio(dir, options.now ?? Date.now).catch(() => undefined)
  const audioPath = join(dir, `elevenlabs-${Date.now()}-${randomUUID()}.mp3`)
  const bytes = Buffer.from(await response.arrayBuffer())
  await writeFile(audioPath, bytes)
  return {
    audioPath,
    audioUrl: pathToFileURL(audioPath).toString(),
    mimeType: 'audio/mpeg'
  }
}
