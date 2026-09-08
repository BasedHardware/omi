import type { Memory } from '@/types/conversation';

const KNOWLEDGE_LEDGER_SCHEMA_VERSION = 'knowledge_ledger.v1';
const LEDGER_KINDS = new Set(['fact', 'document', 'trigger']);
const LEDGER_STATUSES = new Set(['active', 'superseded', 'tombstoned', 'purged']);
const LEDGER_SUBJECT_SCOPES = new Set([
  'primary_user',
  'user_owned_project',
  'user_relationship',
  'third_party',
]);
const LEDGER_SUBJECT_ATTRIBUTIONS = new Set([
  'user',
  'third_party',
  'unknown',
  'legacy_assumed',
]);
const LEDGER_WRITE_REASONS = new Set([
  'direct_user_statement',
  'explicit_remember',
  'agent_reusable_conclusion',
  'recurring_workflow',
  'standing_trigger',
  'onboarding',
  'daily_reconciliation',
  'legacy_migration',
]);

type JsonRecord = Record<string, unknown>;
const MAX_LEDGER_OBJECT_DEPTH = 3;
const MAX_LEDGER_OBJECT_KEYS = 32;
const MAX_LEDGER_ARRAY_ITEMS = 32;
const MAX_LEDGER_VALUE_CHARS = 1_000;

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as JsonRecord)
    : null;
}

function boundedString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function finiteInteger(value: unknown): number | undefined {
  const number = finiteNumber(value);
  return number !== undefined && Number.isInteger(number) ? number : undefined;
}

function stringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const values = value.map(boundedString);
  return values.every((item): item is string => item !== undefined) ? values : undefined;
}

function boundedValue(value: unknown, depth: number): unknown {
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined;
  if (typeof value === 'string') {
    const stringValue = value.trim();
    return stringValue ? stringValue.slice(0, MAX_LEDGER_VALUE_CHARS) : undefined;
  }
  if (depth >= MAX_LEDGER_OBJECT_DEPTH) return undefined;
  if (Array.isArray(value)) {
    return value
      .slice(0, MAX_LEDGER_ARRAY_ITEMS)
      .map((item) => boundedValue(item, depth + 1))
      .filter((item): item is Exclude<typeof item, undefined> => item !== undefined);
  }
  const record = asRecord(value);
  if (!record) return undefined;
  const bounded: JsonRecord = {};
  for (const [key, item] of Object.entries(record).slice(0, MAX_LEDGER_OBJECT_KEYS)) {
    const boundedItem = boundedValue(item, depth + 1);
    if (boundedItem !== undefined) bounded[key] = boundedItem;
  }
  return bounded;
}

function boundedObject(value: unknown): JsonRecord | undefined {
  const bounded = boundedValue(value, 0);
  const record = asRecord(bounded);
  return record ? record : undefined;
}

function evidence(value: unknown): JsonRecord | null {
  const record = asRecord(value);
  const evidenceId = boundedString(record?.evidence_id);
  const independenceGroup = boundedString(record?.independence_group);
  if (!record || !evidenceId || !independenceGroup) return null;
  // Evidence is optional metadata. Preserve forward-compatible evidence fields,
  // but require the shared identity/join keys and the same object bounds before
  // retaining an entry. A future evidence field must not bypass the API budget.
  const bounded = boundedObject(record);
  if (!bounded) return null;
  return { ...bounded, evidence_id: evidenceId, independence_group: independenceGroup };
}

function copyString(target: JsonRecord, raw: JsonRecord, key: string): void {
  const value = boundedString(raw[key]);
  if (value !== undefined) target[key] = value;
}

function copyBoolean(target: JsonRecord, raw: JsonRecord, key: string): void {
  if (typeof raw[key] === 'boolean') target[key] = raw[key];
}

function copyNumber(target: JsonRecord, raw: JsonRecord, key: string): void {
  const value = finiteNumber(raw[key]);
  if (value !== undefined) target[key] = value;
}

function copyInteger(target: JsonRecord, raw: JsonRecord, key: string): void {
  const value = finiteInteger(raw[key]);
  if (value !== undefined) target[key] = value;
}

function copyStringArray(target: JsonRecord, raw: JsonRecord, key: string): void {
  const value = stringArray(raw[key]);
  if (value !== undefined) target[key] = value;
}

/**
 * Normalize a memory at the web API boundary.
 *
 * `content` and stable identity are authoritative for every released row.
 * Ledger authority is an allowlist, enabled only for the exact v1 schema;
 * this prevents legacy and future rows from leaking fields into current
 * behavior and prevents malformed v1 fields from being trusted by spreading
 * the wire object through to callers.
 */
