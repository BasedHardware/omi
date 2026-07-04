import { generateAgentId } from "./sqlite-store.js";
import type { AgentStore } from "./types.js";

export interface SurfaceRef {
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
}

export interface ResolveSurfaceSessionInput {
  ownerId: string;
  surfaceRef: SurfaceRef;
  defaultAdapterId?: string;
  title?: string | null;
}

export interface ResolveSurfaceSessionResult {
  conversationId: string;
  agentSessionId: string;
}

export interface LegacyMainChatSessionEntry {
  chatId: string;
  agentSessionId: string;
}

export function surfaceRefKey(surfaceRef: SurfaceRef): string {
  return `${surfaceRef.surfaceKind}|${surfaceRef.externalRefKind}|${surfaceRef.externalRefId}`;
}

export function resolveSurfaceSession(
  store: AgentStore,
  input: ResolveSurfaceSessionInput,
  nowMs: () => number,
): ResolveSurfaceSessionResult {
  const now = nowMs();
  const existing = store.getOptionalRow(
    `SELECT conversation_id, agent_session_id
     FROM surface_conversations
     WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
    [
      input.ownerId,
      input.surfaceRef.surfaceKind,
      input.surfaceRef.externalRefKind,
      input.surfaceRef.externalRefId,
    ],
  );
  if (existing) {
    const agentSessionId = String(existing.agent_session_id);
    const conversationId = String(existing.conversation_id);
    store.execute(
      `UPDATE surface_conversations
       SET last_active_at_ms = ?
       WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
      [
        now,
        input.ownerId,
        input.surfaceRef.surfaceKind,
        input.surfaceRef.externalRefKind,
        input.surfaceRef.externalRefId,
      ],
    );
    return { conversationId, agentSessionId };
  }

  return store.withTransaction(() => {
    const session = store.insertSession({
      ownerId: input.ownerId,
      surfaceKind: input.surfaceRef.surfaceKind,
      externalRefKind: input.surfaceRef.externalRefKind,
      externalRefId: input.surfaceRef.externalRefId,
      title: input.title ?? null,
      defaultAdapterId: input.defaultAdapterId ?? "acp",
    });
    const conversationId = generateAgentId("conversation");
    store.insertSurfaceConversation({
      ownerId: input.ownerId,
      surfaceKind: input.surfaceRef.surfaceKind,
      externalRefKind: input.surfaceRef.externalRefKind,
      externalRefId: input.surfaceRef.externalRefId,
      conversationId,
      agentSessionId: session.sessionId,
      createdAtMs: now,
      lastActiveAtMs: now,
    });
    return { conversationId, agentSessionId: session.sessionId };
  });
}

export function importLegacyMainChatSessions(
  store: AgentStore,
  input: { ownerId: string; entries: LegacyMainChatSessionEntry[] },
  nowMs: () => number,
): number {
  const now = nowMs();
  let imported = 0;
  for (const entry of input.entries) {
    const chatId = entry.chatId.trim();
    const agentSessionId = entry.agentSessionId.trim();
    if (!chatId || !agentSessionId) continue;

    const surfaceRef: SurfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: chatId,
    };
    const existing = store.getOptionalRow(
      `SELECT conversation_id FROM surface_conversations
       WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
      [input.ownerId, surfaceRef.surfaceKind, surfaceRef.externalRefKind, surfaceRef.externalRefId],
    );
    if (existing) continue;

    const sessionRow = store.getOptionalRow(
      "SELECT session_id FROM sessions WHERE session_id = ? AND owner_id = ?",
      [agentSessionId, input.ownerId],
    );
    const agentSession = sessionRow
      ? agentSessionId
      : store.insertSession({
          ownerId: input.ownerId,
          sessionId: agentSessionId,
          surfaceKind: surfaceRef.surfaceKind,
          externalRefKind: surfaceRef.externalRefKind,
          externalRefId: surfaceRef.externalRefId,
          defaultAdapterId: "acp",
        }).sessionId;

    store.insertSurfaceConversation({
      ownerId: input.ownerId,
      surfaceKind: surfaceRef.surfaceKind,
      externalRefKind: surfaceRef.externalRefKind,
      externalRefId: surfaceRef.externalRefId,
      conversationId: agentSession,
      agentSessionId,
      createdAtMs: now,
      lastActiveAtMs: now,
    });
    imported += 1;
  }
  return imported;
}

export function clearOwnerSurfaceState(store: AgentStore, ownerId: string, nowMs: () => number): {
  invalidatedBindingIds: string[];
} {
  const now = nowMs();
  const sessionRows = store.allRows("SELECT session_id FROM sessions WHERE owner_id = ?", [ownerId]);
  const sessionIds = sessionRows.map((row) => String(row.session_id));
  if (sessionIds.length === 0) {
    return { invalidatedBindingIds: [] };
  }

  const placeholders = sessionIds.map(() => "?").join(", ");
  const bindingRows = store.allRows(
    `SELECT binding_id FROM adapter_bindings
     WHERE session_id IN (${placeholders}) AND status = 'active'`,
    sessionIds,
  );
  const invalidatedBindingIds = bindingRows.map((row) => String(row.binding_id));
  if (invalidatedBindingIds.length > 0) {
    store.execute(
      `UPDATE adapter_bindings
       SET status = 'invalid', invalidated_at_ms = ?, updated_at_ms = ?
       WHERE binding_id IN (${invalidatedBindingIds.map(() => "?").join(", ")})`,
      [now, now, ...invalidatedBindingIds],
    );
  }
  return { invalidatedBindingIds };
}
