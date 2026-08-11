// domain-pending(DIV-CHAT-SOURCE-001)

import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { parseSynthesizedPageJson } from
  "@omi-core/ratified-contracts/projections/synthesized";

import type { ChatAttachmentMetadata, ChatMessageRecord, StoredChatMessage } from "../stores/chat-messages-store.js";

export const CHAT_CONTEXT_PACKET_SCHEMA_VERSION = "v1" as const;
export const CHAT_CONTEXT_TRACE_VERSION = "v1" as const;
const MAX_CONTEXT_ITEMS = 64;
const MAX_TRANSCRIPT_TAIL = 8;
const MAX_UNDELIVERED_DELTAS = 32;
const MAX_CONTEXT_TOKEN_BUDGET = 1_000_000;
const DEFAULT_CONTEXT_TOKEN_BUDGET = 1_024;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;
const SAFE_HASH = /^sha256:[0-9a-f]{64}$/u;
const CONTROL = /[\u0000-\u001f\u007f]/u;
const REDACTION_MARKER = /(?:Bearer\s+|(?:api[_ -]?key|authorization|access[_ -]?token|token|secret|password)\s*[:=]|(?:attachment|file|opaque|reference)(?:[_ -]?id)?\s*[:=]|BEGIN\s+.*PRIVATE\s+KEY)/iu;

export type ChatGenerationContextPolicyDecision = "included" | "excluded" | "degraded";

export interface ChatGenerationContextCandidate {
  readonly sourceKind: string;
  readonly sourceId: string;
  readonly claimId: string | null;
  readonly evidenceId: string;
  readonly ownerAccountId: string;
  readonly sourceHash: string;
  readonly capturedAt: number;
  readonly expiresAt: number | null;
  readonly redactedPreview: string;
  readonly tokenEstimate: number;
  readonly inclusionReason: string;
  readonly policyDecision?: ChatGenerationContextPolicyDecision;
  readonly priority?: number;
  readonly conflictKey?: string | null;
}

export interface ChatGenerationContextItem {
  readonly sourceKind: string;
  readonly sourceId: string;
  readonly claimId: string | null;
  readonly evidenceId: string;
  readonly ownerAccountId: string;
  readonly sourceHash: string;
  readonly capturedAt: number;
  readonly expiresAt: number | null;
  readonly redactedPreview: string;
  readonly tokenEstimate: number;
  readonly inclusionReason: string;
  readonly policyDecision: ChatGenerationContextPolicyDecision;
  readonly trust: "untrusted-evidence";
}

export interface ChatGenerationTranscriptTurn {
  readonly messageId: string;
  readonly sender: string;
  readonly payloadHash: string;
  readonly redactedText: string;
  readonly tokenEstimate: number;
  /** Transcript is data, never an instruction channel for a provider. */
  readonly trust: "untrusted-transcript";
  readonly injectionPolicy: "data-only";
}

export interface ChatGenerationUndeliveredDelta {
  readonly eventId: string;
  readonly sequence: number;
  readonly payloadHash: string;
  readonly redactedText: string;
  readonly tokenEstimate: number;
  /** Undelivered deltas are data, never an instruction channel for a provider. */
  readonly trust: "untrusted-delta";
  readonly injectionPolicy: "data-only";
}

export interface ChatGenerationContextAttachment {
  readonly label: string;
  readonly mediaType: string;
  readonly sizeBytes: number;
  readonly referenceHash: string;
}

export interface ChatGenerationContextBudget {
  readonly maxTokens: number;
  readonly usedTokens: number;
  readonly remainingTokens: number;
  readonly selfNoiseTokens: number;
  readonly omittedItemCount: number;
  readonly compacted: boolean;
}

export interface ChatGenerationContextPacket {
  readonly schemaVersion: typeof CHAT_CONTEXT_PACKET_SCHEMA_VERSION;
  readonly traceVersion: typeof CHAT_CONTEXT_TRACE_VERSION;
  readonly packetHash: string;
  readonly ownerAccountId: string;
  readonly generationId: string;
  readonly createdAt: number;
  readonly items: readonly ChatGenerationContextItem[];
  readonly transcriptTail: readonly ChatGenerationTranscriptTurn[];
  readonly undeliveredDeltas: readonly ChatGenerationUndeliveredDelta[];
  readonly attachments: readonly ChatGenerationContextAttachment[];
  readonly budget: ChatGenerationContextBudget;
}

