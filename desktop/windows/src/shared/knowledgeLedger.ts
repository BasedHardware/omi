/**
 * Additive client contracts for knowledge_ledger.v1.
 *
 * The wire remains tolerant: released Windows clients can read a newer row
 * without manufacturing a kind, lifecycle state, or text value they do not
 * understand. `content` is the authoritative text for every row; optional
 * fields below are projections/metadata only.
 */

export const KNOWLEDGE_LEDGER_SCHEMA_VERSION = 'knowledge_ledger.v1' as const

export type KnowledgeLedgerKind = 'fact' | 'document' | 'trigger' | 'unknown'
export type KnowledgeLedgerStatus = 'active' | 'superseded' | 'tombstoned' | 'purged' | 'unknown'
export type KnowledgeLedgerSubjectScope =
  | 'primary_user'
  | 'user_owned_project'
  | 'user_relationship'
  | 'third_party'
  | 'unknown'

export type KnowledgeLedgerEvidence = {
  artifact_ref?: Record<string, unknown>
  capture_confidence?: number | null
  client_device_id?: string | null
  created_at?: string
  evidence_id?: string
  extractor_id?: string
  extractor_version?: string
  independence_group?: string
  redaction_status?: string
  source_id?: string | null
  source_signal?: string
  source_type?: string | null
  source_state?: string | null
  [key: string]: unknown
}

/**
 * The common released-memory shape plus the additive ledger fields. All ledger
 * fields are optional so this remains a safe adapter for legacy /v3 rows.
 */
export type KnowledgeLedgerMemory = {
  id: string
  uid: string
  content: string
  headline?: string | null
  category?: string
  visibility?: string | null
  tags?: string[]
  created_at: string
  updated_at: string
  conversation_id?: string | null
  layer?: string | null
  memory_tier?: string | null
  primary_capture_device?: string | null
  capture_device_ids?: string[]
  manually_added?: boolean
  capture_confidence?: number | null
  app_id?: string | null
  evidence?: KnowledgeLedgerEvidence[]

  ledger_schema_version?: string
  memory_id?: string | null
  kind?: KnowledgeLedgerKind
  status?: KnowledgeLedgerStatus
  subject_scope?: KnowledgeLedgerSubjectScope
  subject_entity_id?: string | null
  subject_attribution?: 'user' | 'third_party' | 'unknown' | 'legacy_assumed' | string
  slot?: string | null
  valid_from?: string | null
  valid_to?: string | null
  valid_at?: string | null
  invalid_at?: string | null
  superseded_by?: string | null
  canonical_memory_id?: string | null
  curation_weight?: number | null
  intent_backed?: boolean
  user_asserted?: boolean
  write_reason?: string | null
  sensitivity?: string | null
  account_generation?: number | null
  item_revision?: number | null
  ledger_commit_id?: string | null
  ledger_sequence?: number | null
  body?: string | null
  trigger_condition?: Record<string, unknown> | null
  arguments?: Record<string, unknown>
  predicate?: string | null
  qualifiers?: Record<string, unknown>
  object_entity_ids?: string[]
  uncertainty_reasons?: string[]
  veracity?: number | null
  durability?: string | null
  edited?: boolean
  reviewed?: boolean
  user_review?: boolean | null
  is_baseline?: boolean
  is_locked?: boolean
  is_read?: boolean
  is_dismissed?: boolean
  deleted?: boolean
  [key: string]: unknown
}

export type ChatEvidenceReferenceKind =
  | 'conversation_summary'
  | 'conversation_segment'
  | 'screen'
  | 'keyframe'
  | 'request'
  | 'unknown'

export type ChatEvidenceReferenceState =
  | 'available'
  | 'loading'
  | 'offline'
  | 'pruned'
  | 'failed'
  | 'unknown'

export type ChatEvidenceReference = {
  id: string
  kind: ChatEvidenceReferenceKind
  state: ChatEvidenceReferenceState
  title?: string
  summary?: string
  conversationId?: string
  segmentId?: string
  frameId?: string
  requestId?: string
  startMs?: number
  endMs?: number
  capturedAtMs?: number
  errorCode?: string
  errorMessage?: string
  metadata: Record<string, unknown>
}

export type ChatEvidenceReferenceEnvelope = {
  schemaVersion: number
  requestId?: string
  references: ChatEvidenceReference[]
}

