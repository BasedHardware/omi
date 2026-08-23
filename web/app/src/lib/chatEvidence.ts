/**
 * Bounded, fail-soft parsing for supplemental chat evidence.
 *
 * The message text is authoritative. This adapter only admits conversation
 * summary and conversation segment references; screen, keyframe, request,
 * unknown, and future-schema references remain inert and are not rendered.
 */

export const CHAT_EVIDENCE_SCHEMA_VERSION = 1 as const;
export const CHAT_EVIDENCE_MAX_REFERENCES = 24;
export const CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS = 256;
export const CHAT_EVIDENCE_MAX_TITLE_CHARS = 160;
export const CHAT_EVIDENCE_MAX_SUMMARY_CHARS = 600;
export const CHAT_EVIDENCE_MAX_ERROR_CODE_CHARS = 128;
export const CHAT_EVIDENCE_MAX_ERROR_MESSAGE_CHARS = 600;

export type ChatEvidenceKind = 'conversation_summary' | 'conversation_segment';
export type ChatEvidenceState =
  'available' | 'loading' | 'offline' | 'pruned' | 'failed' | 'unknown';

export interface ChatEvidenceReference {
  id: string;
  kind: ChatEvidenceKind;
  state: ChatEvidenceState;
  title?: string;
  summary?: string;
  conversationId: string;
  segmentId?: string;
  errorCode?: string;
  errorMessage?: string;
}

export interface ChatEvidenceEnvelope {
  schemaVersion: number;
  requestId?: string;
  references: ChatEvidenceReference[];
}

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    !(value instanceof Map) &&
    !(value instanceof Set)
  );
}

function boundedString(value: unknown, maxLength: number): string | undefined {
  if (typeof value !== 'string') return undefined;
  const normalized = value.trim();
  return normalized ? normalized.slice(0, maxLength) : undefined;
}

function readSchemaVersion(value: unknown): number | undefined {
  if (typeof value === 'number') return Number.isSafeInteger(value) ? value : undefined;
  if (typeof value === 'string' && /^\s*[+-]?\d+\s*$/.test(value)) {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) ? parsed : undefined;
  }
  return undefined;
}

function parseState(value: unknown): ChatEvidenceState {
  const state = boundedString(value, CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS)?.toLowerCase();
  switch (state) {
    case 'available':
    case 'loading':
    case 'offline':
    case 'pruned':
    case 'failed':
      return state;
    default:
      return 'unknown';
  }
}

function parseReference(value: unknown): ChatEvidenceReference | null {
  if (!isRecord(value)) return null;

  const id = boundedString(
    value.id ?? value.reference_id,
    CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS,
  );
  const kind = boundedString(
    value.kind ?? value.type,
    CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS,
  )?.toLowerCase();
  const conversationId = boundedString(
    value.conversation_id ?? value.conversationId,
    CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS,
  );
  if (!id || !conversationId) return null;

  if (kind !== 'conversation_summary' && kind !== 'conversation_segment') return null;

  const segmentId = boundedString(
    value.segment_id ?? value.segmentId,
    CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS,
  );
  if (kind === 'conversation_segment' && !segmentId) return null;

  const title = boundedString(value.title, CHAT_EVIDENCE_MAX_TITLE_CHARS);
  const summary = boundedString(
    value.summary ?? value.preview,
    CHAT_EVIDENCE_MAX_SUMMARY_CHARS,
  );
  const errorCode = boundedString(
    value.error_code ?? value.errorCode,
    CHAT_EVIDENCE_MAX_ERROR_CODE_CHARS,
  );
  const errorMessage = boundedString(
    value.error_message ?? value.errorMessage,
    CHAT_EVIDENCE_MAX_ERROR_MESSAGE_CHARS,
  );

  return {
    id,
    kind,
    state: parseState(value.state ?? value.status),
    ...(title ? { title } : {}),
    ...(summary ? { summary } : {}),
    conversationId,
    ...(segmentId ? { segmentId } : {}),
    ...(errorCode ? { errorCode } : {}),
    ...(errorMessage ? { errorMessage } : {}),
  };
}

/** Parse an evidence envelope. Invalid entries are dropped, never thrown. */
export function parseChatEvidenceEnvelope(value: unknown): ChatEvidenceEnvelope | null {
  const raw = isRecord(value)
    ? value
    : Array.isArray(value)
      ? { references: value }
      : null;
  if (!raw) return null;

  const hasSchemaVersion =
    Object.prototype.hasOwnProperty.call(raw, 'schema_version') ||
    Object.prototype.hasOwnProperty.call(raw, 'schemaVersion') ||
    Object.prototype.hasOwnProperty.call(raw, 'version');
  const schemaValue = raw.schema_version ?? raw.schemaVersion ?? raw.version;
  const schemaVersion = hasSchemaVersion
    ? (readSchemaVersion(schemaValue) ?? 0)
    : CHAT_EVIDENCE_SCHEMA_VERSION;
  const requestId = boundedString(
    raw.request_id ?? raw.requestId,
    CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS,
  );

  // A future or malformed schema is preserved as metadata only. Its entries
  // must not accidentally acquire current-client meaning.
  if (schemaVersion !== CHAT_EVIDENCE_SCHEMA_VERSION) {
    return {
      schemaVersion,
      ...(requestId ? { requestId } : {}),
      references: [],
    };
  }

  const rawReferences = raw.references ?? raw.evidence_refs ?? raw.evidence_references;
  const references: ChatEvidenceReference[] = [];
  const seenReferenceIds = new Set<string>();
  if (Array.isArray(rawReferences)) {
    for (const rawReference of rawReferences.slice(0, CHAT_EVIDENCE_MAX_REFERENCES)) {
      const reference = parseReference(rawReference);
      if (!reference || seenReferenceIds.has(reference.id)) continue;
      seenReferenceIds.add(reference.id);
      references.push(reference);
    }
  }

  return {
    schemaVersion,
    ...(requestId ? { requestId } : {}),
    references,
  };
}

/**
 * Read direct evidence or the legacy serialized metadata location. This is
 * intentionally capped to one metadata hop so malformed input cannot recurse
 * indefinitely or interfere with rendering the answer text.
 */
export function parseChatEvidenceFromRecord(value: unknown): ChatEvidenceEnvelope | null {
  return parseChatEvidenceFromRecordAtDepth(value, 0);
}

function parseChatEvidenceFromRecordAtDepth(
  value: unknown,
  depth: number,
): ChatEvidenceEnvelope | null {
  if (!isRecord(value)) return null;

  const direct =
    value.evidence ??
    value.evidence_envelope ??
    value.evidence_refs ??
    value.evidence_references;
  if (direct !== undefined) return parseChatEvidenceEnvelope(direct);

  if (typeof value.metadata === 'string') {
    if (depth >= 1) return null;
    try {
      return parseChatEvidenceFromRecordAtDepth(JSON.parse(value.metadata), depth + 1);
    } catch {
      return null;
    }
  }
  if (isRecord(value.metadata) && depth < 1) {
    return parseChatEvidenceFromRecordAtDepth(value.metadata, depth + 1);
  }
  return null;
}
