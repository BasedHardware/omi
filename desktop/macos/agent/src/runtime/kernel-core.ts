import type {
  AdapterAttemptResult,
  AdapterBindingHandle,
  CancelDispatchResult,
  OpenedBinding,
  RuntimeAdapter,
} from "../adapters/interface.js";
import type { ContextSnapshotProjection, OutboundMessage, OutboundMessageDraft } from "../protocol.js";
import { AdapterRegistry } from "./adapter-registry.js";
import { generateAgentId } from "./sqlite-store.js";
import { AdapterRuntimeError, failureFromError, type RuntimeFailure } from "./failures.js";
import {
  clearOwnerSurfaceState,
  importLegacyMainChatSessions,
  resolveSurfaceSession,
  type LegacyMainChatSessionEntry,
  type ResolveSurfaceSessionInput,
} from "./surface-session.js";
import {
  conversationIdForOwnedSurfaceSession,
  conversationIdForSession,
} from "./conversation-turns.js";
import {
  buildContextSnapshot,
  inheritContextSnapshotForSession,
  kernelSystemPolicy,
  renderContextSnapshot,
} from "./context-snapshot.js";
import { repairPersistedAgentSpawnJournals } from "./agent-spawn-journal.js";
import {
  bindProducingJournalTurn,
  searchJournalConversation,
  validateProducingJournalTurnAdmission,
} from "./conversation-journal.js";
import type {
  AdapterBinding,
  AgentArtifact,
  AgentDelegation,
  AgentEvent,
  AgentRun,
  AgentSession,
  AgentStore,
  AgentGrant,
  NewAgentArtifact,
  NewAgentGrant,
  RunAttempt,
  RunStatus,
  AttemptStatus,
  DelegationStatus,
  DesktopAttentionOverride,
  NewDesktopCoordinatorDispatch,
  DesktopCoordinatorDispatch,
  DesktopArtifactDelivery,
  DesktopMemoryCandidate,
  DesktopTaskCandidate,
} from "./types.js";
import type { QueueRunInput } from "./desktop-action-queue.js";
import { buildDesktopActionQueue } from "./desktop-action-queue.js";
import type { DesktopContextPacketBuildInput } from "./desktop-context-packet.js";
import type { DesktopIntentSessionCandidate } from "./desktop-intent-router.js";
import { OmiArtifactStorage } from "./artifact-storage.js";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import {
  ACTIVE_STATUSES,
  TERMINAL_STATUSES,
  DEFAULT_DELEGATION_MAX_DEPTH,
  HARD_DELEGATION_MAX_DEPTH,
  DEFAULT_DELEGATION_MAX_BUDGET_USD,
  HARD_DELEGATION_MAX_BUDGET_USD,
  requiresVerifiedContextDispatch,
  bindingMetadata,
  stableHash,
  stableJsonStringify,
  stableMcpServerConfig,
  stableJsonHash,
  parseJsonObject,
  placeholders,
  isStaleBindingError,
  messageFrom,
  boundedLimit,
  sessionFromRow,
  runFromRow,
  delegationFromRow,
  delegationValues,
  buildDelegatedPrompt,
  requiredChildSessionId,
  attemptFromRow,
  bindingFromRow,
  eventFromRow,
  artifactFromRow,
  desktopDispatchFromRow,
  desktopArtifactDeliveryFromRow,
  desktopMemoryCandidateFromRow,
  desktopTaskCandidateFromRow,
  desktopAttentionOverrideFromRow,
  dispatchToQueueInput,
  deliveryToQueueInput,
  memoryCandidateToQueueInput,
  taskCandidateToQueueInput,
  overrideToQueueInput,
  intentCandidateStatus,
  updateByColumns,
  queueRunGoalText,
  stringValue,
  numberValue,
  nullableString,
  nullableNumber,
  nullableText,
  text,
  refreshMcpAttemptContext,
  mcpServersForBinding,
  canonicalAdapterEventType,
  runColumnMap,
  attemptColumnMap,
  bindingColumnMap,
} from "./kernel-support.js";
import type {
  KernelSessionResolutionInput,
  ExecuteAgentRunInput,
  KernelRunResult,
  CancelRunResult,
  ListSessionsInput,
  KernelSessionSummary,
  GetRunInput,
  KernelRunDetails,
  InspectArtifactsInput,
  PersistArtifactInput,
  UpdateArtifactLifecycleInput,
  SendAgentMessageInput,
  SpawnBackgroundAgentInput,
  SpawnBackgroundAgentResult,
  DelegateAgentInput,
  DelegateAgentResult,
  BeginExternalSurfaceRunInput,
  BeginExternalSurfaceRunResult,
  CompleteExternalSurfaceRunInput,
  CompleteExternalSurfaceRunResult,
  KernelEventSubscriber,
  AgentRuntimeKernelOptions,
} from "./kernel-types.js";
import { ExternalSurfaceAuthorityError, StaleAdapterBindingError } from "./kernel-types.js";
import { providerBoundaryForAdapter, resolveAdapterWithinBoundary } from "./execution-policy.js";
import type { SurfaceRef } from "./surface-session.js";

function runtimeAdapterMetadata(input: ExecuteAgentRunInput, session: AgentSession): Record<string, unknown> {
  return {
    ...(input.metadata ?? {}),
    executionRole: session.executionRole,
    providerBoundary: session.providerBoundary,
    surfaceKind: session.surfaceKind,
    chatFirstUi: input.admittedContextSnapshot?.capabilities.chatFirstUi === true,
    chatFirstControlGeneration:
      input.admittedContextSnapshot?.capabilities.chatFirstControlGeneration ?? null,
  };
}
import {
  RunToolCapabilityBroker,
  type AuthorizedRunToolInvocation,
  type RunToolExecutionLease,
  type RunToolCapabilityRevocationReason,
} from "./run-tool-capability.js";
import type { ToolInvocationIdentity } from "./tool-invocation-ledger.js";
import { normalizeOmiToolName } from "./omi-tool-manifest.js";
import { routeExternalSurfaceTool } from "./external-surface-tool-policy.js";
import {
  applyExecutionProfileToSession,
  readSessionExecutionProfile,
} from "./session-execution-profile.js";


interface ActiveExecution {
  adapter: RuntimeAdapter;
  abortController: AbortController;
  binding: AdapterBindingHandle;
  attemptId: string;
  sessionId: string;
}

export class KernelCore {
  protected readonly store: AgentStore;
  protected readonly registry: AdapterRegistry;
  protected readonly runtimeNodeId: string;
  protected readonly artifactStorage?: OmiArtifactStorage;
  protected readonly recoverRunInput?: AgentRuntimeKernelOptions["recoverRunInput"];
  protected readonly subscribers = new Set<KernelEventSubscriber>();
  protected readonly activeExecutions = new Map<string, ActiveExecution>();
  protected readonly bindingResolutionLocks = new Map<string, Promise<void>>();
  protected readonly toolCapabilities: RunToolCapabilityBroker;
  private transactionDepth = 0;
  private pendingSubscriberEvents: AgentEvent[] = [];

  constructor(options: AgentRuntimeKernelOptions) {
    this.store = options.store;
    this.registry = options.registry;
    this.runtimeNodeId = options.runtimeNodeId ?? "desktop-local";
    this.artifactStorage = options.artifactStorage;
    this.recoverRunInput = options.recoverRunInput;
    this.toolCapabilities = new RunToolCapabilityBroker({
      store: this.store,
      onRejected: options.onToolCapabilityRejected,
      profileForSession: options.toolCapabilityProfileForSession ?? ((sessionId) => {
        const profile = readSessionExecutionProfile(this.store, sessionId);
        return {
          generation: profile.generation,
          adapterId: profile.adapterId,
          executionRole: profile.executionRole,
        };
      }),
    });
    repairPersistedAgentSpawnJournals(this.store);
  }

