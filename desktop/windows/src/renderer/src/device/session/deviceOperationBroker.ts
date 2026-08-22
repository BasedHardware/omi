/**
 * Device operation broker and uncorrelated-callback gate — Windows port of
 * macOS Session/DeviceOperationBroker.swift.
 *
 * The broker serializes correlated request/response exchanges: at most one
 * pending operation per key, an optional timeout on the injected clock, and
 * exactly one terminal event resuming the caller (late timeout/cancel/succeed
 * events are explicit no-ops; cancelAll supersedes even claimed completions).
 *
 * The gate exists for operations whose physical callback identifies only a
 * key (a characteristic or command id), not the attempt. Once an operation
 * terminates without success, a late callback for that key can never again be
 * attributed to a newer operation, so the key is poisoned until session reset.
 */

export type DeviceOperationTermination =
  | 'succeeded'
  | 'timedOut'
  | 'cancelled'
  | 'disconnected'
  | 'failed'

export type DeviceOperationBrokerErrorKind =
  | 'operationAlreadyPending'
  | 'timedOut'
  | 'cancelled'
  | 'disconnected'
  | 'failed'

const BROKER_ERROR_MESSAGES: Record<Exclude<DeviceOperationBrokerErrorKind, 'failed'>, string> = {
  operationAlreadyPending: 'Another operation with the same identity is already pending',
  timedOut: 'Operation timed out',
  cancelled: 'Operation was cancelled',
  disconnected: 'Device disconnected before the operation completed'
}

export class DeviceOperationBrokerError extends Error {
  readonly kind: DeviceOperationBrokerErrorKind

  constructor(kind: DeviceOperationBrokerErrorKind, detail?: string) {
    super(kind === 'failed' ? (detail ?? 'Operation failed') : BROKER_ERROR_MESSAGES[kind])
    this.name = 'DeviceOperationBrokerError'
    this.kind = kind
  }
}

/** Identity of one gate-registered attempt: key plus a monotonic token. */
export interface DeviceOperationHandle {
  key: string
  token: number
}

// --- clock ------------------------------------------------------------------

/** Injectable clock: every sleep/timeout in the device stack goes through
 *  this seam so tests can drive time deterministically. */
export interface DeviceOperationClock {
  sleep(ms: number, signal: AbortSignal): Promise<'elapsed' | 'aborted'>
}

export class RealDeviceOperationClock implements DeviceOperationClock {
  sleep(ms: number, signal: AbortSignal): Promise<'elapsed' | 'aborted'> {
    return new Promise((resolve) => {
      if (signal.aborted) {
        resolve('aborted')
        return
      }
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', onAbort)
        resolve('elapsed')
      }, ms)
      const onAbort = (): void => {
        clearTimeout(timer)
        resolve('aborted')
      }
      signal.addEventListener('abort', onAbort, { once: true })
    })
  }
}

// --- uncorrelated-callback gate ---------------------------------------------

export class UncorrelatedOperationGate {
  private live = new Map<string, DeviceOperationHandle>()
  private poisoned = new Set<string>()
  private nextToken = 1

  /** A key can host a new attempt only when nothing is in flight and no prior
   *  attempt left an uncorrelated callback behind. */
  canStart(key: string): boolean {
    return !this.live.has(key) && !this.poisoned.has(key)
  }

  isPoisoned(key: string): boolean {
    return this.poisoned.has(key)
  }

  /** True while an attempt is registered and unclaimed on the key. */
  hasLiveAttempt(key: string): boolean {
    return this.live.has(key)
  }

  /** Registers an attempt; null when the key is unavailable (in flight or
   *  poisoned) — callers map that to their own identity error message. */
  register(key: string): DeviceOperationHandle | null {
    if (!this.canStart(key)) return null
    const handle: DeviceOperationHandle = { key, token: this.nextToken++ }
    this.live.set(key, handle)
    return handle
  }

  /** Claims the live attempt for an arriving physical callback. Null means
   *  the callback is uncorrelated (no attempt, or the key is poisoned) and
   *  must not be treated as a response. */
  takeHandleForCallback(key: string): DeviceOperationHandle | null {
    if (this.poisoned.has(key)) return null
    const handle = this.live.get(key)
    if (handle === undefined) return null
    this.live.delete(key)
    return handle
  }

  /** Records the attempt's outcome. Any non-success termination poisons the
   *  key permanently until reset(): the physical callback may still arrive
   *  later and must never be attributed to a newer operation. */
  terminal(handle: DeviceOperationHandle, termination: DeviceOperationTermination): void {
    const current = this.live.get(handle.key)
    if (current !== undefined && current.token === handle.token) {
      this.live.delete(handle.key)
    }
    if (termination !== 'succeeded') {
      this.poisoned.add(handle.key)
    }
  }