export type ChatGenerationContextResult = ChatGenerationContextPacket | readonly string[];

export interface ChatGenerationContextSourceInput {
  readonly accountId: string;
  readonly generationId?: string;
  readonly admitted: StoredChatMessage;
  readonly nowEpochMilliseconds?: number;
  readonly history?: readonly ChatMessageRecord[];
  /** Ephemeral request credential. A context source must never persist or return it. */
  readonly bearerToken: string;
}

export type ChatGenerationMemoryContext =
  | Readonly<{
      version: "chat-generation-memory-context-v1";
      state: "loaded";
      /** Exact ratified synthesized-memory page; contains citations and completeness. */
      canonical_page_json: string;
    }>
  | Readonly<{
      version: "chat-generation-memory-context-v1";
      /** Memory was not safely available. This is never proof that no memory exists. */
      state: "unavailable";
    }>;

const UNAVAILABLE_CONTEXT: ChatGenerationMemoryContext = Object.freeze({
  version: "chat-generation-memory-context-v1",
  state: "unavailable",
});

export const unavailableChatGenerationMemoryContext = (): ChatGenerationMemoryContext =>
  UNAVAILABLE_CONTEXT;

export const loadedChatGenerationMemoryContext = (
  canonicalPageJson: string,
): ChatGenerationMemoryContext => {
  if (parseSynthesizedPageJson(canonicalPageJson) === null) {
    throw new TypeError("invalid canonical Chat memory context");
  }
  return Object.freeze({
    version: "chat-generation-memory-context-v1" as const,
    state: "loaded" as const,
    canonical_page_json: canonicalPageJson,
  });
};

/** Detaches a context-source result without invoking caller-owned accessors. */
export const snapshotChatGenerationMemoryContext = (
  value: unknown,
): ChatGenerationMemoryContext | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")
    || Object.values(descriptors).some((descriptor) =>
      !descriptor.enumerable || !("value" in descriptor))) return null;
  const version = descriptors.version?.value;
  const state = descriptors.state?.value;
  if (version !== "chat-generation-memory-context-v1") return null;
  if (state === "unavailable") {
    return keys.length === 2 ? UNAVAILABLE_CONTEXT : null;
  }
  if (state !== "loaded" || keys.length !== 3
    || typeof descriptors.canonical_page_json?.value !== "string") return null;
  try {
    return loadedChatGenerationMemoryContext(descriptors.canonical_page_json.value);
  } catch {
    return null;
  }
};

export interface ChatGenerationContextSource {
  load(input: ChatGenerationContextSourceInput): Promise<ChatGenerationContextResult>;
}

const isSafeId = (value: unknown): value is string => typeof value === "string" && SAFE_ID.test(value);
const isSafeHash = (value: unknown): value is string => typeof value === "string" && SAFE_HASH.test(value);
const isSafeInt = (value: unknown): value is number => typeof value === "number"
  && Number.isSafeInteger(value) && value >= 0;
const isSafeText = (value: unknown, max = 512): value is string => typeof value === "string"
  && value.length > 0 && value.length <= max && value.trim().length > 0 && !CONTROL.test(value)
  && !REDACTION_MARKER.test(value);
const isContextText = (value: unknown, max = 512): value is string => typeof value === "string"
  && value.length > 0 && value.length <= max && value.trim().length > 0 && !CONTROL.test(value);
const tokenEstimateOf = (value: string): number => Math.max(1, Math.ceil(value.trim().split(/\s+/u).length * 1.3));
const hashText = (value: string): string => `sha256:${createHash("sha256").update(value, "utf8").digest("hex")}`;

/**
 * Keeps context previews useful while ensuring the context packet cannot
 * become a credential or opaque-reference transport. Injection-like prose is
 * retained as data and marked with a data-only policy below.
 */