export const CHAT_EVIDENCE_MAX_REFERENCES = 24
export const CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS = 256
export const CHAT_EVIDENCE_MAX_TITLE_CHARS = 160
export const CHAT_EVIDENCE_MAX_SUMMARY_CHARS = 600
export const CHAT_EVIDENCE_MAX_ERROR_CODE_CHARS = 128
export const CHAT_EVIDENCE_MAX_ERROR_MESSAGE_CHARS = 600
export const CHAT_EVIDENCE_MAX_METADATA_ENTRIES = 16
export const CHAT_EVIDENCE_MAX_METADATA_SERIALIZED_CHARS = 2_000
export const CHAT_EVIDENCE_MAX_METADATA_DEPTH = 3
export const CHAT_EVIDENCE_MAX_METADATA_LIST_ITEMS = 24

const LEDGER_KINDS: ReadonlySet<KnowledgeLedgerKind> = new Set(['fact', 'document', 'trigger'])
const LEDGER_STATUSES: ReadonlySet<KnowledgeLedgerStatus> = new Set([
  'active',
  'superseded',
  'tombstoned',
  'purged'
])
const LEDGER_SUBJECT_SCOPES: ReadonlySet<KnowledgeLedgerSubjectScope> = new Set([
  'primary_user',
  'user_owned_project',
  'user_relationship',
  'third_party'
])
const EVIDENCE_KINDS: ReadonlySet<ChatEvidenceReferenceKind> = new Set([
  'conversation_summary',
  'conversation_segment',
  'screen',
  'keyframe',
  'request'
])
const EVIDENCE_STATES: ReadonlySet<ChatEvidenceReferenceState> = new Set([
  'available',
  'loading',
  'offline',
  'pruned',
  'failed'
])

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    !(value instanceof Map) &&
    !(value instanceof Set)
  )
}

function asRecord(value: unknown): JsonRecord | null {
  return isRecord(value) ? value : null
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function boundedString(value: unknown, maxLength?: number): string | undefined {
  const stringValue = asString(value)?.trim()
  if (!stringValue) return undefined
  return maxLength === undefined ? stringValue : stringValue.slice(0, maxLength)
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === 'boolean' || value === null || value === undefined) return undefined
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? Math.trunc(parsed) : undefined
}

function asFiniteNumber(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  return value
}

function asBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined
}

function asStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined
  const result = value
    .map((item) => boundedString(item))
    .filter((item): item is string => item !== undefined)
  return result
}

function boundedMetadataValue(value: unknown, depth: number): unknown {
  if (value === null || typeof value === 'boolean') return value
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined
  if (typeof value === 'string') return boundedString(value, CHAT_EVIDENCE_MAX_SUMMARY_CHARS)
  if (depth > CHAT_EVIDENCE_MAX_METADATA_DEPTH) return undefined
  if (Array.isArray(value)) {
    return value
      .slice(0, CHAT_EVIDENCE_MAX_METADATA_LIST_ITEMS)
      .map((item) => boundedMetadataValue(item, depth + 1))
      .filter((item): item is Exclude<typeof item, undefined> => item !== undefined)
  }
  const record = asRecord(value)
  if (!record) return undefined
  const result: Record<string, unknown> = {}
  for (const [key, item] of Object.entries(record).slice(0, CHAT_EVIDENCE_MAX_METADATA_ENTRIES)) {
    const boundedKey = boundedString(key, CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS)
    const boundedItem = boundedMetadataValue(item, depth + 1)
    if (boundedKey && boundedItem !== undefined) result[boundedKey] = boundedItem
  }
  return result
}

function boundedRecordCopy(value: unknown): Record<string, unknown> | undefined {
  const bounded = boundedMetadataValue(value, 0)
  if (!isRecord(bounded)) return undefined
  const result = { ...bounded }
  // Trim whole fields in input order if a legacy payload still exceeds the
  // serialized ceiling. This keeps the result deterministic and bounded.
  while (Object.keys(result).length > 0) {
    try {
      if (JSON.stringify(result).length <= CHAT_EVIDENCE_MAX_METADATA_SERIALIZED_CHARS) break
    } catch {
      return {}
    }
    delete result[Object.keys(result).at(-1)!]
  }
  return result
}

function parseEnum<T extends string>(value: unknown, allowed: ReadonlySet<T>, unknownValue: T): T {
  const normalized = boundedString(value)?.toLowerCase() as T | undefined
  return normalized !== undefined && allowed.has(normalized) ? normalized : unknownValue
}

