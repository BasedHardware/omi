import { generateAgentId } from "./sqlite-store.js";
import type { AgentStore, ConversationTurn, NewConversationTurn } from "./types.js";
import type { SurfaceRef } from "./surface-session.js";

export const CONVERSATION_TURN_BACKFILL_LIMIT = 50;
export const CONVERSATION_TRANSCRIPT_TAIL_LIMIT = 10;

export interface ConversationTurnImportEntry {
  role: "user" | "assistant";
  content: string;
  surfaceKind?: string;
  createdAtMs?: number;
  metadataJson?: string;
}

export function conversationIdForSession(store: AgentStore, sessionId: string): string | null {
  const row = store.getOptionalRow(
    "SELECT conversation_id FROM surface_conversations WHERE agent_session_id = ?",
    [sessionId],
  );
  return row ? String(row.conversation_id) : null;
}

export function listRecentConversationTurns(
  store: AgentStore,
  conversationId: string,
  limit = CONVERSATION_TRANSCRIPT_TAIL_LIMIT,
): ConversationTurn[] {
  return store
    .allRows(
      `SELECT conversation_id, turn_id, role, surface_kind, content, created_at_ms, metadata_json
       FROM conversation_turns
       WHERE conversation_id = ?
       ORDER BY created_at_ms DESC
       LIMIT ?`,
      [conversationId, limit],
    )
    .map(conversationTurnFromRow)
    .reverse();
}

export function appendConversationTurn(store: AgentStore, input: NewConversationTurn): ConversationTurn {
  return store.insertConversationTurn(input);
}

export function importConversationTurnsBackfill(
  store: AgentStore,
  input: {
    conversationId: string;
    turns: readonly ConversationTurnImportEntry[];
    nowMs: () => number;
  },
): number {
  const existing = store.getOptionalRow(
    "SELECT 1 FROM conversation_turns WHERE conversation_id = ? LIMIT 1",
    [input.conversationId],
  );
  if (existing) return 0;

  const bounded = input.turns
    .filter((turn) => turn.content.trim().length > 0)
    .slice(-CONVERSATION_TURN_BACKFILL_LIMIT);
  const now = input.nowMs();
  let imported = 0;
  for (const [index, turn] of bounded.entries()) {
    store.insertConversationTurn({
      conversationId: input.conversationId,
      turnId: generateAgentId("turn"),
      role: turn.role,
      surfaceKind: turn.surfaceKind ?? "main_chat",
      content: turn.content,
      createdAtMs: turn.createdAtMs ?? now - (bounded.length - index),
      metadataJson: turn.metadataJson ?? JSON.stringify({ source: "swift_backfill" }),
    });
    imported += 1;
  }
  return imported;
}

export function importConversationTurnsForSurface(
  store: AgentStore,
  input: {
    ownerId: string;
    surfaceRef: SurfaceRef;
    turns: readonly ConversationTurnImportEntry[];
    nowMs: () => number;
  },
): number {
  const row = store.getOptionalRow(
    `SELECT conversation_id FROM surface_conversations
     WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
    [input.ownerId, input.surfaceRef.surfaceKind, input.surfaceRef.externalRefKind, input.surfaceRef.externalRefId],
  );
  if (!row) return 0;
  return importConversationTurnsBackfill(store, {
    conversationId: String(row.conversation_id),
    turns: input.turns,
    nowMs: input.nowMs,
  });
}

function conversationTurnFromRow(row: Record<string, unknown>): ConversationTurn {
  return {
    conversationId: String(row.conversation_id),
    turnId: String(row.turn_id),
    role: String(row.role) as ConversationTurn["role"],
    surfaceKind: String(row.surface_kind),
    content: String(row.content),
    createdAtMs: Number(row.created_at_ms),
    metadataJson: String(row.metadata_json ?? "{}"),
  };
}
