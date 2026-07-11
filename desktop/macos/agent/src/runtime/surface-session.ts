import { generateAgentId } from "./sqlite-store.js";
import type { AgentExecutionRole, AgentStore, ProviderBoundary } from "./types.js";

export interface SurfaceRef {
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
}

export interface ResolveSurfaceSessionInput {
  ownerId: string;
  surfaceRef: SurfaceRef;
  defaultAdapterId?: string;
  executionRole?: AgentExecutionRole;
  providerBoundary?: ProviderBoundary;
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

function isSqliteUniqueConstraintError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return (
    error.message.includes("UNIQUE constraint failed") ||
    error.message.includes("SQLITE_CONSTRAINT_UNIQUE")
  );
}

function readSurfaceConversation(
  store: AgentStore,
  input: ResolveSurfaceSessionInput,
): ResolveSurfaceSessionResult | undefined {
  const row = store.getOptionalRow(
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
  if (!row) return undefined;
  return {
    conversationId: String(row.conversation_id),
    agentSessionId: String(row.agent_session_id),
  };
}

function readSessionIdByExternalRef(store: AgentStore, input: ResolveSurfaceSessionInput): string | undefined {
  const row = store.getOptionalRow(
    `SELECT session_id FROM sessions
     WHERE owner_id = ? AND external_ref_kind = ? AND external_ref_id = ?`,
    [input.ownerId, input.surfaceRef.externalRefKind, input.surfaceRef.externalRefId],
  );
  return row ? String(row.session_id) : undefined;
}

function touchSurfaceConversation(store: AgentStore, input: ResolveSurfaceSessionInput, now: number): void {
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
}

function createSurfaceConversationMapping(
  store: AgentStore,
  input: ResolveSurfaceSessionInput,
  agentSessionId: string,
  now: number,
): ResolveSurfaceSessionResult {
  const conversationId = generateAgentId("conversation");
  try {
    store.insertSurfaceConversation({
      ownerId: input.ownerId,
      surfaceKind: input.surfaceRef.surfaceKind,
      externalRefKind: input.surfaceRef.externalRefKind,
      externalRefId: input.surfaceRef.externalRefId,
      conversationId,
      agentSessionId,
      createdAtMs: now,
      lastActiveAtMs: now,
    });
    return { conversationId, agentSessionId };
  } catch (error) {
    if (!isSqliteUniqueConstraintError(error)) throw error;
    const mapped = readSurfaceConversation(store, input);
    if (!mapped) throw error;
    touchSurfaceConversation(store, input, now);
    return mapped;
  }
}

function recoverResolveSurfaceSessionAfterConflict(
  store: AgentStore,
  input: ResolveSurfaceSessionInput,
  now: number,
  error: unknown,
): ResolveSurfaceSessionResult {
  if (!isSqliteUniqueConstraintError(error)) throw error;
  const mapped = readSurfaceConversation(store, input);
  if (mapped) {
    touchSurfaceConversation(store, input, now);
    return mapped;
  }
  const existingSessionId = readSessionIdByExternalRef(store, input);
  if (!existingSessionId) throw error;
  return createSurfaceConversationMapping(store, input, existingSessionId, now);
}

export function resolveSurfaceSession(
  store: AgentStore,
  input: ResolveSurfaceSessionInput,
  nowMs: () => number,
): ResolveSurfaceSessionResult {
  return store.withTransaction(() => {
    const now = nowMs();
    const mapped = readSurfaceConversation(store, input);
    if (mapped) {
      touchSurfaceConversation(store, input, now);
      return mapped;
    }

    const existingSessionId = readSessionIdByExternalRef(store, input);
    if (existingSessionId) {
      return createSurfaceConversationMapping(store, input, existingSessionId, now);
    }

    try {
      const session = store.insertSession({
        ownerId: input.ownerId,
        surfaceKind: input.surfaceRef.surfaceKind,
        externalRefKind: input.surfaceRef.externalRefKind,
        externalRefId: input.surfaceRef.externalRefId,
        title: input.title ?? null,
        defaultAdapterId: input.defaultAdapterId ?? "acp",
        executionRole: input.executionRole,
        providerBoundary: input.providerBoundary,
      });
      return createSurfaceConversationMapping(store, input, session.sessionId, now);
    } catch (error) {
      return recoverResolveSurfaceSessionAfterConflict(store, input, now, error);
    }
  });
}

function resolveLegacyAgentSessionId(
  store: AgentStore,
  input: { ownerId: string; surfaceRef: SurfaceRef; legacySessionId: string; defaultAdapterId?: string },
): string {
  const existingByRef = readSessionIdByExternalRef(store, {
    ownerId: input.ownerId,
    surfaceRef: input.surfaceRef,
  });
  if (existingByRef) return existingByRef;

  const sessionRow = store.getOptionalRow(
    "SELECT session_id FROM sessions WHERE session_id = ? AND owner_id = ?",
    [input.legacySessionId, input.ownerId],
  );
  if (sessionRow) return String(sessionRow.session_id);

  try {
    return store.insertSession({
      ownerId: input.ownerId,
      sessionId: input.legacySessionId,
      surfaceKind: input.surfaceRef.surfaceKind,
      externalRefKind: input.surfaceRef.externalRefKind,
      externalRefId: input.surfaceRef.externalRefId,
      defaultAdapterId: input.defaultAdapterId ?? "acp",
    }).sessionId;
  } catch (error) {
    if (!isSqliteUniqueConstraintError(error)) throw error;
    const raced = readSessionIdByExternalRef(store, {
      ownerId: input.ownerId,
      surfaceRef: input.surfaceRef,
    });
    if (!raced) throw error;
    return raced;
  }
}

// TODO(desktop-agent-platonic-gap-closure G6): delete importLegacyMainChatSessions two desktop releases after the release that ships the platonic branch.
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

    const resolvedSessionId = resolveLegacyAgentSessionId(store, {
      ownerId: input.ownerId,
      surfaceRef,
      legacySessionId: agentSessionId,
      defaultAdapterId: "acp",
    });

    const conversationId = generateAgentId("conversation");
    try {
      store.insertSurfaceConversation({
        ownerId: input.ownerId,
        surfaceKind: surfaceRef.surfaceKind,
        externalRefKind: surfaceRef.externalRefKind,
        externalRefId: surfaceRef.externalRefId,
        conversationId,
        agentSessionId: resolvedSessionId,
        createdAtMs: now,
        lastActiveAtMs: now,
      });
    } catch (error) {
      if (!isSqliteUniqueConstraintError(error)) throw error;
      const mapped = readSurfaceConversation(store, { ownerId: input.ownerId, surfaceRef });
      if (mapped) continue;
      throw error;
    }
    imported += 1;
  }
  return imported;
}

