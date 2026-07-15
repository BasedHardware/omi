import { createHash, randomUUID } from "node:crypto";
import { conversationTurnFromRow } from "./conversation-turns.js";
import { generateAgentId } from "./sqlite-store.js";
import type {
  AgentStore,
  BackendTurnOutboxRecord,
  BackendTurnOutboxStatus,
  ConversationContentBlock,
  ConversationResource,
  ConversationTurn,
  ConversationTurnOrigin,
  ConversationTurnRole,
  ConversationTurnStatus,
} from "./types.js";

const TURN_COLUMNS = `
  conversation_id, turn_id, turn_seq, producer_id, payload_hash,
  role, surface_kind, content, created_at_ms, metadata_json,
  origin, status, content_blocks_json, resources_json, producing_run_id,
  producing_attempt_id, remote_id, updated_at_ms, completed_at_ms
`;

const OUTBOX_COLUMNS = `
  turn_id, conversation_id, owner_id, status, attempt_count, available_at_ms,
  lease_expires_at_ms, remote_id, last_error_code, payload_hash,
  delivery_generation, conversation_generation, created_at_ms, updated_at_ms,
  delivered_at_ms
`;
const DELETE_OUTBOX_COLUMNS = `
  operation_id, conversation_id, owner_id, target_kind, target_id,
  conversation_generation, status, attempt_count, delivery_generation,
  payload_hash, available_at_ms, lease_expires_at_ms, last_error_code,
  created_at_ms, updated_at_ms, delivered_at_ms
`;

const LOCAL_ONLY_SURFACES = new Set(["task_chat", "workstream"]);
const DEFAULT_OUTBOX_LEASE_MS = 30_000;
const MAX_DRAIN_BATCH = 100;
const BACKEND_RECONCILE_PAGE_LIMIT = 100;
const MAX_BACKEND_RECONCILE_CURSOR_BYTES = 512;
const MAX_JOURNAL_REVISION = 2_147_483_647;

export type JournalDeliveryDestination = "backend" | "local";

export interface RecordJournalTurnInput {
  ownerId: string;
  conversationId: string;
  turnId?: string;
  producerId?: string;
  role: ConversationTurnRole;
  surfaceKind: string;
  origin: ConversationTurnOrigin;
  status?: ConversationTurnStatus;
  content: string;
  contentBlocks: readonly ConversationContentBlock[];
  resources?: readonly ConversationResource[];
  producingRunId?: string | null;
  producingAttemptId?: string | null;
  metadataJson?: string;
  createdAtMs?: number;
}

export interface RecordJournalTurnResult {
  turn: ConversationTurn;
  created: boolean;
  duplicate: boolean;
  outboxStatus: BackendTurnOutboxStatus | null;
}

export interface RecordJournalExchangeInput {
  ownerId: string;
  conversationId: string;
  turns: readonly Omit<RecordJournalTurnInput, "ownerId" | "conversationId">[];
}

export interface RecordJournalExchangeResult {
  turns: ConversationTurn[];
  createdTurns: ConversationTurn[];
}

export interface UpdateJournalTurnInput {
  ownerId: string;
  conversationId: string;
  turnId: string;
  status?: ConversationTurnStatus;
  content?: string;
  replaceContentBlocks?: readonly ConversationContentBlock[];
  appendContentBlocks?: readonly ConversationContentBlock[];
  replaceResources?: readonly ConversationResource[];
  appendResources?: readonly ConversationResource[];
  producingRunId?: string | null;
  producingAttemptId?: string | null;
  metadataJson?: string;
  nowMs?: number;
}

/**
 * Kernel-only admission for server-validated chat-first blocks. The caller has
 * already checked the live run capability; this helper binds that exact
 * main-Chat run/attempt to its one streaming assistant placeholder and appends
 * the canonical blocks in the same SQLite transaction.
 */
export interface AppendChatFirstBlocksInput {
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  blocks: readonly ConversationContentBlock[];
}

export interface TerminalizeJournalTurnInput {
  ownerId: string;
  conversationId: string;
  turnId: string;
  producingRunId: string;
  producingAttemptId: string;
  disposition: "accept" | "discard";
  content?: string;
  replaceContentBlocks?: readonly ConversationContentBlock[];
  replaceResources?: readonly ConversationResource[];
  nowMs?: number;
}

export interface ProducingJournalTurnAdmissionInput {
  ownerId: string;
  conversationId: string;
  sessionId: string;
  turnId: string;
}

export interface BindProducingJournalTurnInput extends ProducingJournalTurnAdmissionInput {
  runId: string;
  attemptId: string;
  nowMs?: number;
}

export interface DiscardProducingJournalTurnInput {
  ownerId: string;
  runId: string;
  attemptId: string;
  nowMs?: number;
}

export interface ImportRemoteJournalTurnInput {
  ownerId: string;
  conversationId: string;
  remoteId: string;
  canonicalTurnId?: string | null;
  role: ConversationTurnRole;
  surfaceKind: string;
  content: string;
  contentBlocks: readonly ConversationContentBlock[];
  resources?: readonly ConversationResource[];
  metadataJson?: string;
  createdAtMs: number;
  nowMs?: number;
  source: "backend_reconcile" | "legacy_upgrade";
}

export interface ImportRemoteJournalTurnResult {
  turn: ConversationTurn;
  imported: boolean;
  reconciledLocal: boolean;
}

export interface BackendTurnDelivery extends BackendTurnOutboxRecord {
  /** Existing backend POST idempotency field. Always identical to turn.turnId. */
  clientMessageId: string;
  turn: ConversationTurn;
  payload: BackendTurnPayload;
}

export type BackendTurnResultDisposition = "active" | "superseded" | "duplicate";

export interface BackendTurnPayload {
  turnId: string;
  clientMessageId: string;
  journalRevision: number;
  text: string;
  sender: "human" | "ai";
  appId: string | null;
  sessionId: string | null;
  metadata: string | null;
  messageSource: "desktop_chat" | "realtime_voice";
}

export interface BackendConversationDeleteDelivery {
  operationId: string;
  conversationId: string;
  ownerId: string;
  targetKind: "messages" | "chat_session";
  targetId: string | null;
  conversationGeneration: number;
  status: BackendTurnOutboxStatus;
  attemptCount: number;
  deliveryGeneration: number;
  payloadHash: string;
  availableAtMs: number;
  leaseExpiresAtMs: number | null;
  lastErrorCode: string | null;
  createdAtMs: number;
  updatedAtMs: number;
  deliveredAtMs: number | null;
}

export interface BackendReconcileRequest {
  reconcileId: string;
  ownerId: string;
  conversationId: string;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  targetKind: "messages" | "chat_session";
  targetId: string | null;
  frontierRemoteId: string | null;
  pageCursor: string | null;
  pageLimit: number;
}

export interface BackendReconcileRemoteTurn {
  remoteId: string;
  canonicalTurnId?: string | null;
  role: "user" | "assistant";
  content: string;
  contentBlocks: readonly ConversationContentBlock[];
  resources?: readonly ConversationResource[];
  metadataJson?: string;
  createdAtMs: number;
}

export interface BackendReconcilePageResult {
  importedTurns: ConversationTurn[];
  nextRequest: BackendReconcileRequest | null;
  completed: boolean;
}

export interface JournalTurnRange {
  conversationId: string;
  generation: number;
  generationBaseTurnSeq: number;
  highWaterTurnSeq: number;
  turns: ConversationTurn[];
}

export interface JournalTurnChangedWake {
  ownerId: string;
  conversationGeneration: number;
  generationBaseTurnSeq: number;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turn: ConversationTurn;
}

/**
 * Present a conversation-owned turn through the exact surface binding that
 * requested or observed it. Shared chat surfaces intentionally converge on one
 * conversation, while Swift routes projection events by the turn surface.
 */
export function journalTurnForSurfaceProjection(
  turn: ConversationTurn,
  surfaceKind: string,
): ConversationTurn {
  return { ...turn, surfaceKind: nonEmpty(surfaceKind, "surfaceKind") };
}

export interface MigrateJournalConversationInput {
  ownerId: string;
  sourceConversationId: string;
  destinationConversationId: string;
  nowMs?: number;
}

export interface MigrateJournalConversationResult {
  movedTurnCount: number;
  movedRevisionCount: number;
  movedOutboxCount: number;
  destinationGeneration: number;
  destinationHighWaterTurnSeq: number;
}

export interface BackendTurnAckInput {
  ownerId: string;
  turnId: string;
  remoteId: string;
  deliveryGeneration: number;
  attemptCount: number;
  conversationGeneration: number;
  payloadHash: string;
  nowMs?: number;
}

export interface JournalObservabilitySnapshot {
  turnStatusCounts: Partial<Record<ConversationTurnStatus, number>>;
  deliveryStatusCounts: Partial<Record<BackendTurnOutboxStatus, number>>;
  oldestPendingDeliveryCreatedAtMs: number | null;
}

/**
 * The only durable local insertion API for chat-visible turns. The turn and
 * optional backend projection are committed in the same SQLite transaction.
 */
export function recordJournalTurn(
  store: AgentStore,
  input: RecordJournalTurnInput,
): RecordJournalTurnResult {
  const now = input.createdAtMs ?? Date.now();
  const turnId = nonEmpty(input.turnId ?? generateAgentId("turn"), "turnId");
  const contentBlocks = validateContentBlocks(input.contentBlocks);
  const resources = validateResources(input.resources ?? []);
  const metadataJson = validObjectJson(input.metadataJson ?? "{}", "metadataJson");
  const producerId = nonEmpty(input.producerId ?? `turn:${turnId}`, "producerId");

  return store.withTransaction(() => {
    assertConversationOwner(store, input.conversationId, input.ownerId);
    const canonicalDelivery = canonicalJournalDelivery(store, input.ownerId, input.conversationId);
    assertCanonicalJournalDelivery(input.surfaceKind, canonicalDelivery);
    assertProducingRunOwner(store, input.producingRunId ?? null, input.ownerId);

    const existingByTurnId = findJournalTurnById(store, turnId);
    const existingByProducer = findJournalTurnByProducer(store, input.conversationId, producerId);
    if (
      existingByTurnId
      && existingByProducer
      && existingByTurnId.turnId !== existingByProducer.turnId
    ) {
      throw new Error("Canonical turn ID and producer ID resolve to different journal turns");
    }
    const existing = existingByTurnId ?? existingByProducer;
    if (existing) {
      const normalizedInput = {
        ...input,
        turnId: existing.turnId,
        contentBlocks,
        resources,
        metadataJson,
        producerId,
      };
      assertIdempotentRecord(existing, normalizedInput);
      const outboxStatus = ensureDeliveryState(store, {
        ownerId: input.ownerId,
        conversationId: input.conversationId,
        turnId: existing.turnId,
        delivery: canonicalDelivery,
        nowMs: now,
      });
      return { turn: existing, created: false, duplicate: true, outboxStatus };
    }

    const sequence = nextJournalSequence(store, input.conversationId, now);
    const payloadHash = journalTurnPayloadHash({
      turnId,
      role: input.role,
      surfaceKind: input.surfaceKind,
      content: input.content,
      origin: input.origin,
      status: input.status ?? "pending",
      contentBlocks,
      resources,
      producingRunId: input.producingRunId ?? null,
      producingAttemptId: input.producingAttemptId ?? null,
      remoteId: null,
      metadataJson,
    });
    const turn = store.insertConversationTurn({
      conversationId: input.conversationId,
      turnId,
      turnSeq: sequence.turnSeq,
      producerId,
      payloadHash,
      role: input.role,
      surfaceKind: nonEmpty(input.surfaceKind, "surfaceKind"),
      content: input.content,
      origin: input.origin,
      status: input.status ?? "pending",
      contentBlocks,
      resources,
      producingRunId: input.producingRunId ?? null,
      producingAttemptId: input.producingAttemptId ?? null,
      createdAtMs: now,
      updatedAtMs: now,
      completedAtMs: terminalTurnStatus(input.status ?? "pending") ? now : null,
      metadataJson,
    });
    appendJournalRevision(store, turn, sequence.generation, "recorded", now);
    const outboxStatus = ensureDeliveryState(store, {
      ownerId: input.ownerId,
      conversationId: input.conversationId,
      turnId,
      delivery: canonicalDelivery,
      nowMs: now,
    });
    return { turn, created: true, duplicate: false, outboxStatus };
  });
}

/**
 * Records the visible halves of one logical exchange under one commit. A
 * failure or identity collision on either half rolls back every row, revision,
 * and outbox mutation created by the other half.
 */
export function recordJournalExchange(
  store: AgentStore,
  input: RecordJournalExchangeInput,
): RecordJournalExchangeResult {
  if (input.turns.length > 2) {
    throw new Error("Journal exchange may contain at most two turns");
  }
  const roles = input.turns.map((turn) => turn.role);
  if (new Set(roles).size !== roles.length) {
    throw new Error("Journal exchange may contain at most one turn per role");
  }
  if (roles.length === 2 && (roles[0] !== "user" || roles[1] !== "assistant")) {
    throw new Error("Journal exchange turns must be ordered user then assistant");
  }

  return store.withTransaction(() => {
    assertConversationOwner(store, input.conversationId, input.ownerId);
    const canonicalDelivery = canonicalJournalDelivery(store, input.ownerId, input.conversationId);
    for (const turn of input.turns) {
      assertCanonicalJournalDelivery(turn.surfaceKind, canonicalDelivery);
    }
    const exchangeBaseCreatedAtMs = input.turns[0]?.createdAtMs ?? Date.now();
    const normalizedTurns = input.turns.map((turn, index) => ({
      ...turn,
      // Creation time is the immutable conversation-order key. Preserve an
      // imported timestamp when possible, but make the assistant half strictly
      // later than its user half even when a coarse backend clock ties them.
      createdAtMs: index === 0
        ? exchangeBaseCreatedAtMs
        : Math.max(turn.createdAtMs ?? exchangeBaseCreatedAtMs + index, exchangeBaseCreatedAtMs + index),
    }));
    const results = normalizedTurns.map((turn) => recordJournalTurn(store, {
      ...turn,
      ownerId: input.ownerId,
      conversationId: input.conversationId,
    }));
    return {
      turns: results.map((result) => result.turn),
      createdTurns: results.filter((result) => result.created).map((result) => result.turn),
    };
  });
}

