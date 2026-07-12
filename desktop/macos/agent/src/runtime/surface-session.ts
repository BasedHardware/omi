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
  modelProfile?: string | null;
  defaultCwd?: string | null;
  executionProfileSource?: "creation" | "child_derivation";
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

export const LEGACY_MAIN_CHAT_SESSION_COMPATIBILITY = {
  owner: "desktop-agent-runtime",
  removalCondition: "all supported desktop versions have imported UserDefaults main-chat session aliases",
  removeBy: "2026-10-01",
} as const;

const SHARED_CHAT_SURFACES = new Set(["main_chat", "floating_chat", "realtime_voice", "realtime"]);

function sharesChatContinuity(surfaceRef: SurfaceRef): boolean {
  return surfaceRef.externalRefKind === "chat" && SHARED_CHAT_SURFACES.has(surfaceRef.surfaceKind);
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

function readSharedChatMapping(
  store: AgentStore,
  input: ResolveSurfaceSessionInput,
): ResolveSurfaceSessionResult | undefined {
  if (!sharesChatContinuity(input.surfaceRef)) return undefined;
  const row = store.getOptionalRow(
    `SELECT conversation_id, agent_session_id
     FROM surface_conversations
     WHERE owner_id = ? AND external_ref_kind = ? AND external_ref_id = ?
       AND surface_kind IN ('main_chat', 'floating_chat', 'realtime_voice', 'realtime')
     ORDER BY CASE surface_kind
       WHEN 'main_chat' THEN 0
       WHEN 'floating_chat' THEN 1
       WHEN 'realtime_voice' THEN 2
       ELSE 3 END,
       created_at_ms ASC
     LIMIT 1`,
    [input.ownerId, input.surfaceRef.externalRefKind, input.surfaceRef.externalRefId],
  );
  return row ? {
    conversationId: String(row.conversation_id),
    agentSessionId: String(row.agent_session_id),
  } : undefined;
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
  const shared = readSharedChatMapping(store, input);
  if (shared && shared.agentSessionId !== agentSessionId) {
    throw new Error("Shared chat continuity mapping points at a different canonical session");
  }
  const conversationId = shared?.conversationId ?? generateAgentId("conversation");
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
      const resolved = createSurfaceConversationMapping(store, input, existingSessionId, now);
      return resolved;
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
        modelProfile: input.modelProfile,
        defaultCwd: input.defaultCwd,
        executionProfileSource: input.executionProfileSource,
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
