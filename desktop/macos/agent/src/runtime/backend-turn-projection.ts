import { createHash } from "node:crypto";
import { structuredTurnFallbackText } from "./content-block-fallback.js";
import type { ConversationContentBlock, ConversationTurn } from "./types.js";

const MAX_JOURNAL_REVISION = 2_147_483_647;

export interface BackendTurnPayload {
  turnId: string;
  clientMessageId: string;
  journalRevision: number;
  text: string;
  sender: "human" | "ai";
  appId: string | null;
  sessionId: string | null;
  contentBlocks: ConversationContentBlock[];
  metadata: string | null;
  messageSource: "desktop_chat" | "realtime_voice";
}

export function backendTurnPayload(turn: ConversationTurn): BackendTurnPayload {
  const metadata = parseObjectJson(turn.metadataJson);
  const { content_blocks: _legacyContentBlocks, ...messageMetadata } = metadata;
  const backendMetadata = {
    ...messageMetadata,
    ...(turn.resources.length > 0 ? { resources: turn.resources } : {}),
  };
  const projectedText = turn.content.trim()
    ? turn.content
    : turn.role === "assistant"
      && turn.status === "completed"
      && (turn.contentBlocks.length > 0 || turn.resources.length > 0)
      ? structuredTurnFallbackText(turn.contentBlocks, turn.resources)
      : "";
  return {
    turnId: turn.turnId,
    clientMessageId: turn.turnId,
    journalRevision: boundedJournalRevision(turn.turnSeq),
    text: projectedText,
    sender: turn.role === "user" ? "human" : "ai",
    appId: typeof metadata.appId === "string" ? metadata.appId : null,
    sessionId: typeof metadata.sessionId === "string" ? metadata.sessionId : null,
    contentBlocks: turn.contentBlocks,
    metadata: Object.keys(backendMetadata).length === 0 ? null : stableJson(backendMetadata),
    messageSource: turn.origin === "realtime_voice" ? "realtime_voice" : "desktop_chat",
  };
}

export function backendTombstoneCode(turn: ConversationTurn): string | null {
  const payload = backendTurnPayload(turn);
  if (payload.text.trim()) return null;
  if (turn.status === "failed") return "empty_failed_turn_cancelled";
  if (turn.status === "completed") return "empty_completed_turn_cancelled";
  return null;
}

export function backendTurnPayloadHash(payload: BackendTurnPayload): string {
  return `sha256:${createHash("sha256").update(stableJson(payload)).digest("hex")}`;
}

function boundedJournalRevision(revision: number): number {
  if (!Number.isSafeInteger(revision) || revision < 1 || revision > MAX_JOURNAL_REVISION) {
    throw new Error(`Journal revision must be between 1 and ${MAX_JOURNAL_REVISION}`);
  }
  return revision;
}

function parseObjectJson(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    throw new Error("Journal metadata must be valid JSON");
  }
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stableJson(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
