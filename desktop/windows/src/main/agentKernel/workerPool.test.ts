// Tests for AdapterWorkerPool (macOS worker-pool.ts): exclusive+queued leases,
// binding-level serialization, capacity queueing, no-capacity rejection for
// pinned adapters, and pinned-worker reuse across sequential attempts.

import { describe, expect, it } from 'vitest'
import {
  AdapterWorkerPool,
  DEFAULT_PI_MONO_MAX_WORKERS,
  configuredPiMonoMaxWorkers
} from './workerPool'
import type {
  AdapterBindingHandle,
  AdapterCapabilities,
  RuntimeAdapter
} from '../codingAgent/interface'

function capabilities(requiresPinnedWorker: boolean): AdapterCapabilities {
  return {
    resumeFidelity: requiresPinnedWorker ? 'none' : 'native',
    supportsNativeResume: !requiresPinnedWorker,
    supportsCancellation: true,
    acknowledgesCancellation: false,
    requiresPinnedWorker,
    supportsModelSwitching: true,
    supportsArtifactEmission: false,
    supportsTools: true,
    restartBehavior: requiresPinnedWorker
      ? 'process_local_bindings_stale'
      : 'native_bindings_survive'
  }
}

function fakeAdapter(opts: { requiresPinnedWorker?: boolean } = {}): RuntimeAdapter {
  return {
    adapterId: 'test-adapter',
    capabilities: capabilities(opts.requiresPinnedWorker ?? false),
    async start() {
      /* no-op fake */
    },
    async stop() {
      /* no-op fake */
    },
    async openBinding(input) {
      return {
        sessionId: input.sessionId,
        adapterId: 'test-adapter',
        adapterNativeSessionId: 'native',
        resumeFidelity: 'native',
        cwd: input.cwd
      }
    },
    async resumeBinding(input) {
      return {
        sessionId: input.sessionId,
        adapterId: 'test-adapter',
        adapterNativeSessionId: input.adapterNativeSessionId,
        resumeFidelity: 'native',
        cwd: input.cwd
      }
    },
    async executeAttempt(context) {
      return {
        text: 'ok',
        adapterSessionId: context.binding.adapterNativeSessionId,
        terminalStatus: 'succeeded'
      }
    },
    async cancelAttempt() {
      return { accepted: true, dispatchAttempted: true, adapterAcknowledged: false }
    }
  }
}

function binding(bindingId: string): AdapterBindingHandle {
  return {
    bindingId,
    sessionId: 'ses',
    adapterId: 'test-adapter',
    adapterNativeSessionId: `native-${bindingId}`,
    resumeFidelity: 'native',
    cwd: '/tmp'
  }
}

function gate(): { promise: Promise<void>; open: () => void } {
  let open!: () => void
  const promise = new Promise<void>((resolve) => {
    open = resolve
  })
  return { promise, open }
}

const flush = () => new Promise((resolve) => setImmediate(resolve))

describe('AdapterWorkerPool', () => {
  it('serializes concurrent leases on the same binding', async () => {
    const pool = new AdapterWorkerPool(() => fakeAdapter(), 4)
    const order: string[] = []
    const g = gate()
    const b = binding('b1')

    const first = pool.runExclusiveQueued(b, 'a1', async () => {
      order.push('first-start')
      await g.promise
      order.push('first-end')
    })
    await flush()
    const second = pool.runExclusiveQueued(b, 'a2', async () => {
      order.push('second-start')
    })
    await flush()

    expect(order).toEqual(['first-start']) // second is queued behind the active binding

    g.open()
    await Promise.all([first, second])
    expect(order).toEqual(['first-start', 'first-end', 'second-start'])
  })

  it('queues a second lease when the single worker is busy, then runs it', async () => {
    const pool = new AdapterWorkerPool(() => fakeAdapter(), 1)
    const order: string[] = []
    const g = gate()

    const first = pool.runExclusiveQueued(binding('b1'), 'a1', async () => {
      order.push('first-start')
      await g.promise
      order.push('first-end')
    })
    await flush()
    const second = pool.runExclusiveQueued(binding('b2'), 'a2', async () => {
      order.push('second-start')
    })
    await flush()

    expect(order).toEqual(['first-start'])
    expect(pool.size).toBe(1)

    g.open()
    await Promise.all([first, second])
    expect(order).toEqual(['first-start', 'first-end', 'second-start'])
    expect(pool.size).toBe(1)
  })

  it('rejects a new-binding lease when a pinned worker pool is at capacity', async () => {
    const pool = new AdapterWorkerPool(() => fakeAdapter({ requiresPinnedWorker: true }), 1)
    const g = gate()

    const first = pool.runExclusiveQueued(binding('b1'), 'a1', async () => {
      await g.promise
    })
    await flush()

    await expect(pool.runExclusiveQueued(binding('b2'), 'a2', async () => {})).rejects.toThrow(
      /No adapter worker capacity/
    )

    g.open()
    await first
  })

  it('reuses a pinned worker for sequential attempts on the same binding', async () => {
    const pool = new AdapterWorkerPool(() => fakeAdapter({ requiresPinnedWorker: true }), 1)
    await pool.runExclusiveQueued(binding('b1'), 'a1', async () => {})
    expect(pool.size).toBe(1)
    await pool.runExclusiveQueued(binding('b1'), 'a2', async () => {})
    expect(pool.size).toBe(1)
  })
})

describe('configuredPiMonoMaxWorkers', () => {
  it('defaults to DEFAULT_PI_MONO_MAX_WORKERS (2) when unset', () => {
    expect(DEFAULT_PI_MONO_MAX_WORKERS).toBe(2)
    expect(configuredPiMonoMaxWorkers({})).toBe(2)
  })

  it('honors a valid OMI_PI_MONO_MAX_WORKERS override', () => {
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: '5' })).toBe(5)
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: '1' })).toBe(1)
  })

  it('falls back to the default for non-numeric or out-of-range values', () => {
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: 'nope' })).toBe(2)
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: '0' })).toBe(2)
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: '-3' })).toBe(2)
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: '' })).toBe(2)
  })
})
