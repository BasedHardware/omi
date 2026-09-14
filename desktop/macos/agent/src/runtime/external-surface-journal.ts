import { createHash } from "node:crypto";

import { conversationTurnFromRow } from "./conversation-turns.js";
import { recordJournalExchange, updateJournalTurn } from "./conversation-journal.js";
import type { AgentRun, AgentStore, ConversationTurn, RunAttempt } from "./types.js";

export interface ExternalSurfaceJournalChange {
  ownerId: string;
  conversationId: string;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turn: ConversationTurn;
}

export interface ExternalSurfaceJournalMaterialization {
  materialized: boolean;
  changes: ExternalSurfaceJournalChange[];
}

/**
 * Repairs the canonical voice exchange from a successfully completed external
 * realtime run. The normal Swift journal funnel may already have committed the
 * same stable turn IDs; in that case those rows stay authoritative. This path
 * only fills the crash/restart gap where the run terminalized but the journal
 * exchange never landed (#12731).
 */
export function materializeExternalSurfaceRunJournal(
  store: AgentStore,
  input: {
    ownerId: string;
    run: AgentRun;
    attempt: RunAttempt;
    finalText: string | null;
    nowMs?: number;
  },
): ExternalSurfaceJournalMaterialization {
  const runInput = parseObject(input.run.inputJson);
  const metadata = objectValue(runInput.metadata);
  const external = objectValue(metadata?.externalSurface);
  if (external?.authority !== "swift_realtime") {
    throw new Error("External surface journal materialization requires Swift realtime authority");
  }
  const rawTurnId = typeof external.turnId === "string" ? external.turnId.trim() : "";
  if (!rawTurnId) throw new Error("External surface journal materialization is missing turn identity");

  const surface = store.getOptionalRow(
    `SELECT conversation_id, surface_kind, external_ref_kind, external_ref_id
     FROM surface_conversations
     WHERE owner_id = ? AND agent_session_id = ?
       AND surface_kind IN ('main_chat', 'floating_chat', 'realtime_voice', 'realtime')
     -- This repair belongs to a realtime voice run, so a realtime surface wins.
     -- Ordering main_chat first labelled the repaired voice turns main_chat
     -- whenever the session also had a main-chat alias, and emitted the change
     -- on that surface, so the voice projection never saw its own turn.
     ORDER BY CASE surface_kind
       WHEN 'realtime_voice' THEN 0
       WHEN 'realtime' THEN 1
       WHEN 'floating_chat' THEN 2
       ELSE 3
     END, last_active_at_ms DESC
     LIMIT 1`,
    [input.ownerId, input.run.sessionId],
  );
  if (!surface) throw new Error("External surface run has no canonical journal surface");

  const conversationId = String(surface.conversation_id);
  const surfaceKind = String(surface.surface_kind);
  const externalRefKind = String(surface.external_ref_kind);
  const externalRefId = String(surface.external_ref_id);
  const continuityKey = `voice:${rawTurnId.toLowerCase()}`;
  const userTurnId = stableTurnId(continuityKey, "user");
  const assistantTurnId = stableTurnId(continuityKey, "assistant");
  const existingUser = optionalTurn(store, conversationId, userTurnId);
  const existingAssistant = optionalTurn(store, conversationId, assistantTurnId);

  if (existingUser) assertCanonicalIdentity(existingUser, conversationId, "user", continuityKey);
  if (existingAssistant) {
    assertCanonicalIdentity(existingAssistant, conversationId, "assistant", continuityKey);
    // A spawn receipt can own this continuity key with different assistant
    // prose and run provenance. Stable canonical ownership wins over this
    // repair path; never overwrite it with provider narration.
    if (existingAssistant.status === "completed") {
      return { materialized: true, changes: [] };
    }
    // A failed canonical row is not ownership, it is a conflict: the successful
    // answer is nowhere in history and this path will not overwrite a failure to
    // put it there. Reporting `materialized: true` here told Swift the answer had
    // landed when it had not, which is exactly the silent loss this change exists
    // to close -- so report the truth and let Swift fail closed.
    if (existingAssistant.status === "failed") {
      return { materialized: false, changes: [] };
    }
  }

  const finalText = input.finalText?.trim() ?? "";
  if (!finalText) return { materialized: false, changes: [] };

  const now = input.nowMs ?? Date.now();
  const promptIsSynthetic = external.promptIsSynthetic === true;
  const prompt = typeof runInput.prompt === "string" ? runInput.prompt.trim() : "";
  const metadataJson = JSON.stringify({ continuityKey });
  const userTurn = (createdAtMs: number) => ({
    turnId: userTurnId,
    role: "user" as const,
    surfaceKind,
    origin: "realtime_voice" as const,
    status: "completed" as const,
    content: prompt,
    contentBlocks: [],
    resources: [],
    metadataJson,
    createdAtMs: Math.min(createdAtMs, Number.MAX_SAFE_INTEGER - 1),
  });
  const changes: ExternalSurfaceJournalChange[] = [];
  const change = (turn: ConversationTurn): ExternalSurfaceJournalChange => ({
    ownerId: input.ownerId,
    conversationId,
    surfaceKind,
    externalRefKind,
    externalRefId,
    turn,
  });

  if (existingAssistant) {
    // The user turn can be absent even when the assistant row exists -- a crash
    // between the two writes leaves exactly that. Restore it first, or the
    // repaired exchange is an answer with no question.
    if (!existingUser && !promptIsSynthetic && prompt) {
      // Placed just before the assistant row, not at `now`. The answer already
      // exists and carries an older timestamp, so a restored question stamped now
      // sorts after it and history reads as a reply with no question.
      const restored = recordJournalExchange(store, {
        ownerId: input.ownerId,
        conversationId,
        turns: [userTurn(Math.max(0, existingAssistant.createdAtMs - 1))],
      });
      for (const turn of restored.createdTurns) changes.push(change(turn));
    }
    const updated = updateJournalTurn(store, {
      ownerId: input.ownerId,
      conversationId,
      turnId: assistantTurnId,
      status: "completed",
      content: finalText,
      producingRunId: existingAssistant.producingRunId ?? input.run.runId,
      producingAttemptId: existingAssistant.producingAttemptId ?? input.attempt.attemptId,
      nowMs: now,
    });
    changes.push(change(updated));
    return { materialized: true, changes };
  }

  const turns = [];
  if (!existingUser && !promptIsSynthetic && prompt) turns.push(userTurn(now));
  turns.push({
    turnId: assistantTurnId,
    role: "assistant" as const,
    surfaceKind,
    origin: "realtime_voice" as const,
    status: "completed" as const,
    content: finalText,
    contentBlocks: [],
    resources: [],
    producingRunId: input.run.runId,
    producingAttemptId: input.attempt.attemptId,
    metadataJson,
    createdAtMs: promptIsSynthetic || !prompt ? now : Math.min(now, Number.MAX_SAFE_INTEGER - 1) + 1,
  });
  const recorded = recordJournalExchange(store, {
    ownerId: input.ownerId,
    conversationId,
    turns,
  });
  for (const turn of recorded.createdTurns) changes.push(change(turn));
  return { materialized: true, changes };
}

