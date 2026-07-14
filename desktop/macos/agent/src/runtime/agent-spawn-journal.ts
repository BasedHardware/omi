import { createHash } from "node:crypto";

import { recordJournalTurn, updateJournalTurn } from "./conversation-journal.js";
import { conversationTurnFromRow } from "./conversation-turns.js";
import {
  assertToolResultEnvelope,
  makeToolResultEnvelope,
  type ToolResultEnvelope,
} from "./tool-result-envelope.js";
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
  producerTurnId?: string;
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
  userTurn: ConversationTurn | null;
  assistantTurn: ConversationTurn;
}

export interface AgentSpawnJournalReceipt {
  accepted: true;
  continuityKey: string;
  userTurnId: string | null;
  assistantTurnId: string;
  /** Presentation acknowledgement; typed exact-turn callers retain their own assistant content. */
  assistantText: string;
}

/**
 * The realtime bridge must never send the provider the raw `spawn_agent`
 * result.  That result contains full run input, context, metadata, and often
 * large adapter details.  Instead, Node creates this one receipt before either
 * Swift's pill projection or the provider tool response observes the spawn.
 */
export interface RealtimeSpawnChildReceipt {
  sessionId: string;
  runId: string;
  attemptId: string;
  pillId?: string;
  title: string;
  objective: string;
  provider: string;
  lifecycle: {
    state: RealtimeSpawnLifecycleState;
    attemptState: RealtimeSpawnLifecycleState;
    revision: number;
    adapterId: string;
    updatedAtMs: number;
    error?: RealtimeSpawnCompactError;
  };
}

export interface RealtimeSpawnCompactError {
  code: string;
  message: string;
  retryable?: boolean;
}

export type RealtimeSpawnLifecycleState =
  | "queued"
  | "starting"
  | "running"
  | "waiting_input"
  | "waiting_approval"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "orphaned";

const REALTIME_SPAWN_SCHEMA_VERSION = 1;
const MAX_COMPACT_REALTIME_SPAWN_BYTES = 12 * 1024;
const MAX_COMPACT_PROVIDER_RESULT_BYTES = 4 * 1024;
const LIFECYCLE_STATES = new Set<RealtimeSpawnLifecycleState>([
  "queued",
  "starting",
  "running",
  "waiting_input",
  "waiting_approval",
  "cancelling",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
  "orphaned",
]);

export function agentSpawnJournalReceipt(
  descriptor: AgentSpawnProducerJournalDescriptor,
): AgentSpawnJournalReceipt {
  const presentation = canonicalSpawnJournalPresentation(descriptor);
  return {
    accepted: true,
    continuityKey: presentation.continuityKey,
    userTurnId: presentation.producerTurnId ? null : stableTurnId(presentation.continuityKey, "user"),
    assistantTurnId: presentation.producerTurnId
      ?? stableTurnId(presentation.continuityKey, "assistant"),
    assistantText: presentation.assistantText,
  };
}

/**
 * A realtime spawn receipt proves admission, not completion. Provider text is
 * untrusted presentation input, so it must never claim an outcome for a child
 * whose terminal lifecycle belongs to the kernel. Keep this transformation
 * deterministic: journal repair can replay the same accepted child after its
 * status has changed without colliding with the original assistant turn.
 */
function canonicalSpawnJournalPresentation(
  descriptor: AgentSpawnProducerJournalDescriptor,
): AgentSpawnProducerJournalDescriptor {
  if (
    !["realtime", "realtime_voice"].includes(descriptor.surface.surfaceKind)
      || descriptor.producerTurnId
  ) {
    return descriptor;
  }
  const title = compactDisplayText(descriptor.title, "Background agent", 160);
  return {
    ...descriptor,
    assistantText: `${title} started and is working in the background.`,
  };
}

/**
 * Produces the only realtime `spawn_agent` result allowed across the
 * Node/Swift/provider boundary. `ok: true` means that the journal receipt and
 * one concrete child session/run/attempt lifecycle were durably observed
 * together. A parent-journal acknowledgement on its own is not success.
 */
