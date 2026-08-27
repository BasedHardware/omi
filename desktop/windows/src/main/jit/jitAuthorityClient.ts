import { fetchWithFreshToken, getAbortSignal, getBackendSession } from '../assistants/core/session'
import { createHash } from 'node:crypto'
import type {
  JitRolloutDecision,
  JitRuntimePolicy,
  JitTriggerSnapshot
} from '../../shared/jitTriggerRuntime'
import type { JitLedgerMirrorPage } from './jitTriggerMirror'

export type JitAuthorityClient = {
  rolloutDecision(): Promise<JitRolloutDecision>
  triggerSnapshot(): Promise<JitTriggerSnapshot>
  ledgerMirrorPage(cursor?: string | null): Promise<JitLedgerMirrorPage>
  reserveProactivity?: (input: JitProactivityReservationInput) => Promise<JitProactivityReservation>
}

export type JitProactivityOperation =
  | 'planned_notification'
  | 'ambient_notification'
  | 'nano_triage'
  | 'full_turn'

export type JitProactivityReservationInput = {
  eventId: string
  candidateId: string
  operation: JitProactivityOperation
  accountGeneration: number
  deviceId: string
  triggerMemoryId?: string | null
  triggerRevision?: number | null
  parentEventId?: string | null
}

export type JitProactivityEventReceipt = {
  schemaVersion: 'jit_proactivity_event.v1'
  uid: string
  eventId: string
  candidateId: string
  operation: JitProactivityOperation
  accountGeneration: number
  triggerMemoryId: string | null
  triggerRevision: number | null
  budgetDay: string
  deviceId: string
  createdAt: string
  requestHash: string
  feedbackId: string | null
  parentEventId: string | null
}

export type JitProactivityReservation = {
  reserved: boolean
  receipt: JitProactivityEventReceipt
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

function parsePositiveInteger(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0 || value > 1_000)
    throw new Error(`malformed jit policy ${name}`)
  return value
}

function parseTimezoneAwareSnooze(value: unknown): string | null {
  if (value === null) return null
  const candidate = typeof value === 'string' ? value : null
  const match =
    candidate !== null
      ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.exec(
          candidate
        )
      : null
  if (!match) throw new Error('malformed trigger snapshot snooze')
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const hour = Number(match[4])
  const minute = Number(match[5])
  const second = Number(match[6])
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > new Date(Date.UTC(year, month, 0)).getUTCDate() ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    !Number.isFinite(Date.parse(candidate as string))
  )
    throw new Error('malformed trigger snapshot snooze')
  return candidate as string
}

function parsePolicy(value: unknown): JitRuntimePolicy {
  const record = asRecord(value)
  const embedding = asRecord(record?.embedding)
  if (
    !record ||
    record.schema_version !== 'jit_trigger_policy.v1' ||
    !embedding ||
    typeof embedding.enabled !== 'boolean' ||
    typeof embedding.match_similarity !== 'number' ||
    typeof embedding.triage_similarity !== 'number'
  )
    throw new Error('malformed jit policy')
  const modelId = embedding.model_id
  const modelVersion = embedding.model_version
  const language = embedding.language
  if (
    (modelId !== null && typeof modelId !== 'string') ||
    (modelVersion !== null && typeof modelVersion !== 'string') ||
    (language !== null && typeof language !== 'string') ||
    embedding.match_similarity < 0 ||
    embedding.match_similarity > 1 ||
    embedding.triage_similarity < 0 ||
    embedding.triage_similarity >= embedding.match_similarity
  )
    throw new Error('malformed jit policy embedding')
  if (
    embedding.match_similarity !== 0.82 ||
    embedding.triage_similarity !== 0.74 ||
    (embedding.enabled &&
      (typeof modelId !== 'string' ||
        typeof modelVersion !== 'string' ||
        typeof language !== 'string')) ||
    (!embedding.enabled && (modelId !== null || modelVersion !== null || language !== null))
  )
    throw new Error('unsupported jit policy embedding contract')
  const plannedNotifications = parsePositiveInteger(
    record.planned_notifications_per_trigger_per_day,
    'planned_notifications_per_trigger_per_day'
  )
  const totalNotifications = parsePositiveInteger(
    record.total_proactive_notifications_per_day,
    'total_proactive_notifications_per_day'
  )
  const nanoTriages = parsePositiveInteger(
    record.ambiguous_nano_triages_per_day,
    'ambiguous_nano_triages_per_day'
  )
  const fullTurns = parsePositiveInteger(
    record.full_agent_turns_per_candidate,
    'full_agent_turns_per_candidate'
  )
  const maxCalendarEvents = parsePositiveInteger(record.max_calendar_events, 'max_calendar_events')
  if (
    plannedNotifications !== 1 ||
    totalNotifications !== 3 ||
    nanoTriages !== 8 ||
    fullTurns !== 1 ||
    maxCalendarEvents !== 32
  )
    throw new Error('unsupported jit policy contract')
  return {
    schemaVersion: 'jit_trigger_policy.v1',
    plannedNotificationsPerTriggerPerDay: plannedNotifications,
    totalProactiveNotificationsPerDay: totalNotifications,
    ambiguousNanoTriagesPerDay: nanoTriages,
    fullAgentTurnsPerCandidate: fullTurns,
    maxCalendarEvents,
    embedding: {
      enabled: embedding.enabled,
      matchSimilarity: embedding.match_similarity,
      triageSimilarity: embedding.triage_similarity,
      modelId: modelId as string | null,
      modelVersion: modelVersion as string | null,
      language: language as string | null
    }
  }
}

