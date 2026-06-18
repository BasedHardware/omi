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
import type { LocalKnowledgeGraph } from '../../shared/types'

// ---------------------------------------------------------------------------
// KG write worker
//
// Writes run in a worker_thread so the Electron main thread stays free for
// IPC during the synchronous DELETE+INSERT transaction.
//
// Lifecycle:
//   - Worker is created lazily on the first kg:saveGraph call.
//   - At most one write runs at a time; subsequent kg:saveGraph calls are
//     coalesced — only the latest pending graph is kept.
//   - Reads (queryNodes / status) run on the main thread via WAL mode.
//   - kgSnapshot caches the last successfully written graph so empty-query
//     reads skip SQLite entirely.
// ---------------------------------------------------------------------------

let worker: Worker | null = null
let workerBusy = false
let pendingGraph: LocalKnowledgeGraph | null = null
let lastDispatched: LocalKnowledgeGraph | null = null
let kgSnapshot: LocalKnowledgeGraph | null = null

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

function ensureWorker(): Worker {
  if (worker) return worker
  worker = new Worker(workerScriptPath(), { workerData: { dbPath: dbPath() } })
  worker.on('message', (msg: { type: string; ms?: number; message?: string }) => {
    if (msg.type === 'done') {
      kgSnapshot = lastDispatched
    } else if (msg.type === 'error') {
      console.error('[kg:worker] saveGraph error:', msg.message)
    }
    workerBusy = false
    flushPending()
  })
  worker.on('error', (err) => {
    console.error('[kg:worker] crash:', err.message)
    worker = null
    workerBusy = false
    flushPending()
  })
  return worker
}

function flushPending(): void {
  if (pendingGraph !== null) {
    const next = pendingGraph
    pendingGraph = null
    dispatch(next)
  }
}

function dispatch(graph: LocalKnowledgeGraph): void {
  workerBusy = true
  lastDispatched = graph
  ensureWorker().postMessage({ type: 'replace', nodes: graph.nodes, edges: graph.edges })
}

function enqueueGraph(graph: LocalKnowledgeGraph): void {
  if (workerBusy) {
    pendingGraph = graph
    return
  }
  dispatch(graph)
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

export function registerKgHandlers(): void {
  ipcMain.handle('kg:fileIndexDigest', async () => getFileIndexDigest())

  // Offloaded to worker — returns immediately, write completes asynchronously.
  ipcMain.handle('kg:saveGraph', (_e, graph: LocalKnowledgeGraph) => {
    enqueueGraph(graph)
  })

  ipcMain.handle('kg:status', () => getLocalKGStatus())

  ipcMain.handle('kg:queryNodes', (_e, q: string, limit?: number) => {
    if (q === '' && kgSnapshot !== null) {
      // Hot path: serve from in-memory snapshot, no SQLite access required.
      const cap = limit ?? 80
      const nodes = kgSnapshot.nodes
        .slice()
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, cap)
      const idSet = new Set(nodes.map((n) => n.id))
      const edges = kgSnapshot.edges.filter((e) => idSet.has(e.sourceId) || idSet.has(e.targetId))
      return { nodes, edges }
    }
    return queryKgNodes(q, limit)
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