/** Update or complete the producing turn; block/resource IDs are idempotent. */
export function updateJournalTurn(store: AgentStore, input: UpdateJournalTurnInput): ConversationTurn {
  if (
    input.status === undefined
    && input.content === undefined
    && input.replaceContentBlocks === undefined
    && input.appendContentBlocks === undefined
    && input.replaceResources === undefined
    && input.appendResources === undefined
    && input.producingRunId === undefined
    && input.producingAttemptId === undefined
    && input.metadataJson === undefined
  ) {
    throw new Error("Journal turn update has no changes");
  }
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    assertConversationOwner(store, input.conversationId, input.ownerId);
    const current = requireJournalTurn(store, input.conversationId, input.turnId);
    if (input.status !== undefined) assertTurnStatusTransition(current.status, input.status);
    if (input.producingRunId !== undefined) {
      assertProducingRunOwner(store, input.producingRunId, input.ownerId);
      if (current.producingRunId !== null && current.producingRunId !== input.producingRunId) {
        throw new Error("A journal turn cannot change its producing run");
      }
    }
    if (input.producingAttemptId !== undefined) {
      if (input.producingAttemptId === null) {
        throw new Error("A journal turn producing attempt cannot be cleared");
      }
      if (current.producingAttemptId !== null && current.producingAttemptId !== input.producingAttemptId) {
        const attemptAdvance = store.getOptionalRow(
          `SELECT prior.run_id AS prior_run_id, prior.attempt_no AS prior_attempt_no,
                  next.run_id AS next_run_id, next.attempt_no AS next_attempt_no
           FROM run_attempts prior, run_attempts next
           WHERE prior.attempt_id = ? AND next.attempt_id = ?`,
          [current.producingAttemptId, input.producingAttemptId],
        );
        const targetRunId = input.producingRunId ?? current.producingRunId;
        if (
          !attemptAdvance
          || String(attemptAdvance.prior_run_id) !== targetRunId
          || String(attemptAdvance.next_run_id) !== targetRunId
          || Number(attemptAdvance.next_attempt_no) <= Number(attemptAdvance.prior_attempt_no)
          || terminalTurnStatus(current.status)
        ) {
          throw new Error("A journal turn cannot change its producing attempt");
        }
      }
    }

    const contentBlocks = input.replaceContentBlocks === undefined
      ? mergeById(current.contentBlocks, validateContentBlocks(input.appendContentBlocks ?? []))
      : mergeById([], validateContentBlocks(input.replaceContentBlocks));
    const resources = input.replaceResources === undefined
      ? mergeById(current.resources, validateResources(input.appendResources ?? []))
      : mergeById([], validateResources(input.replaceResources));
    const status = input.status ?? current.status;
    const metadataJson = input.metadataJson === undefined
      ? current.metadataJson
      : validObjectJson(input.metadataJson, "metadataJson");
    const content = input.content ?? current.content;
    const producingRunId = input.producingRunId === undefined ? current.producingRunId : input.producingRunId;
    const producingAttemptId = input.producingAttemptId === undefined
      ? current.producingAttemptId
      : input.producingAttemptId;
    const changed = status !== current.status
      || content !== current.content
      || stableJson(contentBlocks) !== stableJson(current.contentBlocks)
      || stableJson(resources) !== stableJson(current.resources)
      || producingRunId !== current.producingRunId
      || producingAttemptId !== current.producingAttemptId
      || stableJson(parseObjectJson(metadataJson)) !== stableJson(parseObjectJson(current.metadataJson));
    if (!changed) return current;

    const sequence = nextJournalSequence(store, input.conversationId, now);
    const payloadHash = journalTurnPayloadHash({
      turnId: current.turnId,
      role: current.role,
      surfaceKind: current.surfaceKind,
      content,
      origin: current.origin,
      status,
      contentBlocks,
      resources,
      producingRunId,
      producingAttemptId,
      remoteId: current.remoteId,
      metadataJson,
    });

    store.execute(
      `UPDATE conversation_turns
       SET content = ?, status = ?, content_blocks_json = ?, resources_json = ?,
           producing_run_id = ?, producing_attempt_id = ?, metadata_json = ?,
           turn_seq = ?, payload_hash = ?, updated_at_ms = ?,
           completed_at_ms = CASE
             WHEN ? IN ('completed', 'failed') THEN COALESCE(completed_at_ms, ?)
             ELSE NULL
           END
       WHERE conversation_id = ? AND turn_id = ?`,
      [
        content,
        status,
        JSON.stringify(contentBlocks),
        JSON.stringify(resources),
        producingRunId,
        producingAttemptId,
        metadataJson,
        sequence.turnSeq,
        payloadHash,
        now,
        status,
        now,
        input.conversationId,
        input.turnId,
      ],
    );

    const updated = requireJournalTurn(store, input.conversationId, input.turnId);
    appendJournalRevision(store, updated, sequence.generation, "updated", now);
    const backendHash = backendTurnPayloadHash(backendTurnPayload(updated));
    const tombstoneCode = backendTombstoneCode(updated);
    store.execute(
      `UPDATE backend_turn_outbox
       SET payload_hash = ?,
           status = CASE WHEN ? IS NOT NULL THEN 'failed' ELSE 'pending' END,
           attempt_count = 0,
           available_at_ms = ?,
           lease_expires_at_ms = NULL,
           last_error_code = ?,
           updated_at_ms = ?
       WHERE turn_id = ? AND payload_hash != ?`,
      [backendHash, tombstoneCode, now, tombstoneCode, now, input.turnId, backendHash],
    );
    return updated;
  });
}

export function appendChatFirstBlocksToProducingTurn(
  store: AgentStore,
  input: AppendChatFirstBlocksInput,
): ConversationTurn {
  if (input.blocks.length < 1 || input.blocks.length > 8) {
    throw new Error("Chat-first append requires one to eight blocks");
  }
  return store.withTransaction(() => {
    const activeAttempt = store.getOptionalRow(
      `SELECT 1
       FROM run_attempts a
       JOIN runs r ON r.run_id = a.run_id
       JOIN sessions s ON s.session_id = r.session_id
       WHERE a.attempt_id = ?
         AND a.run_id = ?
         AND s.owner_id = ?
         AND s.session_id = ?
         AND r.status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval')
         AND a.status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval')
         AND a.attempt_no = (
           SELECT MAX(latest.attempt_no) FROM run_attempts latest WHERE latest.run_id = r.run_id
         )`,
      [input.attemptId, input.runId, input.ownerId, input.sessionId],
    );
    if (!activeAttempt) {
      throw new Error("Chat-first append requires the current owner-bound run attempt");
    }
    const bound = store.allRows(
      `SELECT conversation_id, turn_id
       FROM conversation_turns
       WHERE producing_run_id = ?
         AND producing_attempt_id = ?
         AND role = 'assistant'
         AND surface_kind = 'main_chat'
         AND status = 'streaming'`,
      [input.runId, input.attemptId],
    );
    if (bound.length > 1) {
      throw new Error("Chat-first append found multiple producing assistant journal turns");
    }
    const producing = bound[0] ?? (() => {
      // The placeholder is journaled before the runtime supplies a run/attempt.
      // Pin it only when the current owner/session has exactly one live main
      // Chat assistant target; user text and display order are never selectors.
      const pending = store.allRows(
        `SELECT DISTINCT ct.conversation_id, ct.turn_id
         FROM surface_conversations sc
         JOIN conversation_turns ct ON ct.conversation_id = sc.conversation_id
         WHERE sc.owner_id = ?
           AND sc.agent_session_id = ?
           AND sc.surface_kind = 'main_chat'
           AND ct.role = 'assistant'
           AND ct.surface_kind = 'main_chat'
           AND ct.status = 'streaming'
           AND ct.producing_run_id IS NULL
           AND ct.producing_attempt_id IS NULL`,
        [input.ownerId, input.sessionId],
      );
      if (pending.length !== 1) {
        throw new Error("Chat-first append requires exactly one live producing assistant journal turn");
      }
      return pending[0]!;
    })();
    return updateJournalTurn(store, {
      ownerId: input.ownerId,
      conversationId: String(producing.conversation_id),
      turnId: String(producing.turn_id),
      producingRunId: input.runId,
      producingAttemptId: input.attemptId,
      appendContentBlocks: input.blocks,
    });
  });
}

export function validateProducingJournalTurnAdmission(
  store: AgentStore,
  input: ProducingJournalTurnAdmissionInput,
): void {
  assertProducingJournalTurnMapping(store, input);
  const turn = requireJournalTurn(store, input.conversationId, nonEmpty(input.turnId, "producingTurnId"));
  if (turn.role !== "assistant" || !["pending", "streaming"].includes(turn.status)) {
    throw new Error("Producing turn admission requires a pending or streaming assistant turn");
  }
  if (turn.producingRunId !== null || turn.producingAttemptId !== null) {
    throw new Error("Producing turn is already bound to a canonical run attempt");
  }
}

export function bindProducingJournalTurn(
  store: AgentStore,
  input: BindProducingJournalTurnInput,
): ConversationTurn {
  return store.withTransaction(() => {
    assertProducingJournalTurnMapping(store, input);
    const authority = store.getOptionalRow(
      `SELECT r.session_id, s.owner_id, a.attempt_no,
              (SELECT latest.attempt_id FROM run_attempts latest
               WHERE latest.run_id = r.run_id ORDER BY latest.attempt_no DESC LIMIT 1) AS latest_attempt_id
       FROM runs r
       JOIN sessions s ON s.session_id = r.session_id
       JOIN run_attempts a ON a.run_id = r.run_id AND a.attempt_id = ?
       WHERE r.run_id = ?`,
      [input.attemptId, input.runId],
    );
    if (
      !authority
      || String(authority.owner_id) !== input.ownerId
      || String(authority.session_id) !== input.sessionId
      || String(authority.latest_attempt_id) !== input.attemptId
    ) {
      throw new Error("Producing turn admission run attempt is not the latest canonical session authority");
    }
    const turn = requireJournalTurn(store, input.conversationId, nonEmpty(input.turnId, "producingTurnId"));
    if (turn.role !== "assistant" || !["pending", "streaming"].includes(turn.status)) {
      throw new Error("Producing turn admission requires a pending or streaming assistant turn");
    }
    if (turn.producingRunId !== null && turn.producingRunId !== input.runId) {
      throw new Error("Producing turn is already bound to a different canonical run");
    }
    return updateJournalTurn(store, {
      ownerId: input.ownerId,
      conversationId: input.conversationId,
      turnId: turn.turnId,
      producingRunId: input.runId,
      producingAttemptId: input.attemptId,
      nowMs: input.nowMs,
    });
  });
}

export function assertPublicJournalUpdatePolicy(
  store: AgentStore,
  input: UpdateJournalTurnInput,
): void {
  assertConversationOwner(store, input.conversationId, input.ownerId);
  const current = requireJournalTurn(store, input.conversationId, input.turnId);
  const linkedTerminal = current.producingRunId !== null
    && current.producingAttemptId !== null
    && terminalTurnStatus(current.status);
  if (!linkedTerminal) return;
  const metadata = parseObjectJson(current.metadataJson) as Record<string, unknown>;
  const discarded = metadata.terminalMarker === "discarded_terminal_projection"
    || store.getOptionalRow(
      `SELECT 1 FROM backend_turn_outbox
       WHERE turn_id = ? AND last_error_code = 'discarded_terminal_projection'`,
      [current.turnId],
    ) !== undefined;
  if (discarded) {
    throw new Error("Discarded terminal journal projection rejects every public update");
  }
  const appendBlocks = input.appendContentBlocks ?? [];
  const appendResources = input.appendResources ?? [];
  const hasAppend = appendBlocks.length > 0 || appendResources.length > 0;
  const hasForbiddenMutation = input.status !== undefined
    || input.content !== undefined
    || input.replaceContentBlocks !== undefined
    || input.replaceResources !== undefined
    || input.producingRunId !== undefined
    || input.producingAttemptId !== undefined
    || input.metadataJson !== undefined;
  if (current.status !== "completed" || hasForbiddenMutation || !hasAppend) {
    throw new Error("Linked terminal journal turns allow only typed completion/resource appends");
  }
  const completions = validateContentBlocks(appendBlocks);
  if (completions.some((block) => block.type !== "agentCompletion")) {
    throw new Error("Linked terminal journal turns accept only agentCompletion blocks");
  }
  const spawnBlocks = current.contentBlocks.filter(
    (block): block is Extract<ConversationContentBlock, { type: "agentSpawn" }> => block.type === "agentSpawn",
  );
  for (const completion of completions as Extract<ConversationContentBlock, { type: "agentCompletion" }>[]) {
    if (!completion.runId || !completion.sessionId) {
      throw new Error("Agent completion append requires canonical session and run identity");
    }
    if (!spawnBlocks.some((spawn) => (
      spawn.runId === completion.runId
      && spawn.sessionId === completion.sessionId
      && (!spawn.pillId || !completion.pillId || spawn.pillId === completion.pillId)
    ))) {
      throw new Error("Agent completion append must match an existing canonical agentSpawn block");
    }
  }
  const allowedRunIds = new Set<string>([
    current.producingRunId!,
    ...spawnBlocks.map((block) => block.runId),
  ]);
  for (const completion of completions) {
    if (completion.type === "agentCompletion" && completion.runId) allowedRunIds.add(completion.runId);
  }
  for (const resource of validateResources(appendResources)) {
    if (resource.runId && !allowedRunIds.has(resource.runId)) {
      throw new Error("Terminal resource append is outside the canonical producing/spawn run graph");
    }
  }
}

