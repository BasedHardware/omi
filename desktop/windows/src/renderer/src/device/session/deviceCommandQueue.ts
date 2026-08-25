/**
 * Strict FIFO serializer for command/response exchanges that share one write
 * channel — Windows port of macOS Session/DeviceCommandQueue.swift. Used by
 * device families (Bee, PLAUD) whose control characteristic multiplexes every
 * command over a single pipe, so interleaved writes would cross-correlate
 * responses.
 */

export class DeviceCommandQueueError extends Error {
  readonly kind = 'closed'

  constructor() {
    super('The device command channel is closed')
    this.name = 'DeviceCommandQueueError'
  }
}

export class DeviceCommandQueue {
  private tail: Promise<void> = Promise.resolve()
  private closed = false
  private activeAbort: AbortController | null = null
  private queuedRejects = new Set<(error: Error) => void>()

  /** Runs the operation after every previously enqueued operation finishes.
   *  Throws closed if the queue is closed now or closes while this item is
   *  still waiting its turn. The signal aborts when the queue closes while
   *  the operation is active. */
  run<T>(operation: (signal: AbortSignal) => Promise<T> | T): Promise<T> {
    if (this.closed) return Promise.reject(new DeviceCommandQueueError())

    const predecessor = this.tail
    let rejectQueued!: (error: Error) => void
    const queuedGate = new Promise<void>((resolve, reject) => {
      rejectQueued = reject
      predecessor.then(
        () => resolve(),
        () => resolve()
      )
    })
    this.queuedRejects.add(rejectQueued)

    const task = (async (): Promise<T> => {
      try {
        await queuedGate
      } finally {
        this.queuedRejects.delete(rejectQueued)
      }
      if (this.closed) throw new DeviceCommandQueueError()
      const abort = new AbortController()
      this.activeAbort = abort
      try {
        return await operation(abort.signal)
      } finally {
        if (this.activeAbort === abort) this.activeAbort = null
      }
    })()

    this.tail = task.then(
      () => undefined,
      () => undefined
    )
    return task
  }

  /** Permanent: cancels queued items, aborts the active operation, and awaits
   *  the chain before returning. */
  async close(): Promise<void> {
    if (!this.closed) {
      this.closed = true
      const rejects = Array.from(this.queuedRejects)
      this.queuedRejects.clear()
      for (const reject of rejects) reject(new DeviceCommandQueueError())
      this.activeAbort?.abort()
    }
    await this.tail
  }
}