/** Parse a ledger kind without silently assigning a default kind. */
export function parseKnowledgeLedgerKind(value: unknown): KnowledgeLedgerKind {
  return parseEnum(value, LEDGER_KINDS, 'unknown')
}

export function parseKnowledgeLedgerStatus(value: unknown): KnowledgeLedgerStatus {
  return parseEnum(value, LEDGER_STATUSES, 'unknown')
}

export function parseKnowledgeLedgerSubjectScope(value: unknown): KnowledgeLedgerSubjectScope {
  return parseEnum(value, LEDGER_SUBJECT_SCOPES, 'unknown')
}

/**
 * Decode a memory row for the existing Windows memory adapter. Missing id,
 * uid, content, or timestamps is rejected: those values cannot be guessed and
 * a malformed row must not become a fabricated profile item.
 */
export function parseKnowledgeLedgerMemory(value: unknown): KnowledgeLedgerMemory | null {
  const raw = asRecord(value)
  if (!raw) return null

  const id = boundedString(raw.id ?? raw.memory_id)
  const uid = boundedString(raw.uid)
  const content = asString(raw.content)
  const createdAt = boundedString(raw.created_at ?? raw.createdAt)
  const updatedAt = boundedString(raw.updated_at ?? raw.updatedAt)
  if (!id || !uid || content === undefined || !content.trim() || !createdAt || !updatedAt)
    return null

  const evidence = Array.isArray(raw.evidence)
    ? raw.evidence
        .map(parseKnowledgeLedgerEvidence)
        .filter((item): item is KnowledgeLedgerEvidence => item !== null)
    : undefined
  const ledgerSchemaVersion = boundedString(raw.ledger_schema_version ?? raw.ledgerSchemaVersion)
  const isLedgerV1 = ledgerSchemaVersion === KNOWLEDGE_LEDGER_SCHEMA_VERSION

  const result: KnowledgeLedgerMemory = {
    id,
    uid,
    // Do not trim or replace this value: text is the authoritative rendering.
    content,
    created_at: createdAt,
    updated_at: updatedAt,
    ...(boundedString(raw.headline) !== undefined ? { headline: boundedString(raw.headline) } : {}),
    ...(asString(raw.category) !== undefined ? { category: raw.category as string } : {}),
    ...(asString(raw.visibility) !== undefined ? { visibility: raw.visibility as string } : {}),
    ...(asStringArray(raw.tags) ? { tags: asStringArray(raw.tags) } : {}),
    ...(boundedString(raw.conversation_id ?? raw.conversationId) !== undefined
      ? { conversation_id: boundedString(raw.conversation_id ?? raw.conversationId) }
      : {}),
    ...(asString(raw.layer) !== undefined ? { layer: raw.layer as string } : {}),
    ...(asString(raw.memory_tier) !== undefined ? { memory_tier: raw.memory_tier as string } : {}),
    ...(asString(raw.primary_capture_device) !== undefined
      ? { primary_capture_device: raw.primary_capture_device as string }
      : {}),
    ...(asStringArray(raw.capture_device_ids)
      ? { capture_device_ids: asStringArray(raw.capture_device_ids) }
      : {}),
    ...(asBoolean(raw.manually_added) !== undefined
      ? { manually_added: raw.manually_added as boolean }
      : {}),
    ...(asFiniteNumber(raw.capture_confidence) !== undefined
      ? { capture_confidence: asFiniteNumber(raw.capture_confidence) }
      : {}),
    ...(asString(raw.app_id) !== undefined ? { app_id: raw.app_id as string } : {}),
    ...(evidence ? { evidence } : {}),
    ...(ledgerSchemaVersion !== undefined ? { ledger_schema_version: ledgerSchemaVersion } : {}),
    ...(boundedString(raw.memory_id) !== undefined
      ? { memory_id: boundedString(raw.memory_id) }
      : {}),
    ...(isLedgerV1 ? { kind: parseKnowledgeLedgerKind(raw.kind) } : {}),
    ...(isLedgerV1 ? { status: parseKnowledgeLedgerStatus(raw.status) } : {}),
    ...(isLedgerV1
      ? {
          subject_scope: parseKnowledgeLedgerSubjectScope(raw.subject_scope ?? raw.subjectScope)
        }
      : {}),
    ...(boundedString(raw.subject_entity_id ?? raw.subjectEntityId) !== undefined
      ? { subject_entity_id: boundedString(raw.subject_entity_id ?? raw.subjectEntityId) }
      : {}),
    ...(boundedString(raw.subject_attribution ?? raw.subjectAttribution) !== undefined
      ? { subject_attribution: boundedString(raw.subject_attribution ?? raw.subjectAttribution) }
      : {}),
    ...(boundedString(raw.slot) !== undefined ? { slot: boundedString(raw.slot) } : {}),
    ...(boundedString(raw.valid_from ?? raw.validFrom) !== undefined
      ? { valid_from: boundedString(raw.valid_from ?? raw.validFrom) }
      : {}),
    ...(boundedString(raw.valid_to ?? raw.validTo) !== undefined
      ? { valid_to: boundedString(raw.valid_to ?? raw.validTo) }
      : {}),
    ...(boundedString(raw.valid_at ?? raw.validAt) !== undefined
      ? { valid_at: boundedString(raw.valid_at ?? raw.validAt) }
      : {}),
    ...(boundedString(raw.invalid_at ?? raw.invalidAt) !== undefined
      ? { invalid_at: boundedString(raw.invalid_at ?? raw.invalidAt) }
      : {}),
    ...(boundedString(raw.superseded_by ?? raw.supersededBy) !== undefined
      ? { superseded_by: boundedString(raw.superseded_by ?? raw.supersededBy) }
      : {}),
    ...(boundedString(raw.canonical_memory_id ?? raw.canonicalMemoryId) !== undefined
      ? { canonical_memory_id: boundedString(raw.canonical_memory_id ?? raw.canonicalMemoryId) }
      : {}),
    ...(asFiniteNumber(raw.curation_weight) !== undefined
      ? { curation_weight: asFiniteNumber(raw.curation_weight) }
      : {}),
    ...(asBoolean(raw.intent_backed) !== undefined
      ? { intent_backed: raw.intent_backed as boolean }
      : {}),
    ...(asBoolean(raw.user_asserted) !== undefined
      ? { user_asserted: raw.user_asserted as boolean }
      : {}),
    ...(boundedString(raw.write_reason) !== undefined
      ? { write_reason: boundedString(raw.write_reason) }
      : {}),
    ...(boundedString(raw.sensitivity) !== undefined
      ? { sensitivity: boundedString(raw.sensitivity) }
      : {}),
    ...(asNumber(raw.account_generation) !== undefined
      ? { account_generation: asNumber(raw.account_generation) }
      : {}),
    ...(asNumber(raw.item_revision) !== undefined
      ? { item_revision: asNumber(raw.item_revision) }
      : {}),
    ...(boundedString(raw.ledger_commit_id ?? raw.ledgerCommitId) !== undefined
      ? { ledger_commit_id: boundedString(raw.ledger_commit_id ?? raw.ledgerCommitId) }
      : {}),
    ...(asNumber(raw.ledger_sequence ?? raw.ledgerSequence) !== undefined
      ? { ledger_sequence: asNumber(raw.ledger_sequence ?? raw.ledgerSequence) }
      : {}),
    ...(isLedgerV1 && asString(raw.body) !== undefined ? { body: raw.body as string } : {}),
    ...(isLedgerV1 &&
    boundedRecordCopy(raw.trigger_condition ?? raw.triggerCondition ?? raw.condition)
      ? {
          trigger_condition: boundedRecordCopy(
            raw.trigger_condition ?? raw.triggerCondition ?? raw.condition
          )
        }
      : {}),
    ...(boundedRecordCopy(raw.arguments) ? { arguments: boundedRecordCopy(raw.arguments) } : {}),
    ...(asString(raw.predicate) !== undefined ? { predicate: raw.predicate as string } : {}),
    ...(boundedRecordCopy(raw.qualifiers) ? { qualifiers: boundedRecordCopy(raw.qualifiers) } : {}),
    ...(asStringArray(raw.object_entity_ids)
      ? { object_entity_ids: asStringArray(raw.object_entity_ids) }
      : {}),
    ...(asStringArray(raw.uncertainty_reasons)
      ? { uncertainty_reasons: asStringArray(raw.uncertainty_reasons) }
      : {}),
    ...(asFiniteNumber(raw.veracity) !== undefined
      ? { veracity: asFiniteNumber(raw.veracity) }
      : {}),
    ...(asString(raw.durability) !== undefined ? { durability: raw.durability as string } : {}),
    ...(asBoolean(raw.edited) !== undefined ? { edited: raw.edited as boolean } : {}),
    ...(asBoolean(raw.reviewed) !== undefined ? { reviewed: raw.reviewed as boolean } : {}),
    ...(asBoolean(raw.user_review) !== undefined
      ? { user_review: raw.user_review as boolean }
      : {}),
    ...(asBoolean(raw.is_baseline) !== undefined
      ? { is_baseline: raw.is_baseline as boolean }
      : {}),
    ...(asBoolean(raw.is_locked) !== undefined ? { is_locked: raw.is_locked as boolean } : {}),
    ...(asBoolean(raw.is_read) !== undefined ? { is_read: raw.is_read as boolean } : {}),
    ...(asBoolean(raw.is_dismissed) !== undefined
      ? { is_dismissed: raw.is_dismissed as boolean }
      : {}),
    ...(asBoolean(raw.deleted) !== undefined ? { deleted: raw.deleted as boolean } : {})
  }
  return result
}