export function discardProducingJournalTurnForRunAttempt(
  store: AgentStore,
  input: DiscardProducingJournalTurnInput,
): ConversationTurn | null {
  return store.withTransaction(() => {
    const rows = store.allRows(
      `SELECT conversation_id, turn_id
       FROM conversation_turns
       WHERE producing_run_id = ? AND producing_attempt_id = ?
       ORDER BY conversation_id, turn_id`,
      [input.runId, input.attemptId],
    );
    if (rows.length === 0) return null;
    if (rows.length !== 1) throw new Error("Canonical run attempt is bound to multiple producing turns");
    return terminalizeJournalTurn(store, {
      ownerId: input.ownerId,
      conversationId: String(rows[0]!.conversation_id),
      turnId: String(rows[0]!.turn_id),
      producingRunId: input.runId,
      producingAttemptId: input.attemptId,
      disposition: "discard",
      nowMs: input.nowMs,
    });
  });
}

/**
 * Authenticated terminal mutation for runtime-produced turns. Callers provide
 * the exact canonical run/attempt proof and final material, while the kernel
 * alone derives success or failure from durable run state.
 */
export function terminalizeJournalTurn(
  store: AgentStore,
  input: TerminalizeJournalTurnInput,
): ConversationTurn {
  const now = input.nowMs ?? Date.now();
  const producingRunId = nonEmpty(input.producingRunId, "producingRunId");
  const producingAttemptId = nonEmpty(input.producingAttemptId, "producingAttemptId");
  const contentBlocks = input.replaceContentBlocks === undefined
    ? undefined
    : validateContentBlocks(input.replaceContentBlocks);
  const resources = input.replaceResources === undefined
    ? undefined
    : validateResources(input.replaceResources);
  return store.withTransaction(() => {
    if (
      input.disposition === "discard"
      && (input.content !== undefined || contentBlocks !== undefined || resources !== undefined)
    ) {
      throw new Error("Discarded journal terminalization cannot apply late material");
    }
    assertConversationOwner(store, input.conversationId, input.ownerId);
    const authority = store.getOptionalRow(
      `SELECT r.status AS run_status, r.session_id, a.status AS attempt_status,
              (SELECT latest.attempt_id
               FROM run_attempts latest
               WHERE latest.run_id = r.run_id
               ORDER BY latest.attempt_no DESC
               LIMIT 1) AS latest_attempt_id
       FROM runs r
       JOIN sessions s ON s.session_id = r.session_id
       JOIN run_attempts a ON a.run_id = r.run_id AND a.attempt_id = ?
       WHERE r.run_id = ? AND s.owner_id = ?`,
      [producingAttemptId, producingRunId, input.ownerId],
    );
    if (!authority) throw new Error("Journal terminalization run or attempt is unknown or outside owner scope");
    if (String(authority.latest_attempt_id) !== producingAttemptId) {
      throw new Error("Journal terminalization requires the latest canonical run attempt");
    }
    if (!store.getOptionalRow(
      `SELECT 1 FROM surface_conversations
       WHERE conversation_id = ? AND owner_id = ? AND agent_session_id = ?
       LIMIT 1`,
      [input.conversationId, input.ownerId, String(authority.session_id)],
    )) {
      throw new Error("Journal terminalization run is not bound to the canonical conversation session");
    }
    const status = input.disposition === "discard"
      ? "failed"
      : journalTerminalStatus(authority.run_status, authority.attempt_status);
    const current = requireJournalTurn(store, input.conversationId, input.turnId);
    if (current.producingRunId !== producingRunId) {
      throw new Error("Journal terminalization run does not match the producing turn");
    }
    if (current.producingAttemptId !== producingAttemptId) {
      throw new Error("Journal terminalization attempt does not match the producing turn");
    }
    const content = input.content ?? current.content;
    const finalContentBlocks = input.disposition === "accept" && contentBlocks !== undefined
      ? monotonicAcceptContentBlocks(current.contentBlocks, contentBlocks)
      : contentBlocks ?? current.contentBlocks;
    const finalResources = input.disposition === "accept" && resources !== undefined
      ? monotonicAcceptResources(current.resources, resources)
      : resources ?? current.resources;
    const metadata = parseObjectJson(current.metadataJson) as Record<string, unknown>;
    const metadataJson = input.disposition === "discard"
      ? JSON.stringify({ ...metadata, terminalMarker: "discarded_terminal_projection" })
      : current.metadataJson;
    const exactReplay = current.status === status
      && current.content === content
      && stableJson(current.contentBlocks) === stableJson(finalContentBlocks)
      && stableJson(current.resources) === stableJson(finalResources)
      && stableJson(parseObjectJson(current.metadataJson)) === stableJson(parseObjectJson(metadataJson));
    if (exactReplay) {
      if (input.disposition === "discard") {
        markDiscardedBackendProjection(store, input.turnId, now);
      }
      return current;
    }
    if (terminalTurnStatus(current.status) && current.producingAttemptId !== null) {
      throw new Error("Journal turn is already terminalized with different canonical material");
    }
    const terminalized = updateJournalTurn(store, {
      ownerId: input.ownerId,
      conversationId: input.conversationId,
      turnId: input.turnId,
      status,
      content,
      replaceContentBlocks: finalContentBlocks,
      replaceResources: finalResources,
      producingRunId,
      producingAttemptId,
      metadataJson,
      nowMs: now,
    });
    if (input.disposition === "discard") {
      markDiscardedBackendProjection(store, input.turnId, now);
    }
    return terminalized;
  });
}

function markDiscardedBackendProjection(store: AgentStore, turnId: string, nowMs: number): void {
  store.execute(
    `UPDATE backend_turn_outbox
     SET status = 'failed', lease_expires_at_ms = NULL,
         last_error_code = 'discarded_terminal_projection', updated_at_ms = ?
     WHERE turn_id = ?`,
    [nowMs, turnId],
  );
}

function monotonicAcceptContentBlocks(
  current: readonly ConversationContentBlock[],
  incoming: readonly ConversationContentBlock[],
): ConversationContentBlock[] {
  const protectedCurrent = new Map(
    current
      .filter((block) => block.type === "agentSpawn" || block.type === "agentCompletion")
      .map((block) => [block.id, block] as const),
  );
  const result = incoming.map((block) => structuredClone(protectedCurrent.get(block.id) ?? block));
  const resultIds = new Set(result.map((block) => block.id));
  for (const block of protectedCurrent.values()) {
    if (!resultIds.has(block.id)) result.push(structuredClone(block));
  }
  return result;
}

function monotonicAcceptResources(
  current: readonly ConversationResource[],
  incoming: readonly ConversationResource[],
): ConversationResource[] {
  const currentById = new Map(current.map((resource) => [resource.id, resource] as const));
  const result = incoming.map((resource) => structuredClone(currentById.get(resource.id) ?? resource));
  const resultIds = new Set(result.map((resource) => resource.id));
  for (const resource of current) {
    if (!resultIds.has(resource.id)) result.push(structuredClone(resource));
  }
  return result;
}

/**
 * Atomically re-homes the current canonical turn graph into another owned
 * conversation. This is the migration boundary for surface consolidation:
 * callers must never copy `conversation_turns` directly because doing so
 * drops typed blocks/resources, revision visibility, delivery identity, and
 * the destination journal sequence.
 */
