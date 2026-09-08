import { createHash } from "node:crypto";

import type { ConversationEvidenceProjection } from "../protocol.js";

/** The journal metadata slot is deliberately versioned so future evidence
 * sources can evolve without creating another transcript store. */
export const CONVERSATION_EVIDENCE_SCHEMA = "omi.evidence@1" as const;
export const MAX_CONVERSATION_EVIDENCE_ITEMS = 8;
export const MAX_CONVERSATION_EVIDENCE_ID_CHARS = 160;
export const MAX_CONVERSATION_EVIDENCE_TITLE_CHARS = 240;
export const MAX_CONVERSATION_EVIDENCE_BODY_BYTES = 64 * 1024;
export const MAX_CONVERSATION_EVIDENCE_DIGEST_CHARS = 160;
export const MAX_CONVERSATION_EVIDENCE_PROVENANCE_KEYS = 12;
export const MAX_CONVERSATION_EVIDENCE_PROVENANCE_KEY_CHARS = 64;
export const MAX_CONVERSATION_EVIDENCE_PROVENANCE_VALUE_CHARS = 256;
export const MAX_CONVERSATION_EVIDENCE_METADATA_BYTES = 512 * 1024;
export const MAX_CONVERSATION_EVIDENCE_CONTEXT_ITEMS = 8;
export const MAX_CONVERSATION_EVIDENCE_CONTEXT_SNIPPET_CHARS = 800;
export const MAX_CONVERSATION_EVIDENCE_CONTEXT_TOTAL_SNIPPET_CHARS = 2_400;

export type ConversationEvidenceKind = "screen" | "document" | "attachment" | "tool_result";
export type ConversationEvidenceAvailability = "pending" | "available" | "partial" | "unavailable";
export type ConversationEvidenceExtractionCompleteness = "complete" | "partial" | "none";

export interface ConversationEvidence {
  id: string;
  kind: ConversationEvidenceKind;
  title: string;
  capturedAtMs: number;
  availability: ConversationEvidenceAvailability;
  extractionCompleteness: ConversationEvidenceExtractionCompleteness;
  /** Full extracted text, bounded and retained locally in journal metadata. */
  bodyText?: string;
  /** Stable source/body digest. It is safe to export, unlike bodyText. */
  digest?: string;
  /** Optional digest of the captured source when bodyText is extracted text. */
  sourceDigest?: string;
  /** Opaque existing artifact identity. It is never a filesystem path. */
  artifactId?: string;
  /** Source facts used for provenance, never treated as instructions. */
  provenance?: Record<string, string>;
}

export interface ConversationEvidenceEnvelope {
  schema: typeof CONVERSATION_EVIDENCE_SCHEMA;
  items: ConversationEvidence[];
}

export interface ConversationEvidenceContextProjection {
  evidence: ConversationEvidenceProjection[];
  evidenceReadRequired: boolean;
}

