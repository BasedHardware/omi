// Kernel support utilities — Windows port of the pure, self-contained helpers
// from the macOS agent runtime's kernel-support.ts
// (desktop/macos/agent/src/runtime/kernel-support.ts).
//
// SCOPE (PR #3a): only the run-path-independent, schema-independent utilities
// live here — status constants, delegation bounds, deterministic hashing /
// JSON canonicalization, the generic column-patch UPDATE helper, and value
// coercers. These have clear standalone unit tests.
//
// DEFERRED to the KernelCore PR (#3b), where they are consumed and can be
// validated against live rows: the row->entity mappers (sessionFromRow etc.),
// the *ColumnMap constants, and the run-path helpers (bindingMetadata,
// mcpServersForBinding, refreshMcpAttemptContext, canonicalAdapterEventType,
// isStaleBindingError). The coordinator/desktop helpers (desktop*FromRow,
// *ToQueueInput, requiresVerifiedContextDispatch, intentCandidateStatus) belong
// to the control-plane PR (#4) and are intentionally omitted.

import { createHash } from 'node:crypto'
import type { AgentStore, RunStatus } from './types'

export { messageFrom } from '../codingAgent/failures'

export const ACTIVE_STATUSES: readonly RunStatus[] = [
  'queued',
  'starting',
  'running',
  'waiting_input',
  'waiting_approval',
  'cancelling'
]
export const TERMINAL_STATUSES: readonly RunStatus[] = [
  'succeeded',
  'failed',
  'cancelled',
  'timed_out',
  'orphaned'
]
export const DEFAULT_DELEGATION_MAX_DEPTH = 3
export const HARD_DELEGATION_MAX_DEPTH = 5
export const DEFAULT_DELEGATION_MAX_BUDGET_USD = 5
export const HARD_DELEGATION_MAX_BUDGET_USD = 10

export function stableHash(value: string | undefined): string {
  return createHash('sha256')
    .update(value ?? '')
    .digest('hex')
}

const REQUEST_SCOPED_MCP_ENV_KEYS = new Set([
  'OMI_BRIDGE_PIPE',
  'OMI_CONTEXT_FILE',
  'OMI_REQUEST_ID',
  'OMI_CLIENT_ID',
  'OMI_PROTOCOL_VERSION',
  'OMI_SESSION_ID',
  'OMI_RUN_ID',
  'OMI_ATTEMPT_ID',
  'OMI_ADAPTER_SESSION_ID'
])

export function stableJsonStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value) ?? 'undefined'
  }
  if (Array.isArray(value)) {
    return `[${value.map((entry) => stableJsonStringify(entry)).join(',')}]`
  }
  const object = value as Record<string, unknown>
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJsonStringify(object[key])}`)
    .join(',')}}`
}

export function stableMcpServerConfig(value: unknown): unknown {
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((server) => {
    if (!server || typeof server !== 'object' || Array.isArray(server)) {
      return server
    }
    const normalized: Record<string, unknown> = { ...(server as Record<string, unknown>) }
    if (Array.isArray(normalized.env)) {
      normalized.env = normalized.env
        .filter((entry) => {
          if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
            return true
          }
          const name = (entry as Record<string, unknown>).name
          return typeof name !== 'string' || !REQUEST_SCOPED_MCP_ENV_KEYS.has(name)
        })
        .sort((left, right) => {
          const leftName =
            left && typeof left === 'object' && !Array.isArray(left)
              ? String((left as Record<string, unknown>).name ?? '')
              : ''
          const rightName =
            right && typeof right === 'object' && !Array.isArray(right)
              ? String((right as Record<string, unknown>).name ?? '')
              : ''
          return leftName.localeCompare(rightName)
        })
    }
    return normalized
  })
}

export function stableJsonHash(value: unknown): string {
  return stableHash(stableJsonStringify(value ?? null))
}

export function parseJsonObject(value: string | null | undefined): Record<string, unknown> {
  if (!value) return {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {}
  } catch {
    return {}
  }
}

export function updateByColumns<T extends Record<string, unknown>>(
  store: AgentStore,
  table: string,
  idColumn: string,
  idValue: string,
  columnMap: Record<string, string>,
  patch: Partial<T>
): void {
  const entries = Object.entries(patch).filter(([, value]) => value !== undefined)
  if (entries.length === 0) return
  const assignments = entries.map(([key]) => `${columnMap[key] ?? key} = ?`).join(', ')
  store.execute(`UPDATE ${table} SET ${assignments} WHERE ${idColumn} = ?`, [
    ...entries.map(([, value]) => value),
    idValue
  ])
}

export function placeholders(count: number): string {
  return Array.from({ length: count }, () => '?').join(', ')
}

export function boundedLimit(value: number | undefined, fallback: number, max: number): number {
  if (value === undefined || !Number.isFinite(value)) return fallback
  return Math.max(1, Math.min(max, Math.floor(value)))
}

export function buildDelegatedPrompt(objective: string, context: string | undefined): string {
  const trimmedObjective = objective.trim()
  const trimmedContext = context?.trim()
  if (!trimmedContext) {
    return trimmedObjective
  }
  return `Objective:\n${trimmedObjective}\n\nContext:\n${trimmedContext}`
}

export function requiredChildSessionId(sessionId: string | undefined): string {
  if (!sessionId) {
    throw new Error('send_agent_message continue mode requires childSessionId')
  }
  return sessionId
}

export function text(value: unknown): string {
  return String(value)
}

export function nullableText(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value)
}

export function nullableNumber(value: unknown): number | null {
  return value === null || value === undefined ? null : Number(value)
}

export function stringValue(value: unknown): string {
  return text(value)
}

export function numberValue(value: unknown): number {
  return Number(value ?? 0)
}

export function nullableString(value: unknown): string | null {
  return nullableText(value)
}
