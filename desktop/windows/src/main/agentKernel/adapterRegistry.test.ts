// Tests for the kernel AdapterRegistry (macOS adapter-registry.ts). Covers the
// register/get/has/capacity API and — the load-bearing part — that every
// registered adapter is wrapped in the contract-checking proxy that rejects the
// Omi/adapter id-conflation the invariants forbid (INV-AGENT).

import { describe, expect, it } from 'vitest'
import { AdapterRegistry } from './adapterRegistry'
import type { AdapterCapabilities, RuntimeAdapter } from '../codingAgent/interface'

function capabilities(overrides: Partial<AdapterCapabilities> = {}): AdapterCapabilities {
  return {
    resumeFidelity: 'native',
    supportsNativeResume: true,
    supportsCancellation: true,
    acknowledgesCancellation: false,
    requiresPinnedWorker: false,
    supportsModelSwitching: true,
    supportsArtifactEmission: false,
    supportsTools: true,
    restartBehavior: 'native_bindings_survive',
    ...overrides
  }
}

function fakeAdapter(opts: { adapterId?: string; conflateBinding?: boolean } = {}): RuntimeAdapter {
  const adapterId = opts.adapterId ?? 'test-adapter'
  let n = 0
  return {
    adapterId,
    capabilities: capabilities(),
    async start() {
      /* no-op fake */
    },
    async stop() {
      /* no-op fake */
    },
    async openBinding(input) {
      return {
        sessionId: input.sessionId,
        adapterId,
        adapterNativeSessionId: opts.conflateBinding ? input.sessionId : `native-${++n}`,
        resumeFidelity: 'native',
        cwd: input.cwd,
        model: input.model
      }
    },
    async resumeBinding(input) {
      return {
        sessionId: input.sessionId,
        adapterId,
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

describe('AdapterRegistry — registry API', () => {
  it('registers, looks up, and reports capacity', () => {
    const registry = new AdapterRegistry()
    expect(registry.has('test-adapter')).toBe(false)
    const pool = registry.register('test-adapter', () => fakeAdapter(), 3)
    expect(registry.has('test-adapter')).toBe(true)
    expect(registry.get('test-adapter')).toBe(pool)
    expect(registry.capacity('test-adapter')).toBe(3)
    expect(registry.adapterIds()).toEqual(['test-adapter'])
  })

  it('rejects duplicate registration and unknown lookup', () => {
    const registry = new AdapterRegistry()
    registry.register('test-adapter', () => fakeAdapter())
    expect(() => registry.register('test-adapter', () => fakeAdapter())).toThrow(
      /already registered/
    )
    expect(() => registry.get('missing')).toThrow(/not registered/)
  })
})

describe('AdapterRegistry — contract checking', () => {
  it('passes a well-behaved adapter through the pool', async () => {
    const registry = new AdapterRegistry()
    const pool = registry.register('test-adapter', () => fakeAdapter(), 1)
    const binding = await pool.runExclusiveQueued(undefined, 'attempt-1', (worker) =>
      worker.adapter.openBinding({ sessionId: 'ses_1', cwd: '/tmp' })
    )
    expect(binding.adapterNativeSessionId).not.toBe('ses_1')
    expect(binding.adapterNativeSessionId).toBe('native-1')
  })

  it('throws when an adapter conflates the Omi sessionId with its native id', async () => {
    const registry = new AdapterRegistry()
    const pool = registry.register('test-adapter', () => fakeAdapter({ conflateBinding: true }), 1)
    await expect(
      pool.runExclusiveQueued(undefined, 'attempt-1', (worker) =>
        worker.adapter.openBinding({ sessionId: 'ses_1', cwd: '/tmp' })
      )
    ).rejects.toThrow(/conflated Omi sessionId/)
  })
})