  authorizeRunToolInvocation(input: {
    capabilityRef: string;
    invocationId: string;
    runId: string;
    attemptId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): AuthorizedRunToolInvocation {
    return this.toolCapabilities.authorize(input);
  }

  authorizeRelayedRunToolInvocation(input: {
    capabilityRef: string;
    invocationId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): AuthorizedRunToolInvocation {
    return this.toolCapabilities.authorizeRelayInvocation(input);
  }

  routeRelayedRunToolProposal(input: {
    capabilityRef: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): { toolName: string; toolInput: Record<string, unknown>; recoveredFromDelegation: boolean } {
    const capability = this.toolCapabilities.activeCapabilityForProposal(input.capabilityRef, input.activeOwnerId);
    const adapter = capability.adapterId === "pi-mono" ? "pi-mono" : "omi-tools-stdio";
    const canonicalToolName = normalizeOmiToolName(adapter, requiredExternalIdentity(input.toolName, "toolName"))
      .canonicalName;
    const decision = routeExternalSurfaceTool({
      toolName: canonicalToolName,
      toolInput: input.toolInput,
      originatingPrompt: capability.originatingUserText,
      precedingAssistantText: capability.precedingAssistantText,
    });
    if (decision.action === "reject") {
      throw new ExternalSurfaceAuthorityError(decision.code, decision.message);
    }
    return decision;
  }

  assertLiveRunToolCapability(input: { capabilityRef: string; activeOwnerId: string }) {
    return this.toolCapabilities.assertLiveCapability(input.capabilityRef, input.activeOwnerId);
  }

  /**
   * Parent-kernel dispatch for the chat-first local history tool. The stdio
   * child only relays its request; this method requires the already-admitted
   * one-use invocation before it can read the caller's journal.
   */
  searchAuthorizedChatHistory(input: {
    invocation: AuthorizedRunToolInvocation;
    toolInput: Record<string, unknown>;
    activeOwnerId: () => string;
  }) {
    const { invocation } = input;
    if (
      invocation.canonicalToolName !== "search_chat_history"
      || invocation.surfaceKind !== "main_chat"
      || invocation.chatFirstUi !== true
      || !Number.isSafeInteger(invocation.chatFirstControlGeneration)
      || invocation.tool.executor.kind !== "nodeTool"
    ) {
      throw new Error("search_chat_history requires an enabled main-Chat tool capability");
    }
    const toolInput = chatHistorySearchToolInput(input.toolInput);
    const lease = this.acquireRunToolExecutionLease(invocation, input.activeOwnerId);
    try {
      lease.assertCurrentAuthority();
      const session = this.readSession(invocation.sessionId);
      this.assertSessionOwner(session, invocation.ownerId);
      if (session.surfaceKind !== "main_chat") {
        throw new Error("search_chat_history requires the caller's main Chat session");
      }
      if (invocation.externalRefKind !== "chat" || !invocation.externalRefId) {
        throw new Error("search_chat_history requires the caller's canonical Chat reference");
      }
      const conversationId = conversationIdForOwnedSurfaceSession(this.store, {
        ownerId: invocation.ownerId,
        sessionId: session.sessionId,
        surfaceKind: "main_chat",
        externalRefKind: invocation.externalRefKind,
        externalRefId: invocation.externalRefId,
      });
      if (!conversationId) throw new Error("search_chat_history requires an exact canonical Chat conversation");
      const matches = searchJournalConversation(this.store, {
        ownerId: invocation.ownerId,
        conversationId,
        ...toolInput,
      });
      lease.assertCurrentAuthority();
      return { matches };
    } finally {
      lease.release();
    }
  }

  markRunToolInvocationDispatched(invocation: AuthorizedRunToolInvocation): void {
    this.toolCapabilities.markInvocationDispatched(invocation);
  }

  acquireRunToolExecutionLease(
    invocation: AuthorizedRunToolInvocation,
    activeOwnerId: () => string,
  ): RunToolExecutionLease {
    return this.toolCapabilities.acquireExecutionLease(invocation, activeOwnerId);
  }

  completeRunToolInvocation(input: ToolInvocationIdentity & {
    capabilityRef: string;
    activeOwnerId: string;
    outcome: "succeeded" | "failed";
    result: string;
  }): void {
    this.toolCapabilities.completeInvocation(input);
  }

  markRunToolInvocationOutcomeUnknown(
    invocation: AuthorizedRunToolInvocation,
    errorCode: string,
  ): void {
    this.toolCapabilities.markInvocationOutcomeUnknown(invocation, errorCode);
  }

  revokeRunToolCapabilities(reason: RunToolCapabilityRevocationReason = "runtime_stopped"): number {
    return this.toolCapabilities.revokeAll(reason);
  }

  revokeRunToolCapabilitiesForOwner(
    ownerId: string,
    reason: RunToolCapabilityRevocationReason = "owner_changed",
  ): number {
    return this.toolCapabilities.revokeForOwner(ownerId, reason);
  }

  beginExternalSurfaceRun(input: BeginExternalSurfaceRunInput): BeginExternalSurfaceRunResult {
    const ownerId = requiredExternalIdentity(input.ownerId, "ownerId");
    const sessionId = requiredExternalIdentity(input.sessionId, "sessionId");
    const turnId = requiredExternalIdentity(input.turnId, "turnId");
    const clientId = requiredExternalIdentity(input.clientId, "clientId");
    const requestId = requiredExternalIdentity(input.requestId, "requestId");
    if (!input.prompt.trim()) {
      throw new ExternalSurfaceAuthorityError("invalid_external_request", "External surface prompt is required");
    }
    if (input.mode !== "ask" && input.mode !== "act") {
      throw new ExternalSurfaceAuthorityError("invalid_external_request", "External surface mode is invalid");
    }
    const session = this.readSession(sessionId);
    if (session.ownerId !== ownerId) {
      throw new ExternalSurfaceAuthorityError("owner_mismatch", "External surface session owner does not match");
    }
    this.assertExternalRealtimeMapping(sessionId, ownerId);

    const idempotencyKey = `external_surface:${stableHash(turnId)}`;
    const existingRow = this.store.getOptionalRow(
      "SELECT * FROM runs WHERE session_id = ? AND idempotency_key = ?",
      [sessionId, idempotencyKey],
    );
    let duplicate = false;
    let run: AgentRun;
    let attempt: RunAttempt;
    if (existingRow) {
      duplicate = true;
      run = runFromRow(existingRow);
      this.assertExternalRunIdentity(run, { ownerId, sessionId, turnId, prompt: input.prompt, mode: input.mode });
      const latestAttemptRow = this.store.getOptionalRow(
        "SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1",
        [run.runId],
      );
      if (TERMINAL_STATUSES.includes(run.status) && run.status !== "orphaned") {
        if (!latestAttemptRow) {
          throw new ExternalSurfaceAuthorityError("run_terminal", "External surface run is terminal without an attempt");
        }
        attempt = attemptFromRow(latestAttemptRow);
        return { ownerId, sessionId, turnId, runId: run.runId, attemptId: attempt.attemptId, duplicate };
      }
      const latestAttempt = latestAttemptRow ? attemptFromRow(latestAttemptRow) : undefined;
      if (run.status === "orphaned" || !latestAttempt || TERMINAL_STATUSES.includes(latestAttempt.status)) {
        this.withTransaction(() => {
          this.updateRun(run.runId, {
            status: "queued",
            completedAtMs: null,
            errorCode: null,
            errorMessage: null,
            updatedAtMs: Date.now(),
          });
        });
        attempt = this.createAttempt({
          runId: run.runId,
          attemptNo: (latestAttempt?.attemptNo ?? 0) + 1,
          adapterId: session.defaultAdapterId,
          retryReason: latestAttempt ? "daemon_restart_external_surface" : null,
          resumeFromAttemptId: latestAttempt?.attemptId ?? null,
        });
        this.markExternalAttemptRunning(session, attempt);
      } else {
        attempt = latestAttempt;
      }
    } else {
      const accepted = this.createAcceptedRun({
        ownerId,
        sessionId,
        surfaceKind: "realtime_voice",
        clientId,
        requestId,
        idempotencyKey,
        prompt: input.prompt,
        mode: input.mode,
        metadata: {
          externalSurface: { authority: "swift_realtime", turnId },
        },
      });
      run = accepted.run;
      attempt = this.createAttempt({
        runId: run.runId,
        attemptNo: 1,
        adapterId: session.defaultAdapterId,
        retryReason: null,
        resumeFromAttemptId: null,
      });
      this.markExternalAttemptRunning(session, attempt);
    }
    this.toolCapabilities.register({ ownerId, sessionId, runId: run.runId, attemptId: attempt.attemptId });
    return { ownerId, sessionId, turnId, runId: run.runId, attemptId: attempt.attemptId, duplicate };
  }

  authorizeExternalSurfaceToolInvocation(input: {
    ownerId: string;
    sessionId: string;
    runId: string;
    attemptId: string;
    invocationId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): AuthorizedRunToolInvocation {
    this.assertExternalRunTuple(input);
    const capability = this.toolCapabilities.activeCapabilityForAttempt(input.attemptId)
      ?? this.toolCapabilities.register({
        ownerId: input.ownerId,
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
      });
    return this.toolCapabilities.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: requiredExternalIdentity(input.invocationId, "invocationId"),
      runId: input.runId,
      attemptId: input.attemptId,
      toolName: requiredExternalIdentity(input.toolName, "toolName"),
      toolInput: input.toolInput,
      activeOwnerId: input.activeOwnerId,
    });
  }

  routeExternalSurfaceToolInvocation(input: {
    ownerId: string;
    sessionId: string;
    runId: string;
    attemptId: string;
    invocationId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
  }): { toolName: string; toolInput: Record<string, unknown>; recoveredFromDelegation: boolean } {
    const { session, run } = this.assertExternalRunTuple(input);
    const adapter = session.defaultAdapterId === "pi-mono" ? "pi-mono" : "omi-tools-stdio";
    const canonicalToolName = normalizeOmiToolName(adapter, requiredExternalIdentity(input.toolName, "toolName"))
      .canonicalName;
    const runInput = parseJsonObject(run.inputJson);
    const decision = routeExternalSurfaceTool({
      toolName: canonicalToolName,
      toolInput: input.toolInput,
      originatingPrompt: typeof runInput.prompt === "string" ? runInput.prompt : "",
      precedingAssistantText: this.toolCapabilities.activeCapabilityForAttempt(input.attemptId)?.precedingAssistantText,
    });
    if (decision.action === "reject") {
      throw new ExternalSurfaceAuthorityError(decision.code, decision.message);
    }
    if (decision.toolName !== "spawn_agent") return decision;
    const prepared = this.prepareAuthorizedSpawnAgentControlInvocation({
      ownerId: input.ownerId,
      sessionId: input.sessionId,
      runId: input.runId,
      attemptId: input.attemptId,
      invocationId: input.invocationId,
      surfaceKind: "realtime_voice",
      toolInput: decision.toolInput,
    });
    return {
      ...decision,
      toolInput: prepared.toolInput,
    };
  }

  prepareAuthorizedSpawnAgentControlInvocation(input: {
    ownerId: string;
    sessionId: string;
    runId: string;
    attemptId: string;
    invocationId: string;
    surfaceKind: string;
    toolInput: Record<string, unknown>;
  }): {
    toolInput: Record<string, unknown>;
    producerJournal: import("./agent-spawn-journal.js").AgentSpawnProducerJournalDescriptor;
    parentRunId: string;
  } {
    const session = this.readSession(input.sessionId);
    const run = this.readRun(input.runId);
    const attempt = this.readAttempt(input.attemptId);
    if (session.ownerId !== input.ownerId || run.sessionId !== session.sessionId || attempt.runId !== run.runId) {
      throw new Error("Authorized spawn caller tuple is outside owner/session scope");
    }
    if (this.readLatestAttempt(run.runId).attemptId !== attempt.attemptId) {
      throw new Error("Authorized spawn caller attempt was superseded");
    }
    const objective = typeof input.toolInput.objective === "string"
      ? input.toolInput.objective.trim()
      : typeof input.toolInput.brief === "string"
        ? input.toolInput.brief.trim()
        : "";
    if (!objective) throw new Error("Authorized spawn objective is required");
    const producerSurface = this.store.getOptionalRow(
      `SELECT surface_kind, external_ref_kind, external_ref_id
       FROM surface_conversations
       WHERE owner_id = ? AND agent_session_id = ?
       ORDER BY CASE WHEN surface_kind = ? THEN 0 ELSE 1 END,
                last_active_at_ms DESC LIMIT 1`,
      [input.ownerId, input.sessionId, input.surfaceKind],
    );
    if (!producerSurface) throw new Error("Authorized spawn caller has no exact journal surface");
    const runInput = parseJsonObject(run.inputJson);
    const runMetadata = runInput.metadata;
    const externalSurface = runMetadata && typeof runMetadata === "object" && !Array.isArray(runMetadata)
      ? (runMetadata as Record<string, unknown>).externalSurface
      : undefined;
    const externalTurnId = externalSurface && typeof externalSurface === "object" && !Array.isArray(externalSurface)
      ? String((externalSurface as Record<string, unknown>).turnId ?? "").trim()
      : "";
    const producerTurnId = typeof runInput.producingTurnId === "string"
      ? runInput.producingTurnId.trim()
      : "";
    const pillId = stableExternalSpawnPillId(requiredExternalIdentity(input.invocationId, "invocationId"));
    const proposedTitle = typeof input.toolInput.title === "string" ? input.toolInput.title.trim() : "";
    const title = proposedTitle || `Delegated: ${objective.slice(0, 80)}`;
    const suppliedMetadata = input.toolInput.metadata;
    const metadata = suppliedMetadata && typeof suppliedMetadata === "object" && !Array.isArray(suppliedMetadata)
      ? { ...(suppliedMetadata as Record<string, unknown>) }
      : {};
    delete metadata.producerJournal;
    const surfaceKind = String(producerSurface.surface_kind);
    const originSurfaceKind = surfaceKind === "main_chat" ? "main_chat"
      : surfaceKind === "task_chat" ? "task_chat"
        : ["realtime", "realtime_voice"].includes(surfaceKind) ? "realtime"
          : ["floating_chat", "floating_bar"].includes(surfaceKind) ? "floating_bar"
            : "agent_control";
    const producerJournal = {
      schemaVersion: 1 as const,
      surface: {
        surfaceKind,
        externalRefKind: String(producerSurface.external_ref_kind),
        externalRefId: String(producerSurface.external_ref_id),
      },
      continuityKey: externalTurnId
        ? `voice:${externalTurnId.toLowerCase()}`
        : `agent_spawn:${input.invocationId}`,
      pillId,
      ...(producerTurnId ? { producerRunId: run.runId, producerTurnId } : {}),
      userText: typeof runInput.prompt === "string" ? runInput.prompt : "",
      assistantText: "I started a background agent for that.",
      objective,
      title,
    };
    return {
      parentRunId: run.runId,
      producerJournal,
      toolInput: {
        ...input.toolInput,
        originSurfaceKind,
        parentRunId: run.runId,
        externalRefId: pillId,
        title,
        metadata: { ...metadata, producerJournal },
      },
    };
  }

  completeExternalSurfaceRun(input: CompleteExternalSurfaceRunInput): CompleteExternalSurfaceRunResult {
    if (!(["completed", "failed", "cancelled"] as const).includes(input.terminalStatus)) {
      throw new ExternalSurfaceAuthorityError("invalid_external_request", "External terminalStatus is invalid");
    }
    const { run, attempt } = this.assertExternalRunTuple(input);
    const persistedStatus = input.terminalStatus === "completed" ? "succeeded" : input.terminalStatus;
    if (TERMINAL_STATUSES.includes(run.status) || TERMINAL_STATUSES.includes(attempt.status)) {
      if (run.status === persistedStatus && attempt.status === persistedStatus) {
        return { ...input, duplicate: true };
      }
      throw new ExternalSurfaceAuthorityError("run_terminal", "External surface run already has a different terminal state");
    }
    const pendingInvocations = Number(this.store.getRow(
      `SELECT COUNT(*) AS count FROM tool_invocation_ledger
       WHERE run_id = ? AND attempt_id = ? AND status IN ('prepared', 'dispatched')`,
      [input.runId, input.attemptId],
    ).count);
    if (pendingInvocations > 0) {
      throw new ExternalSurfaceAuthorityError(
        "external_invocations_pending",
        "External surface run cannot complete while tool invocations are pending",
      );
    }
    const errorCode = input.errorCode?.trim();
    if (errorCode && !/^[a-z0-9_]{1,64}$/.test(errorCode)) {
      throw new ExternalSurfaceAuthorityError("invalid_external_request", "External surface errorCode is invalid");
    }
    this.withTransaction(() => {
      this.finishAttemptAndRun({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        status: persistedStatus,
        finalText: null,
        errorCode: persistedStatus === "failed" ? errorCode ?? "external_surface_failed" : null,
        errorMessage: persistedStatus === "failed" ? "External surface execution failed" : null,
      });
    });
    return { ...input, duplicate: false };
  }

  private assertExternalRunIdentity(
    run: AgentRun,
    expected: { ownerId: string; sessionId: string; turnId: string; prompt: string; mode: "ask" | "act" },
  ): void {
    if (run.sessionId !== expected.sessionId || run.mode !== expected.mode) {
      throw new ExternalSurfaceAuthorityError(
        "external_run_identity_collision",
        "External surface turn identity collides with a different run",
      );
    }
    const input = parseJsonObject(run.inputJson);
    const metadata = input.metadata;
    const externalSurface = metadata && typeof metadata === "object" && !Array.isArray(metadata)
      ? (metadata as Record<string, unknown>).externalSurface
      : undefined;
    if (
      input.prompt !== expected.prompt
      || !externalSurface
      || typeof externalSurface !== "object"
      || Array.isArray(externalSurface)
      || (externalSurface as Record<string, unknown>).authority !== "swift_realtime"
      || (externalSurface as Record<string, unknown>).turnId !== expected.turnId
    ) {
      throw new ExternalSurfaceAuthorityError(
        "external_run_identity_collision",
        "External surface turn identity was replayed with different input",
      );
    }
    this.assertSessionOwner(this.readSession(run.sessionId), expected.ownerId);
  }

  private assertExternalRunTuple(input: {
    ownerId: string;
    sessionId: string;
    runId: string;
    attemptId: string;
  }): { session: AgentSession; run: AgentRun; attempt: RunAttempt } {
    const ownerId = requiredExternalIdentity(input.ownerId, "ownerId");
    const sessionId = requiredExternalIdentity(input.sessionId, "sessionId");
    const runId = requiredExternalIdentity(input.runId, "runId");
    const attemptId = requiredExternalIdentity(input.attemptId, "attemptId");
    const session = this.readSession(sessionId);
    if (session.ownerId !== ownerId) {
      throw new ExternalSurfaceAuthorityError("owner_mismatch", "External surface session owner does not match");
    }
    this.assertExternalRealtimeMapping(sessionId, ownerId);
    const run = this.readRun(runId);
    if (run.sessionId !== sessionId) {
      throw new ExternalSurfaceAuthorityError("run_mismatch", "External surface run does not belong to the session");
    }
    const runInput = parseJsonObject(run.inputJson);
    const metadata = runInput.metadata;
    const externalSurface = metadata && typeof metadata === "object" && !Array.isArray(metadata)
      ? (metadata as Record<string, unknown>).externalSurface
      : undefined;
    if (
      !externalSurface
      || typeof externalSurface !== "object"
      || Array.isArray(externalSurface)
      || (externalSurface as Record<string, unknown>).authority !== "swift_realtime"
    ) {
      throw new ExternalSurfaceAuthorityError("run_mismatch", "Run is not owned by external surface authority");
    }
    const attempt = this.readAttempt(attemptId);
    if (attempt.runId !== runId) {
      throw new ExternalSurfaceAuthorityError("attempt_mismatch", "External surface attempt does not belong to the run");
    }
    const latest = this.readLatestAttempt(runId);
    if (latest.attemptId !== attemptId) {
      throw new ExternalSurfaceAuthorityError("attempt_superseded", "External surface attempt has been superseded");
    }
    return { session, run, attempt };
  }

  private markExternalAttemptRunning(session: AgentSession, attempt: RunAttempt): void {
    const now = Date.now();
    this.withTransaction(() => {
      this.updateRun(attempt.runId, { status: "running", updatedAtMs: now });
      this.updateAttempt(attempt.attemptId, {
        status: "running",
        adapterInstanceId: "swift-realtime",
        startedAtMs: now,
        metadataJson: JSON.stringify({ externalSurfaceAuthority: "swift_realtime" }),
        updatedAtMs: now,
      });
      this.appendEvent({
        sessionId: session.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: "attempt.started",
        payload: { attemptId: attempt.attemptId, authority: "swift_realtime" },
      });
      this.appendEvent({
        sessionId: session.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: "run.running",
        payload: { runId: attempt.runId, attemptId: attempt.attemptId, authority: "swift_realtime" },
      });
    });
  }

  private assertExternalRealtimeMapping(sessionId: string, ownerId: string): void {
    const mapping = this.store.getOptionalRow(
      `SELECT 1 FROM surface_conversations
       WHERE agent_session_id = ? AND owner_id = ? AND surface_kind IN ('realtime_voice', 'realtime')
       LIMIT 1`,
      [sessionId, ownerId],
    );
    if (!mapping) {
      throw new ExternalSurfaceAuthorityError(
        "invalid_external_surface",
        "External run authority requires a resolved realtime_voice surface mapping",
      );
    }
  }

  subscribe(subscriber: KernelEventSubscriber): () => void {
    this.subscribers.add(subscriber);
    return () => this.subscribers.delete(subscriber);
  }

  protected createAcceptedRun(input: ExecuteAgentRunInput): {
    session: AgentSession;
    run: AgentRun;
    contextSnapshot: ContextSnapshotProjection;
  } {
    return this.withTransaction(() => {
      const session = this.resolveSession({ ...input, modelProfile: input.model ?? input.modelProfile });
      if (input.adapterId !== undefined && input.adapterId !== session.defaultAdapterId) {
        throw new Error("Existing session execution profile rejects adapter override");
      }
      if (input.model !== undefined && input.model !== session.modelProfile) {
        throw new Error("Existing session execution profile rejects model override");
      }
      resolveAdapterWithinBoundary({
        providerBoundary: session.providerBoundary,
        defaultAdapterId: session.defaultAdapterId,
        requestedAdapterId: session.defaultAdapterId,
      });
      const contextSnapshot = input.admittedContextSnapshot
        ? inheritContextSnapshotForSession(
            this.store,
            input.admittedContextSnapshot,
            session.sessionId,
            session.ownerId,
          )
        : buildContextSnapshot(
            this.store,
            session.sessionId,
            session.ownerId,
            Date.now(),
            input.surfaceKind,
          );
      const expectationCount = [
        input.expectedContextSnapshotVersion,
        input.expectedContextSnapshotGeneration,
        input.expectedContextRendererFingerprint,
        input.expectedCapabilityVersion,
      ].filter((value) => value !== undefined).length;
      if (expectationCount !== 0 && expectationCount !== 4) {
        throw new Error("Run admission context freshness requires version, generation, renderer, and capability");
      }
      if (
        expectationCount === 4
        && (
          input.expectedContextSnapshotVersion !== contextSnapshot.version
          || input.expectedContextSnapshotGeneration !== contextSnapshot.snapshotGeneration
          || input.expectedContextRendererFingerprint !== contextSnapshot.rendererFingerprint
          || input.expectedCapabilityVersion !== contextSnapshot.capabilityVersion
        )
      ) {
        throw new Error("context_snapshot_projection_mismatch");
      }
      if (input.producingTurnId) {
        const conversationId = conversationIdForSession(this.store, session.sessionId);
        if (!conversationId) {
          throw new Error("Producing turn admission requires a canonical session conversation");
        }
        validateProducingJournalTurnAdmission(this.store, {
          ownerId: session.ownerId,
          sessionId: session.sessionId,
          conversationId,
          turnId: input.producingTurnId,
        });
      }
      const run = this.store.insertRun({
        sessionId: session.sessionId,
        parentRunId: input.parentRunId ?? null,
        clientId: input.clientId,
        requestId: input.requestId,
        idempotencyKey: input.idempotencyKey ?? null,
        status: "queued",
        mode: input.mode ?? "ask",
        profileGeneration: session.executionProfileGeneration,
        inputJson: JSON.stringify({
          prompt: input.prompt,
          producingTurnId: input.producingTurnId ?? null,
          metadata: input.metadata ?? {},
          contextSnapshotVersion: contextSnapshot.version,
          contextSnapshotGeneration: contextSnapshot.snapshotGeneration,
          contextRendererFingerprint: contextSnapshot.rendererFingerprint,
          contextCapabilityVersion: contextSnapshot.capabilityVersion,
          admittedContextSnapshot: contextSnapshot,
        }),
        modelProfile: session.modelProfile,
        requestedModelId: session.modelProfile,
        cwd: session.defaultCwd,
      });
      this.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: "run.queued",
        payload: { runId: run.runId, requestId: run.requestId, clientId: run.clientId },
      });
      this.touchSession(session.sessionId);
      return { session, run, contextSnapshot };
    });
  }