export function validateConversationEvidence(evidence: ConversationEvidence): ConversationEvidence {
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)) {
    throw new Error("Conversation evidence must be an object");
  }
  const id = boundedString(evidence.id, "evidence id", MAX_CONVERSATION_EVIDENCE_ID_CHARS);
  const kind = evidence.kind;
  if (!["screen", "document", "attachment", "tool_result"].includes(kind)) {
    throw new Error("Conversation evidence kind is invalid");
  }
  const title = boundedString(evidence.title, "evidence title", MAX_CONVERSATION_EVIDENCE_TITLE_CHARS);
  if (!Number.isSafeInteger(evidence.capturedAtMs) || evidence.capturedAtMs < 0) {
    throw new Error("Conversation evidence capturedAtMs must be a non-negative integer");
  }
  const availability = evidence.availability;
  if (!["pending", "available", "partial", "unavailable"].includes(availability)) {
    throw new Error("Conversation evidence availability is invalid");
  }
  const extractionCompleteness = evidence.extractionCompleteness;
  if (!["complete", "partial", "none"].includes(extractionCompleteness)) {
    throw new Error("Conversation evidence extractionCompleteness is invalid");
  }
  if (availability === "unavailable" && evidence.bodyText !== undefined) {
    throw new Error("Unavailable conversation evidence cannot contain bodyText");
  }
  if (availability === "pending" && evidence.bodyText !== undefined) {
    throw new Error("Pending conversation evidence cannot contain bodyText");
  }
  if (availability === "pending" && extractionCompleteness !== "none") {
    throw new Error("Pending conversation evidence must have no extraction");
  }
  if (extractionCompleteness === "none" && evidence.bodyText !== undefined) {
    throw new Error("Conversation evidence with no extraction cannot contain bodyText");
  }
  const bodyText = evidence.bodyText === undefined
    ? undefined
    : boundedUtf8String(evidence.bodyText, "evidence bodyText", MAX_CONVERSATION_EVIDENCE_BODY_BYTES);
  const digest = evidence.digest === undefined
    ? bodyText === undefined ? undefined : digestForText(bodyText)
    : boundedString(evidence.digest, "evidence digest", MAX_CONVERSATION_EVIDENCE_DIGEST_CHARS);
  if (bodyText !== undefined && digest !== digestForText(bodyText)) {
    throw new Error("Conversation evidence digest does not match bodyText");
  }
  const sourceDigest = evidence.sourceDigest === undefined
    ? undefined
    : boundedString(evidence.sourceDigest, "evidence sourceDigest", MAX_CONVERSATION_EVIDENCE_DIGEST_CHARS);
  const artifactId = evidence.artifactId === undefined
    ? undefined
    : boundedString(evidence.artifactId, "evidence artifactId", MAX_CONVERSATION_EVIDENCE_ID_CHARS);
  const provenance = evidence.provenance === undefined
    ? undefined
    : validateProvenance(evidence.provenance);
  return {
    id,
    kind: kind as ConversationEvidenceKind,
    title,
    capturedAtMs: evidence.capturedAtMs,
    availability: availability as ConversationEvidenceAvailability,
    extractionCompleteness: extractionCompleteness as ConversationEvidenceExtractionCompleteness,
    ...(bodyText === undefined ? {} : { bodyText }),
    ...(digest === undefined ? {} : { digest }),
    ...(sourceDigest === undefined ? {} : { sourceDigest }),
    ...(artifactId === undefined ? {} : { artifactId }),
    ...(provenance === undefined ? {} : { provenance }),
  };
}

export function validateConversationEvidenceEnvelope(
  envelope: unknown,
): ConversationEvidenceEnvelope {
  if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
    throw new Error("Conversation evidence envelope must be an object");
  }
  const value = envelope as Record<string, unknown>;
  if (value.schema !== CONVERSATION_EVIDENCE_SCHEMA) {
    throw new Error(`Unsupported conversation evidence schema: ${String(value.schema ?? "missing")}`);
  }
  if (!Array.isArray(value.items) || value.items.length > MAX_CONVERSATION_EVIDENCE_ITEMS) {
    throw new Error(`Conversation evidence item count must be between 0 and ${MAX_CONVERSATION_EVIDENCE_ITEMS}`);
  }
  const ids = new Set<string>();
  const items = value.items.map((item) => {
    const validated = validateConversationEvidence(item as ConversationEvidence);
    if (ids.has(validated.id)) throw new Error(`Duplicate conversation evidence ID ${validated.id}`);
    ids.add(validated.id);
    return validated;
  });
  const result: ConversationEvidenceEnvelope = { schema: CONVERSATION_EVIDENCE_SCHEMA, items };
  if (utf8Bytes(stableJson(result)) > MAX_CONVERSATION_EVIDENCE_METADATA_BYTES) {
    throw new Error("Conversation evidence metadata exceeds the 512 KiB limit");
  }
  return result;
}

/** Validate only the evidence namespace in a journal metadata object. */
export function validateConversationEvidenceMetadata(metadata: Record<string, unknown>): void {
  if (metadata.evidence === undefined) return;
  validateConversationEvidenceEnvelope(metadata.evidence);
}

export function parseConversationEvidenceMetadata(metadataJson: string): ConversationEvidenceEnvelope | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(metadataJson) as unknown;
  } catch {
    throw new Error("Journal metadata must be valid JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Journal metadata must contain a JSON object");
  }
  const metadata = parsed as Record<string, unknown>;
  if (metadata.evidence === undefined) return null;
  return validateConversationEvidenceEnvelope(metadata.evidence);
}

