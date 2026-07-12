import { createHash } from "node:crypto";

import { recordJournalTurn, updateJournalTurn } from "./conversation-journal.js";
import { conversationTurnFromRow } from "./conversation-turns.js";
import type { AgentStore, ConversationContentBlock, ConversationResource, ConversationTurn } from "./types.js";

export interface AgentSpawnProducerJournalDescriptor {
  schemaVersion: 1;
  surface: {
    surfaceKind: string;
    externalRefKind: string;
    externalRefId: string;
  };
  continuityKey: string;
  pillId: string;
  userText: string;
  assistantText: string;
  objective: string;
  title: string;
}

export interface EnsureAgentSpawnJournalInput {
  ownerId: string;
  sessionId: string;
  runId: string;
  nowMs?: number;
}

export interface EnsureAgentSpawnJournalResult {
  ownerId: string;
  sessionId: string;
  runId: string;
  conversationId: string;
  descriptor: AgentSpawnProducerJournalDescriptor;
  userTurn: ConversationTurn;
  assistantTurn: ConversationTurn;
}

export interface AgentSpawnJournalReceipt {
  accepted: true;
  continuityKey: string;
  userTurnId: string;
  assistantTurnId: string;
  assistantText: string;
}

export function agentSpawnJournalReceipt(
  descriptor: AgentSpawnProducerJournalDescriptor,
): AgentSpawnJournalReceipt {
  return {
    accepted: true,
    continuityKey: descriptor.continuityKey,
    userTurnId: stableTurnId(descriptor.continuityKey, "user"),
    assistantTurnId: stableTurnId(descriptor.continuityKey, "assistant"),
    assistantText: descriptor.assistantText,
  };
}

export function attachAgentSpawnJournalReceipt(
  result: string,
  descriptor: AgentSpawnProducerJournalDescriptor,
): string {
  const parsed = JSON.parse(result) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Agent spawn tool result must be a JSON object before journal acknowledgement");
  }
  return JSON.stringify({
    ...(parsed as Record<string, unknown>),
    journalReceipt: agentSpawnJournalReceipt(descriptor),
  });
}

/**
 * Materialize the durable producer exchange for an already-accepted canonical
 * child. The descriptor is read only from the accepted run; callers cannot
 * redirect repair to the currently selected chat or supply replacement text.
 */
