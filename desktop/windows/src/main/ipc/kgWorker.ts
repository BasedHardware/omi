/**
 * KG write worker — runs in a Node.js worker_thread so the Electron main
 * thread stays free for IPC during the synchronous SQLite replace transaction.
 *
 * Protocol (parentPort messages):
 *   Receive:  { type: 'replace'; nodes: KgNode[]; edges: KgEdge[] }
 *   Send:     { type: 'done'; ms: number }
 *             { type: 'error'; message: string }
 *
 * workerData: { dbPath: string }
 */
import { parentPort, workerData } from 'worker_threads'
import Database from 'better-sqlite3'

const d = new Database((workerData as { dbPath: string }).dbPath)
// WAL: readers on the main thread are not blocked while we hold the write lock.
d.pragma('journal_mode = WAL')
d.pragma('synchronous = NORMAL')

// Prepare all statements once at startup.
const insertNode = d.prepare(
  `INSERT OR REPLACE INTO local_kg_nodes
     (id, label, node_type, summary, source, created_at, aliases_json, source_refs)
   VALUES (@id, @label, @nodeType, @summary, @source, @createdAt, @aliasesJson, @sourceRefs)`
)
const insertEdge = d.prepare(
  `INSERT OR REPLACE INTO local_kg_edges (id, source_id, target_id, label, created_at)
   VALUES (@id, @sourceId, @targetId, @label, @createdAt)`
)
const deleteEdges = d.prepare('DELETE FROM local_kg_edges')
const deleteNodes = d.prepare('DELETE FROM local_kg_nodes')

type KgNode = {
  id: string
  label: string
  nodeType: string
  summary: string
  source: string
  createdAt: number
  aliases?: string[]
  sourceRefs?: string[]
}
type KgEdge = { id: string; sourceId: string; targetId: string; label: string; createdAt: number }

const doReplace = d.transaction((nodes: KgNode[], edges: KgEdge[]) => {
  deleteEdges.run()
  deleteNodes.run()
  for (const n of nodes) {
    insertNode.run({
      id: n.id,
      label: n.label,
      nodeType: n.nodeType,
      summary: n.summary,
      source: n.source,
      createdAt: n.createdAt,
      aliasesJson: n.aliases?.length ? JSON.stringify(n.aliases) : null,
      sourceRefs: n.sourceRefs?.length ? JSON.stringify(n.sourceRefs) : null
    })
  }
  for (const e of edges) insertEdge.run(e)
})

parentPort!.on('message', (msg: { type: string; nodes: KgNode[]; edges: KgEdge[] }) => {
  if (msg.type !== 'replace') return
  const t0 = performance.now()
  try {
    doReplace(msg.nodes, msg.edges)
    parentPort!.postMessage({ type: 'done', ms: Math.round(performance.now() - t0) })
  } catch (err) {
    parentPort!.postMessage({ type: 'error', message: (err as Error).message })
  }
})