function parseKnowledgeLedgerEvidence(value: unknown): KnowledgeLedgerEvidence | null {
  const raw = asRecord(value)
  if (!raw) return null
  const result = boundedRecordCopy(raw) as KnowledgeLedgerEvidence
  const artifactRef = boundedRecordCopy(raw.artifact_ref)
  if (artifactRef) result.artifact_ref = artifactRef
  return result
}

function parseEvidenceKind(value: unknown): ChatEvidenceReferenceKind {
  return parseEnum(value, EVIDENCE_KINDS, 'unknown')
}

function parseEvidenceState(value: unknown): ChatEvidenceReferenceState {
  return parseEnum(value, EVIDENCE_STATES, 'unknown')
}

function readEvidenceString(value: unknown, maxLength?: number): string | undefined {
  return boundedString(value, maxLength)
}

function readEvidenceInt(value: unknown): number | undefined {
  return asNumber(value)
}

/** Decode one evidence reference using the snake_case/camelCase aliases shared with Flutter. */
export function parseChatEvidenceReference(value: unknown): ChatEvidenceReference {
  const raw = asRecord(value) ?? {}
  return {
    id: readEvidenceString(raw.id ?? raw.reference_id, CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS) ?? '',
    kind: parseEvidenceKind(raw.kind ?? raw.type),
    state: parseEvidenceState(raw.state ?? raw.status),
    ...(readEvidenceString(raw.title, CHAT_EVIDENCE_MAX_TITLE_CHARS)
      ? { title: readEvidenceString(raw.title, CHAT_EVIDENCE_MAX_TITLE_CHARS) }
      : {}),
    ...(readEvidenceString(raw.summary ?? raw.preview, CHAT_EVIDENCE_MAX_SUMMARY_CHARS)
      ? { summary: readEvidenceString(raw.summary ?? raw.preview, CHAT_EVIDENCE_MAX_SUMMARY_CHARS) }
      : {}),
    ...(readEvidenceString(
      raw.conversation_id ?? raw.conversationId,
      CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS
    )
      ? {
          conversationId: readEvidenceString(
            raw.conversation_id ?? raw.conversationId,
            CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS
          )
        }
      : {}),
    ...(readEvidenceString(raw.segment_id ?? raw.segmentId, CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS)
      ? {
          segmentId: readEvidenceString(
            raw.segment_id ?? raw.segmentId,
            CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS
          )
        }
      : {}),
    ...(readEvidenceString(raw.frame_id ?? raw.frameId, CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS)
      ? {
          frameId: readEvidenceString(
            raw.frame_id ?? raw.frameId,
            CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS
          )
        }
      : {}),
    ...(readEvidenceString(raw.request_id ?? raw.requestId, CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS)
      ? {
          requestId: readEvidenceString(
            raw.request_id ?? raw.requestId,
            CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS
          )
        }
      : {}),
    ...(readEvidenceInt(raw.start_ms ?? raw.startMs) !== undefined
      ? { startMs: readEvidenceInt(raw.start_ms ?? raw.startMs) }
      : {}),
    ...(readEvidenceInt(raw.end_ms ?? raw.endMs) !== undefined
      ? { endMs: readEvidenceInt(raw.end_ms ?? raw.endMs) }
      : {}),
    ...(readEvidenceInt(raw.captured_at_ms ?? raw.capturedAtMs) !== undefined
      ? { capturedAtMs: readEvidenceInt(raw.captured_at_ms ?? raw.capturedAtMs) }
      : {}),
    ...(readEvidenceString(raw.error_code ?? raw.errorCode, CHAT_EVIDENCE_MAX_ERROR_CODE_CHARS)
      ? {
          errorCode: readEvidenceString(
            raw.error_code ?? raw.errorCode,
            CHAT_EVIDENCE_MAX_ERROR_CODE_CHARS
          )
        }
      : {}),
    ...(readEvidenceString(
      raw.error_message ?? raw.errorMessage,
      CHAT_EVIDENCE_MAX_ERROR_MESSAGE_CHARS
    )
      ? {
          errorMessage: readEvidenceString(
            raw.error_message ?? raw.errorMessage,
            CHAT_EVIDENCE_MAX_ERROR_MESSAGE_CHARS
          )
        }
      : {}),
    metadata: boundedRecordCopy(raw.metadata) ?? {}
  }
}