export function mergeConversationEvidenceMetadata(
  metadataJson: string,
  evidenceInput: ConversationEvidence,
): { metadataJson: string; evidence: ConversationEvidence; duplicate: boolean } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(metadataJson) as unknown;
  } catch {
    throw new Error("Journal metadata must be valid JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Journal metadata must contain a JSON object");
  }
  const metadata = parsed as Record<string, unknown>;
  validateConversationEvidenceMetadata(metadata);
  const evidence = validateConversationEvidence(evidenceInput);
  const envelope = metadata.evidence === undefined
    ? { schema: CONVERSATION_EVIDENCE_SCHEMA, items: [] }
    : validateConversationEvidenceEnvelope(metadata.evidence);
  const existing = envelope.items.find((item) => item.id === evidence.id);
  if (existing) {
    const transition = mergeEvidenceRevision(existing, evidence);
    if (!transition.changed) {
      return { metadataJson: JSON.stringify(metadata), evidence: existing, duplicate: true };
    }
    const mergedEnvelope = validateConversationEvidenceEnvelope({
      ...envelope,
      items: envelope.items.map((item) => item.id === evidence.id ? transition.evidence : item),
    });
    const next = { ...metadata, evidence: mergedEnvelope };
    if (utf8Bytes(JSON.stringify(next)) > MAX_CONVERSATION_EVIDENCE_METADATA_BYTES) {
      throw new Error("Conversation evidence metadata exceeds the 512 KiB limit");
    }
    return { metadataJson: JSON.stringify(next), evidence: transition.evidence, duplicate: false };
  }
  const merged = validateConversationEvidenceEnvelope({
    ...envelope,
    items: [...envelope.items, evidence],
  });
  const next = { ...metadata, evidence: merged };
  if (utf8Bytes(JSON.stringify(next)) > MAX_CONVERSATION_EVIDENCE_METADATA_BYTES) {
    throw new Error("Conversation evidence metadata exceeds the 512 KiB limit");
  }
  return { metadataJson: JSON.stringify(next), evidence, duplicate: false };
}

/** Preserve already-admitted evidence when a producer replaces ordinary turn
 * metadata during streaming or terminal completion. New evidence items are
 * merged by stable ID; a changed body is a conflict, never an overwrite. */
export function preserveConversationEvidenceOnMetadataUpdate(
  currentMetadataJson: string,
  nextMetadataJson: string,
): string {
  const current = parseMetadataObject(currentMetadataJson);
  const next = parseMetadataObject(nextMetadataJson);
  validateConversationEvidenceMetadata(current);
  validateConversationEvidenceMetadata(next);
  const currentEnvelope = current.evidence === undefined
    ? null
    : validateConversationEvidenceEnvelope(current.evidence);
  const nextEnvelope = next.evidence === undefined
    ? null
    : validateConversationEvidenceEnvelope(next.evidence);
  if (!currentEnvelope) return JSON.stringify(next);
  if (!nextEnvelope) return JSON.stringify({ ...next, evidence: currentEnvelope });
  const mergedItems = [...nextEnvelope.items];
  const nextById = new Map(mergedItems.map((item) => [item.id, item]));
  for (const item of currentEnvelope.items) {
    const replacement = nextById.get(item.id);
    if (replacement) {
      const transition = mergeEvidenceRevision(item, replacement);
      const replacementIndex = mergedItems.findIndex((candidate) => candidate.id === item.id);
      if (replacementIndex >= 0) mergedItems[replacementIndex] = transition.evidence;
    } else {
      mergedItems.push(item);
    }
  }
  const merged = validateConversationEvidenceEnvelope({ ...nextEnvelope, items: mergedItems });
  return JSON.stringify({ ...next, evidence: merged });
}