function stableTurnId(continuityKey: string, role: "user" | "assistant"): string {
  return `turn_${createHash("sha256").update(`${continuityKey}\0${role}`).digest("hex").slice(0, 32)}`;
}

function optionalTurn(store: AgentStore, conversationId: string, turnId: string): ConversationTurn | null {
  const row = store.getOptionalRow(
    "SELECT * FROM conversation_turns WHERE conversation_id = ? AND turn_id = ?",
    [conversationId, turnId],
  );
  return row ? conversationTurnFromRow(row) : null;
}

function assertCanonicalIdentity(
  turn: ConversationTurn,
  conversationId: string,
  role: "user" | "assistant",
  continuityKey: string,
): void {
  const metadata = parseObject(turn.metadataJson);
  if (
    turn.conversationId !== conversationId
    || turn.role !== role
    || (metadata.continuityKey !== undefined && metadata.continuityKey !== continuityKey)
  ) {
    throw new Error("External surface journal stable identity collides with another canonical turn");
  }
}

function parseObject(value: unknown): Record<string, unknown> {
  if (typeof value === "string") {
    try {
      const parsed: unknown = JSON.parse(value);
      return objectValue(parsed) ?? {};
    } catch {
      return {};
    }
  }
  return objectValue(value) ?? {};
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}