  protected async executeAcceptedRun(
    input: ExecuteAgentRunInput,
    accepted: { session: AgentSession; run: AgentRun; contextSnapshot: ContextSnapshotProjection }
  ): Promise<KernelRunResult> {

    const assertExecutionAuthority = (): void => {
      if (!input.authoritySignal?.aborted) return;
      throw input.authoritySignal.reason instanceof Error
        ? input.authoritySignal.reason
        : new Error("Run execution authority was revoked");
    };
    assertExecutionAuthority();
    input.authoritySignal?.addEventListener("abort", () => {
      this.activeExecutions.get(accepted.run.runId)?.abortController.abort(input.authoritySignal?.reason);
    }, { once: true });

    const adapterId = accepted.session.defaultAdapterId;
    input = {
      ...input,
      defaultAdapterId: adapterId,
      adapterId,
      model: accepted.session.modelProfile ?? undefined,
      cwd: accepted.session.defaultCwd ?? undefined,
      systemPrompt: kernelSystemPolicy(
        accepted.session.surfaceKind,
        accepted.session.executionRole,
        accepted.contextSnapshot.contextPlan,
      ),
      systemPromptCacheIdentity: accepted.contextSnapshot.contextPlan.stableCacheIdentity,
      dynamicContextIdentity: accepted.contextSnapshot.contextPlan.dynamicContextIdentity,
      contextPlanId: accepted.contextSnapshot.contextPlan.planId,
      admittedContextSnapshot: accepted.contextSnapshot,
    };
    if (!input.recoverAfterError) {
      const recovery = this.recoverRunInput?.(adapterId);
      if (recovery) {
        input = {
          ...input,
          maxAttempts: input.maxAttempts ?? recovery.maxAttempts,
          recoverAfterError: recovery.recoverAfterError,
        };
      }
    }
    const maxAttempts = Math.max(1, input.maxAttempts ?? 2);
    let retryReason: string | null = null;
    let resumeFromAttemptId: string | null = null;
    let lastAttempt: RunAttempt | undefined;
    let completionDeltaArtifacts: AgentArtifact[] = [];
    const surfaceRef = this.surfaceRefForInput(input);
    const conversationId = conversationIdForSession(this.store, accepted.session.sessionId);
    if (input.producingTurnId && !conversationId) {
      throw new Error("Producing turn admission lost its canonical session conversation");
    }

    for (let attemptNo = 1; attemptNo <= maxAttempts; attemptNo += 1) {
      assertExecutionAuthority();
      const attempt = this.createAttempt({
        runId: accepted.run.runId,
        attemptNo,
        adapterId,
        retryReason,
        resumeFromAttemptId,
        producingTurn: input.producingTurnId ? {
          ownerId: accepted.session.ownerId,
          sessionId: accepted.session.sessionId,
          conversationId: conversationId!,
          turnId: input.producingTurnId,
        } : undefined,
      });
      lastAttempt = attempt;
      const toolCapability = this.toolCapabilities.register({
        ownerId: accepted.session.ownerId,
        sessionId: accepted.session.sessionId,
        runId: accepted.run.runId,
        attemptId: attempt.attemptId,
      });
      const attemptInput = this.inputWithManagedArtifactCwd(input, accepted.session, accepted.run.runId, attempt.attemptId);
      if (attemptInput.cwd && attemptInput.cwd !== (input.cwd ?? accepted.session.defaultCwd ?? undefined)) {
        this.withTransaction(() => {
          this.updateRun(accepted.run.runId, { cwd: attemptInput.cwd, updatedAtMs: Date.now() });
        });
      }

      if (!this.registry.has(adapterId)) {
        const failure: RuntimeFailure = {
          code: "adapter_not_registered",
          source: "runtime",
          adapterId,
          retryable: false,
          userMessage: `Adapter not registered: ${adapterId}`,
          technicalMessage: `Adapter not registered: ${adapterId}`,
        };
        this.failAttemptBeforeExecution(
          attempt,
          "adapter_not_registered",
          failure.userMessage,
          false,
          failure
        );
        break;
      }
      const pool = this.registry.get(adapterId);

      let binding: AdapterBinding;
      let handle: AdapterBindingHandle;
      let bindingResolutionProtectedBindingId: string | null = null;
      try {
        assertExecutionAuthority();
        const resolved = await this.withBindingResolutionLock(accepted.session.sessionId, adapterId, async () => {
          const existingBinding = this.readActiveBinding(accepted.session.sessionId, adapterId);
          const bindingQueueKey = existingBinding ? this.handleForExistingBinding(existingBinding) : undefined;
          return pool.runExclusiveQueued(
            bindingQueueKey,
            `${attempt.attemptId}:binding`,
            async (worker) => {
              const resolved = await this.resolveBindingForAttempt({
                input: attemptInput,
                session: accepted.session,
                adapter: worker.adapter,
                attempt,
                adapterId,
              });
              if (worker.adapter.capabilities.requiresPinnedWorker) {
                if (resolved.replacesBindingId) {
                  worker.replacePinnedBinding(resolved.replacesBindingId, resolved.handle);
                } else {
                  worker.pinBinding(resolved.handle);
                }
              }
              return resolved;
            },
            {
              ...(bindingQueueKey
                ? {}
                : {
                    onIdlePinnedBindingEvicted: (evictedBindingId: string) => {
                      this.markEvictedBindingStale(evictedBindingId, "pinned_worker_reassigned");
                    },
                  }),
              protectPinnedBindingAfterWork: true,
            },
          );
        });
        binding = resolved.binding;
        handle = resolved.handle;
        assertExecutionAuthority();
        bindingResolutionProtectedBindingId = pool.requiresPinnedWorkers ? (handle.bindingId ?? null) : null;
      } catch (error) {
        pool.unprotectPinnedBinding(bindingResolutionProtectedBindingId);
        if (input.authoritySignal?.aborted) {
          if (!this.isTerminalRun(accepted.run.runId)) {
            const failure = failureFromError(error, {
              code: "execution_authority_revoked",
              source: "runtime",
              adapterId: attempt.adapterId,
              retryable: false,
            });
            this.failAttemptBeforeExecution(
              attempt,
              "execution_authority_revoked",
              failure.userMessage,
              false,
              failure,
            );
          }
          break;
        }
        if (isStaleBindingError(error)) {
          const failure = failureFromError(error, {
            code: "stale_binding",
            source: "adapter_process",
            adapterId: attempt.adapterId,
            retryable: attemptNo < maxAttempts,
          });
          this.failAttemptBeforeExecution(attempt, "stale_binding", failure.userMessage, attemptNo < maxAttempts, failure);
          retryReason = "stale_binding";
          resumeFromAttemptId = attempt.attemptId;
          continue;
        }
        if (await this.tryRecoverAttempt(input, attempt, error, "binding_failed", attemptNo < maxAttempts)) {
          retryReason = "recoverable_error";
          resumeFromAttemptId = attempt.attemptId;
          continue;
        }
        const failure = failureFromError(error, {
          code: "binding_failed",
          source: "adapter_process",
          adapterId: attempt.adapterId,
          retryable: false,
        });
        this.failAttemptBeforeExecution(attempt, "binding_failed", failure.userMessage, false, failure);
        break;
      }

      const abortController = new AbortController();
      const protectedPinnedBindingId = pool.requiresPinnedWorkers ? handle.bindingId : null;
      pool.protectPinnedBinding(protectedPinnedBindingId);

      let effectivePrompt = attemptInput.prompt;
      let effectivePromptBlocks = attemptInput.promptBlocks;
      if (surfaceRef) {
        const snapshot = attemptInput.admittedContextSnapshot;
        if (!snapshot) throw new Error("Run is missing its admitted context snapshot");
        const attachments = input.attachments?.length
          ? `\n\n# Attachments\n${stableJsonStringify(input.attachments)}`
          : "";
        effectivePrompt = `${renderContextSnapshot(
          snapshot,
          accepted.session.surfaceKind,
          accepted.session.executionRole,
        )}${attachments}\n\n# User Message\n${input.prompt}`;
        effectivePromptBlocks = attemptInput.promptBlocks
          ? attemptInput.promptBlocks.map((block) =>
              block.type === "text" ? { ...block, text: effectivePrompt } : block,
            )
          : undefined;
      }

      try {
        const result = await pool.runExclusiveQueued(handle, attempt.attemptId, async (worker) => {
          assertExecutionAuthority();
          if (this.runStatus(accepted.run.runId) === "cancelling") {
            throw new Error("cancelled_before_adapter_dispatch");
          }
          this.activeExecutions.set(accepted.run.runId, {
            adapter: worker.adapter,
            abortController,
            binding: handle,
            attemptId: attempt.attemptId,
            sessionId: accepted.session.sessionId,
          });
          refreshMcpAttemptContext(
            mcpServersForBinding(input.mcpServers ?? [], accepted.session.sessionId, adapterId, this.runtimeNodeId),
            { capabilityRef: toolCapability.capabilityRef },
          );
          this.markAttemptRunning(attempt, binding);
          return worker.adapter.executeAttempt(
            {
              sessionId: accepted.session.sessionId,
              ownerId: input.ownerId,
              requestId: accepted.run.requestId,
              clientId: accepted.run.clientId,
              runId: accepted.run.runId,
              attemptId: attempt.attemptId,
              toolCapabilityRef: toolCapability.capabilityRef,
              binding: handle,
              prompt: effectivePromptBlocks ?? [{ type: "text", text: effectivePrompt }],
              mode: input.mode ?? "ask",
              model: input.model,
              tools: input.tools ?? [],
              metadata: input.metadata,
            },
            (event) => this.persistAdapterEvent(accepted.session.sessionId, accepted.run.runId, attempt.attemptId, event),
            abortController.signal,
          );
        });
        this.activeExecutions.delete(accepted.run.runId);
        assertExecutionAuthority();
        if (
          (
            this.runStatus(accepted.run.runId) === "cancelling"
            || this.readAttempt(attempt.attemptId).status === "cancelling"
          )
          && result.terminalStatus !== "cancelled"
        ) {
          throw new Error("cancelled_before_adapter_result_commit");
        }
        const completed = this.completeAttemptAndRun(
          accepted.session,
          accepted.run.runId,
          attempt,
          binding,
          result,
          {
            conversationId,
            surfaceKind: surfaceRef?.surfaceKind ?? accepted.session.surfaceKind,
          },
        );
        return { ...completed, completionDeltaArtifacts };
      } catch (error) {
        this.activeExecutions.delete(accepted.run.runId);
        if (input.authoritySignal?.aborted) {
          if (!this.isTerminalRun(accepted.run.runId)) {
            this.finishAttemptAndRun({
              sessionId: accepted.session.sessionId,
              runId: accepted.run.runId,
              attemptId: attempt.attemptId,
              status: "cancelled",
              finalText: null,
              errorCode: "execution_authority_revoked",
              errorMessage: "Run execution authority was revoked",
              failure: null,
            });
          }
          break;
        }
        if (isStaleBindingError(error)) {
          this.markBindingStale(binding, attempt, messageFrom(error));
          const failure = failureFromError(error, {
            code: "stale_binding",
            source: "adapter_execution",
            adapterId: attempt.adapterId,
            retryable: attemptNo < maxAttempts,
          });
          this.failAttemptBeforeExecution(attempt, "stale_binding", failure.userMessage, attemptNo < maxAttempts, failure);
          retryReason = "stale_binding";
          resumeFromAttemptId = attempt.attemptId;
          continue;
        }
        if (await this.tryRecoverAttempt(input, attempt, error, "adapter_execution_failed", attemptNo < maxAttempts)) {
          retryReason = "recoverable_error";
          resumeFromAttemptId = attempt.attemptId;
          continue;
        }
        const wasCancelling = this.runStatus(accepted.run.runId) === "cancelling";
        const status: AttemptStatus = wasCancelling ? "cancelled" : "failed";
        const failure = wasCancelling ? null : failureFromError(error, {
          code: "adapter_execution_failed",
          source: "adapter_execution",
          adapterId: attempt.adapterId,
          retryable: false,
        });
        this.finishAttemptAndRun({
          sessionId: accepted.session.sessionId,
          runId: accepted.run.runId,
          attemptId: attempt.attemptId,
          status,
          finalText: null,
          errorCode: wasCancelling ? null : "adapter_execution_failed",
          errorMessage: failure?.userMessage ?? null,
          failure,
        });
        break;
      } finally {
        pool.unprotectPinnedBinding(protectedPinnedBindingId);
      }
    }

    const finalRun = this.readRun(accepted.run.runId);
    const attempt = lastAttempt ?? this.readLatestAttempt(accepted.run.runId);
    return {
      session: accepted.session,
      run: finalRun,
      attempt,
      artifacts: this.readArtifacts({ runId: accepted.run.runId, limit: 50 }),
      adapterSessionId: null,
      terminalStatus: finalRun.status === "cancelled" ? "cancelled" : "failed",
      text: finalRun.finalText ?? "",
      completionDeltaArtifacts,
    };
  }