export function compactRealtimeSpawnToolResult(
  result: string,
  descriptor: AgentSpawnProducerJournalDescriptor,
): string {
  let parsed: Record<string, unknown>;
  try {
    parsed = jsonObject(JSON.parse(result));
  } catch {
    return compactRealtimeSpawnFailure(
      "realtime_spawn_result_invalid",
      "The background agent could not be started. Please try again.",
    );
  }
  const sourceEnvelope = canonicalRealtimeSpawnEnvelope(parsed);
  if (!sourceEnvelope) {
    return compactRealtimeSpawnFailure(
      "realtime_spawn_missing_tool_result_envelope",
      "The background agent result was incomplete. Please try again.",
      true,
    );
  }
  if (parsed.ok !== true) {
    const error = compactRawError(parsed.error, "spawn_failed", "The background agent could not be started.");
    return compactRealtimeSpawnFailure(error.code, error.message, error.retryable, sourceEnvelope);
  }

  let child: RealtimeSpawnChildReceipt;
  try {
    child = compactRealtimeSpawnChild(parsed);
  } catch {
    return compactRealtimeSpawnFailure(
      "realtime_spawn_child_receipt_missing",
      "The background agent could not be started. Please try again.",
      true,
      sourceEnvelope,
    );
  }

  const journalReceipt = compactJournalReceipt(agentSpawnJournalReceipt(descriptor));
  const semanticDigest = realtimeSpawnSemanticDigest(journalReceipt, child);
  const providerResult = compactProviderResult(child, semanticDigest, sourceEnvelope);
  const providerBytes = Buffer.byteLength(JSON.stringify(providerResult), "utf8");
  if (providerBytes > MAX_COMPACT_PROVIDER_RESULT_BYTES) {
    return compactRealtimeSpawnFailure(
      "realtime_spawn_provider_result_oversized",
      "The background agent could not be started. Please try again.",
      true,
      sourceEnvelope,
    );
  }

  const envelope = {
    schemaVersion: REALTIME_SPAWN_SCHEMA_VERSION,
    ok: true,
    journalReceipt,
    child,
    semanticDigest,
    providerResult,
    toolResultEnvelope: sourceEnvelope,
  };
  const encoded = JSON.stringify(envelope);
  if (Buffer.byteLength(encoded, "utf8") > MAX_COMPACT_REALTIME_SPAWN_BYTES) {
    return compactRealtimeSpawnFailure(
      "realtime_spawn_result_oversized",
      "The background agent could not be started. Please try again.",
      true,
      sourceEnvelope,
    );
  }
  return encoded;
}

function compactRealtimeSpawnChild(result: Record<string, unknown>): RealtimeSpawnChildReceipt {
  const agents = result.agents;
  if (!Array.isArray(agents) || agents.length === 0) {
    throw new Error("Accepted realtime spawn result has no child receipt");
  }
  const agent = jsonObject(agents[0]);
  const session = jsonObject(agent.session);
  const run = jsonObject(agent.run);
  const attempt = jsonObject(agent.attempt);
  const sessionId = compactIdentifier(session.sessionId, "child.sessionId");
  const runId = compactIdentifier(run.runId, "child.runId");
  const attemptId = compactIdentifier(attempt.attemptId, "child.attemptId");
  if (compactIdentifier(attempt.runId, "child.attempt.runId") !== runId) {
    throw new Error("Realtime spawn child attempt is not bound to its run");
  }
  if (compactIdentifier(run.sessionId, "child.run.sessionId") !== sessionId) {
    throw new Error("Realtime spawn child run is not bound to its session");
  }

  const state = compactLifecycleState(run.status, "child.run.status");
  const attemptState = compactLifecycleState(attempt.status, "child.attempt.status");
  const adapterId = compactIdentifier(attempt.adapterId, "child.attempt.adapterId");
  const updatedAtMs = Math.max(
    compactTimestamp(run.updatedAtMs, "child.run.updatedAtMs"),
    compactTimestamp(attempt.updatedAtMs, "child.attempt.updatedAtMs"),
  );
  const error = compactErrorFields(
    attempt.errorCode ?? run.errorCode,
    attempt.errorMessage ?? run.errorMessage,
  );
  const runInput = optionalJsonObject(run.input);
  const pillId = compactOptionalIdentifier(session.externalRefId, "child.pillId");
  return {
    sessionId,
    runId,
    attemptId,
    ...(pillId ? { pillId } : {}),
    title: compactDisplayText(session.title, "Background agent", 160),
    objective: compactDisplayText(runInput?.prompt, "Background agent", 384),
    provider: adapterId,
    lifecycle: {
      state,
      attemptState,
      revision: updatedAtMs,
      adapterId,
      updatedAtMs,
      ...(error ? { error } : {}),
    },
  };
}