export function ensureAgentSpawnJournal(
  store: AgentStore,
  input: EnsureAgentSpawnJournalInput,
): EnsureAgentSpawnJournalResult {
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    const child = store.getRow(
      `SELECT r.input_json, r.session_id, r.status, r.final_text, r.error_message,
              s.owner_id, s.external_ref_id
       FROM runs r JOIN sessions s ON s.session_id = r.session_id
       WHERE r.run_id = ?`,
      [nonEmpty(input.runId, "runId")],
    );
    if (String(child.session_id) !== nonEmpty(input.sessionId, "sessionId")) {
      throw new Error("Agent spawn journal run does not belong to the supplied child session");
    }
    if (String(child.owner_id) !== nonEmpty(input.ownerId, "ownerId")) {
      throw new Error("Agent spawn journal child is outside owner scope");
    }
    const runInput = parseObject(String(child.input_json), "run input");
    const metadata = objectField(runInput, "metadata");
    const descriptor = parseAgentSpawnProducerJournalDescriptor(metadata.producerJournal);
    if (child.external_ref_id != null && String(child.external_ref_id) !== descriptor.pillId) {
      throw new Error("Agent spawn journal pill identity does not match the accepted child session");
    }
    const surface = store.getOptionalRow(
      `SELECT conversation_id FROM surface_conversations
       WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
      [
        input.ownerId,
        descriptor.surface.surfaceKind,
        descriptor.surface.externalRefKind,
        descriptor.surface.externalRefId,
      ],
    );
    if (!surface) {
      throw new Error("Agent spawn journal producer surface is not an exact owner-bound mapping");
    }
    const conversationId = String(surface.conversation_id);
    const delivery = ["task_chat", "workstream"].includes(descriptor.surface.surfaceKind)
      ? "local" as const
      : "backend" as const;
    const origin = ["realtime", "realtime_voice"].includes(descriptor.surface.surfaceKind)
      ? "realtime_voice" as const
      : "agent_runtime" as const;
    const metadataJson = JSON.stringify({ continuityKey: descriptor.continuityKey });
    const userTurnId = stableTurnId(descriptor.continuityKey, "user");
    const assistantTurnId = stableTurnId(descriptor.continuityKey, "assistant");
    const spawnBlock: ConversationContentBlock = {
      type: "agentSpawn",
      id: stableSpawnBlockId(descriptor.pillId),
      pillId: descriptor.pillId,
      sessionId: input.sessionId,
      runId: input.runId,
      title: descriptor.title,
      objective: descriptor.objective,
    };
    const terminal = ["succeeded", "failed", "cancelled", "timed_out", "orphaned"].includes(String(child.status));
    const completionBlock: ConversationContentBlock | null = terminal ? {
      type: "agentCompletion",
      id: stableCompletionBlockId(input.runId),
      pillId: descriptor.pillId,
      sessionId: input.sessionId,
      runId: input.runId,
      title: descriptor.title,
      promptSnippet: descriptor.objective,
      output: child.final_text == null
        ? child.error_message == null ? "" : String(child.error_message)
        : String(child.final_text),
      status: String(child.status) === "succeeded" ? "completed" : String(child.status),
    } : null;
    const artifactResources = terminal ? runArtifactResources(store, input.sessionId, input.runId) : [];

    let userTurn = recordJournalTurn(store, {
      ownerId: input.ownerId,
      conversationId,
      turnId: userTurnId,
      role: "user",
      surfaceKind: descriptor.surface.surfaceKind,
      origin,
      status: "completed",
      content: descriptor.userText,
      contentBlocks: [],
      resources: [],
      metadataJson,
      delivery,
      createdAtMs: now,
    }).turn;
    if (userTurn.status !== "completed") {
      userTurn = updateJournalTurn(store, {
        ownerId: input.ownerId,
        conversationId,
        turnId: userTurn.turnId,
        status: "completed",
        nowMs: now,
      });
    }

    const existingAssistant = optionalTurn(store, conversationId, assistantTurnId);
    let assistantTurn: ConversationTurn;
    if (!existingAssistant) {
      assistantTurn = recordJournalTurn(store, {
        ownerId: input.ownerId,
        conversationId,
        turnId: assistantTurnId,
        role: "assistant",
        surfaceKind: descriptor.surface.surfaceKind,
        origin,
        status: "completed",
        content: descriptor.assistantText,
        contentBlocks: completionBlock ? [spawnBlock, completionBlock] : [spawnBlock],
        resources: artifactResources,
        producingRunId: input.runId,
        metadataJson,
        delivery,
        createdAtMs: now,
      }).turn;
    } else {
      if (existingAssistant.role !== "assistant" || existingAssistant.content !== descriptor.assistantText) {
        throw new Error("Agent spawn journal assistant identity collides with different producer content");
      }
      if (existingAssistant.producingRunId !== null && existingAssistant.producingRunId !== input.runId) {
        throw new Error("Agent spawn journal assistant is already owned by a different run");
      }
      const blocks = existingAssistant.contentBlocks.filter((block) => {
        if (block.type === "agentSpawn") {
          return block.id !== spawnBlock.id
            && block.pillId !== descriptor.pillId
            && block.runId !== input.runId;
        }
        if (completionBlock && block.type === "agentCompletion") {
          return block.id !== completionBlock.id
            && block.pillId !== descriptor.pillId
            && block.runId !== input.runId;
        }
        return true;
      });
      blocks.push(spawnBlock);
      if (completionBlock) blocks.push(completionBlock);
      const resources = mergeResources(existingAssistant.resources, artifactResources);
      assistantTurn = updateJournalTurn(store, {
        ownerId: input.ownerId,
        conversationId,
        turnId: assistantTurnId,
        status: "completed",
        replaceContentBlocks: blocks,
        replaceResources: resources,
        producingRunId: input.runId,
        metadataJson,
        nowMs: now,
      });
    }
    return {
      ownerId: input.ownerId,
      sessionId: input.sessionId,
      runId: input.runId,
      conversationId,
      descriptor,
      userTurn,
      assistantTurn,
    };
  });
}

export function stableAgentSpawnTurnId(continuityKey: string, role: "user" | "assistant"): string {
  return stableTurnId(nonEmpty(continuityKey, "continuityKey"), role);
}

export function stableAgentSpawnBlockId(pillId: string): string {
  return stableSpawnBlockId(nonEmpty(pillId, "pillId"));
}

export function parseAgentSpawnProducerJournalDescriptor(value: unknown): AgentSpawnProducerJournalDescriptor {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Accepted child run is missing producerJournal metadata");
  }
  const raw = value as Record<string, unknown>;
  if (raw.schemaVersion !== 1) throw new Error("Unsupported producerJournal schemaVersion");
  const surface = objectField(raw, "surface");
  return {
    schemaVersion: 1,
    surface: {
      surfaceKind: boundedText(surface.surfaceKind, "producerJournal.surface.surfaceKind", 128),
      externalRefKind: boundedText(surface.externalRefKind, "producerJournal.surface.externalRefKind", 128),
      externalRefId: boundedText(surface.externalRefId, "producerJournal.surface.externalRefId", 512),
    },
    continuityKey: boundedText(raw.continuityKey, "producerJournal.continuityKey", 512),
    pillId: boundedText(raw.pillId, "producerJournal.pillId", 128),
    userText: boundedText(raw.userText, "producerJournal.userText", 64 * 1024),
    assistantText: boundedText(raw.assistantText, "producerJournal.assistantText", 64 * 1024),
    objective: boundedText(raw.objective, "producerJournal.objective", 64 * 1024),
    title: boundedText(raw.title, "producerJournal.title", 1_024),
  };
}

export function ensureAgentSpawnJournalIfPresent(
  store: AgentStore,
  input: EnsureAgentSpawnJournalInput,
): EnsureAgentSpawnJournalResult | null {
  const row = store.getOptionalRow("SELECT input_json FROM runs WHERE run_id = ?", [input.runId]);
  if (!row) return null;
  const runInput = parseObject(String(row.input_json), "run input");
  const metadata = runInput.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return null;
  const descriptor = (metadata as Record<string, unknown>).producerJournal;
  if (!descriptor || typeof descriptor !== "object" || Array.isArray(descriptor)) return null;
  return ensureAgentSpawnJournal(store, input);
}

export function repairPersistedAgentSpawnJournals(store: AgentStore): EnsureAgentSpawnJournalResult[] {
  const candidates = store.allRows(
    `SELECT r.run_id, r.session_id, s.owner_id
     FROM runs r JOIN sessions s ON s.session_id = r.session_id
     WHERE json_type(r.input_json, '$.metadata.producerJournal') = 'object'
     ORDER BY r.created_at_ms ASC, r.run_id ASC`,
  );
  const repaired: EnsureAgentSpawnJournalResult[] = [];
  for (const candidate of candidates) {
    try {
      repaired.push(ensureAgentSpawnJournal(store, {
        ownerId: String(candidate.owner_id),
        sessionId: String(candidate.session_id),
        runId: String(candidate.run_id),
      }));
    } catch {
      // Invalid/stale compatibility metadata must not prevent daemon startup.
      // New spawn paths validate before acceptance and tests cover repairable rows.
    }
  }
  return repaired;
}

function optionalTurn(store: AgentStore, conversationId: string, turnId: string): ConversationTurn | null {
  const row = store.getOptionalRow(
    "SELECT * FROM conversation_turns WHERE conversation_id = ? AND turn_id = ?",
    [conversationId, turnId],
  );
  return row ? conversationTurnFromRow(row) : null;
}

function stableTurnId(continuityKey: string, role: "user" | "assistant"): string {
  return `turn_${createHash("sha256").update(`${continuityKey}\0${role}`).digest("hex").slice(0, 32)}`;
}

function stableSpawnBlockId(pillId: string): string {
  return `agent_spawn_${createHash("sha256")
    .update(`agent_spawn\0${pillId.toLowerCase()}`)
    .digest("hex")
    .slice(0, 24)}`;
}

function stableCompletionBlockId(runId: string): string {
  return `agent_completion_${createHash("sha256")
    .update(`agent_completion\0${runId}`)
    .digest("hex")
    .slice(0, 24)}`;
}

function runArtifactResources(store: AgentStore, sessionId: string, runId: string): ConversationResource[] {
  return store.allRows(
    `SELECT artifact_id, display_name, kind, uri, mime_type, lifecycle_state
     FROM artifacts WHERE session_id = ? AND run_id = ?
     ORDER BY created_at_ms ASC, artifact_id ASC`,
    [sessionId, runId],
  ).map((row) => ({
    id: `artifact:${String(row.artifact_id)}`,
    origin: "generatedArtifact" as const,
    title: row.display_name == null ? String(row.kind) : String(row.display_name),
    state: String(row.lifecycle_state) as ConversationResource["state"],
    uri: String(row.uri),
    artifactId: String(row.artifact_id),
    sessionId,
    runId,
    ...(row.mime_type == null ? {} : { mimeType: String(row.mime_type) }),
  }));
}

function mergeResources(existing: ConversationResource[], additions: ConversationResource[]): ConversationResource[] {
  const result = [...existing];
  for (const resource of additions) {
    const index = result.findIndex((candidate) => candidate.id === resource.id);
    if (index >= 0) result[index] = resource;
    else result.push(resource);
  }
  return result;
}

function parseObject(json: string, label: string): Record<string, unknown> {
  try {
    const value = JSON.parse(json) as unknown;
    if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  } catch {
    // Fall through to the bounded contract error.
  }
  throw new Error(`Agent spawn journal ${label} is not an object`);
}

function objectField(input: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = input[key];
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Agent spawn journal ${key} is not an object`);
  }
  return value as Record<string, unknown>;
}

function boundedText(value: unknown, field: string, maxBytes: number): string {
  if (typeof value !== "string") throw new Error(`${field} must be a string`);
  const text = value.trim();
  if (!text || Buffer.byteLength(text, "utf8") > maxBytes) {
    throw new Error(`${field} must be non-empty and bounded`);
  }
  return text;
}

function nonEmpty(value: string, field: string): string {
  const text = value.trim();
  if (!text) throw new Error(`${field} must not be empty`);
  return text;
}
