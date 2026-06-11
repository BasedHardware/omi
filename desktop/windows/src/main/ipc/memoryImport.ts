import { ipcMain } from 'electron'
import { parseMemoryDump } from '../memoryImport/parse'

// Parsing only: the renderer owns the Firebase token, so it does the actual
// POST /v3/memories with the strings returned here.
export function registerMemoryImportHandlers(): void {
  ipcMain.handle('memoryImport:parse', async (_e, dump: string) => parseMemoryDump(dump))
}
