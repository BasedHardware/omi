import { ipcMain } from 'electron'
import { runFileIndex, getStatus, scheduleStartupRescan } from '../fileIndex/indexer'
import { getIndexedApps } from './db'

export function registerFileIndexHandlers(): void {
  ipcMain.handle('fileIndex:scan', async () => runFileIndex())
  ipcMain.handle('fileIndex:status', async () => getStatus())
  ipcMain.handle('fileIndex:apps', async (_e, limit?: number) => getIndexedApps(limit))
  // Existing-user backfill: refresh an already-populated index shortly after
  // launch so files added/removed while the app was closed are reflected. No-op
  // for new users (index empty until onboarding's first scan). Cancelable on quit.
  scheduleStartupRescan()
}