function compactJournalReceipt(receipt: AgentSpawnJournalReceipt): AgentSpawnJournalReceipt {
  return {
    ...receipt,
    assistantText: compactDisplayText(receipt.assistantText, "A background agent was started.", 512),
  };
}

function compactProviderResult(
  child: RealtimeSpawnChildReceipt,
  semanticDigest: string,
  toolResultEnvelope: ToolResultEnvelope,
): Record<string, unknown> {
  const status = providerLifecycleStatus(child.lifecycle.state);
  const providerChild = {
    sessionId: child.sessionId,
    runId: child.runId,
    attemptId: child.attemptId,
    state: child.lifecycle.state,
    attemptState: child.lifecycle.attemptState,
    revision: child.lifecycle.revision,
    adapterId: child.lifecycle.adapterId,
    updatedAtMs: child.lifecycle.updatedAtMs,
    ...(child.lifecycle.error ? { error: child.lifecycle.error } : {}),
  };
  return {
    schemaVersion: REALTIME_SPAWN_SCHEMA_VERSION,
    ok: status.ok,
    code: status.code,
    message: status.message,
    child: providerChild,
    semanticDigest,
    toolResultEnvelope,
  };
}

function providerLifecycleStatus(state: RealtimeSpawnLifecycleState): {
  ok: boolean;
  code: string;
  message: string;
} {
  switch (state) {
    case "queued":
      return { ok: true, code: "spawn_queued", message: "The background agent is queued." };
    case "starting":
    case "running":
    case "waiting_input":
    case "waiting_approval":
    case "cancelling":
      return { ok: true, code: "spawn_started", message: "The background agent has started." };
    case "succeeded":
      return { ok: true, code: "spawn_completed", message: "The background agent has completed." };
    case "failed":
      return { ok: false, code: "spawn_child_failed", message: "The background agent failed after being admitted." };
    case "cancelled":
      return { ok: false, code: "spawn_child_cancelled", message: "The background agent was cancelled." };
    case "timed_out":
      return { ok: false, code: "spawn_child_timed_out", message: "The background agent timed out." };
    case "orphaned":
      return { ok: false, code: "spawn_child_orphaned", message: "The background agent is no longer available." };
  }
}

function compactRealtimeSpawnFailure(
  code: string,
  message: string,
  retryable?: boolean,
  sourceEnvelope?: ToolResultEnvelope,
): string {
  const error: RealtimeSpawnCompactError = {
    code: compactErrorCode(code, "realtime_spawn_failed"),
    message: compactDisplayText(message, "The background agent could not be started.", 512),
    ...(retryable === undefined ? {} : { retryable }),
  };
  const providerResult = {
    schemaVersion: REALTIME_SPAWN_SCHEMA_VERSION,
    ok: false,
    code: error.code,
    message: error.message,
    ...(retryable === undefined ? {} : { retryable }),
  };
  const toolResultEnvelope = sourceEnvelope ?? makeToolResultEnvelope({
    status: "failed",
    truncated: false,
    originalBytes: Buffer.byteLength(JSON.stringify(providerResult), "utf8"),
    projectedBytes: Buffer.byteLength(JSON.stringify(providerResult), "utf8"),
    fullOutputRef: null,
    provenance: {
      invocationId: `realtime:spawn:${error.code}`,
      runId: "unknown",
      attemptId: "unknown",
      toolName: "spawn_agent",
    },
  });
  return JSON.stringify({
    schemaVersion: REALTIME_SPAWN_SCHEMA_VERSION,
    ok: false,
    error,
    providerResult: { ...providerResult, toolResultEnvelope },
    toolResultEnvelope,
  });
}

/**
 * A realtime spawn projection may change presentation fields, never the
 * canonical tool-result recovery contract. Direct unit callers that predate
 * the envelope receive a bounded typed failure envelope instead of a bare
 * provider payload.
 */