/** Parse an evidence envelope, dropping malformed reference entries and capping the list. */
export function parseChatEvidenceEnvelope(value: unknown): ChatEvidenceReferenceEnvelope | null {
  const raw = asRecord(value)
  if (!raw) return null
  const schemaKeys = ['schema_version', 'schemaVersion', 'version'] as const
  const schemaKey = schemaKeys.find((key) => Object.prototype.hasOwnProperty.call(raw, key))
  // An absent version is legacy/current v1. An explicitly malformed version is
  // an unknown contract and must not inherit actionable v1 semantics.
  const schemaVersion = schemaKey === undefined ? 1 : (parseSchemaVersion(raw[schemaKey]) ?? 0)
  const rawReferences = raw.references ?? raw.evidence_refs ?? raw.evidence_references
  const references = Array.isArray(rawReferences)
    ? rawReferences
        .filter(isRecord)
        .slice(0, CHAT_EVIDENCE_MAX_REFERENCES)
        .map(parseChatEvidenceReference)
        .map((reference) =>
          schemaVersion === 1
            ? reference
            : { ...reference, kind: 'unknown' as const, state: 'unknown' as const }
        )
    : []
  return {
    schemaVersion,
    ...(readEvidenceString(raw.request_id ?? raw.requestId, CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS)
      ? {
          requestId: readEvidenceString(
            raw.request_id ?? raw.requestId,
            CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS
          )
        }
      : {}),
    references
  }
}