export interface MergeFloatingChatIntoMainChatResult {
  mergedTurns: number;
  removedFloatingMapping: boolean;
}

/** One-time migration: fold legacy floating_chat transcript into main_chat. */
export function mergeFloatingChatIntoMainChat(
  store: AgentStore,
  input: { ownerId: string; chatId?: string },
  nowMs: () => number,
): MergeFloatingChatIntoMainChatResult {
  const chatId = input.chatId?.trim() || "default";
  const floatingRef: SurfaceRef = {
    surfaceKind: "floating_chat",
    externalRefKind: "chat",
    externalRefId: chatId,
  };
  const mainRef: SurfaceRef = {
    surfaceKind: "main_chat",
    externalRefKind: "chat",
    externalRefId: chatId,
  };

  const floatingRow = store.getOptionalRow(
    `SELECT conversation_id FROM surface_conversations
     WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
    [input.ownerId, floatingRef.surfaceKind, floatingRef.externalRefKind, floatingRef.externalRefId],
  );
  if (!floatingRow) {
    return { mergedTurns: 0, removedFloatingMapping: false };
  }

  const floatingConversationId = String(floatingRow.conversation_id);
  const mainResolved = resolveSurfaceSession(store, { ownerId: input.ownerId, surfaceRef: mainRef }, nowMs);
  const mainConversationId = mainResolved.conversationId;

  if (floatingConversationId === mainConversationId) {
    store.execute(
      `DELETE FROM surface_conversations
       WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
      [input.ownerId, floatingRef.surfaceKind, floatingRef.externalRefKind, floatingRef.externalRefId],
    );
    return { mergedTurns: 0, removedFloatingMapping: true };
  }

  const turns = store.allRows(
    `SELECT role, content, created_at_ms, metadata_json
     FROM conversation_turns
     WHERE conversation_id = ?
     ORDER BY created_at_ms ASC`,
    [floatingConversationId],
  );

  let mergedTurns = 0;
  store.withTransaction(() => {
    for (const row of turns) {
      store.insertConversationTurn({
        conversationId: mainConversationId,
        turnId: generateAgentId("turn"),
        role: String(row.role) as "user" | "assistant",
        surfaceKind: "main_chat",
        content: String(row.content),
        createdAtMs: Number(row.created_at_ms),
        metadataJson: String(row.metadata_json ?? "{}"),
      });
      mergedTurns += 1;
    }
    store.execute(`DELETE FROM conversation_turns WHERE conversation_id = ?`, [floatingConversationId]);
    store.execute(
      `DELETE FROM surface_conversations
       WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
      [input.ownerId, floatingRef.surfaceKind, floatingRef.externalRefKind, floatingRef.externalRefId],
    );
  });

  return { mergedTurns, removedFloatingMapping: true };
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
