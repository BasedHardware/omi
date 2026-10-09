import { fetchWithFreshToken, getAbortSignal, getBackendSession } from '../assistants/core/session'

import type { JitRolloutDecision } from '../../shared/jitRollout'

import type { JitLedgerMirrorPage } from './jitTriggerMirror'


export type JitAuthorityClient = {
  rolloutDecision(): Promise<JitRolloutDecision>
  ledgerMirrorPage(cursor?: string | null): Promise<JitLedgerMirrorPage>
}

export type JitAuthorityClientDeps = {
  fetch?: typeof fetch
  session?: () => ReturnType<typeof getBackendSession>
  signal?: () => AbortSignal | undefined
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function parseDecision(value: unknown): JitRolloutDecision {
  const record = asRecord(value)
  if (
    !record ||
    !['enabled', 'disabled', 'unknown'].includes(String(record.rollout)) ||
    !['enabled', 'disabled', 'unknown'].includes(String(record.kill_switch)) ||
    !['enabled', 'disabled', 'unknown'].includes(String(record.effective))
  )
    throw new Error('malformed rollout decision')
  return {
    rollout: record.rollout as JitRolloutDecision['rollout'],
    killSwitch: record.kill_switch as JitRolloutDecision['killSwitch'],
    effective: record.effective as JitRolloutDecision['effective'],
    reason: String(record.reason ?? 'malformed_response'),
    errorClass: String(record.error_class ?? 'malformed')
  }
}

function parseLedgerMirrorPage(value: unknown): JitLedgerMirrorPage {
  const record = asRecord(value)
  if (
    !record ||
    record.schema_version !== 'knowledge_ledger_mirror.v1' ||
    typeof record.owner_id !== 'string' ||
    typeof record.account_generation !== 'number' ||
    typeof record.source_generation !== 'number' ||
    typeof record.writer_epoch !== 'number' ||
    typeof record.head_commit_id !== 'string' ||
    typeof record.commit_sequence !== 'number' ||
    typeof record.epoch_id !== 'string' ||
    typeof record.page_revision !== 'string' ||
    typeof record.chain_revision !== 'string' ||
    !Number.isInteger(record.scanned_count) ||
    (record.scanned_count as number) < 0 ||
    !Number.isInteger(record.projected_count) ||
    (record.projected_count as number) < 0 ||
    (record.projected_count as number) > (record.scanned_count as number) ||
    !Array.isArray(record.rows) ||
    !Array.isArray(record.aliases) ||
    (record.next_cursor !== null && typeof record.next_cursor !== 'string') ||
    typeof record.final_page !== 'boolean'
  )
    throw new Error('malformed ledger mirror page')
  const rows = record.rows.map((raw) => {
    const row = asRecord(raw)
    if (
      !row ||
      typeof row.memory_id !== 'string' ||
      typeof row.item_revision !== 'number' ||
      typeof row.status !== 'string' ||
      typeof row.source_state !== 'string' ||
      (row.canonical_memory_id !== null && typeof row.canonical_memory_id !== 'string') ||
      typeof row.content_purged !== 'boolean' ||
      (row.memory !== null && asRecord(row.memory) === null)
    )
      throw new Error('malformed ledger mirror row')
    return {
      memoryId: row.memory_id,
      itemRevision: row.item_revision,
      status: row.status,
      sourceState: row.source_state,
      canonicalMemoryId: row.canonical_memory_id as string | null,
      contentPurged: row.content_purged,
      memory: row.memory as Record<string, unknown> | null
    }
  })
  const aliases = record.aliases.map((raw) => {
    const alias = asRecord(raw)
    if (
      !alias ||
      typeof alias.alias_memory_id !== 'string' ||
      typeof alias.canonical_memory_id !== 'string' ||
      typeof alias.source_memory_id !== 'string' ||
      (alias.reason !== 'canonical_memory_id' && alias.reason !== 'superseded_by')
    )
      throw new Error('malformed ledger mirror alias')
    return {
      aliasMemoryId: alias.alias_memory_id,
      canonicalMemoryId: alias.canonical_memory_id,
      sourceMemoryId: alias.source_memory_id,
      reason: alias.reason as 'canonical_memory_id' | 'superseded_by'
    }
  })
  const terminalCount = record.terminal_count
  if (
    terminalCount !== undefined &&
    (typeof terminalCount !== 'number' || !Number.isInteger(terminalCount) || terminalCount < 0)
  )
    throw new Error('malformed ledger mirror terminal count')
  return {
    schemaVersion: 'knowledge_ledger_mirror.v1',
    ownerId: record.owner_id,
    accountGeneration: record.account_generation,
    sourceGeneration: record.source_generation,
    writerEpoch: record.writer_epoch,
    headCommitId: record.head_commit_id,
    commitSequence: record.commit_sequence,
    epochId: record.epoch_id,
    pageRevision: record.page_revision,
    chainRevision: record.chain_revision,
    scannedCount: record.scanned_count as number,
    projectedCount: record.projected_count as number,
    terminalCountFromServer: terminalCount !== undefined,
    terminalCount:
      terminalCount === undefined
        ? rows.filter((row) => row.status !== 'active').length
        : terminalCount,
    rows,
    aliases,
    nextCursor: (record.next_cursor as string | null) ?? null,
    finalPage: record.final_page,
    failureReason: typeof record.failure_reason === 'string' ? record.failure_reason : null
  }
}

export function createJitAuthorityClient(deps: JitAuthorityClientDeps = {}): JitAuthorityClient {
  const doFetch = deps.fetch ?? fetch
  const session = deps.session ?? getBackendSession
  const signal = deps.signal ?? getAbortSignal
  const request = async (path: string): Promise<unknown> => {
    const response = await fetchWithFreshToken(async (current) => {
      const result = await doFetch(`${current.apiBase}${path}`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${current.token}`, 'X-App-Platform': 'windows' },
        signal: signal()
      })
      return result
    }, `jit:${path}`)
    if (!response.ok) throw new Error(`jit authority http ${response.status}`)
    return response.json()
  }
  return {
    async rolloutDecision(): Promise<JitRolloutDecision> {
      if (!session()) throw new Error('backend session unavailable')
      return parseDecision(await request('/v1/jit/rollout-decision'))
    },
    async ledgerMirrorPage(cursor?: string | null): Promise<JitLedgerMirrorPage> {
      if (!session()) throw new Error('backend session unavailable')
      const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
      return parseLedgerMirrorPage(
        await request('/v1/jit/knowledge-ledger/mirror-snapshot' + query)
      )
    },

  }
}
export { parseDecision as parseJitRolloutDecision, parseLedgerMirrorPage as parseJitLedgerMirrorPage }