/** Accept the direct list form used by a few older message metadata payloads. */
export function parseChatEvidencePayload(value: unknown): ChatEvidenceReferenceEnvelope | null {
  if (Array.isArray(value)) return parseChatEvidenceEnvelope({ references: value })
  return parseChatEvidenceEnvelope(value)
}

/** Decode direct evidence fields, or the same fields nested in serialized metadata. */
export function parseChatEvidenceFromRecord(value: unknown): ChatEvidenceReferenceEnvelope | null {
  try {
    const raw = asRecord(value)
    if (!raw) return null
    const direct = parseChatEvidencePayload(
      raw.evidence ?? raw.evidence_envelope ?? raw.evidence_refs ?? raw.evidence_references
    )
    if (direct) return direct
    if (typeof raw.metadata === 'string') {
      const metadata = JSON.parse(raw.metadata)
      const nested = parseChatEvidenceFromRecord(metadata)
      if (nested) return nested
    } else if (isRecord(raw.metadata)) {
      return parseChatEvidenceFromRecord(raw.metadata)
    }
  } catch {
    // Evidence is optional UI chrome. A malformed direct/metadata payload must
    // never abort the text/history path that carries the actual answer.
    return null
  }
  return null
}

function parseSchemaVersion(value: unknown): number | undefined {
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) ? value : undefined
  }
  if (typeof value === 'string' && /^\s*[+-]?\d+\s*$/.test(value)) {
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) ? parsed : undefined
  }
  return undefined
}

/** Unknown or unavailable evidence is never actionable. */
export function chatEvidenceReferenceCanOpen(reference: ChatEvidenceReference): boolean {
  if (!reference.id.trim() || reference.state !== 'available') return false
  switch (reference.kind) {
    case 'conversation_summary':
      return Boolean(reference.conversationId)
    case 'conversation_segment':
      return Boolean(reference.conversationId && reference.segmentId)
    case 'screen':
    case 'keyframe':
      return Boolean(reference.frameId)
    case 'request':
      return Boolean(reference.requestId)
    case 'unknown':
      return false
  }
}
