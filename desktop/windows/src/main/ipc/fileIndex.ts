import { ipcMain } from 'electron'
import { runFileIndex, getStatus } from '../fileIndex/indexer'
import { getIndexedApps } from './db'

export function registerFileIndexHandlers(): void {
  ipcMain.handle('fileIndex:scan', async () => runFileIndex())
  ipcMain.handle('fileIndex:status', async () => getStatus())
  ipcMain.handle('fileIndex:apps', async (_e, limit?: number) => getIndexedApps(limit))
}