export function conversationEvidenceForContext(
  metadataJson: string,
  options: {
    maxItems?: number;
    maxSnippetChars?: number;
    maxTotalSnippetChars?: number;
  } = {},
): ConversationEvidenceContextProjection {
  const envelope = parseConversationEvidenceMetadata(metadataJson);
  if (!envelope || envelope.items.length === 0) return { evidence: [], evidenceReadRequired: false };
  const projection: ConversationEvidenceProjection[] = [];
  const maxItems = Math.max(0, Math.min(options.maxItems ?? MAX_CONVERSATION_EVIDENCE_CONTEXT_ITEMS, MAX_CONVERSATION_EVIDENCE_CONTEXT_ITEMS));
  const maxSnippetChars = Math.max(0, Math.min(options.maxSnippetChars ?? MAX_CONVERSATION_EVIDENCE_CONTEXT_SNIPPET_CHARS, MAX_CONVERSATION_EVIDENCE_CONTEXT_SNIPPET_CHARS));
  let snippetBudget = Math.max(0, Math.min(options.maxTotalSnippetChars ?? MAX_CONVERSATION_EVIDENCE_CONTEXT_TOTAL_SNIPPET_CHARS, MAX_CONVERSATION_EVIDENCE_CONTEXT_TOTAL_SNIPPET_CHARS));
  let evidenceReadRequired = false;
  for (const item of envelope.items.slice(0, maxItems)) {
    const snippet = item.bodyText === undefined
      ? ""
      : item.bodyText.slice(0, Math.min(maxSnippetChars, snippetBudget));
    const fullReadRequired = item.availability === "pending"
      ? false
      : Boolean(
        item.artifactId
        || item.bodyText === undefined
        || item.bodyText.length > snippet.length
        || item.availability === "partial",
      );
    evidenceReadRequired ||= fullReadRequired;
    projection.push({
      evidenceId: item.id,
      kind: item.kind,
      title: item.title,
      capturedAtMs: item.capturedAtMs,
      availability: item.availability,
      extractionCompleteness: item.extractionCompleteness,
      ...(snippet ? { snippet } : {}),
      ...((item.digest ?? item.sourceDigest) ? { digest: item.digest ?? item.sourceDigest } : {}),
      fullReadRequired,
    });
    snippetBudget = Math.max(0, snippetBudget - snippet.length);
  }
  if (envelope.items.length > projection.length) evidenceReadRequired = true;
  return { evidence: projection, evidenceReadRequired };
}

/** Backend projection deliberately drops bodyText, artifact references, and provenance. */
export function conversationEvidenceForBackend(
  metadata: Record<string, unknown>,
): Record<string, unknown> {
  if (metadata.evidence === undefined) return metadata;
  const envelope = validateConversationEvidenceEnvelope(metadata.evidence);
  return {
    ...metadata,
    evidence: {
      schema: CONVERSATION_EVIDENCE_SCHEMA,
      items: envelope.items.map((item) => ({
        id: item.id,
        kind: item.kind,
        title: item.title,
        capturedAtMs: item.capturedAtMs,
        availability: item.availability,
        extractionCompleteness: item.extractionCompleteness,
        ...((item.digest ?? item.sourceDigest) ? { digest: item.digest ?? item.sourceDigest } : {}),
        fullReadAvailable: Boolean(item.bodyText || item.artifactId),
      })),
    },
  };
}

/** Backend chat history contains only a compact descriptor. If that descriptor
 * is imported into a cold local journal, drop local-only fields and downgrade
 * availability so the local model never treats a remote mirror as a live
 * capture or a readable source body. */
export function conversationEvidenceForBackendImport(metadataJson: string): string {
  const parsed = parseMetadataObject(metadataJson);
  if (parsed.evidence === undefined) return JSON.stringify(parsed);
  const envelope = validateConversationEvidenceEnvelope(parsed.evidence);
  const items = envelope.items.map((item) => redactImportedConversationEvidence(item));
  return JSON.stringify({
    ...parsed,
    evidence: validateConversationEvidenceEnvelope({ schema: CONVERSATION_EVIDENCE_SCHEMA, items }),
  });
}

export function conversationEvidenceById(metadataJson: string, evidenceId: string): ConversationEvidence | null {
  const envelope = parseConversationEvidenceMetadata(metadataJson);
  return envelope?.items.find((item) => item.id === evidenceId) ?? null;
}

export function conversationEvidenceMatches(item: ConversationEvidence, query: string): boolean {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return false;
  return [item.id, item.kind, item.title, item.bodyText ?? "", ...Object.values(item.provenance ?? {})]
    .some((value) => value.toLocaleLowerCase().includes(normalized));
}

export function conversationEvidenceExcerpt(item: ConversationEvidence, query: string, maxChars = 320): string {
  const source = item.bodyText || item.title;
  const normalized = query.trim().toLocaleLowerCase();
  const index = source.toLocaleLowerCase().indexOf(normalized);
  if (index < 0) return source.slice(0, maxChars);
  const start = Math.max(0, index - Math.floor(maxChars / 3));
  return source.slice(start, start + maxChars);
}

