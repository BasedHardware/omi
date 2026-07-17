import { ipcMain } from 'electron'
import { readStickyNotes } from '../integrations/stickyNotes'
import { connect, disconnect, isConnected, connectedEmail } from '../integrations/oauth'
import { fetchGmail, fetchCalendar } from '../integrations/google'
import {
  xConnect,
  xStatus,
  xSync,
  xDisconnect,
  xRunStateSnapshot,
  type XSession
} from '../integrations/xConnector'
import {
  getSourceState,
  markProcessed,
  lastSyncAt,
  clearSyncState
} from '../integrations/syncState'
import { filterNew } from '../integrations/syncStateLogic'
import {
  gmailSessionConnect,
  gmailSessionStatus,
  gmailSessionFetch,
  gmailSessionDisconnect
} from '../integrations/gmailSession'
import type {
  GoogleStatus,
  GoogleSource,
  FetchNewResult,
  GmailItem,
  CalendarItem,
  GmailSessionStatus,
  GmailSessionFetchResult
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

  // --- Gmail via an Omi-owned Electron session (Option B). The user signs into
  // Google once inside our persistent-partition login window; we replay the same
  // Gmail web endpoints macOS uses over that own-session cookie jar. No OAuth. ---
  ipcMain.handle(
    'integrations:gmailSession:connect',
    async (): Promise<GmailSessionStatus> => gmailSessionConnect()
  )
  ipcMain.handle(
    'integrations:gmailSession:status',
    async (): Promise<GmailSessionStatus> => gmailSessionStatus()
  )
  ipcMain.handle(
    'integrations:gmailSession:fetch',
    async (_e, query?: string, maxResults?: number): Promise<GmailSessionFetchResult> =>
      gmailSessionFetch(query, maxResults)
  )
  ipcMain.handle(
    'integrations:gmailSession:disconnect',
    async (): Promise<GmailSessionStatus> => gmailSessionDisconnect()
  )

  // --- X (Twitter) connector. The renderer relays { apiBase, token } per call; the
  // connect run lives in main so it outlives the Connect panel and streams progress
  // over integrations:x:progress. ---
  ipcMain.handle('integrations:x:status', async (_e, session: XSession) => xStatus(session))
  ipcMain.handle('integrations:x:connect', async (_e, session: XSession) => {
    xConnect(session)
    return xRunStateSnapshot()
  })
  ipcMain.handle('integrations:x:runState', async () => xRunStateSnapshot())
  ipcMain.handle('integrations:x:sync', async (_e, session: XSession) => xSync(session))
  ipcMain.handle('integrations:x:disconnect', async (_e, session: XSession) => {
    await xDisconnect(session)
    return { success: true }
  })
}
