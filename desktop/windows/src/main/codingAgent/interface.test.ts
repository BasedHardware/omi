import { describe, expect, it } from 'vitest'
import {
  adapterCapabilitiesFor,
  assertAdapterBindingContract,
  assertAdapterAttemptResultContract,
  isProductionAdapterId,
  type AdapterAttemptContext,
  type AdapterBindingHandle
} from './interface'

function makeBinding(overrides: Partial<AdapterBindingHandle> = {}): AdapterBindingHandle {
  return {
    sessionId: 'omi-session',
    adapterId: 'acp',
    adapterNativeSessionId: 'native-1',
    resumeFidelity: 'native',
    cwd: 'C:/work',
    ...overrides
  }
}

function makeContext(binding: AdapterBindingHandle): AdapterAttemptContext {
  return {
    sessionId: 'omi-session',
    runId: 'run-1',
    attemptId: 'attempt-1',
    binding,
    prompt: [{ type: 'text', text: 'hi' }],
    mode: 'act'
  }
}

describe('adapter contracts', () => {
  it('rejects an empty native session id', () => {
    expect(() =>
      assertAdapterBindingContract(makeBinding({ adapterNativeSessionId: '' }), 'openBinding')
    ).toThrow('empty adapterNativeSessionId')
  })

  it('rejects conflating the Omi session id with the native session id', () => {
    expect(() =>
      assertAdapterBindingContract(
        makeBinding({ adapterNativeSessionId: 'omi-session' }),
        'openBinding'
      )
    ).toThrow('conflated Omi sessionId')
  })

  it('rejects an attempt result whose native id does not match its binding', () => {
    const binding = makeBinding()
    const context = makeContext(binding)
    expect(() =>
      assertAdapterAttemptResultContract(
        context,
        { text: '', adapterSessionId: 'other-native', terminalStatus: 'succeeded' },
        'executeAttempt'
      )
    ).toThrow('for binding native-1')
    expect(() =>
      assertAdapterAttemptResultContract(
        context,
        { text: '', adapterSessionId: 'omi-session', terminalStatus: 'succeeded' },
        'executeAttempt'
      )
    ).toThrow('conflated Omi sessionId')
    expect(() =>
      assertAdapterAttemptResultContract(
        context,
        { text: 'ok', adapterSessionId: 'native-1', terminalStatus: 'succeeded' },
        'executeAttempt'
      )
    ).not.toThrow()
  })
})

describe('capability matrix', () => {
  it('derives restart behavior from resume/pinning expectations', () => {
    expect(adapterCapabilitiesFor('acp').restartBehavior).toBe('native_bindings_survive')
    expect(adapterCapabilitiesFor('openclaw').restartBehavior).toBe('native_bindings_survive')
    expect(adapterCapabilitiesFor('hermes').restartBehavior).toBe('process_local_bindings_stale')
    expect(adapterCapabilitiesFor('codex').restartBehavior).toBe('process_local_bindings_stale')
    // pi-mono has no native resume but pins its worker → process_local_bindings_stale.
    expect(adapterCapabilitiesFor('pi-mono').restartBehavior).toBe('process_local_bindings_stale')
  })

  it('knows the production adapters, including the managed-cloud pi-mono (PR-D)', () => {
    expect(isProductionAdapterId('acp')).toBe(true)
    expect(isProductionAdapterId('openclaw')).toBe(true)
    expect(isProductionAdapterId('hermes')).toBe(true)
    expect(isProductionAdapterId('codex')).toBe(true)
    // pi-mono is now a registered managed-cloud production adapter (matrix member).
    expect(isProductionAdapterId('pi-mono')).toBe(true)
    expect(isProductionAdapterId('a2a')).toBe(false)
  })
})