function canonicalRealtimeSpawnEnvelope(result: Record<string, unknown>): ToolResultEnvelope | undefined {
  try {
    assertToolResultEnvelope(result.toolResultEnvelope);
    return result.toolResultEnvelope;
  } catch {
    return undefined;
  }
}

function compactRawError(value: unknown, fallbackCode: string, fallbackMessage: string): RealtimeSpawnCompactError {
  const error = optionalJsonObject(value);
  return {
    code: compactErrorCode(error?.code, fallbackCode),
    message: compactDisplayText(error?.message, fallbackMessage, 512),
    ...(typeof error?.retryable === "boolean" ? { retryable: error.retryable } : {}),
  };
}

function compactErrorFields(code: unknown, message: unknown): RealtimeSpawnCompactError | undefined {
  if (code == null && message == null) return undefined;
  return {
    code: compactErrorCode(code, "child_execution_failed"),
    message: compactDisplayText(message, "The background agent failed.", 512),
  };
}

function realtimeSpawnSemanticDigest(
  journalReceipt: AgentSpawnJournalReceipt,
  child: RealtimeSpawnChildReceipt,
): string {
  return createHash("sha256")
    .update(JSON.stringify({ journalReceipt, child }))
    .digest("hex")
    .slice(0, 32);
}

function compactLifecycleState(value: unknown, field: string): RealtimeSpawnLifecycleState {
  const state = compactIdentifier(value, field) as RealtimeSpawnLifecycleState;
  if (!LIFECYCLE_STATES.has(state)) throw new Error(`${field} is invalid`);
  return state;
}