  protected surfaceRefForInput(input: ExecuteAgentRunInput): SurfaceRef | null {
    if (!input.surfaceKind || !input.externalRefKind || !input.externalRefId) return null;
    return {
      surfaceKind: input.surfaceKind,
      externalRefKind: input.externalRefKind,
      externalRefId: input.externalRefId,
    };
  }
  protected validateSensitiveContextDispatches(input: DesktopContextPacketBuildInput): void {
    for (const snippet of input.snippets) {
      if (snippet.selected === false || !requiresVerifiedContextDispatch(snippet)) continue;
      const dispatchId = snippet.dispatchId?.trim();
      if (!dispatchId) {
        throw new Error(`Sensitive context snippet ${snippet.snippetId} requires a dispatch id`);
      }
      const row = this.store.getOptionalRow("SELECT * FROM desktop_dispatches WHERE dispatch_id = ? AND owner_id = ?", [
        dispatchId,
        input.ownerId,
      ]);
      if (!row) {
        throw new Error(`Sensitive context dispatch ${dispatchId} was not found for owner`);
      }
      const dispatch = desktopDispatchFromRow(row);
      const resolution = parseJsonObject(dispatch.resolutionJson);
      if (!["approval", "screen_context"].includes(dispatch.kind)) {
        throw new Error(`Sensitive context dispatch ${dispatchId} has invalid kind`);
      }
      if (dispatch.status !== "resolved" || resolution.decision !== "allow") {
        throw new Error(`Sensitive context dispatch ${dispatchId} is not approved`);
      }
      if (dispatch.operation && dispatch.operation !== snippet.operation) {
        throw new Error(`Sensitive context dispatch ${dispatchId} operation does not match snippet`);
      }
    }
  }
  private admittedContextSnapshotForRun(run: AgentRun): ContextSnapshotProjection {
    const input = parseJsonObject(run.inputJson);
    const snapshot = input.admittedContextSnapshot;
    if (
      !snapshot
      || typeof snapshot !== "object"
      || Array.isArray(snapshot)
      || typeof (snapshot as Record<string, unknown>).version !== "string"
      || !Number.isSafeInteger((snapshot as Record<string, unknown>).snapshotGeneration)
      || !Array.isArray((snapshot as Record<string, unknown>).recentTurns)
      || !Array.isArray((snapshot as Record<string, unknown>).sourceOutcomes)
      || !Array.isArray((snapshot as Record<string, unknown>).activeRuns)
    ) {
      throw new Error(`Parent run ${run.runId} is missing its admitted context snapshot`);
    }
    return snapshot as ContextSnapshotProjection;
  }