  /** Session teardown: a new physical connection gets clean identities. */
  reset(): void {
    this.live.clear()
    this.poisoned.clear()
  }
}

// --- broker -----------------------------------------------------------------

interface PendingOperation {
  key: string
  settled: boolean
  claimed: boolean
  startTask: Promise<void>
  startFailed: boolean
  startError: unknown
  timeoutAbort: AbortController | null
  onTerminal: ((termination: DeviceOperationTermination) => void) | null
  resolve: (value: unknown) => void
  reject: (error: unknown) => void
}

export interface PerformOptions {
  key: string
  /** Milliseconds; omit or null for no timeout. */
  timeoutMs?: number | null
  /** Fires with the mapped termination before the caller's promise settles. */
  onTerminal?: (termination: DeviceOperationTermination) => void
  /** Kicks off the physical operation. A start failure is surfaced when the
   *  operation is later completed via succeed(). */
  start: () => void | Promise<void>
}

export class DeviceOperationBroker {
  private pending = new Map<string, PendingOperation>()

  constructor(private readonly clock: DeviceOperationClock = new RealDeviceOperationClock()) {}

  hasPending(key: string): boolean {
    return this.pending.has(key)
  }

  perform<T>(options: PerformOptions): Promise<T> {
    if (this.pending.has(options.key)) {
      return Promise.reject(new DeviceOperationBrokerError('operationAlreadyPending'))
    }

    let resolve!: (value: unknown) => void
    let reject!: (error: unknown) => void
    const promise = new Promise<unknown>((res, rej) => {
      resolve = res
      reject = rej
    })

    const op: PendingOperation = {
      key: options.key,
      settled: false,
      claimed: false,
      startTask: Promise.resolve(),
      startFailed: false,
      startError: null,
      timeoutAbort: null,
      onTerminal: options.onTerminal ?? null,
      resolve,
      reject
    }
    this.pending.set(options.key, op)

    op.startTask = (async () => {
      try {
        await options.start()
      } catch (error) {
        op.startFailed = true
        op.startError = error
        // Settle now rather than waiting for a completion that a failed start
        // will never produce: without a timeout the caller would hang forever,
        // and with one it would report a misleading timeout.
        if (!op.settled && !op.claimed) {
          this.settle(op, 'failed', { reject: error })
        }
      }
    })()

    const timeoutMs = options.timeoutMs ?? null
    if (timeoutMs !== null) {
      const abort = new AbortController()
      op.timeoutAbort = abort
      void this.clock.sleep(timeoutMs, abort.signal).then((outcome) => {
        if (outcome !== 'elapsed') return
        if (op.settled || op.claimed) return
        this.settle(op, 'timedOut', {
          reject: new DeviceOperationBrokerError('timedOut')
        })
      })
    }

    return promise as Promise<T>
  }

  /** Completes the pending operation for a key with a value. The claim is
   *  exclusive against timeout/fail, but cancelAll supersedes it while the
   *  start task is still being awaited. A failed start throws its own error
   *  instead of returning the value. */
  succeed(key: string, value: unknown): void {
    const op = this.pending.get(key)
    if (op === undefined || op.settled || op.claimed) return
    op.claimed = true
    void (async () => {
      await op.startTask
      if (op.settled) return
      if (op.startFailed) {
        this.settle(op, 'failed', { reject: op.startError })
        return
      }
      this.settle(op, 'succeeded', { resolve: value })
    })()
  }

  /** Fails the pending operation for a key (e.g. an error-bearing callback). */
  fail(key: string, error: Error): void {
    const op = this.pending.get(key)
    if (op === undefined || op.settled || op.claimed) return
    this.settle(op, 'failed', { reject: error })
  }

  /** Terminates every pending operation, superseding even claimed completions
   *  whose start task is still settling. */
  cancelAll(reason: 'cancelled' | 'disconnected' = 'cancelled'): void {
    const ops = Array.from(this.pending.values())
    for (const op of ops) {
      if (op.settled) continue
      this.settle(op, reason, { reject: new DeviceOperationBrokerError(reason) })
    }
  }

  private settle(
    op: PendingOperation,
    termination: DeviceOperationTermination,
    outcome: { resolve?: unknown; reject?: unknown }
  ): void {
    if (op.settled) return
    op.settled = true
    op.timeoutAbort?.abort()
    if (this.pending.get(op.key) === op) {
      this.pending.delete(op.key)
    }
    try {
      op.onTerminal?.(termination)
    } catch (error) {
      // A terminal hook decides nothing about the caller: rethrowing here would
      // both strand the promise and surface as an unhandled rejection.
      console.warn('[device] operation terminal hook threw:', error)
    }
    if ('resolve' in outcome) {
      op.resolve(outcome.resolve)
    } else {
      op.reject(outcome.reject)
    }
  }
}
