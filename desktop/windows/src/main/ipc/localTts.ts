import { ipcMain } from 'electron'
import type { LocalTtsSynthesizeRequest } from '../../shared/types'
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

export function registerLocalTtsHandlers(): void {
  ipcMain.handle('omi-local-tts:status', async () => {
    return getManagedKokoroStatus()
  })
  ipcMain.handle('omi-local-tts:synthesize', async (_e, raw: unknown) => {
    return synthesizeWithManagedKokoro(normalizeSynthesizeRequest(raw))
  })
}
