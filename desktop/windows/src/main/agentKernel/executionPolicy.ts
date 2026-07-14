// Execution-policy guards — Windows port of the macOS agent runtime's
// execution-policy.ts (desktop/macos/agent/src/runtime/execution-policy.ts).
//
// Two concerns live here:
//  1. Provider boundaries — a session is pinned to the credential scope of the
//     adapter that first ran it, so a locally-authenticated provider can never
//     be silently rerouted to a managed one (or vice versa).
//  2. Leaf-role guards — leaf (delegated/background) agents may not use the
//     agent-control tools that spawn or message other agents, so a worker
//     cannot recursively fan out. (INV-AGENT leaf-role guard.)
//
// AgentExecutionRole and ProviderBoundary are owned by ./types (the store uses
// them), so we import rather than redefine them.

import {
  adapterCredentialScopeFor,
  isProductionAdapterId,
  type AdapterCredentialScope,
  type ProductionAdapterId
} from '../codingAgent/interface'
import type { AgentExecutionRole, ProviderBoundary } from './types'

export type { AgentExecutionRole, ProviderBoundary }

/**
 * Agent-control tools a leaf worker is forbidden from calling. A leaf agent is
 * a terminal executor; only coordinators may spawn or message other agents.
 */
export const LEAF_AGENT_CONTROL_TOOLS = new Set([
  'send_agent_message',
  'spawn_background_agent',
  'spawn_agent',
  'run_agent_and_wait'
])

/**
 * Adapter ids whose credentials are Omi-managed cloud routing but which have no
 * Windows adapter implementation yet. macOS ships `pi-mono` as a managed-cloud
 * production adapter, so a session persisted against it must pin to
 * `managed_cloud` here too — otherwise the same session would resolve to a
 * different credential scope on the two platforms, which is exactly what the
 * provider boundary exists to prevent. Remove an id from this set once a real
 * Windows adapter for it is registered in ADAPTER_CAPABILITY_MATRIX.
 */
const MANAGED_CLOUD_ADAPTER_IDS = new Set<string>(['pi-mono'])

export function providerBoundaryForAdapter(adapterId: string): ProviderBoundary {
  if (isProductionAdapterId(adapterId)) {
    return adapterCredentialScopeFor(adapterId) === 'managed_cloud'
      ? 'managed_cloud'
      : `local_user:${adapterId}`
  }
  if (MANAGED_CLOUD_ADAPTER_IDS.has(adapterId)) {
    return 'managed_cloud'
  }
  return `local_user:${adapterId}`
}

export function credentialScopeForBoundary(boundary: ProviderBoundary): AdapterCredentialScope {
  return boundary === 'managed_cloud' ? 'managed_cloud' : 'local_user'
}

export function resolveAdapterWithinBoundary(input: {
  providerBoundary: ProviderBoundary
  defaultAdapterId: string
  requestedAdapterId?: string
}): string {
  const requestedAdapterId = input.requestedAdapterId ?? input.defaultAdapterId
  if (!isProductionAdapterId(input.defaultAdapterId)) {
    // Test/development adapters are deliberately outside the production
    // registry. They may only keep their current adapter identity.
    if (requestedAdapterId !== input.defaultAdapterId) {
      throw new Error(`Adapter ${requestedAdapterId} is outside the owning execution boundary.`)
    }
    return requestedAdapterId
  }
  if (!isProductionAdapterId(requestedAdapterId)) {
    throw new Error(`Unknown production adapter: ${requestedAdapterId}`)
  }
  if (requestedAdapterId === 'acp' && input.providerBoundary !== 'local_user:acp') {
    throw new Error('Local Claude is available only when the User Claude mode is selected.')
  }
  if (input.providerBoundary === 'managed_cloud') {
    if (adapterCredentialScopeFor(requestedAdapterId) !== 'managed_cloud') {
      throw new Error('Managed Omi agents can only use Omi cloud routing.')
    }
    return requestedAdapterId
  }
  const pinnedAdapterId = input.providerBoundary.slice('local_user:'.length)
  if (requestedAdapterId !== pinnedAdapterId) {
    if (requestedAdapterId === 'acp') {
      throw new Error('Local Claude is available only when the User Claude mode is selected.')
    }
    throw new Error(`Local provider mode is pinned to ${pinnedAdapterId}.`)
  }
  return requestedAdapterId
}

export function assertProductionAdapterScopeDeclared(adapterId: ProductionAdapterId): void {
  const scope = adapterCredentialScopeFor(adapterId)
  if (scope !== 'managed_cloud' && scope !== 'local_user') {
    throw new Error(`Production adapter ${adapterId} is missing credentialScope`)
  }
}

export function executionRoleAllowsTool(role: AgentExecutionRole, toolName: string): boolean {
  return role !== 'leaf' || !LEAF_AGENT_CONTROL_TOOLS.has(toolName)
}

export function executionRoleForSurface(input: {
  surfaceKind: string
  externalRefKind?: string | null
}): AgentExecutionRole {
  return input.surfaceKind === 'delegated_agent' ||
    input.surfaceKind === 'background_agent' ||
    (input.surfaceKind === 'floating_bar' && input.externalRefKind === 'pill')
    ? 'leaf'
    : 'coordinator'
}