  protected createDelegatedRun(
    parentSession: AgentSession,
    parentRun: AgentRun,
    childRunInput: ExecuteAgentRunInput,
    input: DelegateAgentInput
  ): { session: AgentSession; run: AgentRun; delegation: AgentDelegation; contextSnapshot: ContextSnapshotProjection } {
    return this.withTransaction(() => {
      const session = this.resolveSession(childRunInput);
      if (session.sessionId === parentSession.sessionId) {
        throw new Error("Delegated child session must be distinct from parent session");
      }
      const contextSnapshot = inheritContextSnapshotForSession(
        this.store,
        this.admittedContextSnapshotForRun(parentRun),
        session.sessionId,
        session.ownerId,
      );
      const run = this.store.insertRun({
        sessionId: session.sessionId,
        parentRunId: parentRun.runId,
        clientId: childRunInput.clientId,
        requestId: childRunInput.requestId,
        status: "queued",
        mode: childRunInput.mode ?? "ask",
        inputJson: JSON.stringify({
          prompt: childRunInput.prompt,
          metadata: childRunInput.metadata ?? {},
          contextSnapshotVersion: contextSnapshot.version,
          contextSnapshotGeneration: contextSnapshot.snapshotGeneration,
          contextRendererFingerprint: contextSnapshot.rendererFingerprint,
          contextCapabilityVersion: contextSnapshot.capabilityVersion,
          admittedContextSnapshot: contextSnapshot,
        }),
        requestedModelId: childRunInput.model ?? null,
        cwd: childRunInput.cwd ?? session.defaultCwd,
      });
      const now = Date.now();
      const delegation: AgentDelegation = {
        delegationId: generateAgentId("delegation"),
        parentSessionId: parentSession.sessionId,
        parentRunId: parentRun.runId,
        childSessionId: session.sessionId,
        childRunId: run.runId,
        mode: input.mode,
        status: "pending",
        objective: input.objective,
        requestJson: JSON.stringify({
          mode: input.mode,
          objective: input.objective,
          contextProvided: Boolean(input.context),
          childSurfaceKind: childRunInput.surfaceKind,
          childExternalRefKind: childRunInput.externalRefKind ?? null,
          childExternalRefId: childRunInput.externalRefId ?? null,
          maxDepth: input.maxDepth ?? DEFAULT_DELEGATION_MAX_DEPTH,
          maxBudgetUsd: input.maxBudgetUsd ?? DEFAULT_DELEGATION_MAX_BUDGET_USD,
        }),
        resultArtifactId: null,
        createdAtMs: now,
        completedAtMs: null,
      };
      this.store.execute(
        `INSERT INTO delegations (
          delegation_id, parent_session_id, parent_run_id, child_session_id, child_run_id,
          mode, status, objective, request_json, result_artifact_id, created_at_ms, completed_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        delegationValues(delegation),
      );
      this.appendEvent({
        sessionId: parentSession.sessionId,
        runId: parentRun.runId,
        type: "delegation.created",
        payload: {
          delegationId: delegation.delegationId,
          mode: delegation.mode,
          childSessionId: session.sessionId,
          childRunId: run.runId,
        },
      });
      this.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: "run.queued",
        payload: {
          runId: run.runId,
          requestId: run.requestId,
          clientId: run.clientId,
          parentRunId: parentRun.runId,
          delegationId: delegation.delegationId,
        },
      });
      this.touchSession(session.sessionId);
      return { session, run, delegation, contextSnapshot };
    });
  }

  protected async executeDelegationAsync(
    childRunInput: ExecuteAgentRunInput,
    created: {
      session: AgentSession;
      run: AgentRun;
      delegation: AgentDelegation;
      contextSnapshot: ContextSnapshotProjection;
    },
    markRunning = true
  ): Promise<DelegateAgentResult> {
    if (markRunning) {
      created = { ...created, delegation: this.updateDelegationStatus(created.delegation, "running") };
    }
    const result = await this.executeAcceptedRun(childRunInput, {
      session: created.session,
      run: created.run,
      contextSnapshot: created.contextSnapshot,
    });
    const status = result.terminalStatus === "succeeded" ? "succeeded" : result.terminalStatus;
    const delegation = this.updateDelegationStatus(created.delegation, status);
    const artifacts = this.readArtifacts({ runId: result.run.runId, limit: 50 });
    return {
      delegation,
      childSession: result.session,
      childRun: result.run,
      childAttempt: result.attempt,
      adapterSessionId: result.adapterSessionId,
      terminalStatus: result.terminalStatus,
      result: {
        summary: result.text,
        artifacts,
        verifiedEffects: [],
        openQuestions: [],
        usage: {
          inputTokens: result.run.inputTokens,
          outputTokens: result.run.outputTokens,
          cacheReadTokens: result.run.cacheReadTokens,
          cacheWriteTokens: result.run.cacheWriteTokens,
          costUsd: result.run.costUsd,
        },
      },
    };
  }

  protected updateDelegationStatus(delegation: AgentDelegation, status: DelegationStatus, errorMessage?: string): AgentDelegation {
    const now = Date.now();
    this.withTransaction(() => {
      this.store.execute(
        `UPDATE delegations
         SET status = ?, completed_at_ms = ?, result_artifact_id = result_artifact_id
         WHERE delegation_id = ?`,
        [status, status === "running" || status === "pending" ? null : now, delegation.delegationId],
      );
      if (status !== "running") {
        this.appendEvent({
          sessionId: delegation.parentSessionId,
          runId: delegation.parentRunId,
          type: "delegation.completed",
          payload: {
            delegationId: delegation.delegationId,
            childSessionId: delegation.childSessionId,
            childRunId: delegation.childRunId,
            status,
            errorMessage,
          },
        });
      }
    });
    return this.readDelegation(delegation.delegationId);
  }

  protected assertDelegationConstraints(input: DelegateAgentInput): void {
    const maxDepth = input.maxDepth ?? DEFAULT_DELEGATION_MAX_DEPTH;
    if (!Number.isInteger(maxDepth) || maxDepth < 1 || maxDepth > HARD_DELEGATION_MAX_DEPTH) {
      throw new Error(`Delegation maxDepth must be between 1 and ${HARD_DELEGATION_MAX_DEPTH}`);
    }
    const maxBudgetUsd = input.maxBudgetUsd ?? DEFAULT_DELEGATION_MAX_BUDGET_USD;
    if (!Number.isFinite(maxBudgetUsd) || maxBudgetUsd <= 0 || maxBudgetUsd > HARD_DELEGATION_MAX_BUDGET_USD) {
      throw new Error(`Delegation maxBudgetUsd must be greater than 0 and at most ${HARD_DELEGATION_MAX_BUDGET_USD}`);
    }
    const parentDepth = this.delegationDepth(input.parentRunId);
    if (parentDepth + 1 > maxDepth) {
      throw new Error(`Delegation depth ${parentDepth + 1} exceeds maxDepth ${maxDepth}`);
    }
  }

  protected resolveSession(input: KernelSessionResolutionInput): AgentSession {
    // An explicit canonical session is authoritative even when the caller also
    // supplies a new surface reference. This is how one long-running thread can
    // move between task scopes without silently forking its runtime identity.
    if (input.sessionId) {
      const existing = this.findExistingSession(input);
      if (existing) return existing;
    }
    if (input.surfaceKind && input.externalRefKind && input.externalRefId) {
      const resolved = resolveSurfaceSession(
        this.store,
        {
          ownerId: input.ownerId,
          surfaceRef: {
            surfaceKind: input.surfaceKind,
            externalRefKind: input.externalRefKind,
            externalRefId: input.externalRefId,
          },
          defaultAdapterId: input.defaultAdapterId,
          executionRole: input.executionRole,
          providerBoundary: input.providerBoundary,
          modelProfile: input.modelProfile,
          defaultCwd: "cwd" in input ? (input as ExecuteAgentRunInput).cwd ?? null : null,
          executionProfileSource: input.executionProfileSource,
          title: input.title ?? null,
        },
        () => Date.now(),
      );
      const session = this.readSession(resolved.agentSessionId);
      const hasCreationEvent = this.store.getOptionalRow(
        "SELECT event_id FROM events WHERE session_id = ? AND type = 'session.created' LIMIT 1",
        [session.sessionId],
      );
      if (!hasCreationEvent) {
        this.appendEvent({
          sessionId: session.sessionId,
          type: "session.created",
          payload: { sessionId: session.sessionId, ownerId: session.ownerId, surfaceKind: session.surfaceKind },
        });
      }
      return session;
    }
    const existing = this.findExistingSession(input);
    if (existing) return existing;
    const session = this.store.insertSession({
      ownerId: input.ownerId,
      surfaceKind: input.surfaceKind,
      externalRefKind: input.externalRefKind ?? null,
      externalRefId: input.externalRefId ?? null,
      title: input.title ?? null,
      defaultAdapterId: input.defaultAdapterId ?? "acp",
      executionRole: input.executionRole ?? "coordinator",
      providerBoundary:
        input.providerBoundary ?? providerBoundaryForAdapter(input.defaultAdapterId ?? "acp"),
      modelProfile: input.modelProfile ?? null,
      defaultCwd: "cwd" in input ? (input as ExecuteAgentRunInput).cwd ?? null : null,
      executionProfileSource: input.executionProfileSource,
    });
    this.appendEvent({
      sessionId: session.sessionId,
      type: "session.created",
      payload: { sessionId: session.sessionId, ownerId: session.ownerId, surfaceKind: session.surfaceKind },
    });
    return session;
  }

  protected findExistingSession(input: KernelSessionResolutionInput): AgentSession | undefined {
    if (input.sessionId) {
      const session = this.readSession(input.sessionId);
      if (session.ownerId !== input.ownerId) {
        throw new Error(`Session ${input.sessionId} does not belong to owner ${input.ownerId}`);
      }
      return session;
    }
    if (input.surfaceKind && input.externalRefKind && input.externalRefId) {
      const mapped = this.store.getOptionalRow(
        `SELECT agent_session_id FROM surface_conversations
         WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
        [input.ownerId, input.surfaceKind, input.externalRefKind, input.externalRefId],
      );
      if (mapped) {
        return this.readSession(String(mapped.agent_session_id));
      }
    }
    if (input.externalRefKind && input.externalRefId) {
      const row = this.store.getOptionalRow(
        "SELECT * FROM sessions WHERE owner_id = ? AND external_ref_kind = ? AND external_ref_id = ?",
        [input.ownerId, input.externalRefKind, input.externalRefId],
      );
      if (row) return sessionFromRow(row);
      return undefined;
    }
    return undefined;
  }

  protected findInvalidationSessionIds(input: KernelSessionResolutionInput): string[] {
    if (input.sessionId || input.externalRefKind || input.externalRefId) {
      return [];
    }
    return this.store
      .allRows("SELECT session_id FROM sessions WHERE owner_id = ?", [input.ownerId])
      .map((row) => String(row.session_id));
  }

  protected createAttempt(input: {
    runId: string;
    attemptNo: number;
    adapterId: string;
    retryReason: string | null;
    resumeFromAttemptId: string | null;
    producingTurn?: {
      ownerId: string;
      sessionId: string;
      conversationId: string;
      turnId: string;
    };
  }): RunAttempt {
    return this.withTransaction(() => {
      const active = this.readActiveAttempt(input.runId);
      if (active) {
        throw new Error(`Run ${input.runId} already has active attempt ${active.attemptId}`);
      }
      this.updateRun(input.runId, {
        status: "starting",
        startedAtMs: input.attemptNo === 1 ? Date.now() : undefined,
        updatedAtMs: Date.now(),
      });
      const run = this.readRun(input.runId);
      const attempt = this.store.insertAttempt({
        runId: input.runId,
        attemptNo: input.attemptNo,
        profileGeneration: run.profileGeneration,
        status: "starting",
        adapterId: input.adapterId,
        adapterInstanceId: "",
        runtimeNodeId: this.runtimeNodeId,
        retryReason: input.retryReason,
        resumeFromAttemptId: input.resumeFromAttemptId,
        retryable: input.retryReason ? 1 : 0,
      });
      if (input.producingTurn) {
        bindProducingJournalTurn(this.store, {
          ...input.producingTurn,
          runId: input.runId,
          attemptId: attempt.attemptId,
        });
      }
      this.appendEvent({
        sessionId: run.sessionId,
        runId: input.runId,
        type: "run.starting",
        payload: { runId: input.runId, attemptNo: input.attemptNo },
      });
      this.appendEvent({
        sessionId: run.sessionId,
        runId: input.runId,
        attemptId: attempt.attemptId,
        type: "attempt.created",
        payload: {
          attemptId: attempt.attemptId,
          attemptNo: attempt.attemptNo,
          retryReason: input.retryReason,
          resumeFromAttemptId: input.resumeFromAttemptId,
        },
      });
      return attempt;
    });
  }

  protected async resolveBindingForAttempt(input: {
    input: ExecuteAgentRunInput;
    session: AgentSession;
    adapter: RuntimeAdapter;
    attempt: RunAttempt;
    adapterId: string;
  }): Promise<{ binding: AdapterBinding; handle: AdapterBindingHandle; replacesBindingId?: string }> {
    const active = this.readActiveBinding(input.session.sessionId, input.adapterId);
    if (active) {
      const handle = await this.resumeOrReplaceBinding(active, input);
      return { binding: this.readBinding(handle.bindingId!), handle, replacesBindingId: handle.replacesBindingId };
    }

    const nextGeneration = this.nextBindingGeneration(input.session.sessionId, input.adapterId);
    const previousBinding = nextGeneration > 1 ? this.readLatestBinding(input.session.sessionId, input.adapterId) : undefined;
    return this.openNewBinding(input, nextGeneration, previousBinding?.bindingId ?? null);
  }

  protected handleForExistingBinding(binding: AdapterBinding): AdapterBindingHandle {
    return {
      bindingId: binding.bindingId,
      sessionId: binding.sessionId,
      adapterId: binding.adapterId,
      adapterNativeSessionId: binding.adapterNativeSessionId ?? "",
      resumeFidelity: binding.resumeFidelity,
      cwd: binding.cwd ?? process.cwd(),
      model: binding.modelId ?? undefined,
    };
  }

  protected isBindingCompatible(
    binding: AdapterBinding,
    input: {
      input: ExecuteAgentRunInput;
      session: AgentSession;
      adapter?: RuntimeAdapter;
    }
  ): boolean {
    if (binding.profileGeneration !== input.session.executionProfileGeneration) {
      return false;
    }
    const requestedCwd = input.input.cwd ?? input.session.defaultCwd ?? process.cwd();
    const bindingCwd = binding.cwd ?? process.cwd();
    if (bindingCwd !== requestedCwd) {
      return false;
    }
    if (input.input.model !== undefined && binding.modelId !== input.input.model) {
      return false;
    }
    const requestedSystemPromptHash = stableHash(
      input.input.systemPromptCacheIdentity ?? input.input.systemPrompt);
    if (binding.systemPromptHash !== null && binding.systemPromptHash !== requestedSystemPromptHash) {
      return false;
    }
    const metadata = parseJsonObject(binding.metadataJson);
    const effectiveMcpServers = input.adapter?.effectiveMcpServers
      ? input.adapter.effectiveMcpServers(input.input.mcpServers ?? [])
      : input.input.mcpServers ?? [];
    const expectedMcpServersHash = stableJsonHash(stableMcpServerConfig(effectiveMcpServers));
    if (metadata.mcpServersHash === undefined) {
      return true;
    }
    return metadata.mcpServersHash === expectedMcpServersHash;
  }

  protected async resumeOrReplaceBinding(
    binding: AdapterBinding,
    input: {
      input: ExecuteAgentRunInput;
      session: AgentSession;
      adapter: RuntimeAdapter;
      attempt: RunAttempt;
      adapterId: string;
    }
  ): Promise<AdapterBindingHandle & { replacesBindingId?: string }> {
    if (!this.isBindingCompatible(binding, input)) {
      this.markBindingStale(binding, input.attempt, "binding_context_changed");
      const opened = await this.openNewBinding(input, binding.bindingGeneration + 1, binding.bindingId);
      return { ...opened.handle, replacesBindingId: opened.replacesBindingId };
    }
    const canUseProcessLocalBinding =
      binding.adapterInstanceId === this.runtimeNodeId &&
      binding.adapterNativeSessionId &&
      binding.resumeFidelity === "none";
    if (!binding.adapterNativeSessionId || (!input.adapter.capabilities.supportsNativeResume && !canUseProcessLocalBinding)) {
      this.markBindingStale(binding, input.attempt, "binding_not_resumable");
      const opened = await this.openNewBinding(input, binding.bindingGeneration + 1, binding.bindingId);
      return { ...opened.handle, replacesBindingId: opened.replacesBindingId };
    }
    try {
      const resumed = await input.adapter.resumeBinding({
        sessionId: input.session.sessionId,
        adapterNativeSessionId: binding.adapterNativeSessionId,
        cwd: input.input.cwd ?? binding.cwd ?? input.session.defaultCwd ?? process.cwd(),
        model: input.input.model ?? binding.modelId ?? undefined,
        systemPrompt: input.input.systemPrompt,
        mcpServers: mcpServersForBinding(input.input.mcpServers ?? [], input.session.sessionId, input.adapterId, this.runtimeNodeId),
        metadata: runtimeAdapterMetadata(input.input, input.session),
      });
      this.withTransaction(() => {
        this.updateBinding(binding.bindingId, {
          adapterInstanceId: this.runtimeNodeId,
          cwd: input.input.cwd ?? binding.cwd ?? input.session.defaultCwd ?? null,
          modelId: input.input.model ?? binding.modelId ?? null,
          systemPromptHash: stableHash(input.input.systemPromptCacheIdentity ?? input.input.systemPrompt),
          metadataJson: bindingMetadata(input.input, input.adapter),
          lastUsedAtMs: Date.now(),
          updatedAtMs: Date.now(),
        });
        this.appendEvent({
          sessionId: input.session.sessionId,
          runId: input.attempt.runId,
          attemptId: input.attempt.attemptId,
          type: "binding.resumed",
          payload: {
            bindingId: binding.bindingId,
            adapterId: input.adapterId,
            bindingGeneration: binding.bindingGeneration,
            systemPromptCacheIdentity: input.input.systemPromptCacheIdentity ?? null,
            dynamicContextIdentity: input.input.dynamicContextIdentity ?? null,
            contextPlanId: input.input.contextPlanId ?? null,
          },
        });
      });
      return {
        ...resumed,
        bindingId: binding.bindingId,
        sessionId: input.session.sessionId,
        adapterId: input.adapterId,
      };
    } catch (error) {
      this.markBindingStale(binding, input.attempt, messageFrom(error));
      throw new StaleAdapterBindingError(messageFrom(error));
    }
  }

  protected async openNewBinding(
    input: {
      input: ExecuteAgentRunInput;
      session: AgentSession;
      adapter: RuntimeAdapter;
      attempt: RunAttempt;
      adapterId: string;
    },
    generation: number,
    replacesBindingId: string | null
  ): Promise<{ binding: AdapterBinding; handle: AdapterBindingHandle; replacesBindingId?: string }> {
    const opened = await input.adapter.openBinding({
      sessionId: input.session.sessionId,
      cwd: input.input.cwd ?? input.session.defaultCwd ?? process.cwd(),
      model: input.input.model,
      systemPrompt: input.input.systemPrompt,
      mcpServers: mcpServersForBinding(input.input.mcpServers ?? [], input.session.sessionId, input.adapterId, this.runtimeNodeId),
      metadata: runtimeAdapterMetadata(input.input, input.session),
    });
    const binding = this.withTransaction(() => {
      this.closeConflictingNativeBinding(
        input.adapterId,
        opened.adapterNativeSessionId,
        input.attempt,
        "native_session_reused"
      );
      const created = this.store.insertAdapterBinding({
        sessionId: input.session.sessionId,
        adapterId: input.adapterId,
        bindingGeneration: generation,
        profileGeneration: input.session.executionProfileGeneration,
        adapterNativeSessionId: opened.adapterNativeSessionId,
        adapterInstanceId: this.runtimeNodeId,
        resumeFidelity: opened.resumeFidelity,
        status: "active",
        cwd: opened.cwd,
        modelId: opened.model ?? input.input.model ?? null,
        systemPromptHash: stableHash(input.input.systemPromptCacheIdentity ?? input.input.systemPrompt),
        metadataJson: bindingMetadata(input.input, input.adapter),
        lastUsedAtMs: Date.now(),
      });
      this.appendEvent({
        sessionId: input.session.sessionId,
        runId: input.attempt.runId,
        attemptId: input.attempt.attemptId,
        type: replacesBindingId ? "binding.replaced" : "binding.created",
        payload: {
          bindingId: created.bindingId,
          replacesBindingId,
          bindingGeneration: created.bindingGeneration,
          adapterId: input.adapterId,
          resumeFidelity: created.resumeFidelity,
          systemPromptCacheIdentity: input.input.systemPromptCacheIdentity ?? null,
          dynamicContextIdentity: input.input.dynamicContextIdentity ?? null,
          contextPlanId: input.input.contextPlanId ?? null,
        },
      });
      return created;
    });
    return {
      binding,
      replacesBindingId: replacesBindingId ?? undefined,
      handle: {
        ...opened,
        bindingId: binding.bindingId,
        sessionId: input.session.sessionId,
        adapterId: input.adapterId,
      },
    };
  }

  protected markAttemptRunning(attempt: RunAttempt, binding: AdapterBinding): void {
    const run = this.readRun(attempt.runId);
    this.withTransaction(() => {
      this.updateRun(attempt.runId, { status: "running", updatedAtMs: Date.now() });
      this.updateAttempt(attempt.attemptId, {
        status: "running",
        bindingId: binding.bindingId,
        adapterInstanceId: this.runtimeNodeId,
        startedAtMs: Date.now(),
        updatedAtMs: Date.now(),
      });
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: "attempt.started",
        payload: { attemptId: attempt.attemptId, bindingId: binding.bindingId },
      });
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: "run.running",
        payload: { runId: attempt.runId, attemptId: attempt.attemptId },
      });
    });
  }

  protected completeAttemptAndRun(
    session: AgentSession,
    runId: string,
    attempt: RunAttempt,
    binding: AdapterBinding,
    result: AdapterAttemptResult,
    turnRecord?: { conversationId: string | null; surfaceKind: string },
  ): KernelRunResult {
    const status = result.terminalStatus;
    this.withTransaction(() => {
      this.updateBinding(binding.bindingId, {
        adapterNativeSessionId: result.adapterSessionId,
        lastUsedAtMs: Date.now(),
        updatedAtMs: Date.now(),
      });
      const emittedArtifacts = result.artifacts ?? [];
      const existingArtifacts = this.readArtifacts({ sessionId: session.sessionId, limit: 500 });
      const runScope = {
        ownerId: session.ownerId,
        sessionId: session.sessionId,
        runId,
        attemptId: attempt.attemptId,
      };
      const runDirectoryArtifacts = this.artifactStorage?.discoverRunArtifacts(
        runScope,
        [...emittedArtifacts, ...existingArtifacts]
      ) ?? [];
      const artifacts = [
        ...emittedArtifacts,
        ...runDirectoryArtifacts,
        ...(this.artifactStorage?.discoverReportedTerminalArtifacts(
          result.text,
          [...emittedArtifacts, ...existingArtifacts, ...runDirectoryArtifacts]
        ) ?? []),
      ];
      for (const rawArtifact of artifacts) {
        const artifact = this.artifactStorage?.normalizeArtifact(rawArtifact, runScope) ?? rawArtifact;
        this.persistArtifactInTransaction({
          sessionId: session.sessionId,
          runId,
          attemptId: attempt.attemptId,
          kind: artifact.kind,
          role: artifact.role,
          uri: artifact.uri,
          displayName: artifact.displayName,
          mimeType: artifact.mimeType,
          contentHash: artifact.contentHash,
          sizeBytes: artifact.sizeBytes,
          metadata: artifact.metadata,
        });
      }
      this.finishAttemptAndRun({
        sessionId: session.sessionId,
        runId,
        attemptId: attempt.attemptId,
        status,
        finalText: result.text,
        result,
        errorCode: status === "failed" ? result.failure?.code ?? "adapter_execution_failed" : null,
        errorMessage: status === "failed" ? result.failure?.userMessage ?? null : null,
        failure: result.failure,
      });
    });
    return {
      session,
      run: this.readRun(runId),
      attempt: this.readAttempt(attempt.attemptId),
      artifacts: this.readArtifacts({ runId, limit: 50 }),
      adapterSessionId: result.adapterSessionId,
      terminalStatus: status,
      text: result.text,
    };
  }

  protected inputWithManagedArtifactCwd(
    input: ExecuteAgentRunInput,
    session: AgentSession,
    runId: string,
    attemptId: string
  ): ExecuteAgentRunInput {
    if (!this.artifactStorage) {
      return input;
    }
    const requestedCwd = input.cwd ?? session.defaultCwd;
    if (requestedCwd && !this.artifactStorage.isRootDirectory(requestedCwd)) {
      return input;
    }
    const cwd = this.artifactStorage.prepareRunDirectory({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId,
      attemptId,
    });
    return { ...input, cwd };
  }

  protected finishAttemptAndRun(input: {
    sessionId: string;
    runId: string;
    attemptId: string;
    status: AttemptStatus;
    finalText: string | null;
    result?: AdapterAttemptResult;
    errorCode?: string | null;
    errorMessage?: string | null;
    failure?: RuntimeFailure | null;
  }): void {
    const now = Date.now();
    const completedStatus = input.status;
    this.updateAttempt(input.attemptId, {
      status: completedStatus,
      completedAtMs: now,
      errorCode: input.errorCode ?? null,
      errorMessage: input.errorMessage ?? null,
      updatedAtMs: now,
    });
    this.updateRun(input.runId, {
      status: completedStatus,
      finalText: input.finalText,
      resultJson: input.result ? JSON.stringify(input.result) : input.failure ? JSON.stringify({ failure: input.failure }) : null,
      errorCode: input.errorCode ?? null,
      errorMessage: input.errorMessage ?? null,
      inputTokens: input.result?.inputTokens ?? null,
      outputTokens: input.result?.outputTokens ?? null,
      cacheReadTokens: input.result?.cacheReadTokens ?? null,
      cacheWriteTokens: input.result?.cacheWriteTokens ?? null,
      costUsd: input.result?.costUsd ?? null,
      completedAtMs: now,
      updatedAtMs: now,
    });
    if (completedStatus === "failed" || completedStatus === "cancelled") {
      this.appendEvent({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        type: completedStatus === "failed" ? "attempt.failed" : "attempt.cancelled",
        payload: { attemptId: input.attemptId, status: completedStatus, failure: input.failure ?? input.result?.failure },
      });
    }
    if (completedStatus === "succeeded") {
      this.appendEvent({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        type: "message.completed",
        payload: { text: input.finalText ?? "" },
      });
      this.appendEvent({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        type: "usage.updated",
        payload: {
          inputTokens: input.result?.inputTokens ?? null,
          outputTokens: input.result?.outputTokens ?? null,
          cacheReadTokens: input.result?.cacheReadTokens ?? null,
          cacheWriteTokens: input.result?.cacheWriteTokens ?? null,
          costUsd: input.result?.costUsd ?? null,
        },
      });
    }
    this.appendEvent({
      sessionId: input.sessionId,
      runId: input.runId,
      attemptId: input.attemptId,
      type: `run.${completedStatus}`,
      payload: { runId: input.runId, status: completedStatus, failure: input.failure ?? input.result?.failure },
    });
  }

  protected failAttemptBeforeExecution(
    attempt: RunAttempt,
    errorCode: string,
    errorMessage: string,
    retryable: boolean,
    failure?: RuntimeFailure
  ): void {
    const run = this.readRun(attempt.runId);
    this.withTransaction(() => {
      this.updateAttempt(attempt.attemptId, {
        status: "failed",
        retryable: retryable ? 1 : 0,
        completedAtMs: Date.now(),
        errorCode,
        errorMessage,
        updatedAtMs: Date.now(),
      });
      if (!retryable) {
        this.updateRun(attempt.runId, {
          status: "failed",
          errorCode,
          errorMessage,
          resultJson: failure ? JSON.stringify({ failure }) : null,
          completedAtMs: Date.now(),
          updatedAtMs: Date.now(),
        });
        this.appendEvent({
          sessionId: run.sessionId,
          runId: attempt.runId,
          attemptId: attempt.attemptId,
          type: "run.failed",
          payload: { runId: attempt.runId, errorCode, errorMessage, failure },
        });
      }
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: "attempt.failed",
        payload: { attemptId: attempt.attemptId, errorCode, errorMessage, retryable, failure },
      });
    });
  }

  protected async tryRecoverAttempt(
    input: ExecuteAgentRunInput,
    attempt: RunAttempt,
    error: unknown,
    errorCode: string,
    canRetry: boolean
  ): Promise<boolean> {
    if (!canRetry || !input.recoverAfterError) {
      return false;
    }
    let recovered = false;
    try {
      recovered = await input.recoverAfterError(error);
    } catch {
      return false;
    }
    if (!recovered) {
      return false;
    }
    const failure = failureFromError(error, {
      code: errorCode,
      source: "adapter_process",
      adapterId: attempt.adapterId,
      retryable: true,
    });
    this.failAttemptBeforeExecution(attempt, errorCode, failure.userMessage, true, failure);
    return true;
  }

  protected persistAdapterEvent(sessionId: string, runId: string, attemptId: string, event: OutboundMessageDraft): void {
    if (this.isTerminalAttempt(attemptId) || this.isTerminalRun(runId)) {
      return;
    }
    const eventType = canonicalAdapterEventType(event);
    if (!eventType) {
      return;
    }
    this.withTransaction(() => {
      if (this.isTerminalAttempt(attemptId) || this.isTerminalRun(runId)) {
        return;
      }
      this.appendEvent({
        sessionId,
        runId,
        attemptId,
        type: eventType,
        retentionClass: event.type === "text_delta" || event.type === "thinking_delta" ? "transient" : "core",
        payload: event,
      });
    });
  }

  protected closeConflictingNativeBinding(
    adapterId: string,
    adapterNativeSessionId: string | null | undefined,
    attempt: RunAttempt,
    reason: string
  ): void {
    if (!adapterNativeSessionId) {
      return;
    }
    const row = this.store.getOptionalRow(
      `SELECT binding_id, session_id, status
       FROM adapter_bindings
       WHERE adapter_id = ? AND adapter_native_session_id = ? AND status NOT IN ('active', 'closed')
       ORDER BY updated_at_ms DESC
       LIMIT 1`,
      [adapterId, adapterNativeSessionId]
    );
    if (!row) {
      return;
    }
    const now = Date.now();
    const bindingId = String(row.binding_id);
    this.updateBinding(bindingId, {
      status: "closed",
      invalidatedAtMs: now,
      updatedAtMs: now,
    });
    this.appendEvent({
      sessionId: String(row.session_id),
      runId: attempt.runId,
      attemptId: attempt.attemptId,
      type: "binding.stale",
      payload: { bindingId, adapterId, adapterNativeSessionId, reason },
    });
  }

  protected markBindingStale(binding: AdapterBinding, attempt: RunAttempt, reason: string): void {
    const run = this.readRun(attempt.runId);
    this.withTransaction(() => {
      this.updateBinding(binding.bindingId, {
        status: "stale",
        invalidatedAtMs: Date.now(),
        updatedAtMs: Date.now(),
      });
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: "binding.stale",
        payload: { bindingId: binding.bindingId, reason },
      });
    });
  }

  protected markEvictedBindingStale(bindingId: string, reason: string): void {
    const binding = this.readBinding(bindingId);
    this.withTransaction(() => {
      this.updateBinding(binding.bindingId, {
        status: "stale",
        invalidatedAtMs: Date.now(),
        updatedAtMs: Date.now(),
      });
      this.appendEvent({
        sessionId: binding.sessionId,
        runId: null,
        attemptId: null,
        type: "binding.stale",
        payload: { bindingId: binding.bindingId, reason },
      });
    });
  }

  protected persistArtifactInTransaction(input: PersistArtifactInput): AgentArtifact {
    const scope = this.resolveArtifactScope(input);
    const artifactInput: NewAgentArtifact = {
      artifactId: input.artifactId,
      sessionId: scope.sessionId,
      runId: scope.runId,
      attemptId: scope.attemptId,
      kind: input.kind,
      role: input.role,
      uri: input.uri,
      displayName: input.displayName ?? null,
      mimeType: input.mimeType ?? null,
      contentHash: input.contentHash ?? null,
      sizeBytes: input.sizeBytes ?? null,
      metadataJson: input.metadataJson ?? JSON.stringify(input.metadata ?? {}),
      createdAtMs: input.createdAtMs,
    };
    const artifact = this.store.insertArtifact(artifactInput);
    this.appendEvent({
      sessionId: artifact.sessionId,
      runId: artifact.runId,
      attemptId: artifact.attemptId,
      type: "artifact.created",
      payload: {
        artifactId: artifact.artifactId,
        kind: artifact.kind,
        role: artifact.role,
        uri: artifact.uri,
        displayName: artifact.displayName,
        mimeType: artifact.mimeType,
        contentHash: artifact.contentHash,
        sizeBytes: artifact.sizeBytes,
        lifecycleState: artifact.lifecycleState,
      },
    });
    return artifact;
  }

  protected resolveArtifactScope(input: PersistArtifactInput): {
    sessionId: string;
    runId: string | null;
    attemptId: string | null;
  } {
    let sessionId = input.sessionId ?? null;
    let runId = input.runId ?? null;
    const attemptId = input.attemptId ?? null;

    if (attemptId) {
      const attempt = this.readAttempt(attemptId);
      if (runId && runId !== attempt.runId) {
        throw new Error(`Artifact attempt ${attemptId} belongs to run ${attempt.runId}, not ${runId}`);
      }
      runId = attempt.runId;
    }

    if (runId) {
      const run = this.readRun(runId);
      if (sessionId && sessionId !== run.sessionId) {
        throw new Error(`Artifact run ${runId} belongs to session ${run.sessionId}, not ${sessionId}`);
      }
      sessionId = run.sessionId;
    }

    if (!sessionId) {
      throw new Error("Artifact persistence requires sessionId, runId, or attemptId");
    }

    return { sessionId, runId, attemptId };
  }
  protected appendEvent(input: {
    sessionId: string;
    type: string;
    runId?: string | null;
    attemptId?: string | null;
    retentionClass?: "core" | "transient";
    visibility?: "ui" | "internal";
    payload?: unknown;
  }): AgentEvent {
    const event = this.store.appendEvent({
      sessionId: input.sessionId,
      runId: input.runId ?? null,
      attemptId: input.attemptId ?? null,
      type: input.type,
      retentionClass: input.retentionClass ?? "core",
      visibility: input.visibility ?? "ui",
      payloadJson: JSON.stringify(input.payload ?? {}),
    });
    this.toolCapabilities.handleKernelEvent(event);
    if (this.transactionDepth > 0) {
      this.pendingSubscriberEvents.push(event);
      return event;
    }
    this.notifySubscribers(event);
    return event;
  }

  protected withTransaction<T>(work: () => T): T {
    const pendingStart = this.pendingSubscriberEvents.length;
    this.transactionDepth += 1;
    let committed = false;
    try {
      const result = this.store.withTransaction(work);
      committed = true;
      return result;
    } finally {
      this.transactionDepth -= 1;
      if (!committed) {
        this.pendingSubscriberEvents.splice(pendingStart);
      }
      if (this.transactionDepth === 0) {
        const events = this.pendingSubscriberEvents;
        this.pendingSubscriberEvents = [];
        for (const event of events) {
          this.notifySubscribers(event);
        }
      }
    }
  }

  protected notifySubscribers(event: AgentEvent): void {
    for (const subscriber of this.subscribers) {
      try {
        subscriber(event);
      } catch {
        // Subscribers are observers; event persistence must not be rolled back
        // by UI/projection listener failures.
      }
    }
  }

  protected async withBindingResolutionLock<T>(
    sessionId: string,
    adapterId: string,
    work: () => Promise<T>
  ): Promise<T> {
    const key = `${sessionId}:${adapterId}`;
    const previous = this.bindingResolutionLocks.get(key);
    let release!: () => void;
    const current = new Promise<void>((resolve) => {
      release = resolve;
    });
    const tail = previous ? previous.then(() => current, () => current) : current;
    this.bindingResolutionLocks.set(key, tail);
    try {
      if (previous) {
        await previous.catch(() => undefined);
      }
      return await work();
    } finally {
      release();
      if (this.bindingResolutionLocks.get(key) === tail) {
        this.bindingResolutionLocks.delete(key);
      }
    }
  }

  protected readSession(sessionId: string): AgentSession {
    const session = sessionFromRow(this.store.getRow("SELECT * FROM sessions WHERE session_id = ?", [sessionId]));
    return applyExecutionProfileToSession(session, readSessionExecutionProfile(this.store, sessionId));
  }

  protected readRun(runId: string): AgentRun {
    return runFromRow(this.store.getRow("SELECT * FROM runs WHERE run_id = ?", [runId]));
  }

  protected assertSessionOwner(session: AgentSession, ownerId: string): void {
    if (session.ownerId !== ownerId) {
      throw new Error("Agent session is not visible to the active owner");
    }
  }

  protected assertRunOwner(run: AgentRun, ownerId: string): void {
    this.assertSessionOwner(this.readSession(run.sessionId), ownerId);
  }

  protected assertAttemptOwner(attempt: RunAttempt, ownerId: string): void {
    this.assertRunOwner(this.readRun(attempt.runId), ownerId);
  }

  protected assertArtifactSelectorOwner(input: InspectArtifactsInput, ownerId: string): void {
    if (input.artifactId) {
      this.assertSessionOwner(this.readSession(this.readArtifact(input.artifactId).sessionId), ownerId);
    }
    if (input.sessionId) {
      this.assertSessionOwner(this.readSession(input.sessionId), ownerId);
    }
    if (input.runId) {
      this.assertRunOwner(this.readRun(input.runId), ownerId);
    }
    if (input.attemptId) {
      this.assertAttemptOwner(this.readAttempt(input.attemptId), ownerId);
    }
  }

  protected readLatestRunForSession(sessionId: string): AgentRun | undefined {
    const row = this.store.getOptionalRow("SELECT * FROM runs WHERE session_id = ? ORDER BY created_at_ms DESC LIMIT 1", [sessionId]);
    return row ? runFromRow(row) : undefined;
  }

  protected readActiveRunForSession(sessionId: string): AgentRun | undefined {
    const row = this.store.getOptionalRow(
      `SELECT * FROM runs WHERE session_id = ? AND status IN (${placeholders(ACTIVE_STATUSES.length)}) ORDER BY created_at_ms DESC LIMIT 1`,
      [sessionId, ...ACTIVE_STATUSES],
    );
    return row ? runFromRow(row) : undefined;
  }

  protected readAttempt(attemptId: string): RunAttempt {
    return attemptFromRow(this.store.getRow("SELECT * FROM run_attempts WHERE attempt_id = ?", [attemptId]));
  }

  protected readLatestAttempt(runId: string): RunAttempt {
    return attemptFromRow(this.store.getRow("SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1", [runId]));
  }

  protected readAttemptsForRun(runId: string): RunAttempt[] {
    return this.store.allRows("SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no ASC", [runId]).map(attemptFromRow);
  }

  protected readActiveAttempt(runId: string): RunAttempt | undefined {
    const row = this.store.getOptionalRow(
      `SELECT * FROM run_attempts WHERE run_id = ? AND status IN (${placeholders(ACTIVE_STATUSES.length)}) ORDER BY attempt_no DESC LIMIT 1`,
      [runId, ...ACTIVE_STATUSES],
    );
    return row ? attemptFromRow(row) : undefined;
  }

  protected readBinding(bindingId: string): AdapterBinding {
    return bindingFromRow(this.store.getRow("SELECT * FROM adapter_bindings WHERE binding_id = ?", [bindingId]));
  }

  protected readActiveBinding(sessionId: string, adapterId: string): AdapterBinding | undefined {
    const row = this.store.getOptionalRow(
      "SELECT * FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = ?",
      [sessionId, adapterId, "active"],
    );
    return row ? bindingFromRow(row) : undefined;
  }

  protected readLatestBinding(sessionId: string, adapterId: string): AdapterBinding | undefined {
    const row = this.store.getOptionalRow(
      "SELECT * FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? ORDER BY binding_generation DESC LIMIT 1",
      [sessionId, adapterId],
    );
    return row ? bindingFromRow(row) : undefined;
  }

  protected readBindingsForSession(sessionId: string): AdapterBinding[] {
    return this.store
      .allRows("SELECT * FROM adapter_bindings WHERE session_id = ? ORDER BY adapter_id ASC, binding_generation DESC", [sessionId])
      .map(bindingFromRow);
  }

  protected readEventsForRun(runId: string, limit: number): AgentEvent[] {
    return this.store
      .allRows("SELECT * FROM events WHERE run_id = ? ORDER BY event_seq ASC LIMIT ?", [runId, limit])
      .map(eventFromRow);
  }

  protected readArtifacts(input: InspectArtifactsInput): AgentArtifact[] {
    const where: string[] = [];
    const values: unknown[] = [];
    if (input.artifactId) {
      where.push("artifact_id = ?");
      values.push(input.artifactId);
    }
    if (input.sessionId) {
      where.push("session_id = ?");
      values.push(input.sessionId);
    }
    if (input.runId) {
      where.push("run_id = ?");
      values.push(input.runId);
    }
    if (input.attemptId) {
      where.push("attempt_id = ?");
      values.push(input.attemptId);
    }
    if (input.role) {
      where.push("role = ?");
      values.push(input.role);
    }
    const limit = boundedLimit(input.limit, 50, 200);
    return this.store
      .allRows(
        `SELECT * FROM artifacts
         ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
         ORDER BY created_at_ms DESC
         LIMIT ?`,
        [...values, limit],
      )
      .map(artifactFromRow);
  }

  protected readArtifact(artifactId: string): AgentArtifact {
    return artifactFromRow(this.store.getRow("SELECT * FROM artifacts WHERE artifact_id = ?", [artifactId]));
  }

  protected assertArtifactScope(
    artifact: AgentArtifact,
    input: Pick<UpdateArtifactLifecycleInput, "sessionId" | "runId" | "attemptId">
  ): void {
    if (input.sessionId && input.sessionId !== artifact.sessionId) {
      throw new Error(`Artifact ${artifact.artifactId} belongs to session ${artifact.sessionId}, not ${input.sessionId}`);
    }
    if (input.runId && input.runId !== artifact.runId) {
      throw new Error(`Artifact ${artifact.artifactId} belongs to run ${artifact.runId ?? "none"}, not ${input.runId}`);
    }
    if (input.attemptId && input.attemptId !== artifact.attemptId) {
      throw new Error(`Artifact ${artifact.artifactId} belongs to attempt ${artifact.attemptId ?? "none"}, not ${input.attemptId}`);
    }
  }

  protected readDelegation(delegationId: string): AgentDelegation {
    return delegationFromRow(this.store.getRow("SELECT * FROM delegations WHERE delegation_id = ?", [delegationId]));
  }

  protected readParentDelegationsForRun(runId: string): AgentDelegation[] {
    return this.store
      .allRows("SELECT * FROM delegations WHERE parent_run_id = ? ORDER BY created_at_ms ASC", [runId])
      .map(delegationFromRow);
  }

  protected readChildDelegationsForRun(runId: string): AgentDelegation[] {
    return this.store
      .allRows("SELECT * FROM delegations WHERE child_run_id = ? ORDER BY created_at_ms ASC", [runId])
      .map(delegationFromRow);
  }

  protected readDesktopDispatches(ownerId: string, limit: number): DesktopCoordinatorDispatch[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_dispatches
         WHERE owner_id = ?
         ORDER BY status = 'pending' DESC, priority DESC, created_at_ms DESC
         LIMIT ?`,
        [ownerId, limit],
      )
      .map(desktopDispatchFromRow);
  }

  protected readDesktopArtifactDeliveries(ownerId: string, limit: number): DesktopArtifactDelivery[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_artifact_deliveries
         WHERE owner_id = ?
         ORDER BY updated_at_ms DESC
         LIMIT ?`,
        [ownerId, limit],
      )
      .map(desktopArtifactDeliveryFromRow);
  }

  protected readDesktopMemoryCandidates(ownerId: string, limit: number): DesktopMemoryCandidate[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_memory_candidates
         WHERE owner_id = ?
         ORDER BY status = 'pending' DESC, created_at_ms DESC
         LIMIT ?`,
        [ownerId, limit],
      )
      .map(desktopMemoryCandidateFromRow);
  }

  protected readDesktopTaskCandidates(ownerId: string, limit: number): DesktopTaskCandidate[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_task_candidates
         WHERE owner_id = ?
         ORDER BY status = 'pending' DESC, created_at_ms DESC
         LIMIT ?`,
        [ownerId, limit],
      )
      .map(desktopTaskCandidateFromRow);
  }

  protected readDesktopAttentionOverrides(ownerId: string): DesktopAttentionOverride[] {
    return this.store
      .allRows("SELECT * FROM desktop_attention_overrides WHERE owner_id = ?", [ownerId])
      .map(desktopAttentionOverrideFromRow);
  }

  protected readDesktopQueueRuns(ownerId: string, limit: number): QueueRunInput[] {
    return this.store
      .allRows(
        `SELECT r.*, s.owner_id, s.title, s.external_ref_kind, s.external_ref_id
         FROM runs r
         JOIN sessions s ON s.session_id = r.session_id
         WHERE s.owner_id = ?
         ORDER BY r.updated_at_ms DESC
         LIMIT ?`,
        [ownerId, limit],
      )
      .map((row) => ({
        runId: stringValue(row.run_id),
        sessionId: stringValue(row.session_id),
        ownerId: stringValue(row.owner_id),
        status: stringValue(row.status) as RunStatus,
        title: nullableString(row.title),
        goalText: queueRunGoalText(row),
        completedAtMs: nullableNumber(row.completed_at_ms),
        updatedAtMs: numberValue(row.updated_at_ms),
        createdAtMs: numberValue(row.created_at_ms),
        visibleUserGoal: true,
        reusable: stringValue(row.status) === "succeeded" || stringValue(row.status) === "cancelled",
      }));
  }

  protected desktopIntentSessionCandidates(ownerId: string, surfaceKind: string, taskId: string | null): DesktopIntentSessionCandidate[] {
    const rows = this.store.allRows(
      `SELECT s.*, r.run_id, r.status AS run_status, r.updated_at_ms AS run_updated_at_ms
       FROM sessions s
       LEFT JOIN runs r ON r.run_id = (
         SELECT run_id FROM runs latest
         WHERE latest.session_id = s.session_id
         ORDER BY latest.updated_at_ms DESC
         LIMIT 1
       )
       WHERE s.owner_id = ?
       ORDER BY s.last_activity_at_ms DESC
       LIMIT 50`,
      [ownerId],
    );
    return rows.map((row) => {
      const candidateTaskId = nullableString(row.external_ref_kind) === "task" ? nullableString(row.external_ref_id) : null;
      const runStatus = nullableString(row.run_status);
      const runUpdatedAtMs = numberValue(row.run_updated_at_ms);
      const staleAfterMs = 30 * 60 * 1000;
      const relevance =
        taskId && candidateTaskId === taskId
          ? 1
          : stringValue(row.surface_kind) === surfaceKind
            ? 0.7
            : 0.2;
      return {
        sessionId: stringValue(row.session_id),
        runId: nullableString(row.run_id),
        surfaceKind: stringValue(row.surface_kind),
        taskId: candidateTaskId,
        title: nullableString(row.title),
        status: intentCandidateStatus(runStatus, runUpdatedAtMs, Date.now(), staleAfterMs),
        relevance,
        lastActivityAtMs: numberValue(row.last_activity_at_ms),
      };
    });
  }

  protected delegationDepth(parentRunId: string): number {
    const row = this.store.getRow(
      `WITH RECURSIVE ancestors(run_id, depth) AS (
         SELECT ?, 0
         UNION ALL
         SELECT r.parent_run_id, ancestors.depth + 1
         FROM runs r
         JOIN ancestors ON r.run_id = ancestors.run_id
         WHERE r.parent_run_id IS NOT NULL
       )
       SELECT COALESCE(MAX(depth), 0) AS depth FROM ancestors`,
      [parentRunId],
    );
    return Number(row.depth);
  }

  protected nextBindingGeneration(sessionId: string, adapterId: string): number {
    const row = this.store.getRow(
      "SELECT COALESCE(MAX(binding_generation), 0) AS max_generation FROM adapter_bindings WHERE session_id = ? AND adapter_id = ?",
      [sessionId, adapterId],
    );
    return Number(row.max_generation) + 1;
  }

  protected runStatus(runId: string): RunStatus {
    return String(this.store.getRow("SELECT status FROM runs WHERE run_id = ?", [runId]).status) as RunStatus;
  }

  protected isTerminalRun(runId: string): boolean {
    return TERMINAL_STATUSES.includes(this.runStatus(runId));
  }

  protected isTerminalAttempt(attemptId: string): boolean {
    const status = String(this.store.getRow("SELECT status FROM run_attempts WHERE attempt_id = ?", [attemptId]).status) as AttemptStatus;
    return TERMINAL_STATUSES.includes(status);
  }

  protected touchSession(sessionId: string): void {
    this.store.execute("UPDATE sessions SET updated_at_ms = ?, last_activity_at_ms = ? WHERE session_id = ?", [Date.now(), Date.now(), sessionId]);
    this.appendEvent({
      sessionId,
      type: "session.updated",
      payload: { sessionId },
    });
  }

  protected updateRun(runId: string, patch: Partial<AgentRun>): void {
    updateByColumns(this.store, "runs", "run_id", runId, runColumnMap, patch);
  }

  protected updateAttempt(attemptId: string, patch: Partial<RunAttempt>): void {
    updateByColumns(this.store, "run_attempts", "attempt_id", attemptId, attemptColumnMap, patch);
  }

  protected updateBinding(bindingId: string, patch: Partial<AdapterBinding>): void {
    updateByColumns(this.store, "adapter_bindings", "binding_id", bindingId, bindingColumnMap, patch);
  }
}

