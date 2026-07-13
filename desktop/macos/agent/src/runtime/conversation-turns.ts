import type {
  AgentStore,
  ConversationContentBlock,
  ConversationResource,
  ConversationTurn,
} from "./types.js";

/** Resolve the canonical journal conversation associated with a kernel session. */
export function conversationIdForSession(store: AgentStore, sessionId: string): string | null {
  const row = store.getOptionalRow(
    `SELECT conversation_id FROM surface_conversations
     WHERE agent_session_id = ?
     ORDER BY last_active_at_ms DESC
     LIMIT 1`,
    [sessionId],
  );
  return row ? String(row.conversation_id) : null;
}

/** Shared row codec for the canonical journal reader. This function never writes. */
export function conversationTurnFromRow(row: Record<string, unknown>): ConversationTurn {
  return {
    conversationId: String(row.conversation_id),
    turnId: String(row.turn_id),
    turnSeq: Number(row.turn_seq ?? 0),
    producerId: String(row.producer_id ?? `legacy:${String(row.turn_id)}`),
    payloadHash: String(row.payload_hash ?? "legacy"),
    role: String(row.role) as ConversationTurn["role"],
    surfaceKind: String(row.surface_kind),
    content: String(row.content),
    origin: String(row.origin ?? "legacy") as ConversationTurn["origin"],
    status: String(row.status ?? "completed") as ConversationTurn["status"],
    contentBlocks: parseArray<ConversationContentBlock>(row.content_blocks_json),
    resources: parseArray<ConversationResource>(row.resources_json),
    producingRunId: row.producing_run_id == null ? null : String(row.producing_run_id),
    producingAttemptId: row.producing_attempt_id == null ? null : String(row.producing_attempt_id),
    remoteId: row.remote_id == null ? null : String(row.remote_id),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms ?? row.created_at_ms),
    completedAtMs: row.completed_at_ms == null ? null : Number(row.completed_at_ms),
    metadataJson: String(row.metadata_json ?? "{}"),
  };
}

function parseArray<T>(raw: unknown): T[] {
  if (typeof raw !== "string") return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed as T[] : [];
  } catch {
    return [];
  }
}