const redactText = (value: string, max = 512): string => {
  const bounded = value.slice(0, max);
  const redacted = bounded
    .replace(/Bearer\s+[^\s,;]+/giu, "[redacted]")
    .replace(/(?:api[_ -]?key|authorization|token|secret|password|access[_ -]?token)\s*[:=]\s*[^\s,;]+/giu, "[redacted]")
    .replace(/(?:attachment|file|opaque|reference)(?:[_ -]?id)?\s*[:=]\s*[^\s,;]+/giu, "[redacted]")
    .replace(/BEGIN\s+[^\n]*PRIVATE\s+KEY[\s\S]*?END\s+[^\n]*PRIVATE\s+KEY/giu, "[redacted]");
  return redacted.trim().length === 0 ? "[redacted]" : redacted;
};

const canonicalJson = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
};

const candidateOrder = (left: ChatGenerationContextCandidate, right: ChatGenerationContextCandidate): number => {
  const priority = (right.priority ?? 0) - (left.priority ?? 0);
  if (priority !== 0) return priority;
  return left.sourceId < right.sourceId ? -1 : left.sourceId > right.sourceId ? 1 : 0;
};

const validateCandidate = (candidate: ChatGenerationContextCandidate): void => {
  if (!isSafeId(candidate.sourceKind) || !isSafeId(candidate.sourceId)
    || !(candidate.claimId === null || isSafeId(candidate.claimId)) || !isSafeId(candidate.evidenceId)
    || !isSafeId(candidate.ownerAccountId) || !isSafeHash(candidate.sourceHash)
    || !isSafeInt(candidate.capturedAt) || !(candidate.expiresAt === null || isSafeInt(candidate.expiresAt))
    || !isContextText(candidate.redactedPreview) || !isSafeInt(candidate.tokenEstimate)
    || candidate.tokenEstimate === 0 || !isContextText(candidate.inclusionReason)
    || (candidate.policyDecision !== undefined && !["included", "excluded", "degraded"].includes(candidate.policyDecision))
    || (candidate.priority !== undefined && (typeof candidate.priority !== "number" || !Number.isFinite(candidate.priority)))
    || (candidate.conflictKey !== undefined && !(candidate.conflictKey === null || isSafeId(candidate.conflictKey)))) {
    throw new TypeError("invalid context candidate");
  }
};

const attachmentRefs = (
  attachments: readonly ChatAttachmentMetadata[],
  allowedIds: ReadonlySet<string>,
): readonly ChatGenerationContextAttachment[] => Object.freeze(attachments
  .filter((attachment) => allowedIds.has(attachment.id))
  .sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0)
  .map((attachment) => {
    if (typeof attachment.displayName !== "string" || attachment.displayName.length === 0
      || attachment.displayName.length > 512 || CONTROL.test(attachment.displayName)
      || typeof attachment.mediaType !== "string" || attachment.mediaType.length === 0
      || attachment.mediaType.length > 128 || CONTROL.test(attachment.mediaType)
      || !isSafeInt(attachment.sizeBytes)) throw new TypeError("invalid context attachment metadata");
    return Object.freeze({
      label: redactText(attachment.displayName),
      mediaType: redactText(attachment.mediaType, 128),
      sizeBytes: attachment.sizeBytes,
      referenceHash: hashText(`attachment\0${attachment.id}`),
    });
  }));

const transcriptTail = (
  history: readonly ChatMessageRecord[],
): readonly ChatGenerationTranscriptTurn[] => Object.freeze([...history]
  .sort((left, right) => left.createdAt < right.createdAt ? -1
    : left.createdAt > right.createdAt ? 1 : left.id < right.id ? -1 : left.id > right.id ? 1 : 0)
  .map((message) => Object.freeze({
    messageId: message.id,
    sender: message.sender,
    payloadHash: isSafeHash(message.payloadHash) ? message.payloadHash : hashText(message.text),
    redactedText: redactText(message.text),
    tokenEstimate: tokenEstimateOf(message.text),
    trust: "untrusted-transcript" as const,
    injectionPolicy: "data-only" as const,
  })));

