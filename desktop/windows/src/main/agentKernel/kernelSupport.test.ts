// Unit tests for the pure kernelSupport.ts utilities ported in PR #3a:
// deterministic hashing / JSON canonicalization, MCP-config normalization
// (request-scoped env stripping + ordering), the generic column-patch UPDATE
// helper, and value coercers.

import { describe, expect, it, vi } from 'vitest'
import {
  KERNEL_MCP_PROTOCOL_VERSION,
  boundedLimit,
  buildDelegatedPrompt,
  nullableNumber,
  nullableText,
  parseJsonObject,
  placeholders,
  requiredChildSessionId,
  stableJsonHash,
  stableJsonStringify,
  stableMcpServerConfig,
  updateByColumns
} from './kernelSupport'
import { PROTOCOL_VERSION as AUTOMATION_HELPER_PROTOCOL_VERSION } from '../automation/protocol'
import type { AgentStore } from './types'

describe('KERNEL_MCP_PROTOCOL_VERSION', () => {
  // The agent runtime's MCP tool-context contract is macOS protocol v2. Windows
  // ALSO has an unrelated `automation/protocol.ts` exporting PROTOCOL_VERSION = 1
  // — that is the C# UI-automation helper's wire format and has nothing to do with
  // the agent runtime. Importing it here would silently stamp protocolVersion: 1
  // into the MCP context file every adapter reads. Pin the value, and pin that the
  // two are NOT the same number, so the mistake cannot be made quietly.
  it('is 2, matching the macOS agent protocol', () => {
    expect(KERNEL_MCP_PROTOCOL_VERSION).toBe(2)
  })

  it('is not the UI-automation helper protocol version', () => {
    expect(AUTOMATION_HELPER_PROTOCOL_VERSION).toBe(1)
    expect(KERNEL_MCP_PROTOCOL_VERSION).not.toBe(AUTOMATION_HELPER_PROTOCOL_VERSION)
  })
})

describe('kernelSupport — deterministic serialization', () => {
  it('canonicalizes object key order', () => {
    expect(stableJsonStringify({ b: 1, a: 2 })).toBe(stableJsonStringify({ a: 2, b: 1 }))
    expect(stableJsonStringify({ b: 1, a: 2 })).toBe('{"a":2,"b":1}')
  })

  it('produces a stable hash irrespective of key order', () => {
    expect(stableJsonHash({ x: [1, 2], y: 'z' })).toBe(stableJsonHash({ y: 'z', x: [1, 2] }))
  })

  it('strips request-scoped MCP env entries and sorts servers by env name', () => {
    const normalized = stableMcpServerConfig([
      {
        name: 'omi',
        env: [
          { name: 'OMI_REQUEST_ID', value: 'req-123' },
          { name: 'OMI_STATIC', value: 'keep' },
          { name: 'OMI_CONTEXT_FILE', value: '/tmp/ctx.json' }
        ]
      }
    ]) as Array<{ env: Array<{ name: string }> }>
    const envNames = normalized[0].env.map((e) => e.name)
    expect(envNames).toEqual(['OMI_STATIC'])
  })

  it('produces identical hashes when only request-scoped env differs', () => {
    const a = stableJsonHash(
      stableMcpServerConfig([{ name: 'omi', env: [{ name: 'OMI_RUN_ID', value: 'run-a' }] }])
    )
    const b = stableJsonHash(
      stableMcpServerConfig([{ name: 'omi', env: [{ name: 'OMI_RUN_ID', value: 'run-b' }] }])
    )
    expect(a).toBe(b)
  })

  it('treats non-array MCP config as empty', () => {
    expect(stableMcpServerConfig(undefined)).toEqual([])
    expect(stableMcpServerConfig({})).toEqual([])
  })
})

describe('kernelSupport — helpers', () => {
  it('parses JSON objects and rejects arrays / malformed input', () => {
    expect(parseJsonObject('{"a":1}')).toEqual({ a: 1 })
    expect(parseJsonObject('[1,2]')).toEqual({})
    expect(parseJsonObject('not json')).toEqual({})
    expect(parseJsonObject(null)).toEqual({})
  })

  it('bounds limits with a fallback and ceiling', () => {
    expect(boundedLimit(undefined, 50, 500)).toBe(50)
    expect(boundedLimit(1000, 50, 500)).toBe(500)
    expect(boundedLimit(0, 50, 500)).toBe(1)
    expect(boundedLimit(NaN, 50, 500)).toBe(50)
  })

  it('emits N sql placeholders', () => {
    expect(placeholders(3)).toBe('?, ?, ?')
    expect(placeholders(0)).toBe('')
  })

  it('builds a delegated prompt with optional context', () => {
    expect(buildDelegatedPrompt('do it', undefined)).toBe('do it')
    expect(buildDelegatedPrompt('do it', 'because')).toBe('Objective:\ndo it\n\nContext:\nbecause')
  })

  it('requires a child session id in continue mode', () => {
    expect(requiredChildSessionId('ses_1')).toBe('ses_1')
    expect(() => requiredChildSessionId(undefined)).toThrow(/requires childSessionId/)
  })

  it('coerces nullable values', () => {
    expect(nullableText(undefined)).toBeNull()
    expect(nullableText(5)).toBe('5')
    expect(nullableNumber(null)).toBeNull()
    expect(nullableNumber('7')).toBe(7)
  })

  it('updateByColumns skips undefined fields and maps camelCase to columns', () => {
    const execute = vi.fn().mockReturnValue(1)
    const store = { execute } as unknown as AgentStore
    updateByColumns(
      store,
      'runs',
      'run_id',
      'run_1',
      { statusText: 'status', updatedAtMs: 'updated_at_ms' },
      {
        statusText: 'running',
        updatedAtMs: undefined
      } as Record<string, unknown>
    )
    expect(execute).toHaveBeenCalledWith('UPDATE runs SET status = ? WHERE run_id = ?', [
      'running',
      'run_1'
    ])
  })

  it('updateByColumns is a no-op when the patch has no defined fields', () => {
    const execute = vi.fn()
    const store = { execute } as unknown as AgentStore
    updateByColumns(store, 'runs', 'run_id', 'run_1', {}, { a: undefined } as Record<
      string,
      unknown
    >)
    expect(execute).not.toHaveBeenCalled()
  })
})
