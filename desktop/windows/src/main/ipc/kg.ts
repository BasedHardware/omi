import { app, ipcMain } from 'electron'
import { join } from 'path'
import { Worker } from 'worker_threads'
import {
  execSafeSelect,
  getFileIndexDigest,
  getLocalKGStatus,
  queryKgNodes,
  searchIndexedFiles
} from './db'
import { guardSelect } from '../../shared/sqlGuard'
import { KgWriteQueue } from './kgWriteQueue'
import type { LocalKnowledgeGraph } from '../../shared/types'

// ---------------------------------------------------------------------------
// KG write worker
//
// Writes run in a worker_thread so the Electron main thread stays free for
// IPC during the synchronous DELETE+INSERT transaction.
//
// Lifecycle (managed by KgWriteQueue):
//   - Worker is created lazily on the first kg:saveGraph call.
//   - At most one write runs at a time; subsequent kg:saveGraph calls are
//     coalesced — only the latest pending graph is kept.
//   - kg:saveGraph returns a Promise that resolves when the write commits and
//     rejects on worker error or factory failure.
//   - Reads (queryNodes / status) run on the main thread via WAL mode.
//   - The queue's snapshot caches the last successfully written graph so
//     empty-query reads skip SQLite entirely.
// ---------------------------------------------------------------------------

function dbPath(): string {
  return process.env.OMI_DB_PATH ?? join(app.getPath('userData'), 'omi.db')
}

function workerScriptPath(): string {
  // Packaged builds: kgWorker.js is unpacked from the asar (see electron-builder.yml).
  // Dev: vite emits kgWorker.js into out/main/ alongside index.js.
  if (app.isPackaged) {
    return join(process.resourcesPath, 'app.asar.unpacked', 'out', 'main', 'kgWorker.js')
  }
  return join(__dirname, 'kgWorker.js')
}

let writeQueue: KgWriteQueue | null = null

function getQueue(): KgWriteQueue {
  if (!writeQueue) {
    writeQueue = new KgWriteQueue(
      () => new Worker(workerScriptPath(), { workerData: { dbPath: dbPath() } })
    )
  }
  return writeQueue
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

export function registerKgHandlers(): void {
  // Terminate the worker thread before Electron quits so the process does not
  // hang waiting for the background thread and the SQLite connection it holds.
  app.on('before-quit', () => {
    writeQueue?.terminate()
    writeQueue = null
  })

  ipcMain.handle('kg:fileIndexDigest', async () => getFileIndexDigest())

  // Returns a Promise that resolves after the worker commits the write and
  // rejects on worker error or factory failure, so callers can await durability.
  ipcMain.handle('kg:saveGraph', (_e, graph: LocalKnowledgeGraph) => {
    return getQueue().enqueue(graph)
  })

  ipcMain.handle('kg:status', () => getLocalKGStatus())

  ipcMain.handle('kg:queryNodes', (_e, q: string, limit?: number) => {
    // Resolve cap once so snapshot and DB paths always return the same count.
    const cap = limit ?? 80
    const snap = getQueue().snapshot
    if (q === '' && snap !== null) {
      // Hot path: serve from in-memory snapshot, no SQLite access required.
      const nodes = snap.nodes
        .slice()
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, cap)
      const idSet = new Set(nodes.map((n) => n.id))
      const edges = snap.edges.filter((e) => idSet.has(e.sourceId) || idSet.has(e.targetId))
      return { nodes, edges }
    }
    return queryKgNodes(q, cap)
  })

  ipcMain.handle('kg:searchFiles', async (_e, q: string, fileType?: string, limit?: number) =>
    searchIndexedFiles(q, fileType, limit)
  )
  // The chat agent writes SQL here. guardSelect validates read-only + single
  // statement; execSafeSelect runs it on a readonly connection (defense in depth).
  ipcMain.handle('kg:executeSql', async (_e, sql: string) =>
    execSafeSelect(guardSelect(String(sql ?? '')))
  )
}