export function migrateJournalConversation(
  store: AgentStore,
  input: MigrateJournalConversationInput,
): MigrateJournalConversationResult {
  if (input.sourceConversationId === input.destinationConversationId) {
    return store.withTransaction(() => {
      assertConversationOwner(store, input.destinationConversationId, input.ownerId);
      const state = ensureJournalState(store, input.destinationConversationId, input.nowMs ?? Date.now());
      return {
        movedTurnCount: 0,
        movedRevisionCount: 0,
        movedOutboxCount: 0,
        destinationGeneration: state.generation,
        destinationHighWaterTurnSeq: state.highWaterTurnSeq,
      };
    });
  }
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    assertConversationOwner(store, input.sourceConversationId, input.ownerId);
    assertConversationOwner(store, input.destinationConversationId, input.ownerId);
    const sourceState = ensureJournalState(store, input.sourceConversationId, now);
    ensureJournalState(store, input.destinationConversationId, now);

    const sourceTurns = store.allRows(
      `SELECT ${TURN_COLUMNS}
       FROM conversation_turns
       WHERE conversation_id = ?
       ORDER BY turn_seq ASC, created_at_ms ASC, turn_id ASC`,
      [input.sourceConversationId],
    ).map(conversationTurnFromRow);
    if (sourceTurns.length === 0) {
      const destinationState = requireJournalState(store, input.destinationConversationId);
      return {
        movedTurnCount: 0,
        movedRevisionCount: 0,
        movedOutboxCount: 0,
        destinationGeneration: destinationState.generation,
        destinationHighWaterTurnSeq: destinationState.highWaterTurnSeq,
      };
    }

    assertJournalMigrationIdentityAvailable(store, input.destinationConversationId, sourceTurns);
    const sourceTurnIds = new Set(sourceTurns.map((turn) => turn.turnId));
    const revisionRows = store.allRows(
      `SELECT conversation_id, turn_seq, generation, turn_id, producer_id,
              mutation_kind, turn_json, payload_hash, created_at_ms
       FROM conversation_turn_revisions
       WHERE conversation_id = ? AND generation = ?
       ORDER BY turn_seq ASC`,
      [input.sourceConversationId, sourceState.generation],
    ).filter((row) => sourceTurnIds.has(String(row.turn_id)));
    const outboxRows = store.allRows(
      `SELECT ${OUTBOX_COLUMNS}, client_message_id
       FROM backend_turn_outbox
       WHERE conversation_id = ?
       ORDER BY created_at_ms ASC, turn_id ASC`,
      [input.sourceConversationId],
    );

    const currentById = new Map(sourceTurns.map((turn) => [turn.turnId, turn]));
    const migratedRevisions: Array<{
      turn: ConversationTurn;
      mutationKind: "recorded" | "updated" | "imported";
      createdAtMs: number;
    }> = [];
    const migratedCurrentSequence = new Map<string, number>();
    for (const row of revisionRows) {
      const current = currentById.get(String(row.turn_id));
      if (!current) continue;
      const sequence = nextJournalSequence(store, input.destinationConversationId, now);
      const revision = migratedJournalRevisionTurn(row, current, input.destinationConversationId, sequence.turnSeq);
      migratedRevisions.push({
        turn: revision,
        mutationKind: journalMutationKind(row.mutation_kind),
        createdAtMs: Number(row.created_at_ms),
      });
      if (Number(row.turn_seq) === current.turnSeq) {
        migratedCurrentSequence.set(current.turnId, sequence.turnSeq);
      }
    }
    for (const current of sourceTurns) {
      if (migratedCurrentSequence.has(current.turnId)) continue;
      const sequence = nextJournalSequence(store, input.destinationConversationId, now);
      migratedRevisions.push({
        turn: {
          ...current,
          conversationId: input.destinationConversationId,
          turnSeq: sequence.turnSeq,
        },
        mutationKind: "imported",
        createdAtMs: now,
      });
      migratedCurrentSequence.set(current.turnId, sequence.turnSeq);
    }

    store.execute("DELETE FROM backend_turn_outbox WHERE conversation_id = ?", [input.sourceConversationId]);
    store.execute("DELETE FROM conversation_turns WHERE conversation_id = ?", [input.sourceConversationId]);
    store.execute(
      "DELETE FROM conversation_turn_revisions WHERE conversation_id = ? AND generation = ?",
      [input.sourceConversationId, sourceState.generation],
    );

    for (const source of sourceTurns) {
      const turnSeq = migratedCurrentSequence.get(source.turnId);
      if (turnSeq === undefined) throw new Error("Journal migration did not assign the current turn sequence");
      store.insertConversationTurn({
        conversationId: input.destinationConversationId,
        turnId: source.turnId,
        turnSeq,
        producerId: source.producerId,
        payloadHash: source.payloadHash,
        role: source.role,
        surfaceKind: source.surfaceKind,
        content: source.content,
        origin: source.origin,
        status: source.status,
        contentBlocks: source.contentBlocks,
        resources: source.resources,
        producingRunId: source.producingRunId,
        producingAttemptId: source.producingAttemptId,
        remoteId: source.remoteId,
        createdAtMs: source.createdAtMs,
        updatedAtMs: source.updatedAtMs,
        completedAtMs: source.completedAtMs,
        metadataJson: source.metadataJson,
      });
    }

    const destinationState = requireJournalState(store, input.destinationConversationId);
    for (const revision of migratedRevisions.sort((left, right) => left.turn.turnSeq - right.turn.turnSeq)) {
      appendJournalRevision(
        store,
        revision.turn,
        destinationState.generation,
        revision.mutationKind,
        revision.createdAtMs,
      );
    }
    for (const row of outboxRows) {
      store.execute(
        `INSERT INTO backend_turn_outbox(
           turn_id, conversation_id, owner_id, client_message_id, status,
           attempt_count, available_at_ms, lease_expires_at_ms, remote_id,
           last_error_code, payload_hash, delivery_generation,
           conversation_generation, created_at_ms, updated_at_ms, delivered_at_ms
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          row.turn_id,
          input.destinationConversationId,
          row.owner_id,
          row.client_message_id,
          row.status,
          row.attempt_count,
          row.available_at_ms,
          row.lease_expires_at_ms,
          row.remote_id,
          row.last_error_code,
          row.payload_hash,
          row.delivery_generation,
          destinationState.generation,
          row.created_at_ms,
          row.updated_at_ms,
          row.delivered_at_ms,
        ],
      );
    }
    return {
      movedTurnCount: sourceTurns.length,
      movedRevisionCount: migratedRevisions.length,
      movedOutboxCount: outboxRows.length,
      destinationGeneration: destinationState.generation,
      destinationHighWaterTurnSeq: destinationState.highWaterTurnSeq,
    };
  });
}

export function listJournalTurns(
  store: AgentStore,
  input: {
    ownerId: string;
    conversationId: string;
    afterTurnSeq?: number;
    statuses?: readonly ConversationTurnStatus[];
    limit?: number;
  },
): JournalTurnRange {
  assertConversationOwner(store, input.conversationId, input.ownerId);
  const limit = boundedLimit(input.limit ?? 100);
  store.execute(
    `INSERT INTO conversation_journal_state(
       conversation_id, generation, high_water_turn_seq, updated_at_ms
     ) VALUES (?, 1, 0, ?)
     ON CONFLICT(conversation_id) DO NOTHING`,
    [input.conversationId, Date.now()],
  );
  const state = requireJournalState(store, input.conversationId);
  const values: unknown[] = [input.conversationId, input.afterTurnSeq ?? 0];
  let statusClause = "";
  if (input.statuses && input.statuses.length > 0) {
    statusClause = ` AND json_extract(turn_json, '$.status') IN (${input.statuses.map(() => "?").join(", ")})`;
    values.push(...input.statuses);
  }
  values.push(limit);
  const turns = store.allRows(
    `SELECT turn_json
     FROM conversation_turn_revisions
     WHERE conversation_id = ? AND generation = ${state.generation} AND turn_seq > ?${statusClause}
     ORDER BY turn_seq ASC
     LIMIT ?`,
    values,
  ).map((row) => JSON.parse(String(row.turn_json)) as ConversationTurn);
  return {
    conversationId: input.conversationId,
    generation: state.generation,
    generationBaseTurnSeq: state.generationBaseTurnSeq,
    highWaterTurnSeq: state.highWaterTurnSeq,
    turns,
  };
}

export function clearJournalConversation(
  store: AgentStore,
  input: { ownerId: string; conversationId: string; expectedGeneration: number; nowMs?: number },
): {
  conversationId: string;
  generation: number;
  generationBaseTurnSeq: number;
  highWaterTurnSeq: number;
  deletedTurns: number;
  backendDeleteOperationId: string | null;
} {
  if (!Number.isSafeInteger(input.expectedGeneration) || input.expectedGeneration < 1) {
    throw new Error("Journal clear expectedGeneration must be a positive integer");
  }
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    assertConversationOwner(store, input.conversationId, input.ownerId);
    store.execute(
      `INSERT INTO conversation_journal_state(
         conversation_id, generation, high_water_turn_seq, updated_at_ms
       ) VALUES (?, 1, 0, ?)
       ON CONFLICT(conversation_id) DO NOTHING`,
      [input.conversationId, now],
    );
    const current = requireJournalState(store, input.conversationId);
    if (input.expectedGeneration !== current.generation) {
      throw new Error("Journal clear generation is stale");
    }
    const generation = current.generation + 1;
    const highWaterTurnSeq = current.highWaterTurnSeq + 1;
    store.execute(
      `UPDATE conversation_journal_state
       SET generation = ?, generation_base_turn_seq = ?, high_water_turn_seq = ?, cleared_at_ms = ?, updated_at_ms = ?
       WHERE conversation_id = ?`,
      [generation, highWaterTurnSeq, highWaterTurnSeq, now, now, input.conversationId],
    );
    store.execute(
      `INSERT OR REPLACE INTO cleared_backend_turn_claims(
         turn_id, conversation_id, owner_id, attempt_count, delivery_generation,
         conversation_generation, payload_hash, lease_expires_at_ms, status,
         result_outcome, created_at_ms, settled_at_ms
       )
       SELECT turn_id, conversation_id, owner_id, attempt_count, delivery_generation,
              conversation_generation, payload_hash, COALESCE(lease_expires_at_ms, ?),
              'waiting', NULL, ?, NULL
       FROM backend_turn_outbox
       WHERE conversation_id = ? AND status = 'delivering'`,
      [now, now, input.conversationId],
    );
    store.execute(
      `UPDATE backend_reconcile_state
       SET conversation_generation = ?, frontier_remote_id = NULL,
           candidate_frontier_remote_id = NULL, in_flight_id = NULL,
           page_cursor = NULL, page_count = 0, status = 'idle',
           last_error_code = 'conversation_cleared', last_requested_at_ms = NULL,
           last_completed_at_ms = NULL, updated_at_ms = ?
       WHERE conversation_id = ?`,
      [generation, now, input.conversationId],
    );
    const backendDeleteOperationId = enqueueBackendConversationDelete(store, {
      ownerId: input.ownerId,
      conversationId: input.conversationId,
      conversationGeneration: generation,
      nowMs: now,
    });
    // Canonical rows are hard-deleted. The narrow claim tombstone above retains
    // only exact physical-delivery identity so a pre-clear POST can settle
    // before the backend delete is acknowledged; it is never projected as chat.
    store.execute(
      `DELETE FROM backend_turn_outbox
       WHERE conversation_id = ? AND status != 'delivered'`,
      [input.conversationId],
    );
    const deletedTurns = store.execute(
      "DELETE FROM conversation_turns WHERE conversation_id = ?",
      [input.conversationId],
    );
    return {
      conversationId: input.conversationId,
      generation,
      generationBaseTurnSeq: highWaterTurnSeq,
      highWaterTurnSeq,
      deletedTurns,
      backendDeleteOperationId,
    };
  });
}

/**
 * Import a backend row only when it is genuinely remote. A canonical turn ID
 * reconciles a local outbox row in place; remote IDs independently dedupe
 * backend-only rows across polling cycles.
 */
export function importRemoteJournalTurn(
  store: AgentStore,
  input: ImportRemoteJournalTurnInput,
): ImportRemoteJournalTurnResult {
  if (input.source !== "backend_reconcile" && input.source !== "legacy_upgrade") {
    throw new Error("Remote journal import requires a kernel-owned import source");
  }
  const remoteId = nonEmpty(input.remoteId, "remoteId");
  const canonicalTurnId = input.canonicalTurnId == null
    ? null
    : nonEmpty(input.canonicalTurnId, "canonicalTurnId");
  const now = input.nowMs ?? Date.now();
  const contentBlocks = validateContentBlocks(input.contentBlocks);
  const resources = validateResources(input.resources ?? []);
  const metadataJson = validObjectJson(input.metadataJson ?? "{}", "metadataJson");

  return store.withTransaction(() => {
    assertConversationOwner(store, input.conversationId, input.ownerId);
    if (canonicalTurnId) {
      const local = findJournalTurnById(store, canonicalTurnId);
      if (local) {
        if (local.conversationId !== input.conversationId) {
          throw new Error("Canonical turn ID belongs to a different conversation");
        }
        acknowledgeBackendTurn(store, {
          ownerId: input.ownerId,
          turnId: canonicalTurnId,
          remoteId,
          nowMs: now,
          requireOutbox: false,
        });
        return {
          turn: requireJournalTurn(store, input.conversationId, canonicalTurnId),
          imported: false,
          reconciledLocal: true,
        };
      }
    }

    const existingRemote = findJournalTurnByRemoteId(store, input.conversationId, remoteId);
    if (existingRemote) {
      return { turn: existingRemote, imported: false, reconciledLocal: false };
    }

    const turnId = canonicalTurnId ?? generateAgentId("turn");
    const sequence = nextJournalSequence(store, input.conversationId, now);
    const producerId = `legacy_remote:${remoteId}`;
    const payloadHash = journalTurnPayloadHash({
      turnId,
      role: input.role,
      surfaceKind: input.surfaceKind,
      content: input.content,
      origin: "backend_import",
      status: "completed",
      contentBlocks,
      resources,
      producingRunId: null,
      producingAttemptId: null,
      remoteId,
      metadataJson,
    });
    const turn = store.insertConversationTurn({
      conversationId: input.conversationId,
      turnId,
      turnSeq: sequence.turnSeq,
      producerId,
      payloadHash,
      role: input.role,
      surfaceKind: nonEmpty(input.surfaceKind, "surfaceKind"),
      content: input.content,
      origin: "backend_import",
      status: "completed",
      contentBlocks,
      resources,
      producingRunId: null,
      producingAttemptId: null,
      remoteId,
      createdAtMs: input.createdAtMs,
      updatedAtMs: now,
      completedAtMs: input.createdAtMs,
      metadataJson,
    });
    appendJournalRevision(store, turn, sequence.generation, "imported", now);
    return { turn, imported: true, reconciledLocal: false };
  });
}

function backendTargetForConversation(
  store: AgentStore,
  ownerId: string,
  conversationId: string,
): Omit<BackendReconcileRequest, "reconcileId" | "ownerId" | "conversationId" | "frontierRemoteId" | "pageCursor" | "pageLimit"> | null {
  const surface = store.getOptionalRow(
    `SELECT surface_kind, external_ref_kind, external_ref_id
     FROM surface_conversations
     WHERE conversation_id = ? AND owner_id = ? AND surface_kind = 'main_chat'
     ORDER BY CASE WHEN external_ref_id LIKE 'default%' THEN 0 ELSE 1 END,
              last_active_at_ms DESC
     LIMIT 1`,
    [conversationId, ownerId],
  );
  if (!surface) return null;
  const externalRefId = String(surface.external_ref_id);
  const targetKind = externalRefId === "default" || externalRefId.startsWith("default|")
    ? "messages" as const
    : "chat_session" as const;
  return {
    surfaceKind: String(surface.surface_kind),
    externalRefKind: String(surface.external_ref_kind),
    externalRefId,
    targetKind,
    targetId: targetKind === "messages"
      ? (externalRefId.includes("|") ? externalRefId.slice(externalRefId.indexOf("|") + 1) || null : null)
      : externalRefId,
  };
}

export function beginBackendReconcilesForOwner(
  store: AgentStore,
  input: {
    ownerId: string;
    conversationId?: string;
    nowMs?: number;
    cooldownMs?: number;
    limit?: number;
  },
): BackendReconcileRequest[] {
  const ownerId = nonEmpty(input.ownerId, "ownerId");
  const now = input.nowMs ?? Date.now();
  const cooldownMs = Math.max(1, input.cooldownMs ?? 5_000);
  const limit = boundedLimit(input.limit ?? 5);
  const rows = store.allRows(
    `SELECT sc.conversation_id
     FROM surface_conversations sc
     LEFT JOIN backend_reconcile_state state ON state.conversation_id = sc.conversation_id
     WHERE sc.owner_id = ? AND sc.surface_kind = 'main_chat'
       AND (? IS NULL OR sc.conversation_id = ?)
       AND COALESCE(state.status, 'idle') != 'fetching'
       AND NOT EXISTS (
         SELECT 1 FROM backend_conversation_delete_outbox deletion
         WHERE deletion.conversation_id = sc.conversation_id AND deletion.status != 'delivered'
       )
       AND (state.last_requested_at_ms IS NULL OR state.last_requested_at_ms <= ?)
     GROUP BY sc.conversation_id
     ORDER BY MAX(sc.last_active_at_ms) DESC, sc.conversation_id ASC
     LIMIT ?`,
    [ownerId, input.conversationId ?? null, input.conversationId ?? null, now - cooldownMs, limit],
  );
  return rows.flatMap((row) => {
    const request = beginBackendReconcile(store, {
      ownerId,
      conversationId: String(row.conversation_id),
      nowMs: now,
    });
    return request ? [request] : [];
  });
}

export function beginBackendReconcile(
  store: AgentStore,
  input: { ownerId: string; conversationId: string; nowMs?: number },
): BackendReconcileRequest | null {
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    assertConversationOwner(store, input.conversationId, input.ownerId);
    const pendingDelete = store.getOptionalRow(
      `SELECT operation_id FROM backend_conversation_delete_outbox
       WHERE conversation_id = ? AND status != 'delivered' LIMIT 1`,
      [input.conversationId],
    );
    if (pendingDelete) return null;
    const target = backendTargetForConversation(store, input.ownerId, input.conversationId);
    if (!target) return null;
    store.execute(
      `INSERT INTO conversation_journal_state(
         conversation_id, generation, high_water_turn_seq, updated_at_ms
       ) VALUES (?, 1, 0, ?)
       ON CONFLICT(conversation_id) DO NOTHING`,
      [input.conversationId, now],
    );
    const journalState = requireJournalState(store, input.conversationId);
    store.execute(
      `INSERT INTO backend_reconcile_state(
         conversation_id, owner_id, conversation_generation, status, page_cursor, page_count, updated_at_ms
       ) VALUES (?, ?, ?, 'idle', NULL, 0, ?)
       ON CONFLICT(conversation_id) DO NOTHING`,
      [input.conversationId, input.ownerId, journalState.generation, now],
    );
    const state = store.getRow(
      "SELECT * FROM backend_reconcile_state WHERE conversation_id = ?",
      [input.conversationId],
    );
    if (String(state.owner_id) !== input.ownerId) throw new Error("Backend reconcile is outside owner scope");
    if (String(state.status) === "fetching") return null;
    const reconcileId = `reconcile:${randomUUID()}`;
    store.execute(
      `UPDATE backend_reconcile_state
       SET in_flight_id = ?, candidate_frontier_remote_id = NULL,
           conversation_generation = ?,
           page_cursor = NULL, page_count = 0, status = 'fetching',
           last_error_code = NULL, last_requested_at_ms = ?, updated_at_ms = ?
       WHERE conversation_id = ?`,
      [reconcileId, journalState.generation, now, now, input.conversationId],
    );
    return {
      reconcileId,
      ownerId: input.ownerId,
      conversationId: input.conversationId,
      ...target,
      frontierRemoteId: state.frontier_remote_id == null ? null : String(state.frontier_remote_id),
      pageCursor: null,
      pageLimit: BACKEND_RECONCILE_PAGE_LIMIT,
    };
  });
}

export function applyBackendReconcilePage(
  store: AgentStore,
  input: {
    ownerId: string;
    reconcileId: string;
    conversationId: string;
    pageCursor: string | null;
    nextCursor?: string | null;
    turns: readonly BackendReconcileRemoteTurn[];
    hasMore: boolean;
    nowMs?: number;
  },
): BackendReconcilePageResult {
  const now = input.nowMs ?? Date.now();
  if (input.turns.length > BACKEND_RECONCILE_PAGE_LIMIT) {
    throw new Error("Backend reconcile page exceeds the bounded page limit");
  }
  const pageCursor = boundedReconcileCursor(input.pageCursor, "pageCursor");
  const nextCursor = boundedReconcileCursor(input.nextCursor ?? null, "nextCursor");
  return store.withTransaction(() => {
    const state = store.getRow(
      "SELECT * FROM backend_reconcile_state WHERE conversation_id = ?",
      [input.conversationId],
    );
    const journalState = requireJournalState(store, input.conversationId);
    if (
      String(state.owner_id) !== input.ownerId
      || String(state.status) !== "fetching"
      || String(state.in_flight_id) !== input.reconcileId
      || (state.page_cursor == null ? null : String(state.page_cursor)) !== pageCursor
      || Number(state.conversation_generation) !== journalState.generation
    ) {
      throw new Error("Backend reconcile page does not match the active owner-scoped request");
    }
    const frontier = state.frontier_remote_id == null ? null : String(state.frontier_remote_id);
    const remoteIds = input.turns.map((turn) => nonEmpty(turn.remoteId, "remoteId"));
    const frontierIndex = frontier ? remoteIds.indexOf(frontier) : -1;
    const newTurns = frontierIndex >= 0 ? input.turns.slice(0, frontierIndex) : input.turns;
    const importedTurns: ConversationTurn[] = [];
    for (const turn of newTurns) {
      const imported = importRemoteJournalTurn(store, {
        ownerId: input.ownerId,
        conversationId: input.conversationId,
        remoteId: turn.remoteId,
        canonicalTurnId: turn.canonicalTurnId,
        role: turn.role,
        surfaceKind: "main_chat",
        content: turn.content,
        contentBlocks: turn.contentBlocks,
        resources: turn.resources,
        metadataJson: turn.metadataJson,
        createdAtMs: turn.createdAtMs,
        nowMs: now,
        source: "backend_reconcile",
      });
      if (imported.imported || imported.reconciledLocal) importedTurns.push(imported.turn);
    }
    const candidateFrontier = Number(state.page_count) === 0 && remoteIds.length > 0
      ? remoteIds[0]!
      : state.candidate_frontier_remote_id == null ? null : String(state.candidate_frontier_remote_id);
    const completed = frontierIndex >= 0 || !input.hasMore;
    if (completed) {
      store.execute(
        `UPDATE backend_reconcile_state
         SET frontier_remote_id = COALESCE(?, frontier_remote_id),
             candidate_frontier_remote_id = NULL, in_flight_id = NULL,
             page_cursor = NULL, page_count = 0, status = 'idle',
             last_error_code = NULL, last_completed_at_ms = ?, updated_at_ms = ?
         WHERE conversation_id = ?`,
        [candidateFrontier, now, now, input.conversationId],
      );
      return { importedTurns, nextRequest: null, completed: true };
    }
    if (!nextCursor) throw new Error("Backend reconcile continuation requires a stable next cursor");
    if (nextCursor === pageCursor) throw new Error("Backend reconcile next cursor did not advance");
    const pageCount = Number(state.page_count) + 1;
    store.execute(
      `UPDATE backend_reconcile_state
       SET candidate_frontier_remote_id = ?, page_cursor = ?, page_count = ?, updated_at_ms = ?
       WHERE conversation_id = ?`,
      [candidateFrontier, nextCursor, pageCount, now, input.conversationId],
    );
    const target = backendTargetForConversation(store, input.ownerId, input.conversationId);
    if (!target) throw new Error("Backend reconcile target disappeared");
    return {
      importedTurns,
      completed: false,
      nextRequest: {
        reconcileId: input.reconcileId,
        ownerId: input.ownerId,
        conversationId: input.conversationId,
        ...target,
        frontierRemoteId: frontier,
        pageCursor: nextCursor,
        pageLimit: BACKEND_RECONCILE_PAGE_LIMIT,
      },
    };
  });
}

export function failBackendReconcile(
  store: AgentStore,
  input: {
    ownerId: string;
    reconcileId: string;
    conversationId: string;
    errorCode: string;
    nowMs?: number;
  },
): void {
  const now = input.nowMs ?? Date.now();
  const errorCode = boundedErrorCode(input.errorCode);
  store.withTransaction(() => {
    const state = store.getRow(
      "SELECT owner_id, in_flight_id, status FROM backend_reconcile_state WHERE conversation_id = ?",
      [input.conversationId],
    );
    if (
      String(state.owner_id) !== input.ownerId
      || String(state.in_flight_id) !== input.reconcileId
      || String(state.status) !== "fetching"
    ) {
      throw new Error("Backend reconcile failure does not match the active owner-scoped request");
    }
    store.execute(
      `UPDATE backend_reconcile_state
       SET in_flight_id = NULL, candidate_frontier_remote_id = NULL,
           page_cursor = NULL, page_count = 0, status = 'failed',
           last_error_code = ?, updated_at_ms = ?
       WHERE conversation_id = ?`,
      [errorCode, now, input.conversationId],
    );
  });
}

function enqueueBackendConversationDelete(
  store: AgentStore,
  input: { ownerId: string; conversationId: string; conversationGeneration: number; nowMs: number },
): string | null {
  const target = backendTargetForConversation(store, input.ownerId, input.conversationId);
  if (!target) return null;
  const { targetKind, targetId } = target;
  const operationId = `delete:${input.conversationId}:${input.conversationGeneration}`;
  const payloadHash = sha256(stableJson({
    operationId,
    ownerId: input.ownerId,
    targetKind,
    targetId,
    conversationGeneration: input.conversationGeneration,
  }));
  store.execute(
    `INSERT INTO backend_conversation_delete_outbox(
       operation_id, conversation_id, owner_id, target_kind, target_id,
       conversation_generation, status, attempt_count, delivery_generation,
       payload_hash, available_at_ms, lease_expires_at_ms, last_error_code,
       created_at_ms, updated_at_ms, delivered_at_ms
     ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, 0, ?, ?, NULL, NULL, ?, ?, NULL)`,
    [
      operationId,
      input.conversationId,
      input.ownerId,
      targetKind,
      targetId,
      input.conversationGeneration,
      payloadHash,
      input.nowMs,
      input.nowMs,
      input.nowMs,
    ],
  );
  return operationId;
}

export function drainBackendConversationDeleteOutbox(
  store: AgentStore,
  input: { ownerId: string; limit?: number; nowMs?: number; leaseMs?: number },
): BackendConversationDeleteDelivery[] {
  const ownerId = nonEmpty(input.ownerId, "ownerId");
  const now = input.nowMs ?? Date.now();
  const leaseMs = Math.max(1, input.leaseMs ?? DEFAULT_OUTBOX_LEASE_MS);
  const limit = boundedLimit(input.limit ?? 20);
  return store.withTransaction(() => {
    const candidates = store.allRows(
      `SELECT operation_id
       FROM backend_conversation_delete_outbox
       WHERE owner_id = ? AND (
         (status IN ('pending', 'retrying') AND available_at_ms <= ?)
         OR (status = 'delivering' AND lease_expires_at_ms IS NOT NULL AND lease_expires_at_ms <= ?)
       )
       ORDER BY available_at_ms ASC, created_at_ms ASC, operation_id ASC
       LIMIT ?`,
      [ownerId, now, now, limit],
    );
    return candidates.map((candidate) => {
      const operationId = String(candidate.operation_id);
      store.execute(
        `UPDATE backend_conversation_delete_outbox
         SET status = 'delivering', attempt_count = attempt_count + 1,
             delivery_generation = delivery_generation + 1,
             lease_expires_at_ms = ?, updated_at_ms = ?
         WHERE operation_id = ?`,
        [now + leaseMs, now, operationId],
      );
      return requireBackendConversationDelete(store, operationId);
    });
  });
}

export function ackBackendConversationDeleteOutbox(
  store: AgentStore,
  input: {
    ownerId: string;
    operationId: string;
    conversationGeneration: number;
    attemptCount: number;
    deliveryGeneration: number;
    payloadHash: string;
    nowMs?: number;
  },
): BackendConversationDeleteDelivery {
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    const current = requireBackendConversationDelete(store, input.operationId);
    assertBackendConversationDeleteClaim(current, input);
    store.execute(
      `UPDATE cleared_backend_turn_claims
       SET status = 'settled', result_outcome = 'expired', settled_at_ms = ?
       WHERE conversation_id = ? AND status = 'waiting' AND lease_expires_at_ms <= ?`,
      [now, current.conversationId, now],
    );
    const waiting = Number(store.getRow(
      `SELECT COUNT(*) AS count FROM cleared_backend_turn_claims
       WHERE conversation_id = ? AND status = 'waiting'`,
      [current.conversationId],
    ).count);
    if (waiting > 0) {
      throw new Error("Backend conversation delete is waiting for prior turn claims to settle or expire");
    }
    store.execute(
      `UPDATE backend_conversation_delete_outbox
       SET status = 'delivered', lease_expires_at_ms = NULL, last_error_code = NULL,
           delivered_at_ms = ?, updated_at_ms = ?
       WHERE operation_id = ?`,
      [now, now, input.operationId],
    );
    store.execute(
      "DELETE FROM cleared_backend_turn_claims WHERE conversation_id = ? AND status = 'settled'",
      [current.conversationId],
    );
    return requireBackendConversationDelete(store, input.operationId);
  });
}

export function failBackendConversationDeleteOutbox(
  store: AgentStore,
  input: {
    ownerId: string;
    operationId: string;
    conversationGeneration: number;
    attemptCount: number;
    deliveryGeneration: number;
    payloadHash: string;
    errorCode: string;
    retryAtMs?: number;
    nowMs?: number;
  },
): BackendConversationDeleteDelivery {
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    const current = requireBackendConversationDelete(store, input.operationId);
    assertBackendConversationDeleteClaim(current, input);
    const status = input.retryAtMs === undefined ? "failed" : "retrying";
    store.execute(
      `UPDATE backend_conversation_delete_outbox
       SET status = ?, available_at_ms = ?, lease_expires_at_ms = NULL,
           last_error_code = ?, updated_at_ms = ?
       WHERE operation_id = ?`,
      [
        status,
        input.retryAtMs ?? current.availableAtMs,
        boundedErrorCode(input.errorCode),
        now,
        input.operationId,
      ],
    );
    return requireBackendConversationDelete(store, input.operationId);
  });
}

function requireBackendConversationDelete(
  store: AgentStore,
  operationId: string,
): BackendConversationDeleteDelivery {
  const row = store.getOptionalRow(
    `SELECT ${DELETE_OUTBOX_COLUMNS}
     FROM backend_conversation_delete_outbox WHERE operation_id = ?`,
    [operationId],
  );
  if (!row) throw new Error(`Unknown backend conversation delete ${operationId}`);
  return {
    operationId: String(row.operation_id),
    conversationId: String(row.conversation_id),
    ownerId: String(row.owner_id),
    targetKind: String(row.target_kind) as BackendConversationDeleteDelivery["targetKind"],
    targetId: row.target_id == null ? null : String(row.target_id),
    conversationGeneration: Number(row.conversation_generation),
    status: String(row.status) as BackendTurnOutboxStatus,
    attemptCount: Number(row.attempt_count),
    deliveryGeneration: Number(row.delivery_generation),
    payloadHash: String(row.payload_hash),
    availableAtMs: Number(row.available_at_ms),
    leaseExpiresAtMs: row.lease_expires_at_ms == null ? null : Number(row.lease_expires_at_ms),
    lastErrorCode: row.last_error_code == null ? null : String(row.last_error_code),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
    deliveredAtMs: row.delivered_at_ms == null ? null : Number(row.delivered_at_ms),
  };
}

function assertBackendConversationDeleteClaim(
  current: BackendConversationDeleteDelivery,
  input: {
    ownerId: string;
    conversationGeneration: number;
    attemptCount: number;
    deliveryGeneration: number;
    payloadHash: string;
  },
): void {
  if (current.ownerId !== input.ownerId) throw new Error("Backend conversation delete is outside owner scope");
  if (
    current.status !== "delivering"
    || current.conversationGeneration !== input.conversationGeneration
    || current.attemptCount !== input.attemptCount
    || current.deliveryGeneration !== input.deliveryGeneration
    || current.payloadHash !== input.payloadHash
  ) {
    throw new Error("Backend conversation delete result does not match the active claim");
  }
}

/** Atomically leases completed journal rows for the backend sync adapter. */
export function drainBackendTurnOutbox(
  store: AgentStore,
  input: { ownerId?: string; limit?: number; nowMs?: number; leaseMs?: number } = {},
): BackendTurnDelivery[] {
  const now = input.nowMs ?? Date.now();
  const leaseMs = Math.max(1, input.leaseMs ?? DEFAULT_OUTBOX_LEASE_MS);
  const limit = boundedLimit(input.limit ?? 20);
  return store.withTransaction(() => {
    const ownerClause = input.ownerId ? " AND o.owner_id = ?" : "";
    const values: unknown[] = [now, now];
    if (input.ownerId) values.push(input.ownerId);
    values.push(limit);
    const candidates = store.allRows(
      `SELECT o.turn_id
       FROM backend_turn_outbox o
       JOIN conversation_turns t
         ON t.conversation_id = o.conversation_id AND t.turn_id = o.turn_id
       WHERE (
         (o.status IN ('pending', 'retrying') AND o.available_at_ms <= ?)
         OR (o.status = 'delivering' AND o.lease_expires_at_ms IS NOT NULL AND o.lease_expires_at_ms <= ?)
       )
         AND t.status IN ('completed', 'failed')${ownerClause}
         AND NOT EXISTS (
           SELECT 1 FROM backend_conversation_delete_outbox d
           WHERE d.conversation_id = o.conversation_id AND d.status != 'delivered'
         )
       ORDER BY o.available_at_ms ASC, o.created_at_ms ASC, o.turn_id ASC
       LIMIT ?`,
      values,
    );

    const deliveries: BackendTurnDelivery[] = [];
    for (const candidate of candidates) {
      const turnId = String(candidate.turn_id);
      const currentOutbox = requireOutboxRecord(store, turnId);
      const turn = requireJournalTurn(store, currentOutbox.conversationId, turnId);
      const payload = backendTurnPayload(turn);
      const payloadHash = backendTurnPayloadHash(payload);
      if (payloadHash !== currentOutbox.payloadHash) {
        throw new Error("Backend turn outbox revision does not match the canonical journal turn");
      }
      const journalState = requireJournalState(store, currentOutbox.conversationId);
      store.execute(
        `UPDATE backend_turn_outbox
         SET status = 'delivering', attempt_count = attempt_count + 1,
             delivery_generation = delivery_generation + 1,
             conversation_generation = ?, payload_hash = ?,
             lease_expires_at_ms = ?, updated_at_ms = ?
         WHERE turn_id = ?`,
        [journalState.generation, payloadHash, now + leaseMs, now, turnId],
      );
      const outbox = requireOutboxRecord(store, turnId);
      deliveries.push({ ...outbox, clientMessageId: turnId, turn, payload });
    }
    return deliveries;
  });
}

export function ackBackendTurnOutbox(
  store: AgentStore,
  input: BackendTurnAckInput,
): BackendTurnOutboxRecord {
  return acknowledgeBackendTurn(store, { ...input, nowMs: input.nowMs ?? Date.now(), requireOutbox: true });
}

/**
 * ACK plus notification projections for every surface bound to the mutated
 * conversation. The wake carries the post-ACK remote-id revision; consumers
 * still range-fetch by turnSeq before applying it.
 */
export function ackBackendTurnOutboxWithWakes(
  store: AgentStore,
  input: BackendTurnAckInput,
): { outbox: BackendTurnOutboxRecord; wakes: JournalTurnChangedWake[] } {
  const outbox = ackBackendTurnOutbox(store, input);
  const turn = requireJournalTurn(store, outbox.conversationId, input.turnId);
  return {
    outbox,
    wakes: journalTurnChangedWakes(store, input.ownerId, turn),
  };
}

/**
 * Classify a backend result against durable claim and journal history.
 *
 * A turn revision can supersede a physical POST while it is in flight. The
 * exact ACK/failure mutators intentionally continue to reject that stale
 * claim; this boundary absorbs it only when the supplied payload is provably a
 * prior canonical revision (or the exact result was already settled).
 */
export function classifyBackendTurnResultDisposition(
  store: AgentStore,
  input: {
    ownerId: string;
    turnId: string;
    conversationId: string;
    attemptCount: number;
    deliveryGeneration: number;
    conversationGeneration: number;
    payloadHash: string;
    ok: boolean;
    remoteId?: string;
    errorCode?: string;
  },
): BackendTurnResultDisposition {
  for (const [label, value] of [
    ["attemptCount", input.attemptCount],
    ["deliveryGeneration", input.deliveryGeneration],
    ["conversationGeneration", input.conversationGeneration],
  ] as const) {
    if (!Number.isSafeInteger(value) || value < 1) {
      throw new Error(`Backend sync result ${label} must be a positive safe integer`);
    }
  }
  nonEmpty(input.payloadHash, "payloadHash");
  const current = requireOutboxRecord(store, input.turnId);
  if (current.ownerId !== input.ownerId) {
    throw new Error("Backend sync result owner does not match the claim owner");
  }
  if (current.conversationId !== input.conversationId) {
    throw new Error("Backend sync result conversation does not match the active claim");
  }
  const exactClaim = current.deliveryGeneration === input.deliveryGeneration
    && current.attemptCount === input.attemptCount
    && current.conversationGeneration === input.conversationGeneration
    && current.payloadHash === input.payloadHash;
  if (exactClaim && current.status === "delivering") return "active";
  if (exactClaim && current.status === "delivered") {
    if (!input.ok || !input.remoteId || current.remoteId !== input.remoteId) {
      throw new Error("Duplicate backend sync success conflicts with the delivered result");
    }
    return "duplicate";
  }
  if (exactClaim && (current.status === "retrying" || current.status === "failed")) {
    const errorCode = input.errorCode ?? "backend_sync_failed";
    if (input.ok || current.lastErrorCode !== errorCode) {
      throw new Error("Duplicate backend sync failure conflicts with the settled result");
    }
    return "duplicate";
  }
  if (
    input.deliveryGeneration > current.deliveryGeneration
    || input.conversationGeneration > current.conversationGeneration
  ) {
    throw new Error("Backend sync result claims a future delivery generation");
  }
  const currentTurn = requireJournalTurn(store, input.conversationId, input.turnId);
  const historicalTurnSeq = historicalBackendPayloadTurnSeq(store, {
    conversationId: input.conversationId,
    turnId: input.turnId,
    conversationGeneration: input.conversationGeneration,
    payloadHash: input.payloadHash,
  });
  if (historicalTurnSeq === null) {
    throw new Error("Backend sync result payload was never a canonical journal revision");
  }
  const olderClaim = input.deliveryGeneration < current.deliveryGeneration;
  const olderPayloadOnSupersededClaim = input.deliveryGeneration === current.deliveryGeneration
    && input.payloadHash !== current.payloadHash
    && historicalTurnSeq < currentTurn.turnSeq
    && current.status !== "delivering"
    && current.attemptCount === 0
    && input.attemptCount > 0;
  if (olderClaim || olderPayloadOnSupersededClaim) return "superseded";
  throw new Error("Backend sync result does not match the active claimed generation");
}

/** Settle an exact pre-clear physical POST claim after its canonical turn was removed. */
export function settleClearedBackendTurnClaim(
  store: AgentStore,
  input: {
    ownerId: string;
    turnId: string;
    conversationId: string;
    attemptCount: number;
    deliveryGeneration: number;
    conversationGeneration: number;
    payloadHash: string;
    ok: boolean;
    nowMs?: number;
  },
): boolean {
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    const row = store.getOptionalRow(
      "SELECT * FROM cleared_backend_turn_claims WHERE turn_id = ?",
      [input.turnId],
    );
    if (!row) return false;
    if (
      String(row.owner_id) !== input.ownerId
      || String(row.conversation_id) !== input.conversationId
      || Number(row.attempt_count) !== input.attemptCount
      || Number(row.delivery_generation) !== input.deliveryGeneration
      || Number(row.conversation_generation) !== input.conversationGeneration
      || String(row.payload_hash) !== input.payloadHash
    ) {
      throw new Error("Cleared backend turn result does not match the preserved physical claim");
    }
    if (String(row.status) === "settled") return true;
    store.execute(
      `UPDATE cleared_backend_turn_claims
       SET status = 'settled', result_outcome = ?, settled_at_ms = ?
       WHERE turn_id = ?`,
      [input.ok ? "succeeded" : "failed", now, input.turnId],
    );
    return true;
  });
}

/** Project a canonical turn mutation to every surface bound to its conversation. */
export function journalTurnChangedWakes(
  store: AgentStore,
  ownerId: string,
  turn: ConversationTurn,
): JournalTurnChangedWake[] {
  assertConversationOwner(store, turn.conversationId, ownerId);
  const state = requireJournalState(store, turn.conversationId);
  const surfaces = store.allRows(
    `SELECT surface_kind, external_ref_kind, external_ref_id
     FROM surface_conversations
     WHERE owner_id = ? AND conversation_id = ?
     ORDER BY surface_kind ASC, external_ref_kind ASC, external_ref_id ASC`,
    [ownerId, turn.conversationId],
  );
  return surfaces.map((surface) => {
    const surfaceKind = String(surface.surface_kind);
    return {
      ownerId,
      conversationGeneration: state.generation,
      generationBaseTurnSeq: state.generationBaseTurnSeq,
      surfaceKind,
      externalRefKind: String(surface.external_ref_kind),
      externalRefId: String(surface.external_ref_id),
      // Swift treats this payload as a wake only, but its router keys from the
      // turn's surfaceKind. Project the binding surface so every wake routes.
      turn: journalTurnForSurfaceProjection(turn, surfaceKind),
    };
  });
}

export function failBackendTurnOutbox(
  store: AgentStore,
  input: {
    ownerId: string;
    turnId: string;
    deliveryGeneration: number;
    attemptCount: number;
    conversationGeneration: number;
    payloadHash: string;
    errorCode: string;
    retryAtMs?: number;
    nowMs?: number;
  },
): BackendTurnOutboxRecord {
  const now = input.nowMs ?? Date.now();
  const errorCode = boundedErrorCode(input.errorCode);
  return store.withTransaction(() => {
    const current = requireOutboxRecord(store, input.turnId);
    if (current.ownerId !== input.ownerId) throw new Error("Backend turn delivery is outside owner scope");
    assertClaimMatches(current, input);
    if (current.status === "delivered") throw new Error("Delivered backend turn cannot be failed");
    const status: BackendTurnOutboxStatus = input.retryAtMs === undefined ? "failed" : "retrying";
    store.execute(
      `UPDATE backend_turn_outbox
       SET status = ?, available_at_ms = ?, lease_expires_at_ms = NULL,
           last_error_code = ?, updated_at_ms = ?
       WHERE turn_id = ?`,
      [status, input.retryAtMs ?? current.availableAtMs, errorCode, now, input.turnId],
    );
    return requireOutboxRecord(store, input.turnId);
  });
}

/** State-only health projection. It intentionally never returns turn content. */
export function getJournalObservability(
  store: AgentStore,
  input: { ownerId?: string } = {},
): JournalObservabilitySnapshot {
  const ownerTurnClause = input.ownerId
    ? ` WHERE EXISTS (
          SELECT 1 FROM surface_conversations sc
          WHERE sc.conversation_id = conversation_turns.conversation_id AND sc.owner_id = ?
        )`
    : "";
  const turnRows = store.allRows(
    `SELECT status, COUNT(*) AS count FROM conversation_turns${ownerTurnClause} GROUP BY status`,
    input.ownerId ? [input.ownerId] : [],
  );
  const deliveryWhere = input.ownerId ? " WHERE owner_id = ?" : "";
  const deliveryRows = store.allRows(
    `SELECT status, COUNT(*) AS count FROM backend_turn_outbox${deliveryWhere} GROUP BY status`,
    input.ownerId ? [input.ownerId] : [],
  );
  const oldest = store.getOptionalRow(
    `SELECT MIN(created_at_ms) AS oldest
     FROM backend_turn_outbox
     WHERE status IN ('pending', 'delivering', 'retrying')${input.ownerId ? " AND owner_id = ?" : ""}`,
    input.ownerId ? [input.ownerId] : [],
  );
  return {
    turnStatusCounts: countRows<ConversationTurnStatus>(turnRows),
    deliveryStatusCounts: countRows<BackendTurnOutboxStatus>(deliveryRows),
    oldestPendingDeliveryCreatedAtMs: oldest?.oldest == null ? null : Number(oldest.oldest),
  };
}

function ensureDeliveryState(
  store: AgentStore,
  input: {
    ownerId: string;
    conversationId: string;
    turnId: string;
    delivery: JournalDeliveryDestination;
    nowMs: number;
  },
): BackendTurnOutboxStatus | null {
  const existing = store.getOptionalRow(
    `SELECT ${OUTBOX_COLUMNS} FROM backend_turn_outbox WHERE turn_id = ?`,
    [input.turnId],
  );
  if (input.delivery === "local") {
    if (existing) throw new Error("Journal turn delivery destination cannot change from backend to local");
    return null;
  }
  const turn = requireJournalTurn(store, input.conversationId, input.turnId);
  const payloadHash = backendTurnPayloadHash(backendTurnPayload(turn));
  const journalState = requireJournalState(store, input.conversationId);
  const tombstoneCode = backendTombstoneCode(turn);
  store.execute(
    `INSERT INTO backend_turn_outbox (
       turn_id, conversation_id, owner_id, client_message_id, status, attempt_count,
       available_at_ms, payload_hash, delivery_generation, conversation_generation,
       last_error_code, created_at_ms, updated_at_ms
     ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, 0, ?, ?, ?, ?)
     ON CONFLICT(turn_id) DO NOTHING`,
    [
      input.turnId,
      input.conversationId,
      input.ownerId,
      input.turnId,
      tombstoneCode ? "failed" : "pending",
      input.nowMs,
      payloadHash,
      journalState.generation,
      tombstoneCode,
      input.nowMs,
      input.nowMs,
    ],
  );
  const row = requireOutboxRecord(store, input.turnId);
  if (row.ownerId !== input.ownerId || row.conversationId !== input.conversationId) {
    throw new Error("Canonical turn ID is already bound to a different backend delivery");
  }
  return row.status;
}

function acknowledgeBackendTurn(
  store: AgentStore,
  input: {
    ownerId: string;
    turnId: string;
    remoteId: string;
    nowMs: number;
    requireOutbox: boolean;
    deliveryGeneration?: number;
    attemptCount?: number;
    conversationGeneration?: number;
    payloadHash?: string;
  },
): BackendTurnOutboxRecord {
  const remoteId = nonEmpty(input.remoteId, "remoteId");
  return store.withTransaction(() => {
    const turn = findJournalTurnById(store, input.turnId);
    if (!turn) throw new Error(`Unknown journal turn ${input.turnId}`);
    assertConversationOwner(store, turn.conversationId, input.ownerId);
    if (turn.remoteId !== null && turn.remoteId !== remoteId) {
      throw new Error("Journal turn is already reconciled to a different remote ID");
    }
    const existing = store.getOptionalRow(
      `SELECT ${OUTBOX_COLUMNS} FROM backend_turn_outbox WHERE turn_id = ?`,
      [input.turnId],
    );
    if (!existing && input.requireOutbox) throw new Error(`Journal turn ${input.turnId} has no backend delivery`);
    if (existing) {
      const outbox = outboxRecordFromRow(existing);
      if (outbox.ownerId !== input.ownerId) throw new Error("Backend turn delivery is outside owner scope");
      if (input.requireOutbox) {
        assertClaimMatches(outbox, {
          deliveryGeneration: input.deliveryGeneration!,
          attemptCount: input.attemptCount!,
          conversationGeneration: input.conversationGeneration!,
          payloadHash: input.payloadHash!,
        });
      }
      if (outbox.remoteId !== null && outbox.remoteId !== remoteId) {
        throw new Error("Backend delivery is already acknowledged with a different remote ID");
      }
      store.execute(
        `UPDATE backend_turn_outbox
         SET status = 'delivered', remote_id = ?, lease_expires_at_ms = NULL,
             last_error_code = NULL, updated_at_ms = ?, delivered_at_ms = COALESCE(delivered_at_ms, ?)
         WHERE turn_id = ?`,
        [remoteId, input.nowMs, input.nowMs, input.turnId],
      );
    }
    if (turn.remoteId === null) {
      const sequence = nextJournalSequence(store, turn.conversationId, input.nowMs);
      const payloadHash = journalTurnPayloadHash({
        turnId: turn.turnId,
        role: turn.role,
        surfaceKind: turn.surfaceKind,
        content: turn.content,
        origin: turn.origin,
        status: turn.status,
        contentBlocks: turn.contentBlocks,
        resources: turn.resources,
        producingRunId: turn.producingRunId,
        producingAttemptId: turn.producingAttemptId,
        remoteId,
        metadataJson: turn.metadataJson,
      });
      store.execute(
        `UPDATE conversation_turns
         SET remote_id = ?, turn_seq = ?, payload_hash = ?, updated_at_ms = MAX(updated_at_ms, ?)
         WHERE conversation_id = ? AND turn_id = ?`,
        [remoteId, sequence.turnSeq, payloadHash, input.nowMs, turn.conversationId, input.turnId],
      );
      appendJournalRevision(
        store,
        requireJournalTurn(store, turn.conversationId, input.turnId),
        sequence.generation,
        "updated",
        input.nowMs,
      );
    }
    if (existing) return requireOutboxRecord(store, input.turnId);
    return {
      turnId: input.turnId,
      conversationId: turn.conversationId,
      ownerId: input.ownerId,
      status: "delivered",
      attemptCount: 0,
      deliveryGeneration: 0,
      conversationGeneration: requireJournalState(store, turn.conversationId).generation,
      payloadHash: backendTurnPayloadHash(backendTurnPayload(turn)),
      availableAtMs: input.nowMs,
      leaseExpiresAtMs: null,
      remoteId,
      lastErrorCode: null,
      createdAtMs: turn.createdAtMs,
      updatedAtMs: input.nowMs,
      deliveredAtMs: input.nowMs,
    };
  });
}

function findJournalTurnById(store: AgentStore, turnId: string): ConversationTurn | null {
  const row = store.getOptionalRow(
    `SELECT ${TURN_COLUMNS} FROM conversation_turns WHERE turn_id = ? ORDER BY created_at_ms ASC LIMIT 1`,
    [turnId],
  );
  return row ? conversationTurnFromRow(row) : null;
}

function findJournalTurnByProducer(
  store: AgentStore,
  conversationId: string,
  producerId: string,
): ConversationTurn | null {
  const row = store.getOptionalRow(
    `SELECT ${TURN_COLUMNS}
     FROM conversation_turns
     WHERE conversation_id = ? AND producer_id = ?
     LIMIT 1`,
    [conversationId, producerId],
  );
  return row ? conversationTurnFromRow(row) : null;
}

function findJournalTurnByRemoteId(
  store: AgentStore,
  conversationId: string,
  remoteId: string,
): ConversationTurn | null {
  const row = store.getOptionalRow(
    `SELECT ${TURN_COLUMNS}
     FROM conversation_turns WHERE conversation_id = ? AND remote_id = ? LIMIT 1`,
    [conversationId, remoteId],
  );
  return row ? conversationTurnFromRow(row) : null;
}

function requireJournalTurn(store: AgentStore, conversationId: string, turnId: string): ConversationTurn {
  const row = store.getOptionalRow(
    `SELECT ${TURN_COLUMNS}
     FROM conversation_turns WHERE conversation_id = ? AND turn_id = ?`,
    [conversationId, turnId],
  );
  if (!row) throw new Error(`Unknown journal turn ${turnId}`);
  return conversationTurnFromRow(row);
}

function requireOutboxRecord(store: AgentStore, turnId: string): BackendTurnOutboxRecord {
  const row = store.getOptionalRow(
    `SELECT ${OUTBOX_COLUMNS} FROM backend_turn_outbox WHERE turn_id = ?`,
    [turnId],
  );
  if (!row) throw new Error(`Journal turn ${turnId} has no backend delivery`);
  return outboxRecordFromRow(row);
}

function outboxRecordFromRow(row: Record<string, unknown>): BackendTurnOutboxRecord {
  return {
    turnId: String(row.turn_id),
    conversationId: String(row.conversation_id),
    ownerId: String(row.owner_id),
    status: String(row.status) as BackendTurnOutboxStatus,
    attemptCount: Number(row.attempt_count),
    deliveryGeneration: Number(row.delivery_generation),
    conversationGeneration: Number(row.conversation_generation),
    payloadHash: String(row.payload_hash),
    availableAtMs: Number(row.available_at_ms),
    leaseExpiresAtMs: row.lease_expires_at_ms == null ? null : Number(row.lease_expires_at_ms),
    remoteId: row.remote_id == null ? null : String(row.remote_id),
    lastErrorCode: row.last_error_code == null ? null : String(row.last_error_code),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
    deliveredAtMs: row.delivered_at_ms == null ? null : Number(row.delivered_at_ms),
  };
}

function assertClaimMatches(
  current: BackendTurnOutboxRecord,
  claim: { deliveryGeneration: number; attemptCount: number; conversationGeneration: number; payloadHash: string },
): void {
  if (
    current.status !== "delivering"
    || current.deliveryGeneration !== claim.deliveryGeneration
    || current.attemptCount !== claim.attemptCount
    || current.conversationGeneration !== claim.conversationGeneration
    || current.payloadHash !== claim.payloadHash
  ) {
    throw new Error("Backend delivery acknowledgement does not match the active claimed generation");
  }
}

function assertConversationOwner(store: AgentStore, conversationId: string, ownerId: string): void {
  const row = store.getOptionalRow(
    `SELECT 1 FROM surface_conversations WHERE conversation_id = ? AND owner_id = ? LIMIT 1`,
    [conversationId, ownerId],
  );
  if (!row) throw new Error("Journal conversation is outside owner scope");
}

function assertProducingJournalTurnMapping(
  store: AgentStore,
  input: ProducingJournalTurnAdmissionInput,
): void {
  assertConversationOwner(store, input.conversationId, input.ownerId);
  const mapping = store.getOptionalRow(
    `SELECT 1 FROM surface_conversations
     WHERE conversation_id = ? AND owner_id = ? AND agent_session_id = ?
     LIMIT 1`,
    [input.conversationId, input.ownerId, input.sessionId],
  );
  if (!mapping) {
    throw new Error("Producing turn admission requires the exact canonical owner/session/conversation mapping");
  }
}

function assertProducingRunOwner(store: AgentStore, runId: string | null, ownerId: string): void {
  if (runId === null) return;
  const row = store.getOptionalRow(
    `SELECT 1
     FROM runs r JOIN sessions s ON s.session_id = r.session_id
     WHERE r.run_id = ? AND s.owner_id = ?`,
    [runId, ownerId],
  );
  if (!row) throw new Error("Producing run is outside owner scope");
}

function assertIdempotentRecord(
  existing: ConversationTurn,
  input: RecordJournalTurnInput & {
    turnId: string;
    contentBlocks: ConversationContentBlock[];
    resources: ConversationResource[];
    metadataJson: string;
    producerId: string;
  },
): void {
  if (existing.conversationId !== input.conversationId) {
    throw new Error("Canonical turn ID belongs to a different conversation");
  }
  const equivalent = existing.role === input.role
    && existing.surfaceKind === input.surfaceKind
    && existing.content === input.content
    && existing.origin === input.origin
    && existing.producerId === input.producerId
    && existing.producingRunId === (input.producingRunId ?? null)
    && existing.producingAttemptId === (input.producingAttemptId ?? null)
    && stableJson(existing.contentBlocks) === stableJson(input.contentBlocks)
    && stableJson(existing.resources) === stableJson(input.resources)
    && stableJson(parseObjectJson(existing.metadataJson)) === stableJson(parseObjectJson(input.metadataJson));
  if (!equivalent) throw new Error("Canonical turn or producer identity collision has different journal content");
}

function canonicalJournalDelivery(
  store: AgentStore,
  ownerId: string,
  conversationId: string,
): JournalDeliveryDestination {
  const surfaces = store.allRows(
    `SELECT DISTINCT surface_kind
     FROM surface_conversations
     WHERE conversation_id = ? AND owner_id = ?`,
    [conversationId, ownerId],
  );
  if (surfaces.length === 0) throw new Error("Journal conversation is outside owner scope");
  const destinations = new Set(
    surfaces.map((surface) => journalDeliveryForSurface(String(surface.surface_kind))),
  );
  if (destinations.size !== 1) {
    throw new Error("Journal conversation mixes local-only and backend-backed canonical surfaces");
  }
  return destinations.values().next().value!;
}

function assertCanonicalJournalDelivery(
  surfaceKind: string,
  canonicalDelivery: JournalDeliveryDestination,
): void {
  const normalizedSurfaceKind = nonEmpty(surfaceKind, "surfaceKind");
  if (journalDeliveryForSurface(normalizedSurfaceKind) !== canonicalDelivery) {
    throw new Error("Journal turn surface does not match the canonical conversation delivery boundary");
  }
}

function journalDeliveryForSurface(surfaceKind: string): JournalDeliveryDestination {
  return LOCAL_ONLY_SURFACES.has(surfaceKind) ? "local" : "backend";
}

function validateContentBlocks(blocks: readonly ConversationContentBlock[]): ConversationContentBlock[] {
  const ids = new Set<string>();
  return blocks.map((block) => {
    const id = nonEmpty(block.id, "content block id");
    nonEmpty(block.type, "content block type");
    if (ids.has(id)) throw new Error(`Duplicate content block ID ${id}`);
    ids.add(id);
    if (block.type === "questionCard") {
      nonEmpty(block.questionId, "question ID");
      if (block.text.length === 0 || block.text.length > 300) throw new Error("Question card text is out of bounds");
      nonEmpty(block.subject.id, "question subject ID");
      if (!["task", "goal", "capture"].includes(block.subject.kind)) throw new Error("Question subject kind is invalid");
      if (block.options.length < 1 || block.options.length > 4) throw new Error("Question card option count is out of bounds");
      const optionIds = new Set<string>();
      let defers = 0;
      for (const option of block.options) {
        nonEmpty(option.optionId, "question option ID");
        if (optionIds.has(option.optionId)) throw new Error("Question option IDs must be unique");
        optionIds.add(option.optionId);
        if (option.label.length === 0 || option.label.length > 80) throw new Error("Question option label is out of bounds");
        if (option.preparedAnswer.length === 0 || option.preparedAnswer.length > 500) {
          throw new Error("Question option prepared answer is out of bounds");
        }
        if (option.defer === true) defers += 1;
      }
      if (defers > 1) throw new Error("Question card may contain at most one defer option");
    } else if (block.type === "taskCard") {
      nonEmpty(block.taskId, "task ID");
    } else if (block.type === "goalLink") {
      nonEmpty(block.goalId, "goal ID");
      if (block.summary.length === 0 || block.summary.length > 200) throw new Error("Goal summary is out of bounds");
    } else if (block.type === "captureLink") {
      nonEmpty(block.conversationId, "conversation ID");
      if (block.summary.length === 0 || block.summary.length > 200) throw new Error("Capture summary is out of bounds");
      if (block.momentTimestampMs !== undefined && (!Number.isSafeInteger(block.momentTimestampMs) || block.momentTimestampMs < 0)) {
        throw new Error("Capture moment timestamp is invalid");
      }
    }
    return structuredClone(block);
  });
}

function validateResources(resources: readonly ConversationResource[]): ConversationResource[] {
  const ids = new Set<string>();
  return resources.map((resource) => {
    const id = nonEmpty(resource.id, "resource id");
    nonEmpty(resource.title, "resource title");
    if (ids.has(id)) throw new Error(`Duplicate resource ID ${id}`);
    ids.add(id);
    return structuredClone(resource);
  });
}

function mergeById<T extends { id: string }>(current: readonly T[], updates: readonly T[]): T[] {
  const result = current.map((value) => structuredClone(value));
  const indexes = new Map(result.map((value, index) => [value.id, index]));
  for (const value of updates) {
    const index = indexes.get(value.id);
    if (index === undefined) {
      indexes.set(value.id, result.length);
      result.push(structuredClone(value));
    } else {
      result[index] = structuredClone(value);
    }
  }
  return result;
}

function assertTurnStatusTransition(from: ConversationTurnStatus, to: ConversationTurnStatus): void {
  const allowed: Record<ConversationTurnStatus, readonly ConversationTurnStatus[]> = {
    pending: ["pending", "streaming", "completed", "failed"],
    streaming: ["streaming", "completed", "failed"],
    completed: ["completed"],
    failed: ["failed"],
  };
  if (!allowed[from].includes(to)) throw new Error(`Invalid journal turn status transition ${from} -> ${to}`);
}

function terminalTurnStatus(status: ConversationTurnStatus): boolean {
  return status === "completed" || status === "failed";
}

function journalTerminalStatus(runStatus: unknown, attemptStatus: unknown): ConversationTurnStatus {
  const terminal = new Set(["succeeded", "failed", "cancelled", "timed_out", "orphaned"]);
  const run = String(runStatus);
  const attempt = String(attemptStatus);
  if (!terminal.has(run) || !terminal.has(attempt)) {
    throw new Error("Journal terminalization requires a terminal canonical run and attempt");
  }
  if ((run === "succeeded") !== (attempt === "succeeded")) {
    throw new Error("Journal terminalization run and attempt outcomes disagree");
  }
  return run === "succeeded" ? "completed" : "failed";
}

function boundedLimit(limit: number): number {
  if (!Number.isInteger(limit) || limit <= 0) throw new Error("Journal list limit must be a positive integer");
  return Math.min(limit, MAX_DRAIN_BATCH);
}

function boundedErrorCode(value: string): string {
  const code = nonEmpty(value, "errorCode");
  if (code.length > 128 || !/^[A-Za-z0-9_.:-]+$/.test(code)) {
    throw new Error("Backend turn failure requires a bounded error code, not a raw error message");
  }
  return code;
}

function boundedReconcileCursor(value: string | null, label: string): string | null {
  if (value === null) return null;
  if (typeof value !== "string") throw new Error(`Backend reconcile ${label} must be a string or null`);
  const cursor = value.trim();
  if (!cursor || Buffer.byteLength(cursor, "utf8") > MAX_BACKEND_RECONCILE_CURSOR_BYTES) {
    throw new Error(`Backend reconcile ${label} is empty or unbounded`);
  }
  return cursor;
}

function validObjectJson(raw: string, field: string): string {
  const parsed = parseObjectJson(raw);
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${field} must contain a JSON object`);
  }
  return JSON.stringify(parsed);
}

