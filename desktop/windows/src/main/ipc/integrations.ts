import { ipcMain } from 'electron'
import { readStickyNotes } from '../integrations/stickyNotes'
import {
  xConnect,
  xStatus,
  xSync,
  xDisconnect,
  xRunStateSnapshot,
  type XSession
} from '../integrations/xConnector'
import {
  gmailSessionConnect,
  gmailSessionStatus,
  gmailSessionVerify,
  gmailSessionFetch,
  gmailSessionDisconnect
} from '../integrations/gmailSession'
import type {
  GmailSessionStatus,
  GmailSessionFetchResult
} from '../../shared/types'

// All integrations IPC lives here so concurrent chat/KG work doesn't conflict
// in index.ts.
export function registerIntegrationsHandlers(): void {
  ipcMain.handle('integrations:stickyNotes:read', async () => readStickyNotes())

  // --- Gmail via an Omi-owned Electron session (Option B). The user signs into
  // Google once inside our persistent-partition login window; we replay the same
  // Gmail web endpoints macOS uses over that own-session cookie jar. No OAuth. ---
  ipcMain.handle(
    'integrations:gmailSession:connect',
    async (_e, email?: string): Promise<GmailSessionStatus> => gmailSessionConnect(email)
  )
  ipcMain.handle(
    'integrations:gmailSession:status',
    async (): Promise<GmailSessionStatus> => gmailSessionStatus()
  )
  // A network probe (vs. the cheap cookie-presence status): the renderer calls this
  // after a failed fetch so a stale-but-present session flips the row to reconnect.
  ipcMain.handle(
    'integrations:gmailSession:verify',
    async (): Promise<GmailSessionStatus> => gmailSessionVerify()
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
