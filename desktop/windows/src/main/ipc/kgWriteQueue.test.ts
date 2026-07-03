import { describe, it, expect, beforeEach } from 'vitest'
import { KgWriteQueue } from './kgWriteQueue'
import type { LocalKnowledgeGraph } from '../../shared/types'

// ---------------------------------------------------------------------------
// Minimal Worker stand-in — controllable from the test.
// ---------------------------------------------------------------------------

type MsgListener = (msg: { type: string; ms?: number; message?: string }) => void
type ErrListener = (err: Error) => void
type ExitListener = (code: number) => void

class MockWorker {
  private msgListeners: MsgListener[] = []
  private errListeners: ErrListener[] = []
  private exitListeners: ExitListener[] = []
  readonly posted: unknown[] = []
  terminated = false

  on(event: 'message', fn: MsgListener): void
  on(event: 'error', fn: ErrListener): void
  on(event: 'exit', fn: ExitListener): void
  on(event: string, fn: unknown): void {
    if (event === 'message') this.msgListeners.push(fn as MsgListener)
    else if (event === 'error') this.errListeners.push(fn as ErrListener)
    else if (event === 'exit') this.exitListeners.push(fn as ExitListener)
  }

  postMessage(msg: unknown): void {
    this.posted.push(msg)
  }

  terminate(): Promise<number> {
    this.terminated = true
    return Promise.resolve(1)
  }

  // All emit helpers snapshot the listener list before iterating, mirroring
  // Node.js EventEmitter's behaviour where listeners added inside a handler
  // don't fire in the same emission cycle.

  /** Simulate the worker posting { type:'done' } */
  emitDone(ms = 1): void {
    for (const fn of this.msgListeners.slice()) fn({ type: 'done', ms })
  }

  /** Simulate the worker posting { type:'error' } */
  emitWorkerError(message: string): void {
    for (const fn of this.msgListeners.slice()) fn({ type: 'error', message })
  }

  /** Simulate the worker thread crashing (Worker 'error' event) */
  emitCrash(err: Error): void {
    for (const fn of this.errListeners.slice()) fn(err)
  }

