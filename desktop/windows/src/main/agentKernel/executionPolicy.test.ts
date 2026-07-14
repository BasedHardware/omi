// Port-parity tests for executionPolicy.ts (macOS execution-policy.ts). Covers
// the leaf-role control-tool guard (INV-AGENT) and the provider-boundary
// resolution that pins a session to its adapter's credential scope.

import { describe, expect, it } from 'vitest'
import {
  LEAF_AGENT_CONTROL_TOOLS,
  credentialScopeForBoundary,
  executionRoleAllowsTool,
  executionRoleForSurface,
  providerBoundaryForAdapter,
  resolveAdapterWithinBoundary
} from './executionPolicy'

describe('executionPolicy — leaf-role guards', () => {
  it('blocks leaf workers from every agent-control tool', () => {
    for (const tool of LEAF_AGENT_CONTROL_TOOLS) {
      expect(executionRoleAllowsTool('leaf', tool)).toBe(false)
    }
  })

  it('allows leaf workers non-control tools and allows coordinators everything', () => {
    expect(executionRoleAllowsTool('leaf', 'search_memory')).toBe(true)
    expect(executionRoleAllowsTool('coordinator', 'spawn_background_agent')).toBe(true)
    expect(executionRoleAllowsTool('coordinator', 'send_agent_message')).toBe(true)
  })

  it('classifies delegated/background/pill surfaces as leaf, everything else coordinator', () => {
    expect(executionRoleForSurface({ surfaceKind: 'delegated_agent' })).toBe('leaf')
    expect(executionRoleForSurface({ surfaceKind: 'background_agent' })).toBe('leaf')
    expect(executionRoleForSurface({ surfaceKind: 'floating_bar', externalRefKind: 'pill' })).toBe(
      'leaf'
    )
    expect(executionRoleForSurface({ surfaceKind: 'floating_bar', externalRefKind: 'chat' })).toBe(
      'coordinator'
    )
    expect(executionRoleForSurface({ surfaceKind: 'main_chat' })).toBe('coordinator')
  })
})

describe('executionPolicy — provider boundaries', () => {
  it('derives a local_user boundary for every Windows adapter', () => {
    // Windows ships only local-user adapters (no managed_cloud pi-mono).
    expect(providerBoundaryForAdapter('acp')).toBe('local_user:acp')
    expect(providerBoundaryForAdapter('openclaw')).toBe('local_user:openclaw')
    expect(providerBoundaryForAdapter('hermes')).toBe('local_user:hermes')
    expect(providerBoundaryForAdapter('codex')).toBe('local_user:codex')
  })

  it('maps a boundary back to a credential scope', () => {
    expect(credentialScopeForBoundary('local_user:acp')).toBe('local_user')
    expect(credentialScopeForBoundary('managed_cloud')).toBe('managed_cloud')
  })

  it('keeps a request within its pinned local boundary', () => {
    expect(
      resolveAdapterWithinBoundary({
        providerBoundary: 'local_user:acp',
        defaultAdapterId: 'acp',
        requestedAdapterId: 'acp'
      })
    ).toBe('acp')
    expect(
      resolveAdapterWithinBoundary({
        providerBoundary: 'local_user:openclaw',
        defaultAdapterId: 'openclaw',
        requestedAdapterId: 'openclaw'
      })
    ).toBe('openclaw')
  })

  it('rejects Local Claude unless the User Claude boundary is selected', () => {
    expect(() =>
      resolveAdapterWithinBoundary({
        providerBoundary: 'local_user:openclaw',
        defaultAdapterId: 'openclaw',
        requestedAdapterId: 'acp'
      })
    ).toThrow(/User Claude mode/)
  })

  it('rejects crossing from one pinned local provider to another', () => {
    expect(() =>
      resolveAdapterWithinBoundary({
        providerBoundary: 'local_user:openclaw',
        defaultAdapterId: 'openclaw',
        requestedAdapterId: 'hermes'
      })
    ).toThrow(/pinned to openclaw/)
  })

  it('rejects an unknown production adapter', () => {
    expect(() =>
      resolveAdapterWithinBoundary({
        providerBoundary: 'local_user:acp',
        defaultAdapterId: 'acp',
        requestedAdapterId: 'nope'
      })
    ).toThrow(/Unknown production adapter/)
  })

  it('lets a non-production (test) adapter keep only its own identity', () => {
    expect(
      resolveAdapterWithinBoundary({
        providerBoundary: 'local_user:test-adapter',
        defaultAdapterId: 'test-adapter',
        requestedAdapterId: 'test-adapter'
      })
    ).toBe('test-adapter')
    expect(() =>
      resolveAdapterWithinBoundary({
        providerBoundary: 'local_user:test-adapter',
        defaultAdapterId: 'test-adapter',
        requestedAdapterId: 'acp'
      })
    ).toThrow(/outside the owning execution boundary/)
  })
})
