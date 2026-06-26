/**
 * KgWriteQueue — manages the lifecycle of the KG write worker and serialises
 * graph-replace operations so the Electron main thread is never blocked.
 *
 * Lifecycle:
 *   - Worker created lazily via `workerFactory` on the first enqueue call.
 *   - At most one write runs at a time; subsequent enqueues are coalesced —
 *     only the latest pending graph is kept (last-write-wins).
 *   - `enqueue()` returns a Promise that:
 *       - resolves after the worker posts { type:'done' }
 *       - rejects on { type:'error' }, worker 'error' event, or factory throw
 *   - Coalesced callers share the same resolve cycle: all pending waiters
 *     resolve together once the combined write completes.
 *   - On dispatch failure the factory error is not retried immediately; the
 *     queue drains (rejecting all waiters) so callers surface the error and
 *     the next enqueue can retry with a fresh worker.
 */

import { Worker } from 'worker_threads'
import type { LocalKnowledgeGraph } from '../../shared/types'

type Waiter = { resolve: () => void; reject: (e: Error) => void }

export class KgWriteQueue {
  private worker: Worker | null = null
  private busy = false
  private pendingGraph: LocalKnowledgeGraph | null = null
  private lastDispatched: LocalKnowledgeGraph | null = null
  private _snapshot: LocalKnowledgeGraph | null = null

  // Waiters for the currently in-flight write.
  private activeWaiters: Waiter[] = []
  // Waiters whose graphs are queued behind the active write.
  // All pending waiters resolve together when the next write completes,
  // regardless of which specific graph was coalesced away.
  private pendingWaiters: Waiter[] = []

  constructor(private readonly workerFactory: () => Worker) {}

  get snapshot(): LocalKnowledgeGraph | null {
    return this._snapshot
  }

  /**
   * Enqueue a graph replace. Returns a Promise that resolves once the graph
   * (or a superseding graph) has been durably written by the worker.
   */
  enqueue(graph: LocalKnowledgeGraph): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      if (this.busy) {
        // Coalesce: keep only the latest pending graph; all callers in the
        // pending window share the same resolve cycle.
        this.pendingGraph = graph
        this.pendingWaiters.push({ resolve, reject })
      } else {
        this.activeWaiters.push({ resolve, reject })
        this.dispatch(graph)
      }
    })
  }

  private ensureWorker(): Worker {
    if (this.worker) return this.worker
    this.worker = this.workerFactory()
    this.worker.on('message', (msg: { type: string; ms?: number; message?: string }) => {
      if (msg.type === 'done') {
        this._snapshot = this.lastDispatched
        const waiters = this.activeWaiters.splice(0)
        this.busy = false
        this.flush()
        for (const w of waiters) w.resolve()
      } else if (msg.type === 'error') {
        console.error('[kg:worker] saveGraph error:', msg.message)
        const waiters = this.activeWaiters.splice(0)
        this.busy = false
        this.flush()
        const err = new Error(msg.message ?? 'kgWorker error')
        for (const w of waiters) w.reject(err)
      }
    })
    this.worker.on('error', (err: Error) => {
      console.error('[kg:worker] crash:', err.message)
      this.worker = null
      const waiters = this.activeWaiters.splice(0)
      this.busy = false
      // Attempt to flush pending with a fresh worker on the next dispatch.
      this.flush()
      for (const w of waiters) w.reject(err)
    })
    return this.worker
  }

  private dispatch(graph: LocalKnowledgeGraph): void {
    this.busy = true
    this.lastDispatched = graph
    try {
      this.ensureWorker().postMessage({ type: 'replace', nodes: graph.nodes, edges: graph.edges })
    } catch (err) {
      // Worker construction failed (e.g. kgWorker.js missing from packaged build).
      // Reject all waiters (active + pending) and clear the queue so future
      // enqueues can retry with a fresh factory call.
      console.error('[kg:worker] failed to dispatch:', (err as Error).message)
      this.worker = null
      this.busy = false
      this.pendingGraph = null
      const allWaiters = [...this.activeWaiters.splice(0), ...this.pendingWaiters.splice(0)]
      const e = err as Error
      for (const w of allWaiters) w.reject(e)
    }
  }

  private flush(): void {
    if (this.pendingGraph !== null) {
      const next = this.pendingGraph
      this.pendingGraph = null
      // Transfer pending waiters to active before dispatching so they are
      // resolved/rejected when the upcoming write completes.
      this.activeWaiters = this.pendingWaiters.splice(0)
      this.dispatch(next)
    }
  }
}