function requiredExternalIdentity(value: string, field: string): string {
  const normalized = value?.trim();
  if (!normalized) {
    throw new ExternalSurfaceAuthorityError("invalid_external_request", `External surface ${field} is required`);
  }
  return normalized;
}

function chatHistorySearchToolInput(input: Record<string, unknown>): {
  query: string;
  startDate?: string;
  endDate?: string;
  limit?: number;
} {
  if (typeof input.query !== "string") {
    throw new Error("search_chat_history requires a query string");
  }
  const readOptionalString = (value: unknown, field: string): string | undefined => {
    if (value === undefined) return undefined;
    if (typeof value !== "string") throw new Error(`search_chat_history ${field} must be a string`);
    return value;
  };
  if (input.limit !== undefined && (typeof input.limit !== "number" || !Number.isSafeInteger(input.limit))) {
    throw new Error("search_chat_history limit must be an integer");
  }
  return {
    query: input.query,
    startDate: readOptionalString(input.start_date, "start_date"),
    endDate: readOptionalString(input.end_date, "end_date"),
    ...(typeof input.limit === "number" ? { limit: input.limit } : {}),
  };
}

function stableExternalSpawnPillId(invocationId: string): string {
  const digest = stableHash(`external-spawn:${invocationId}`).replace(/^sha256:/, "").slice(0, 32);
  return `${digest.slice(0, 8)}-${digest.slice(8, 12)}-${digest.slice(12, 16)}-${digest.slice(16, 20)}-${digest.slice(20)}`;
}