const deltas = (
  input: readonly ChatGenerationUndeliveredDelta[],
): readonly ChatGenerationUndeliveredDelta[] => Object.freeze([...input]
  .sort((left, right) => left.sequence - right.sequence || (left.eventId < right.eventId ? -1 : 1))
  .map((delta) => {
    if (!isSafeId(delta.eventId) || !isSafeHash(delta.payloadHash) || !isSafeInt(delta.sequence)
      || !isSafeInt(delta.tokenEstimate) || delta.tokenEstimate === 0
      || typeof delta.redactedText !== "string" || CONTROL.test(delta.redactedText)) {
      throw new TypeError("invalid undelivered context delta");
    }
    return Object.freeze({
      eventId: delta.eventId,
      sequence: delta.sequence,
      payloadHash: delta.payloadHash,
      redactedText: redactText(delta.redactedText),
      tokenEstimate: delta.tokenEstimate,
      trust: "untrusted-delta" as const,
      injectionPolicy: "data-only" as const,
    });
  }));

const attachmentTokenEstimate = (attachment: ChatGenerationContextAttachment): number =>
  tokenEstimateOf(`${attachment.label} ${attachment.mediaType}`);

export interface CreateChatGenerationContextPacketInput {
  readonly accountId: string;
  readonly generationId: string;
  readonly nowEpochMilliseconds: number;
  readonly candidates?: readonly ChatGenerationContextCandidate[];
  readonly history?: readonly ChatMessageRecord[];
  readonly undeliveredDeltas?: readonly ChatGenerationUndeliveredDelta[];
  readonly attachments?: readonly ChatAttachmentMetadata[];
  readonly attachmentSubset?: readonly string[];
  readonly maxTokens?: number;
}