export function normalizeKnowledgeLedgerMemory(value: unknown): Memory | null {
  const raw = asRecord(value);
  if (!raw) return null;

  const id = boundedString(raw.id ?? raw.memory_id);
  const uid = boundedString(raw.uid);
  const content = typeof raw.content === 'string' ? raw.content : undefined;
  const createdAt = boundedString(raw.created_at ?? raw.createdAt);
  const updatedAt = boundedString(raw.updated_at ?? raw.updatedAt);
  if (
    !id ||
    !uid ||
    content === undefined ||
    !content.trim() ||
    !createdAt ||
    !updatedAt
  ) {
    return null;
  }

  const normalized: JsonRecord = {
    id,
    uid,
    content,
    created_at: createdAt,
    updated_at: updatedAt,
  };

  // These fields are part of the released memory shape, not ledger authority.
  for (const key of [
    'headline',
    'category',
    'visibility',
    'conversation_id',
    'layer',
    'memory_tier',
    'primary_capture_device',
    'app_id',
  ]) {
    copyString(normalized, raw, key);
  }
  for (const key of ['tags', 'capture_device_ids']) copyStringArray(normalized, raw, key);
  for (const key of [
    'manually_added',
    'edited',
    'reviewed',
    'is_baseline',
    'is_locked',
    'is_read',
    'is_dismissed',
    'deleted',
  ]) {
    copyBoolean(normalized, raw, key);
  }
  if (typeof raw.user_review === 'boolean' || raw.user_review === null) {
    normalized.user_review = raw.user_review;
  }
  if (raw.capture_confidence === null) normalized.capture_confidence = null;
  else copyNumber(normalized, raw, 'capture_confidence');

  const ledgerSchemaVersion = boundedString(
    raw.ledger_schema_version ?? raw.ledgerSchemaVersion,
  );
  if (ledgerSchemaVersion) normalized.ledger_schema_version = ledgerSchemaVersion;

  if (Array.isArray(raw.evidence)) {
    normalized.evidence = raw.evidence
      .map(evidence)
      .filter((item): item is JsonRecord => item !== null);
  }

  if (ledgerSchemaVersion !== KNOWLEDGE_LEDGER_SCHEMA_VERSION) {
    return normalized as unknown as Memory;
  }

  const kind = boundedString(raw.kind)?.toLowerCase();
  if (!kind || !LEDGER_KINDS.has(kind)) return normalized as unknown as Memory;
  normalized.kind = kind;

  const subjectScope = boundedString(raw.subject_scope)?.toLowerCase();
  if (subjectScope && LEDGER_SUBJECT_SCOPES.has(subjectScope)) {
    normalized.subject_scope = subjectScope;
  }
  const status = boundedString(raw.status)?.toLowerCase();
  if (status && LEDGER_STATUSES.has(status)) normalized.status = status;

  for (const key of [
    'subject_entity_id',
    'valid_from',
    'valid_to',
    'valid_at',
    'invalid_at',
    'superseded_by',
    'canonical_memory_id',
    'sensitivity',
    'ledger_commit_id',
  ]) {
    copyString(normalized, raw, key);
  }
  const subjectAttribution = boundedString(raw.subject_attribution)?.toLowerCase();
  if (subjectAttribution && LEDGER_SUBJECT_ATTRIBUTIONS.has(subjectAttribution)) {
    normalized.subject_attribution = subjectAttribution;
  }
  const writeReason = boundedString(raw.write_reason)?.toLowerCase();
  if (writeReason && LEDGER_WRITE_REASONS.has(writeReason)) {
    normalized.write_reason = writeReason;
  }

  for (const key of ['intent_backed', 'user_asserted']) copyBoolean(normalized, raw, key);
  copyInteger(normalized, raw, 'curation_weight');
  copyNumber(normalized, raw, 'veracity');
  for (const key of ['account_generation', 'item_revision', 'ledger_sequence']) {
    copyInteger(normalized, raw, key);
  }
  for (const key of ['arguments', 'qualifiers']) {
    const value = boundedObject(raw[key]);
    if (value) normalized[key] = value;
  }
  copyString(normalized, raw, 'predicate');
  for (const key of ['object_entity_ids', 'uncertainty_reasons']) {
    copyStringArray(normalized, raw, key);
  }

  // These fields are coupled to kind. A valid-looking field on the wrong kind
  // is authority data too, so it is dropped rather than exposed generically.
  if (kind === 'fact') copyString(normalized, raw, 'slot');
  if (kind === 'document') copyString(normalized, raw, 'body');
  if (kind === 'trigger') {
    const condition = boundedObject(raw.trigger_condition ?? raw.condition);
    if (condition) normalized.trigger_condition = condition;
  }

  return normalized as unknown as Memory;
}

export function normalizeKnowledgeLedgerMemories(value: unknown): Memory[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(normalizeKnowledgeLedgerMemory)
    .filter((memory): memory is Memory => memory !== null);
}
