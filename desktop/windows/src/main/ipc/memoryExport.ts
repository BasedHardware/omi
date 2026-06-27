import { dialog, ipcMain } from 'electron'
import { exportToObsidian } from '../memoryExport/obsidian'
import { exportToFile } from '../memoryExport/plainFile'
import { exportToNotion } from '../memoryExport/notion'
import type { ExportMemory, MemoryExportResult } from '../../shared/types'

// The renderer fetches memories (it owns the API token) and hands them here for
// the file-writing / Notion targets, which need main-process fs + network.
export function registerMemoryExportHandlers(): void {
  ipcMain.handle(
    'memoryExport:obsidian',
    async (_e, memories: ExportMemory[]): Promise<MemoryExportResult> => {
      const r = await dialog.showOpenDialog({
        title: 'Choose your Obsidian vault folder',
        properties: ['openDirectory']
      })
      if (r.canceled || r.filePaths.length === 0) return { canceled: true, count: 0 }
      const location = await exportToObsidian(r.filePaths[0], memories)
      return { count: memories.length, location }
    }
  )

  ipcMain.handle(
    'memoryExport:file',
    async (_e, memories: ExportMemory[]): Promise<MemoryExportResult> => {
      const r = await dialog.showSaveDialog({
        title: 'Export memories',
        defaultPath: 'Omi-Memories.md',
        filters: [{ name: 'Markdown', extensions: ['md'] }]
      })
      if (r.canceled || !r.filePath) return { canceled: true, count: 0 }
      const location = await exportToFile(r.filePath, memories)
      return { count: memories.length, location }
    }
  )

  ipcMain.handle(
    'memoryExport:notion',
    async (
      _e,
      args: { token: string; parentPageId: string; memories: ExportMemory[] }
    ): Promise<MemoryExportResult> => {
      const location = await exportToNotion(args.token, args.parentPageId, args.memories)
      return { count: args.memories.length, location }
    }
  )
}