function parseObjectJson(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
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

function sha256(value: string): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function journalTurnPayloadHash(value: Record<string, unknown>): string {
  return sha256(stableJson(value));
}

function backendTurnPayload(turn: ConversationTurn): BackendTurnPayload {
  const metadata = parseObjectJson(turn.metadataJson) as Record<string, unknown>;
  const backendMetadata = {
    ...metadata,
    ...(turn.contentBlocks.length > 0 ? { content_blocks: turn.contentBlocks } : {}),
    ...(turn.resources.length > 0 ? { resources: turn.resources } : {}),
  };
  const projectedText = turn.content.trim()
    ? turn.content
    : turn.role === "assistant"
      && turn.status === "completed"
      && (turn.contentBlocks.length > 0 || turn.resources.length > 0)
      ? "Done."
      : "";
  return {
    turnId: turn.turnId,
    clientMessageId: turn.turnId,
    journalRevision: boundedJournalRevision(turn.turnSeq),
    text: projectedText,
    sender: turn.role === "user" ? "human" : "ai",
    appId: typeof metadata.appId === "string" ? metadata.appId : null,
    sessionId: typeof metadata.sessionId === "string" ? metadata.sessionId : null,
    metadata: Object.keys(backendMetadata).length === 0 ? null : stableJson(backendMetadata),
    messageSource: turn.origin === "realtime_voice" ? "realtime_voice" : "desktop_chat",
  };
}

function boundedJournalRevision(revision: number): number {
  if (!Number.isSafeInteger(revision) || revision < 1 || revision > MAX_JOURNAL_REVISION) {
    throw new Error(`Journal revision must be between 1 and ${MAX_JOURNAL_REVISION}`);
  }
  return revision;
}

function backendTombstoneCode(turn: ConversationTurn): string | null {
  const payload = backendTurnPayload(turn);
  if (payload.text.trim()) return null;
  if (turn.status === "failed") return "empty_failed_turn_cancelled";
  if (turn.status === "completed") return "empty_completed_turn_cancelled";
  return null;
}

function backendTurnPayloadHash(payload: BackendTurnPayload): string {
  return sha256(stableJson(payload));
}

function historicalBackendPayloadTurnSeq(
  store: AgentStore,
  input: {
    conversationId: string;
    turnId: string;
    conversationGeneration: number;
    payloadHash: string;
  },
): number | null {
  const rows = store.allRows(
    `SELECT turn_json FROM conversation_turn_revisions
     WHERE conversation_id = ? AND turn_id = ? AND generation = ?
     ORDER BY turn_seq DESC`,
    [input.conversationId, input.turnId, input.conversationGeneration],
  );
  for (const row of rows) {
    const parsed = JSON.parse(String(row.turn_json)) as ConversationTurn;
    if (parsed.conversationId !== input.conversationId || parsed.turnId !== input.turnId) {
      throw new Error("Backend sync result history has inconsistent turn identity");
    }
    if (backendTurnPayloadHash(backendTurnPayload(parsed)) === input.payloadHash) {
      return parsed.turnSeq;
    }
  }
  return null;
}

function nextJournalSequence(
  store: AgentStore,
  conversationId: string,
  nowMs: number,
): { generation: number; turnSeq: number } {
  store.execute(
    `INSERT INTO conversation_journal_state(
       conversation_id, generation, high_water_turn_seq, updated_at_ms
     ) VALUES (?, 1, 1, ?)
     ON CONFLICT(conversation_id) DO UPDATE SET
       high_water_turn_seq = conversation_journal_state.high_water_turn_seq + 1,
       updated_at_ms = excluded.updated_at_ms`,
    [conversationId, nowMs],
  );
  const state = requireJournalState(store, conversationId);
  return { generation: state.generation, turnSeq: state.highWaterTurnSeq };
}

function ensureJournalState(
  store: AgentStore,
  conversationId: string,
  nowMs: number,
): { generation: number; generationBaseTurnSeq: number; highWaterTurnSeq: number } {
  store.execute(
    `INSERT INTO conversation_journal_state(
       conversation_id, generation, high_water_turn_seq, updated_at_ms
     ) SELECT ?, 1, COALESCE(MAX(turn_seq), 0), ?
       FROM conversation_turns WHERE conversation_id = ?
     ON CONFLICT(conversation_id) DO NOTHING`,
    [conversationId, nowMs, conversationId],
  );
  return requireJournalState(store, conversationId);
}

function assertJournalMigrationIdentityAvailable(
  store: AgentStore,
  destinationConversationId: string,
  sourceTurns: readonly ConversationTurn[],
): void {
  for (const turn of sourceTurns) {
    if (store.getOptionalRow(
      "SELECT 1 FROM conversation_turns WHERE conversation_id = ? AND turn_id = ?",
      [destinationConversationId, turn.turnId],
    )) {
      throw new Error(`Journal migration turn identity collision: ${turn.turnId}`);
    }
    if (store.getOptionalRow(
      "SELECT 1 FROM conversation_turns WHERE conversation_id = ? AND producer_id = ?",
      [destinationConversationId, turn.producerId],
    )) {
      throw new Error(`Journal migration producer identity collision: ${turn.producerId}`);
    }
    if (turn.remoteId && store.getOptionalRow(
      "SELECT 1 FROM conversation_turns WHERE conversation_id = ? AND remote_id = ?",
      [destinationConversationId, turn.remoteId],
    )) {
      throw new Error(`Journal migration remote identity collision: ${turn.remoteId}`);
    }
  }
}

function journalMutationKind(value: unknown): "recorded" | "updated" | "imported" {
  if (value === "recorded" || value === "updated" || value === "imported") return value;
  throw new Error("Journal migration encountered an invalid revision mutation kind");
}

function migratedJournalRevisionTurn(
  row: Record<string, unknown>,
  current: ConversationTurn,
  destinationConversationId: string,
  destinationTurnSeq: number,
): ConversationTurn {
  let parsed: Record<string, unknown>;
  try {
    const candidate = JSON.parse(String(row.turn_json)) as unknown;
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) throw new Error("not an object");
    parsed = candidate as Record<string, unknown>;
  } catch {
    throw new Error(`Journal migration encountered an invalid revision for ${current.turnId}`);
  }
  if (String(parsed.turnId ?? current.turnId) !== current.turnId) {
    throw new Error("Journal migration revision turn identity does not match its current turn");
  }
  const role = parsed.role ?? current.role;
  if (role !== "user" && role !== "assistant") throw new Error("Journal migration revision has an invalid role");
  const status = parsed.status ?? current.status;
  if (status !== "pending" && status !== "streaming" && status !== "completed" && status !== "failed") {
    throw new Error("Journal migration revision has an invalid status");
  }
  const contentBlocks = validateContentBlocks(
    Array.isArray(parsed.contentBlocks) ? parsed.contentBlocks as ConversationContentBlock[] : current.contentBlocks,
  );
  const resources = validateResources(
    Array.isArray(parsed.resources) ? parsed.resources as ConversationResource[] : current.resources,
  );
  const metadataJson = validObjectJson(String(parsed.metadataJson ?? current.metadataJson), "metadataJson");
  return {
    conversationId: destinationConversationId,
    turnId: current.turnId,
    turnSeq: destinationTurnSeq,
    producerId: String(parsed.producerId ?? row.producer_id ?? current.producerId),
    payloadHash: String(parsed.payloadHash ?? row.payload_hash ?? current.payloadHash),
    role,
    surfaceKind: String(parsed.surfaceKind ?? current.surfaceKind),
    content: String(parsed.content ?? current.content),
    origin: (parsed.origin ?? current.origin) as ConversationTurnOrigin,
    status,
    contentBlocks,
    resources,
    producingRunId: parsed.producingRunId === undefined
      ? current.producingRunId
      : parsed.producingRunId == null ? null : String(parsed.producingRunId),
    producingAttemptId: parsed.producingAttemptId === undefined
      ? current.producingAttemptId
      : parsed.producingAttemptId == null ? null : String(parsed.producingAttemptId),
    remoteId: parsed.remoteId === undefined
      ? current.remoteId
      : parsed.remoteId == null ? null : String(parsed.remoteId),
    createdAtMs: Number(parsed.createdAtMs ?? current.createdAtMs),
    updatedAtMs: Number(parsed.updatedAtMs ?? current.updatedAtMs),
    completedAtMs: parsed.completedAtMs === undefined
      ? current.completedAtMs
      : parsed.completedAtMs == null ? null : Number(parsed.completedAtMs),
    metadataJson,
  };
}