function redactImportedConversationEvidence(item: ConversationEvidence): ConversationEvidence {
  const digest = item.digest ?? item.sourceDigest;
  const missingLocally = item.availability === "pending" || item.availability === "unavailable";
  return {
    id: item.id,
    kind: item.kind,
    title: item.title,
    capturedAtMs: item.capturedAtMs,
    availability: missingLocally ? "unavailable" : "partial",
    extractionCompleteness: missingLocally || item.extractionCompleteness === "none" ? "none" : "partial",
    ...(digest === undefined ? {} : { digest }),
  };
}

/**
 * Evidence capture may be admitted before OCR/extraction finishes. A pending
 * descriptor is a durable promise for one source identity; it may resolve to
 * one final descriptor exactly once, while retries and stale metadata updates
 * remain idempotent and can never replace completed body text.
 */
function mergeEvidenceRevision(
  existing: ConversationEvidence,
  incoming: ConversationEvidence,
): { evidence: ConversationEvidence; changed: boolean } {
  if (existing.availability === "pending" || incoming.availability === "pending") {
    assertPendingSourceIdentity(existing, incoming);
    if (existing.availability === "pending" && incoming.availability !== "pending") {
      return { evidence: incoming, changed: true };
    }
    if (existing.availability !== "pending" && incoming.availability === "pending") {
      return { evidence: existing, changed: false };
    }
  }
  if (stableJson(existing) !== stableJson(incoming)) {
    throw new Error(`Conversation evidence ID ${existing.id} already contains different content`);
  }
  return { evidence: existing, changed: false };
}

function assertPendingSourceIdentity(
  existing: ConversationEvidence,
  incoming: ConversationEvidence,
): void {
  const existingIdentity = {
    id: existing.id,
    kind: existing.kind,
    title: existing.title,
    capturedAtMs: existing.capturedAtMs,
    sourceDigest: existing.sourceDigest,
    artifactId: existing.artifactId,
    provenance: existing.provenance,
  };
  const incomingIdentity = {
    id: incoming.id,
    kind: incoming.kind,
    title: incoming.title,
    capturedAtMs: incoming.capturedAtMs,
    sourceDigest: incoming.sourceDigest,
    artifactId: incoming.artifactId,
    provenance: incoming.provenance,
  };
  if (stableJson(existingIdentity) !== stableJson(incomingIdentity)) {
    throw new Error(`Conversation evidence ID ${existing.id} changed its pending source identity`);
  }
}

function validateProvenance(input: Record<string, string>): Record<string, string> {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Conversation evidence provenance must be an object");
  }
  const entries = Object.entries(input);
  if (entries.length > MAX_CONVERSATION_EVIDENCE_PROVENANCE_KEYS) {
    throw new Error("Conversation evidence provenance has too many fields");
  }
  const result: Record<string, string> = {};
  for (const [key, value] of entries) {
    const validatedKey = boundedString(key, "evidence provenance key", MAX_CONVERSATION_EVIDENCE_PROVENANCE_KEY_CHARS);
    const validatedValue = boundedString(value, `evidence provenance ${validatedKey}`, MAX_CONVERSATION_EVIDENCE_PROVENANCE_VALUE_CHARS);
    result[validatedKey] = validatedValue;
  }
  return result;
}

function parseMetadataObject(metadataJson: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(metadataJson) as unknown;
  } catch {
    throw new Error("Journal metadata must be valid JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Journal metadata must contain a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function boundedString(value: unknown, field: string, maxChars: number): string {
  if (typeof value !== "string") throw new Error(`${field} must be a string`);
  const result = value.trim();
  if (!result || result.length > maxChars) throw new Error(`${field} is empty or too long`);
  return result;
}

function boundedUtf8String(value: unknown, field: string, maxBytes: number): string {
  if (typeof value !== "string" || utf8Bytes(value) > maxBytes) {
    throw new Error(`${field} is not a string or exceeds ${maxBytes} bytes`);
  }
  return value;
}

function utf8Bytes(value: string): number {
  return Buffer.byteLength(value, "utf8");
}

function digestForText(value: string): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stableJson(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
