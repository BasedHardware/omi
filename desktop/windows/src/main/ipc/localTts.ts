import { ipcMain } from 'electron'
import type { ElevenLabsTtsSynthesizeRequest, LocalTtsSynthesizeRequest } from '../../shared/types'
import { synthesizeWithElevenLabs } from '../elevenlabs/tts'
import { getManagedKokoroStatus, synthesizeWithManagedKokoro } from '../localTts/kokoroRuntime'

function normalizeSynthesizeRequest(raw: unknown): LocalTtsSynthesizeRequest {
  if (!raw || typeof raw !== 'object') throw new Error('Invalid local TTS request')
  const record = raw as Record<string, unknown>
  if (typeof record.text !== 'string') throw new Error('Text is required for local TTS')
  return {
    text: record.text,
    voice: typeof record.voice === 'string' ? record.voice : undefined,
    speed: typeof record.speed === 'number' ? record.speed : undefined
  }
}

function normalizeElevenLabsSynthesizeRequest(raw: unknown): ElevenLabsTtsSynthesizeRequest {
  if (!raw || typeof raw !== 'object') throw new Error('Invalid ElevenLabs TTS request')
  const record = raw as Record<string, unknown>
  if (typeof record.text !== 'string') throw new Error('Text is required for ElevenLabs TTS')
  return {
    text: record.text,
    voiceId: typeof record.voiceId === 'string' ? record.voiceId : undefined,
    modelId: typeof record.modelId === 'string' ? record.modelId : undefined,
    outputFormat: typeof record.outputFormat === 'string' ? record.outputFormat : undefined
  }
}

export function registerLocalTtsHandlers(): void {
  ipcMain.handle('omi-local-tts:status', async () => {
    return getManagedKokoroStatus()
  })
  ipcMain.handle('omi-local-tts:synthesize', async (_e, raw: unknown) => {
    return synthesizeWithManagedKokoro(normalizeSynthesizeRequest(raw))
  })
  ipcMain.handle('omi-elevenlabs-tts:synthesize', async (_e, raw: unknown) => {
    return synthesizeWithElevenLabs(normalizeElevenLabsSynthesizeRequest(raw))
  })
}