/** Builds a detached packet with deterministic expiry, conflict, and budget rules. */
export const createChatGenerationContextPacket = (
  input: CreateChatGenerationContextPacketInput,
): ChatGenerationContextPacket => {
  if (!isSafeId(input.accountId) || !isSafeId(input.generationId) || !isSafeInt(input.nowEpochMilliseconds)
    || (input.maxTokens !== undefined && (!isSafeInt(input.maxTokens)
      || input.maxTokens === 0 || input.maxTokens > MAX_CONTEXT_TOKEN_BUDGET))) {
    throw new TypeError("invalid context packet input");
  }
  const maxTokens = input.maxTokens ?? DEFAULT_CONTEXT_TOKEN_BUDGET;
  const candidates = [...(input.candidates ?? [])];
  candidates.forEach(validateCandidate);
  const eligible = candidates.filter((candidate) => candidate.ownerAccountId === input.accountId
    && (candidate.expiresAt === null || candidate.expiresAt > input.nowEpochMilliseconds)
    && candidate.policyDecision !== "excluded");
  const byConflict = new Set<string>();
  const selected: ChatGenerationContextItem[] = [];
  let usedTokens = 0;
  let omittedItemCount = candidates.length - eligible.length;
  let selfNoiseTokens = candidates.filter((candidate) => !eligible.includes(candidate))
    .reduce((total, candidate) => total + candidate.tokenEstimate, 0);
  for (const candidate of eligible.sort(candidateOrder)) {
    if (candidate.conflictKey !== null && candidate.conflictKey !== undefined && byConflict.has(candidate.conflictKey)) {
      omittedItemCount += 1;
      selfNoiseTokens += candidate.tokenEstimate;
      continue;
    }
    if (selected.length >= MAX_CONTEXT_ITEMS) {
      omittedItemCount += 1;
      selfNoiseTokens += candidate.tokenEstimate;
      continue;
    }
    if (usedTokens + candidate.tokenEstimate > maxTokens) {
      omittedItemCount += 1;
      selfNoiseTokens += candidate.tokenEstimate;
      continue;
    }
    usedTokens += candidate.tokenEstimate;
    if (candidate.conflictKey !== null && candidate.conflictKey !== undefined) byConflict.add(candidate.conflictKey);
    selected.push(Object.freeze({
      sourceKind: candidate.sourceKind,
      sourceId: candidate.sourceId,
      claimId: candidate.claimId,
      evidenceId: candidate.evidenceId,
      ownerAccountId: candidate.ownerAccountId,
      sourceHash: candidate.sourceHash,
      capturedAt: candidate.capturedAt,
      expiresAt: candidate.expiresAt,
      redactedPreview: redactText(candidate.redactedPreview),
      tokenEstimate: candidate.tokenEstimate,
      inclusionReason: redactText(candidate.inclusionReason),
      policyDecision: candidate.policyDecision ?? "included",
      trust: "untrusted-evidence",
    }));
  }
  const tail = transcriptTail(input.history ?? []);
  const undelivered = deltas(input.undeliveredDeltas ?? []);
  const attachmentIds = new Set(input.attachmentSubset ?? []);
  const attachments = attachmentRefs(input.attachments ?? [], attachmentIds);

  const takeWithBudget = <T>(
    entries: readonly T[],
    maxEntries: number,
    tokenCost: (entry: T) => number,
  ): { readonly selected: readonly T[]; readonly omitted: number; readonly noise: number } => {
    const bounded = entries.slice(Math.max(0, entries.length - maxEntries));
    let omitted = entries.length - bounded.length;
    let noise = entries.slice(0, Math.max(0, entries.length - maxEntries))
      .reduce((total, entry) => total + tokenCost(entry), 0);
    const kept: T[] = [];
    for (let index = bounded.length - 1; index >= 0; index -= 1) {
      const entry = bounded[index]!;
      const cost = tokenCost(entry);
      if (usedTokens + cost > maxTokens) {
        omitted += 1;
        noise += cost;
        continue;
      }
      usedTokens += cost;
      kept.unshift(entry);
    }
    return { selected: Object.freeze(kept), omitted, noise };
  };
  const boundedTail = takeWithBudget(tail, MAX_TRANSCRIPT_TAIL, (entry) => entry.tokenEstimate);
  omittedItemCount += boundedTail.omitted;
  selfNoiseTokens += boundedTail.noise;
  const boundedDeltas = takeWithBudget(undelivered, MAX_UNDELIVERED_DELTAS, (entry) => entry.tokenEstimate);
  omittedItemCount += boundedDeltas.omitted;
  selfNoiseTokens += boundedDeltas.noise;
  const boundedAttachments = takeWithBudget(attachments, attachments.length, attachmentTokenEstimate);
  omittedItemCount += boundedAttachments.omitted;
  selfNoiseTokens += boundedAttachments.noise;
  const packetWithoutHash = {
    schemaVersion: CHAT_CONTEXT_PACKET_SCHEMA_VERSION,
    traceVersion: CHAT_CONTEXT_TRACE_VERSION,
    ownerAccountId: input.accountId,
    generationId: input.generationId,
    createdAt: input.nowEpochMilliseconds,
    items: Object.freeze(selected),
    transcriptTail: boundedTail.selected,
    undeliveredDeltas: boundedDeltas.selected,
    attachments: boundedAttachments.selected,
    budget: Object.freeze({
      maxTokens,
      usedTokens,
      remainingTokens: maxTokens - usedTokens,
      selfNoiseTokens,
      omittedItemCount,
      compacted: omittedItemCount > 0 || tail.length > MAX_TRANSCRIPT_TAIL
        || undelivered.length > MAX_UNDELIVERED_DELTAS || selected.length >= MAX_CONTEXT_ITEMS,
    }),
  };
  const packetHash = hashText(canonicalJson(packetWithoutHash));
  return Object.freeze({ ...packetWithoutHash, packetHash });
};

const isPlainRecord = (value: unknown): value is Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};