function compactTimestamp(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${field} must be a non-negative timestamp`);
  }
  return value;
}

function compactIdentifier(value: unknown, field: string): string {
  if (typeof value !== "string") throw new Error(`${field} must be a string`);
  const text = value.trim();
  if (!text || Buffer.byteLength(text, "utf8") > 256) {
    throw new Error(`${field} must be non-empty and bounded`);
  }
  return text;
}

function compactOptionalIdentifier(value: unknown, field: string): string | undefined {
  if (value == null) return undefined;
  return compactIdentifier(value, field);
}

function compactErrorCode(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  const code = value.trim();
  return /^[a-z0-9_]{1,64}$/.test(code) ? code : fallback;
}

function compactDisplayText(value: unknown, fallback: string, maxBytes: number): string {
  const text = typeof value === "string" ? value.trim() : "";
  const candidate = text || fallback;
  if (Buffer.byteLength(candidate, "utf8") <= maxBytes) return candidate;
  const suffix = "…";
  const limit = Math.max(0, maxBytes - Buffer.byteLength(suffix, "utf8"));
  let bounded = "";
  for (const character of candidate) {
    if (Buffer.byteLength(bounded + character, "utf8") > limit) break;
    bounded += character;
  }
  return `${bounded}${suffix}`;
}

function jsonObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected a JSON object");
  }
  return value as Record<string, unknown>;
}

function optionalJsonObject(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
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
      `SELECT r.input_json, r.session_id, r.parent_run_id, r.status, r.final_text, r.error_message,
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
    const descriptor = canonicalSpawnJournalPresentation(
      parseAgentSpawnProducerJournalDescriptor(metadata.producerJournal),
    );
    if (child.external_ref_id != null && String(child.external_ref_id) !== descriptor.pillId) {
      throw new Error("Agent spawn journal pill identity does not match the accepted child session");
    }
    const surface = store.getOptionalRow(
      `SELECT conversation_id, agent_session_id FROM surface_conversations
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
    const origin = ["realtime", "realtime_voice"].includes(descriptor.surface.surfaceKind)
      ? "realtime_voice" as const
      : "agent_runtime" as const;
    const metadataJson = JSON.stringify({ continuityKey: descriptor.continuityKey });
    const userTurnId = stableTurnId(descriptor.continuityKey, "user");
    const assistantTurnId = stableTurnId(descriptor.continuityKey, "assistant");
    // Chat projections order equal timestamps by hashed turn ID, which can put
    // the assistant before its voice prompt. Reserve one safe millisecond so
    // the canonical producer pair remains user -> assistant after every replay.
    const userCreatedAtMs = Math.min(now, Number.MAX_SAFE_INTEGER - 1);
    const assistantCreatedAtMs = userCreatedAtMs + 1;
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

    if (descriptor.producerTurnId) {
      const assistantTurn = requireExactProducerTurn(store, {
        ownerId: input.ownerId,
        conversationId,
        producerSessionId: String(surface.agent_session_id),
        producerTurnId: descriptor.producerTurnId,
        parentRunId: child.parent_run_id == null ? null : String(child.parent_run_id),
      });
      const blocks = mergeSpawnBlocks(assistantTurn.contentBlocks, spawnBlock, completionBlock);
      const resources = mergeResources(assistantTurn.resources, artifactResources);
      const updatedAssistant = updateJournalTurn(store, {
        ownerId: input.ownerId,
        conversationId,
        turnId: assistantTurn.turnId,
        replaceContentBlocks: blocks,
        replaceResources: resources,
        nowMs: now,
      });
      return {
        ownerId: input.ownerId,
        sessionId: input.sessionId,
        runId: input.runId,
        conversationId,
        descriptor,
        userTurn: null,
        assistantTurn: updatedAssistant,
      };
    }

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
      createdAtMs: userCreatedAtMs,
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
        createdAtMs: assistantCreatedAtMs,
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
    ...(raw.producerTurnId === undefined
      ? {}
      : { producerTurnId: boundedText(raw.producerTurnId, "producerJournal.producerTurnId", 512) }),
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

function requireExactProducerTurn(
  store: AgentStore,
  input: {
    ownerId: string;
    conversationId: string;
    producerSessionId: string;
    producerTurnId: string;
    parentRunId: string | null;
  },
): ConversationTurn {
  if (!input.parentRunId) {
    throw new Error("Agent spawn producerTurnId requires a canonical parent run");
  }
  const parent = store.getOptionalRow(
    `SELECT r.input_json, r.session_id, s.owner_id
     FROM runs r JOIN sessions s ON s.session_id = r.session_id
     WHERE r.run_id = ?`,
    [input.parentRunId],
  );
  if (!parent || String(parent.owner_id) !== input.ownerId) {
    throw new Error("Agent spawn producer turn parent is outside owner scope");
  }
  if (String(parent.session_id) !== input.producerSessionId) {
    throw new Error("Agent spawn producer turn is outside the parent session conversation");
  }
  const parentInput = parseObject(String(parent.input_json), "parent run input");
  if (parentInput.producingTurnId !== input.producerTurnId) {
    throw new Error("Agent spawn producerTurnId does not match the parent query producing turn");
  }
  const turn = optionalTurn(store, input.conversationId, input.producerTurnId);
  if (!turn) throw new Error("Agent spawn producer turn is missing from the exact conversation");
  if (turn.role !== "assistant") {
    throw new Error("Agent spawn producer turn must be an assistant turn");
  }
  if (turn.producingRunId !== input.parentRunId || !turn.producingAttemptId) {
    throw new Error("Agent spawn producer turn is not bound to the parent query run");
  }
  const attempt = store.getOptionalRow(
    "SELECT run_id FROM run_attempts WHERE attempt_id = ?",
    [turn.producingAttemptId],
  );
  if (!attempt || String(attempt.run_id) !== input.parentRunId) {
    throw new Error("Agent spawn producer turn attempt is outside the parent query run");
  }
  const metadata = parseObject(turn.metadataJson, "producer turn metadata");
  if (Object.prototype.hasOwnProperty.call(metadata, "terminalMarker")) {
    throw new Error("Agent spawn producer turn rejects terminal-marker targets");
  }
  return turn;
}

function mergeSpawnBlocks(
  existing: ConversationContentBlock[],
  spawn: ConversationContentBlock,
  completion: ConversationContentBlock | null,
): ConversationContentBlock[] {
  const blocks = existing.filter((block) => {
    if (block.type === "agentSpawn" && spawn.type === "agentSpawn") {
      return block.id !== spawn.id && block.pillId !== spawn.pillId && block.runId !== spawn.runId;
    }
    if (completion && block.type === "agentCompletion" && completion.type === "agentCompletion") {
      return block.id !== completion.id
        && block.pillId !== completion.pillId
        && block.runId !== completion.runId;
    }
    return true;
  });
  blocks.push(spawn);
  if (completion) blocks.push(completion);
  return blocks;
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