function requireJournalState(
  store: AgentStore,
  conversationId: string,
): { generation: number; generationBaseTurnSeq: number; highWaterTurnSeq: number } {
  const row = store.getRow(
    `SELECT generation, generation_base_turn_seq, high_water_turn_seq
     FROM conversation_journal_state WHERE conversation_id = ?`,
    [conversationId],
  );
  return {
    generation: Number(row.generation),
    generationBaseTurnSeq: Number(row.generation_base_turn_seq ?? 0),
    highWaterTurnSeq: Number(row.high_water_turn_seq),
  };
}

function appendJournalRevision(
  store: AgentStore,
  turn: ConversationTurn,
  generation: number,
  mutationKind: "recorded" | "updated" | "imported",
  nowMs: number,
): void {
  store.execute(
    `INSERT INTO conversation_turn_revisions(
       conversation_id, turn_seq, generation, turn_id, producer_id,
       mutation_kind, turn_json, payload_hash, created_at_ms
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      turn.conversationId,
      turn.turnSeq,
      generation,
      turn.turnId,
      turn.producerId,
      mutationKind,
      JSON.stringify(turn),
      turn.payloadHash,
      nowMs,
    ],
  );
}

function nonEmpty(value: string, field: string): string {
  const trimmed = value.trim();
  if (!trimmed) throw new Error(`${field} must not be empty`);
  return trimmed;
}

function countRows<T extends string>(rows: Record<string, unknown>[]): Partial<Record<T, number>> {
  const result: Partial<Record<T, number>> = {};
  for (const row of rows) result[String(row.status) as T] = Number(row.count);
  return result;
}