const hasExactKeys = (value: unknown, keys: readonly string[]): value is Record<string, unknown> => {
  if (!isPlainRecord(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === [...keys].sort()[index]);
};

const isTranscriptTurn = (value: unknown): value is ChatGenerationTranscriptTurn => {
  if (!hasExactKeys(value, ["injectionPolicy", "messageId", "payloadHash", "redactedText", "sender", "tokenEstimate", "trust"])) return false;
  const turn = value as unknown as ChatGenerationTranscriptTurn;
  return isSafeId(turn.messageId) && isSafeText(turn.sender, 128) && isSafeHash(turn.payloadHash)
    && typeof turn.redactedText === "string" && turn.redactedText.length <= 512 && !CONTROL.test(turn.redactedText)
    && isSafeInt(turn.tokenEstimate) && turn.tokenEstimate > 0
    && turn.trust === "untrusted-transcript" && turn.injectionPolicy === "data-only";
};

const isUndeliveredDelta = (value: unknown): value is ChatGenerationUndeliveredDelta => {
  if (!hasExactKeys(value, ["eventId", "injectionPolicy", "payloadHash", "redactedText", "sequence", "tokenEstimate", "trust"])) return false;
  const delta = value as unknown as ChatGenerationUndeliveredDelta;
  return isSafeId(delta.eventId) && isSafeHash(delta.payloadHash) && isSafeInt(delta.sequence)
    && typeof delta.redactedText === "string" && delta.redactedText.length <= 512 && !CONTROL.test(delta.redactedText)
    && isSafeInt(delta.tokenEstimate) && delta.tokenEstimate > 0
    && delta.trust === "untrusted-delta" && delta.injectionPolicy === "data-only";
};

const isContextItem = (value: unknown): value is ChatGenerationContextItem => {
  if (!hasExactKeys(value, ["capturedAt", "claimId", "evidenceId", "expiresAt", "inclusionReason", "ownerAccountId", "policyDecision", "redactedPreview", "sourceHash", "sourceId", "sourceKind", "tokenEstimate", "trust"])) return false;
  const item = value as unknown as ChatGenerationContextItem;
  return isSafeId(item.sourceKind) && isSafeId(item.sourceId)
    && (item.claimId === null || isSafeId(item.claimId)) && isSafeId(item.evidenceId)
    && isSafeId(item.ownerAccountId) && isSafeHash(item.sourceHash)
    && isSafeInt(item.capturedAt) && (item.expiresAt === null || isSafeInt(item.expiresAt))
    && isSafeText(item.redactedPreview) && isSafeInt(item.tokenEstimate) && item.tokenEstimate > 0
    && isSafeText(item.inclusionReason) && ["included", "excluded", "degraded"].includes(item.policyDecision)
    && item.trust === "untrusted-evidence";
};

const isAttachment = (value: unknown): value is ChatGenerationContextAttachment => {
  if (!hasExactKeys(value, ["label", "mediaType", "referenceHash", "sizeBytes"])) return false;
  const attachment = value as unknown as ChatGenerationContextAttachment;
  return isSafeText(attachment.label) && isSafeText(attachment.mediaType, 128)
    && isSafeInt(attachment.sizeBytes) && isSafeHash(attachment.referenceHash);
};

const isBudget = (value: unknown): value is ChatGenerationContextBudget => {
  if (!hasExactKeys(value, ["compacted", "maxTokens", "omittedItemCount", "remainingTokens", "selfNoiseTokens", "usedTokens"])) return false;
  const budget = value as unknown as ChatGenerationContextBudget;
  return isSafeInt(budget.maxTokens) && budget.maxTokens > 0
    && isSafeInt(budget.usedTokens) && budget.usedTokens <= budget.maxTokens
    && isSafeInt(budget.remainingTokens) && budget.remainingTokens === budget.maxTokens - budget.usedTokens
    && isSafeInt(budget.selfNoiseTokens) && isSafeInt(budget.omittedItemCount)
    && typeof budget.compacted === "boolean";
};

const isPacket = (value: unknown): value is ChatGenerationContextPacket => {
  if (!hasExactKeys(value, ["attachments", "budget", "createdAt", "generationId", "items", "ownerAccountId", "packetHash", "schemaVersion", "traceVersion", "transcriptTail", "undeliveredDeltas"])) return false;
  const packet = value as unknown as ChatGenerationContextPacket;
  return packet.schemaVersion === CHAT_CONTEXT_PACKET_SCHEMA_VERSION
    && packet.traceVersion === CHAT_CONTEXT_TRACE_VERSION
    && isSafeHash(packet.packetHash) && isSafeId(packet.ownerAccountId) && isSafeId(packet.generationId)
    && isSafeInt(packet.createdAt)
    && Array.isArray(packet.items) && packet.items.length <= MAX_CONTEXT_ITEMS && packet.items.every(isContextItem)
    && Array.isArray(packet.transcriptTail) && packet.transcriptTail.length <= MAX_TRANSCRIPT_TAIL && packet.transcriptTail.every(isTranscriptTurn)
    && Array.isArray(packet.undeliveredDeltas) && packet.undeliveredDeltas.length <= MAX_UNDELIVERED_DELTAS && packet.undeliveredDeltas.every(isUndeliveredDelta)
    && Array.isArray(packet.attachments) && packet.attachments.every(isAttachment)
    && isBudget(packet.budget);
};

const deepFreeze = <T>(value: T, seen = new WeakSet<object>()): T => {
  if (value !== null && typeof value === "object" && !seen.has(value as object)) {
    seen.add(value as object);
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child, seen);
    Object.freeze(value);
  }
  return value;
};

