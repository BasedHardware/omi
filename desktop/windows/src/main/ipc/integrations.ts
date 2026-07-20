import { ipcMain } from 'electron'
import { readStickyNotes } from '../integrations/stickyNotes'
import { connect, disconnect, isConnected, connectedEmail } from '../integrations/oauth'
import { fetchGmail, fetchCalendar } from '../integrations/google'
import {
  getSourceState,
  markProcessed,
  lastSyncAt,
  clearSyncState
} from '../integrations/syncState'
import { filterNew } from '../integrations/syncStateLogic'
import { translateToGlosses, defaultSignOpts } from '../integrations/signLanguage'
import type {
  GoogleStatus,
  GoogleSource,
  FetchNewResult,
  GmailItem,
  CalendarItem,
  TranslationResult
} from '../../shared/types'

// All integrations IPC lives here (3e Sticky Notes + 3d Gmail/Calendar) so
// concurrent chat/KG work doesn't conflict in index.ts.
function googleStatus(): GoogleStatus {
  const connected = isConnected()
  return {
    connected,
    email: connected ? connectedEmail() : undefined,
    lastSyncAt: connected ? lastSyncAt() || undefined : undefined
  }
}

export function registerIntegrationsHandlers(): void {
  ipcMain.handle('integrations:stickyNotes:read', async () => readStickyNotes())

  ipcMain.handle('integrations:google:connect', async (): Promise<GoogleStatus> => {
    await connect()
    return googleStatus()
  })

  ipcMain.handle('integrations:google:disconnect', async (): Promise<GoogleStatus> => {
    disconnect()
    clearSyncState()
    return googleStatus()
  })

  ipcMain.handle('integrations:google:status', async (): Promise<GoogleStatus> => googleStatus())

  ipcMain.handle(
    'integrations:google:gmailFetchNew',
    async (): Promise<FetchNewResult<GmailItem>> => {
      if (!isConnected()) return { ok: false, items: [], error: 'not_connected' }
      try {
        const all = await fetchGmail()
        return { ok: true, items: filterNew(all, getSourceState('gmail').processedIds) }
      } catch (e) {
        return { ok: false, items: [], error: (e as Error).message }
      }
    }
  )

  ipcMain.handle(
    'integrations:google:calendarFetchNew',
    async (): Promise<FetchNewResult<CalendarItem>> => {
      if (!isConnected()) return { ok: false, items: [], error: 'not_connected' }
      try {
        const all = await fetchCalendar()
        return { ok: true, items: filterNew(all, getSourceState('calendar').processedIds) }
      } catch (e) {
        return { ok: false, items: [], error: (e as Error).message }
      }
    }
  )

  ipcMain.handle(
    'integrations:google:markProcessed',
    async (_e, source: GoogleSource, ids: string[]): Promise<void> => {
      markProcessed(source, ids)
    }
  )

  ipcMain.handle(
    'integrations:signLanguage:translate',
    async (_e, payload: unknown): Promise<TranslationResult> => {
      const text = typeof payload === 'string' ? payload : (payload as { text?: string })?.text
      const spokenLanguage =
        typeof payload === 'object' && payload ? (payload as { spokenLanguage?: string }).spokenLanguage : 'en'
      const signedLanguage =
        typeof payload === 'object' && payload ? (payload as { signedLanguage?: string }).signedLanguage : 'ase'
      if (!text) throw new Error('No text provided for translation')
      return translateToGlosses(text, spokenLanguage ?? 'en', signedLanguage ?? 'ase', defaultSignOpts())
    }
  )
}