function parseSnapshot(value: unknown): JitTriggerSnapshot {
  const record = asRecord(value)
  if (
    !record ||
    typeof record.owner_id !== 'string' ||
    typeof record.account_generation !== 'number' ||
    typeof record.commit_sequence !== 'number' ||
    typeof record.head_commit_id !== 'string' ||
    typeof record.snapshot_revision !== 'string' ||
    typeof record.complete !== 'boolean' ||
    !Array.isArray(record.rows)
  )
    throw new Error('malformed trigger snapshot')
  const rows = record.rows.map((raw) => {
    const row = asRecord(raw)
    const action = asRecord(row?.action)
    if (
      !row ||
      !action ||
      typeof row.memory_id !== 'string' ||
      typeof row.item_revision !== 'number' ||
      typeof row.updated_at !== 'string' ||
      typeof row.trigger_condition_json !== 'string' ||
      action.type !== 'agent_prompt' ||
      typeof action.prompt !== 'string'
    )
      throw new Error('malformed trigger snapshot row')
    const budget = row.wakeup_budget_per_day
    if (!Object.prototype.hasOwnProperty.call(row, 'snoozed_until'))
      throw new Error('malformed trigger snapshot snooze')
    if (
      budget !== null &&
      budget !== undefined &&
      (typeof budget !== 'number' || !Number.isInteger(budget))
    )
      throw new Error('malformed trigger snapshot budget')
    return {
      memoryId: row.memory_id,
      itemRevision: row.item_revision,
      updatedAt: row.updated_at,
      triggerConditionJson: row.trigger_condition_json,
      action: { type: 'agent_prompt' as const, prompt: action.prompt },
      wakeupBudgetPerDay: budget === undefined ? null : budget,
      snoozedUntil: parseTimezoneAwareSnooze(row.snoozed_until)
    }
  })
  return {
    ownerId: record.owner_id,
    accountGeneration: record.account_generation,
    headCommitId: record.head_commit_id,
    commitSequence: record.commit_sequence,
    snapshotRevision: record.snapshot_revision,
    complete: record.complete,
    rows,
    failureReason: typeof record.failure_reason === 'string' ? record.failure_reason : null,
    policy: parsePolicy(record.policy)
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

function parseProactivityReservation(
  value: unknown,
  expected: JitProactivityReservationInput,
  ownerId: string
): JitProactivityReservation {
  const envelope = asRecord(value)
  const receipt = asRecord(envelope?.receipt)
  if (!envelope || typeof envelope.reserved !== 'boolean' || !receipt)
    throw new Error('malformed jit proactivity reservation')
  if (
    !/^[a-f0-9]{64}$/.test(expected.eventId) ||
    !/^[a-f0-9]{64}$/.test(expected.candidateId) ||
    !/^[a-f0-9]{64}$/.test(expected.deviceId) ||
    (expected.parentEventId !== null &&
      expected.parentEventId !== undefined &&
      !/^[a-f0-9]{64}$/.test(expected.parentEventId))
  )
    throw new Error('malformed jit proactivity identity')
  const operation = receipt.operation
  const triggerMemoryId = receipt.trigger_memory_id
  const triggerRevision = receipt.trigger_revision
  const expectedRequestHash = createHash('sha256')
    .update(
      JSON.stringify({
        account_generation: expected.accountGeneration,
        candidate_id: expected.candidateId,
        device_id: expected.deviceId,
        event_id: expected.eventId,
        operation: expected.operation,
        parent_event_id: expected.parentEventId ?? null,
        schema_version: 'jit_proactivity_event.v1',
        trigger_memory_id: expected.triggerMemoryId ?? null,
        trigger_revision: expected.triggerRevision ?? null,
        uid: ownerId
      })
    )
    .digest('hex')
  if (
    receipt.schema_version !== 'jit_proactivity_event.v1' ||
    receipt.uid !== ownerId ||
    typeof receipt.event_id !== 'string' ||
    receipt.event_id !== expected.eventId ||
    typeof receipt.candidate_id !== 'string' ||
    receipt.candidate_id !== expected.candidateId ||
    operation !== expected.operation ||
    typeof receipt.account_generation !== 'number' ||
    !Number.isInteger(receipt.account_generation) ||
    receipt.account_generation !== expected.accountGeneration ||
    (triggerMemoryId !== null && typeof triggerMemoryId !== 'string') ||
    (triggerRevision !== null &&
      (typeof triggerRevision !== 'number' || !Number.isInteger(triggerRevision))) ||
    (expected.triggerMemoryId ?? null) !== (triggerMemoryId ?? null) ||
    (expected.triggerRevision ?? null) !== (triggerRevision ?? null) ||
    typeof receipt.budget_day !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}$/.test(receipt.budget_day) ||
    typeof receipt.device_id !== 'string' ||
    receipt.device_id !== expected.deviceId ||
    typeof receipt.created_at !== 'string' ||
    !Number.isFinite(Date.parse(receipt.created_at)) ||
    typeof receipt.request_hash !== 'string' ||
    receipt.request_hash !== expectedRequestHash ||
    (receipt.feedback_id !== null && typeof receipt.feedback_id !== 'string') ||
    (receipt.parent_event_id !== undefined &&
      receipt.parent_event_id !== null &&
      typeof receipt.parent_event_id !== 'string') ||
    (expected.parentEventId ?? null) !== (receipt.parent_event_id ?? null)
  )
    throw new Error('malformed jit proactivity receipt')
  return {
    reserved: envelope.reserved,
    receipt: {
      schemaVersion: 'jit_proactivity_event.v1',
      uid: ownerId,
      eventId: receipt.event_id,
      candidateId: receipt.candidate_id,
      operation: operation as JitProactivityOperation,
      accountGeneration: receipt.account_generation,
      triggerMemoryId: (triggerMemoryId as string | null) ?? null,
      triggerRevision: (triggerRevision as number | null) ?? null,
      budgetDay: receipt.budget_day,
      deviceId: receipt.device_id,
      createdAt: receipt.created_at,
      requestHash: receipt.request_hash,
      feedbackId: (receipt.feedback_id as string | null) ?? null,
      parentEventId: (receipt.parent_event_id as string | null) ?? null
    }
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
    async triggerSnapshot(): Promise<JitTriggerSnapshot> {
      if (!session()) throw new Error('backend session unavailable')
      return parseSnapshot(await request('/v1/jit/trigger-snapshot'))
    },
    async ledgerMirrorPage(cursor?: string | null): Promise<JitLedgerMirrorPage> {
      if (!session()) throw new Error('backend session unavailable')
      const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
      return parseLedgerMirrorPage(
        await request('/v1/jit/knowledge-ledger/mirror-snapshot' + query)
      )
    },
    async reserveProactivity(
      input: JitProactivityReservationInput
    ): Promise<JitProactivityReservation> {
      const current = session()
      if (!current) throw new Error('backend session unavailable')
      const response = await fetchWithFreshToken(async (fresh) => {
        const result = await doFetch(`${fresh.apiBase}/v1/jit/proactivity/reservations`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${fresh.token}`,
            'Content-Type': 'application/json',
            'X-App-Platform': 'windows'
          },
          signal: signal(),
          body: JSON.stringify({
            event_id: input.eventId,
            candidate_id: input.candidateId,
            operation: input.operation,
            account_generation: input.accountGeneration,
            device_id: input.deviceId,
            ...(input.parentEventId == null ? {} : { parent_event_id: input.parentEventId }),
            ...(input.triggerMemoryId == null ? {} : { trigger_memory_id: input.triggerMemoryId }),
            ...(input.triggerRevision == null ? {} : { trigger_revision: input.triggerRevision })
          })
        })
        return result
      }, 'jit:proactivity-reservation')
      if (!response.ok) throw new Error(`jit proactivity reservation http ${response.status}`)
      return parseProactivityReservation(
        await response.json(),
        input,
        tokenOwnerId(current.token) ?? ''
      )
    }
  }
}

function tokenOwnerId(token: string): string | null {
  try {
    const payload = JSON.parse(
      Buffer.from(token.split('.')[1] ?? '', 'base64').toString('utf8')
    ) as {
      sub?: unknown
      user_id?: unknown
    }
    const owner = payload.user_id ?? payload.sub
    return typeof owner === 'string' && owner.trim() ? owner.trim() : null
  } catch {
    return null
  }
}

export {
  parseDecision as parseJitRolloutDecision,
  parseSnapshot as parseJitTriggerSnapshot,
  parseLedgerMirrorPage as parseJitLedgerMirrorPage,
  parseProactivityReservation as parseJitProactivityReservation
}