  /** Simulate the worker thread exiting (Worker 'exit' event) */
  emitExit(code = 1): void {
    for (const fn of this.exitListeners.slice()) fn(code)
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeGraph(label: string, nodeCount = 1): LocalKnowledgeGraph {
  const nodes = Array.from({ length: nodeCount }, (_, i) => ({
    id: `${label}-node-${i}`,
    label: `${label} node ${i}`,
    nodeType: 'project' as const,
    summary: '',
    source: 'files' as const,
    createdAt: Date.now() + i,
  }))
  return { nodes, edges: [] }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('KgWriteQueue', () => {
  let worker: MockWorker
  let queue: KgWriteQueue

  beforeEach(() => {
    worker = new MockWorker()
    queue = new KgWriteQueue(() => worker as unknown as import('worker_threads').Worker)
  })

  // -------------------------------------------------------------------------
  // Basic round-trip
  // -------------------------------------------------------------------------

  it('resolves after the worker posts done', async () => {
    const graph = makeGraph('A')
    const p = queue.enqueue(graph)
    expect(worker.posted).toHaveLength(1)
    expect((worker.posted[0] as { type: string }).type).toBe('replace')

    worker.emitDone()
    await expect(p).resolves.toBeUndefined()
  })

  it('populates snapshot only after done (not before)', async () => {
    const graph = makeGraph('A')
    const p = queue.enqueue(graph)
    expect(queue.snapshot).toBeNull()

    worker.emitDone()
    await p
    expect(queue.snapshot).toBe(graph)
  })

  // -------------------------------------------------------------------------
  // Coalescing
  // -------------------------------------------------------------------------

  it('coalesces rapid enqueues: only dispatches latest when first write finishes', async () => {
    const graphA = makeGraph('A')
    const graphB = makeGraph('B')
    const graphC = makeGraph('C')

    const pA = queue.enqueue(graphA)
    const pB = queue.enqueue(graphB) // queued behind A
    const pC = queue.enqueue(graphC) // replaces B in the pending slot

    // Only A is dispatched so far
    expect(worker.posted).toHaveLength(1)

    // Finish A
    worker.emitDone()
    await pA

    // C (not B) should now be dispatched
    expect(worker.posted).toHaveLength(2)
    const secondMsg = worker.posted[1] as { type: string; nodes: { id: string }[] }
    expect(secondMsg.nodes[0].id).toBe(graphC.nodes[0].id)

    // Finish C — both B and C callers resolve
    worker.emitDone()
    await Promise.all([pB, pC])
    expect(queue.snapshot).toBe(graphC)
  })

  it('snapshot is updated to the latest written graph after coalescing', async () => {
    const graphA = makeGraph('A')
    const graphB = makeGraph('B')

    const pA = queue.enqueue(graphA)
    queue.enqueue(graphB) // pending, will be dispatched after A

    worker.emitDone() // A finishes
    await pA
    expect(queue.snapshot).toBe(graphA)

    worker.emitDone() // B finishes
    expect(queue.snapshot).toBe(graphB)
  })

  // -------------------------------------------------------------------------
  // Error paths — protocol error
  // -------------------------------------------------------------------------

  it('rejects when the worker posts { type:"error" }', async () => {
    const graph = makeGraph('A')
    const p = queue.enqueue(graph)

    worker.emitWorkerError('db locked')
    await expect(p).rejects.toThrow('db locked')
  })

  it('rejects when the worker thread crashes (error event)', async () => {
    const graph = makeGraph('A')
    const p = queue.enqueue(graph)

    worker.emitCrash(new Error('SIGKILL'))
    await expect(p).rejects.toThrow('SIGKILL')
  })

  it('retries pending graph on a fresh worker after crash', async () => {
    const graphA = makeGraph('A')
    const graphB = makeGraph('B')

    const pA = queue.enqueue(graphA)
    const pB = queue.enqueue(graphB) // pending

    worker.emitCrash(new Error('crash'))
    await expect(pA).rejects.toThrow('crash')

    // flush() re-dispatches B on the same MockWorker (factory returns same instance).
    worker.emitDone()
    await expect(pB).resolves.toBeUndefined()
  })

  it('rejects when the worker factory throws at construction time', async () => {
    const throwingQueue = new KgWriteQueue(() => {
      throw new Error('kgWorker.js not found')
    })

    const graphA = makeGraph('A')
    const graphB = makeGraph('B')

    const pA = throwingQueue.enqueue(graphA)
    const pB = throwingQueue.enqueue(graphB) // pending at time of dispatch failure

    // Both should reject — factory throws drain the entire queue
    await expect(pA).rejects.toThrow('kgWorker.js not found')
    await expect(pB).rejects.toThrow('kgWorker.js not found')
  })

  // -------------------------------------------------------------------------
  // Error paths — exit event
  // -------------------------------------------------------------------------

  it('rejects active waiter when worker exits without an error event', async () => {
    const graph = makeGraph('A')
    const p = queue.enqueue(graph)

    // Simulate native crash / OOM kill: exit fires, no 'error' event.
    worker.emitExit(137)
    await expect(p).rejects.toThrow('exited unexpectedly (code 137)')
  })

  it('retries pending graph after unexpected exit', async () => {
    const graphA = makeGraph('A')
    const graphB = makeGraph('B')

    const pA = queue.enqueue(graphA)
    const pB = queue.enqueue(graphB) // pending

    worker.emitExit(1)
    await expect(pA).rejects.toThrow('exited unexpectedly')

    // flush() re-dispatches B; same MockWorker instance used by factory.
    worker.emitDone()
    await expect(pB).resolves.toBeUndefined()
  })

  it('does not double-reject when both error and exit fire for the same crash', async () => {
    const graph = makeGraph('A')
    const p = queue.enqueue(graph)

    // Node.js worker_threads can emit 'error' then 'exit' for the same crash.
    worker.emitCrash(new Error('crash'))
    worker.emitExit(1) // should be a no-op — guard catches it

    // Only one rejection, not two.
    await expect(p).rejects.toThrow('crash')
  })

  // -------------------------------------------------------------------------
  // Shutdown — terminate()
  // -------------------------------------------------------------------------

  it('terminate() rejects active waiter and calls worker.terminate()', async () => {
    const graph = makeGraph('A')
    const p = queue.enqueue(graph)
    expect(worker.terminated).toBe(false)

    queue.terminate()

    await expect(p).rejects.toThrow('terminated')
    expect(worker.terminated).toBe(true)
  })

  it('terminate() rejects both active and pending waiters', async () => {
    const pA = queue.enqueue(makeGraph('A'))
    const pB = queue.enqueue(makeGraph('B')) // pending

    queue.terminate()

    await expect(pA).rejects.toThrow('terminated')
    await expect(pB).rejects.toThrow('terminated')
  })

  it("terminate() exit event does not re-reject after terminate() clears the worker ref", async () => {
    const p = queue.enqueue(makeGraph('A'))
    queue.terminate()
    await expect(p).rejects.toThrow('terminated')

    // Firing exit after terminate() should be a silent no-op via the guard.
    expect(() => worker.emitExit(1)).not.toThrow()
  })

  it('terminate() is safe when no worker has been created', () => {
    // Queue lazily creates the worker; terminate() before any enqueue is a no-op.
    expect(() => queue.terminate()).not.toThrow()
  })

  it('late message from stale worker after terminate() does not corrupt snapshot or waiters', async () => {
    const graphA = makeGraph('A')
    const p = queue.enqueue(graphA)

    // Terminate while write is in flight — rejects the waiter.
    queue.terminate()
    await expect(p).rejects.toThrow('terminated')
    expect(queue.snapshot).toBeNull()

    // A buffered 'done' arrives from the now-stale worker after terminate().
    // The 'message' guard (this.worker !== w) must discard it so snapshot stays
    // null and no new flush is triggered.
    worker.emitDone()
    expect(queue.snapshot).toBeNull()
  })

  // -------------------------------------------------------------------------
  // Snapshot hot-path correctness
  // -------------------------------------------------------------------------

  it('snapshot reflects only successfully written graphs', async () => {
    const graphA = makeGraph('A')
    const p = queue.enqueue(graphA)

    worker.emitWorkerError('fail')
    await expect(p).rejects.toThrow()
    // snapshot stays null — no successful write
    expect(queue.snapshot).toBeNull()
  })

  it('snapshot is not updated when the worker crashes', async () => {
    const graphFirst = makeGraph('first')
    const p1 = queue.enqueue(graphFirst)
    worker.emitDone()
    await p1
    expect(queue.snapshot).toBe(graphFirst)

    const graphSecond = makeGraph('second')
    const p2 = queue.enqueue(graphSecond)
    worker.emitCrash(new Error('crash'))
    await expect(p2).rejects.toThrow()
    // snapshot stays as first successful write
    expect(queue.snapshot).toBe(graphFirst)
  })

  // -------------------------------------------------------------------------
  // Sequential saves (no contention)
  // -------------------------------------------------------------------------

  it('handles multiple sequential saves correctly', async () => {
    for (let i = 0; i < 3; i++) {
      const graph = makeGraph(`seq-${i}`)
      const p = queue.enqueue(graph)
      worker.emitDone()
      await p
      expect(queue.snapshot).toEqual(graph)
    }
    expect(worker.posted).toHaveLength(3)
  })
})
