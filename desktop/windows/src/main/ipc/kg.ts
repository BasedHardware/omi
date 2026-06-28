import { ipcMain } from 'electron'
import {
  execSafeSelect,
  getFileIndexDigest,
  getLocalKGStatus,
  queryKgNodes,
  replaceLocalGraph,
  searchIndexedFiles
} from './db'
import { guardSelect } from '../../shared/sqlGuard'
import type { LocalKnowledgeGraph } from '../../shared/types'

// All local-knowledge-graph IPC. Kept in this dedicated module so registration
// is a single append in index.ts (conflict discipline with the concurrent
// integrations/Settings work).
export function registerKgHandlers(): void {
  ipcMain.handle('kg:fileIndexDigest', async () => getFileIndexDigest())
  ipcMain.handle('kg:saveGraph', async (_e, graph: LocalKnowledgeGraph) => replaceLocalGraph(graph))
  ipcMain.handle('kg:status', async () => getLocalKGStatus())
  ipcMain.handle('kg:queryNodes', async (_e, q: string, limit?: number) => queryKgNodes(q, limit))
  ipcMain.handle('kg:searchFiles', async (_e, q: string, fileType?: string, limit?: number) =>
    searchIndexedFiles(q, fileType, limit)
  )
  // The chat agent writes SQL here. guardSelect validates read-only + single
  // statement; execSafeSelect runs it on a readonly connection (defense in depth).
  ipcMain.handle('kg:executeSql', async (_e, sql: string) =>
    execSafeSelect(guardSelect(String(sql ?? '')))
  )
}