/** Validates ownership/hash and converts legacy bare context strings. */
export const normalizeChatGenerationContext = (
  value: ChatGenerationContextResult,
  input: { readonly accountId: string; readonly generationId: string; readonly nowEpochMilliseconds: number },
): ChatGenerationContextPacket => {
  let detached: unknown;
  try {
    detached = structuredClone(value);
  } catch {
    throw new TypeError("context value is not cloneable");
  }
  if (isPacket(detached)) {
    if (detached.ownerAccountId !== input.accountId || detached.generationId !== input.generationId) {
      throw new TypeError("context packet owner or generation mismatch");
    }
    const { packetHash, ...withoutHash } = detached;
    if (hashText(canonicalJson(withoutHash)) !== packetHash) throw new TypeError("context packet hash mismatch");
    return deepFreeze(detached);
  }
  if (!Array.isArray(detached) || detached.some((entry) => typeof entry !== "string" || entry.length > 512)) {
    throw new TypeError("invalid legacy context");
  }
  return createChatGenerationContextPacket({
    accountId: input.accountId,
    generationId: input.generationId,
    nowEpochMilliseconds: input.nowEpochMilliseconds,
    candidates: detached.map((text, index) => ({
      sourceKind: "legacy",
      sourceId: `legacy:${index}`,
      claimId: null,
      evidenceId: `evidence:legacy:${index}`,
      ownerAccountId: input.accountId,
      sourceHash: hashText(text),
      capturedAt: input.nowEpochMilliseconds,
      expiresAt: null,
      redactedPreview: text,
      tokenEstimate: tokenEstimateOf(text),
      inclusionReason: "legacy_context",
    })),
  });
};

export interface DeterministicContextSourceOptions {
  readonly candidates?: readonly ChatGenerationContextCandidate[]
    | ((input: ChatGenerationContextSourceInput) => readonly ChatGenerationContextCandidate[]);
  readonly maxTokens?: number;
  readonly attachmentSubset?: readonly string[]
    | ((input: ChatGenerationContextSourceInput) => readonly string[]);
  readonly undeliveredDeltas?: readonly ChatGenerationUndeliveredDelta[]
    | ((input: ChatGenerationContextSourceInput) => readonly ChatGenerationUndeliveredDelta[]);
}

/** Deterministic context adapter used by scenarios and local conformance tests. */
export const createDeterministicChatGenerationContextSource = (
  options: DeterministicContextSourceOptions = {},
): ChatGenerationContextSource => Object.freeze({
  async load(input: ChatGenerationContextSourceInput): Promise<ChatGenerationContextPacket> {
    const candidates = typeof options.candidates === "function" ? options.candidates(input) : options.candidates;
    const attachmentSubset = typeof options.attachmentSubset === "function"
      ? options.attachmentSubset(input) : options.attachmentSubset;
    const undeliveredDeltas = typeof options.undeliveredDeltas === "function"
      ? options.undeliveredDeltas(input) : options.undeliveredDeltas;
    return createChatGenerationContextPacket({
      accountId: input.accountId,
      generationId: input.generationId ?? input.admitted.generationId ?? `generation:${input.admitted.message.id}`,
      nowEpochMilliseconds: input.nowEpochMilliseconds ?? input.admitted.message.createdAt,
      candidates: candidates?.filter((candidate) => candidate.ownerAccountId === input.accountId),
      history: input.history,
      undeliveredDeltas,
      attachments: input.admitted.message.attachments,
      attachmentSubset,
      maxTokens: options.maxTokens,
    });
  },
});

/** Deliberately empty adapter; it now returns a truthful, hashable packet. */
export const createEmptyChatGenerationContextSource = (): ChatGenerationContextSource =>
  createDeterministicChatGenerationContextSource();
