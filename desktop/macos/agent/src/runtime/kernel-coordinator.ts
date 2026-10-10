import type {
  AdapterAttemptResult,
  AdapterBindingHandle,
  CancelDispatchResult,
  OpenedBinding,
  RuntimeAdapter,
} from "../adapters/interface.js";
import type { OutboundMessage } from "../protocol.js";
import { AdapterRegistry } from "./adapter-registry.js";
import { AdapterRuntimeError, failureFromError } from "./failures.js";
import {
  clearOwnerSurfaceState,
  importLegacyMainChatSessions,
  resolveSurfaceSession,
  type LegacyMainChatSessionEntry,
  type ResolveSurfaceSessionInput,
  type ResolveSurfaceSessionResult,
} from "./surface-session.js";
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
  DelegationStatus,
  DesktopAttentionOverride,
  NewDesktopCoordinatorDispatch,
  DesktopCoordinatorDispatch,
  NewDesktopContextPacket,
} from "./types.js";
import { buildDesktopActionQueue, type DesktopActionQueueItem } from "./desktop-action-queue.js";
import { buildDesktopContextPacket, type BuiltDesktopContextPacket, type DesktopContextPacketBuildInput } from "./desktop-context-packet.js";
import {
  DesktopIntentRouter,
  type DesktopIntentEffectKind,
  type DesktopIntentRoute,
  type DesktopIntentRouteAuthority,
  type DesktopIntentRouteRequest,
  type DesktopIntentSyntaxFacts,
  type DesktopIntentTarget,
} from "./desktop-intent-router.js";
import { OmiArtifactStorage } from "./artifact-storage.js";
import { DESKTOP_APPROVAL_POLICY, type DesktopApprovalDecision } from "./desktop-tool-policy.js";
import {
  toolApprovalInvocationBinding,
  toolApprovalOffersSessionGrant,
  type ReleasedToolApproval,
  type RunToolAuthorizationOutcome,
  type ToolApprovalDenialCode,
} from "./run-tool-capability.js";
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
  DesktopAwarenessSnapshotInput,
  DesktopAwarenessSnapshot,
  DesktopActionQueueInput,
  DesktopOpenLoopsInput,
  DesktopContextPacketPersistInput,
  ResolveDesktopDispatchInput,
  ResolveDesktopDispatchResult,
  UpdateArtifactLifecycleInput,
  UpdateArtifactLifecycleResult,
  PersistArtifactInput,
  InvalidateBindingsInput,
  InvalidateBindingsResult,
  StaleProcessLocalBindingsInput,
  StaleProcessLocalBindingsResult,
  SendAgentMessageInput,
  SpawnBackgroundAgentInput,
  SpawnBackgroundAgentResult,
  DelegateAgentInput,
  DelegateAgentResult,
  KernelEventSubscriber,
  AgentRuntimeKernelOptions,
} from "./kernel-types.js";
import { StaleAdapterBindingError } from "./kernel-types.js";

import { KernelSessions } from "./kernel-sessions.js";
import {
  buildWorkstreamOpenLoopSnapshot,
  deliverDesktopTaskCandidate,
  exportWorkstreamContinuationCheckpoint,
  importWorkstreamContinuationCheckpoint,
  migrateTaskSessionsToWorkstreams,
  persistWorkstreamArtifactVersion,
  persistAuthorizedPreparedArtifact,
  persistWorkstreamContextPacket,
  projectWorkstreamContinuity,
  projectCanonicalCandidateResolution,
  readWorkstreamContinuationCheckpoint,
  reconcileLegacyTaskCandidateOutbox,
  resolveWorkstreamSession,
  type CanonicalCandidateTransport,
  type PersistWorkstreamArtifactVersionInput,
  type PersistAuthorizedPreparedArtifactInput,
  type PersistWorkstreamContextInput,
  type TaskSessionMigrationReport,
  type WorkstreamContinuationCheckpoint,
  type WorkstreamOpenLoopSnapshot,
  type WorkstreamProductContext,
  type WorkstreamSessionInput,
} from "./workstream-continuity.js";

/**
 * Longest grant a user answer may mint through a dispatch. "Allow for this
 * chat" is meant in hours, not forever; a longer request is a configuration
 * mistake, never a durable broad grant (control-plane spec section 17).
 */
const MAX_DESKTOP_DISPATCH_GRANT_TTL_MS = 24 * 60 * 60_000;

/** The only payload key a model-created dispatch may never carry: it would impersonate a parked tool invocation. */
const TOOL_APPROVAL_BINDING_PAYLOAD_KEY = "invocation";

export class AgentRuntimeKernel extends KernelSessions {
  private readonly desktopIntentRouter = new DesktopIntentRouter();

  resolveWorkstreamSession(input: WorkstreamSessionInput): ResolveSurfaceSessionResult {
    return resolveWorkstreamSession(this.store, input);
  }

  persistWorkstreamContextPacket(input: PersistWorkstreamContextInput): BuiltDesktopContextPacket {
    return persistWorkstreamContextPacket(this.store, input);
  }

  persistWorkstreamArtifactVersion(input: PersistWorkstreamArtifactVersionInput) {
    return persistWorkstreamArtifactVersion(this.store, input);
  }

  persistAuthorizedPreparedArtifact(input: PersistAuthorizedPreparedArtifactInput) {
    return persistAuthorizedPreparedArtifact(this.store, input);
  }

  projectWorkstreamContinuity(input: { ownerId: string; workstreamId: string; nowMs?: number }) {
    return projectWorkstreamContinuity(this.store, input);
  }

  exportWorkstreamContinuationCheckpoint(input: WorkstreamSessionInput & {
    sourceRuntimeId?: string;
    context: WorkstreamProductContext;
    ttlMs: number;
    nowMs?: number;
    exportDispatchId?: string;
  }): WorkstreamContinuationCheckpoint {
    return exportWorkstreamContinuationCheckpoint(this.store, {
      ...input,
      sourceRuntimeId: input.sourceRuntimeId ?? this.runtimeNodeId,
    });
  }

  importWorkstreamContinuationCheckpoint(
    checkpoint: WorkstreamContinuationCheckpoint,
    input: { targetRuntimeId?: string; nowMs?: number } = {},
  ): ResolveSurfaceSessionResult {
    return importWorkstreamContinuationCheckpoint(this.store, checkpoint, {
      ...input,
      targetRuntimeId: input.targetRuntimeId ?? this.runtimeNodeId,
    });
  }

  deliverDesktopTaskCandidate(input: {
    ownerId: string;
    candidateId: string;
    transport: CanonicalCandidateTransport;
    nowMs?: () => number;
  }) {
    return deliverDesktopTaskCandidate(this.store, input);
  }

  projectCanonicalCandidateResolution(input: Parameters<typeof projectCanonicalCandidateResolution>[1]) {
    return projectCanonicalCandidateResolution(this.store, input);
  }

  reconcileLegacyTaskCandidateOutbox(input: Parameters<typeof reconcileLegacyTaskCandidateOutbox>[1]) {
    return reconcileLegacyTaskCandidateOutbox(this.store, input);
  }

  readWorkstreamContinuationCheckpoint(input: Parameters<typeof readWorkstreamContinuationCheckpoint>[1]) {
    return readWorkstreamContinuationCheckpoint(this.store, input);
  }

  buildWorkstreamOpenLoopSnapshot(input: {
    ownerId?: string;
    ttlMs?: number;
    nowMs?: number;
    limit?: number;
  } = {}): WorkstreamOpenLoopSnapshot {
    const ownerId = input.ownerId ?? "desktop-local-user";
    const sessionWorkstreamIds = new Map(
      this.store
        .allRows(
          `SELECT session_id, external_ref_id FROM sessions
           WHERE owner_id = ? AND external_ref_kind = 'workstream'`,
          [ownerId],
        )
        .map((row) => [String(row.session_id), String(row.external_ref_id)] as const),
    );
    return buildWorkstreamOpenLoopSnapshot({
      ownerId,
      sourceRuntimeId: this.runtimeNodeId,
      actionQueue: this.listDesktopActionQueue({ ownerId, limit: input.limit }),
      sessionWorkstreamIds,
      ttlMs: input.ttlMs,
      nowMs: input.nowMs,
    });
  }

  migrateTaskSessionsToWorkstreams(input: {
    ownerId: string;
    mappings: Array<{ taskId: string; workstreamId: string }>;
    nowMs?: number;
  }): TaskSessionMigrationReport {
    return migrateTaskSessionsToWorkstreams(this.store, {
      ...input,
      sourceRuntimeId: this.runtimeNodeId,
    });
  }

  buildDesktopAwarenessSnapshot(input: DesktopAwarenessSnapshotInput): DesktopAwarenessSnapshot {
    const ownerId = input.ownerId ?? "desktop-local-user";
    const limit = boundedLimit(input.limit, 50, 200);
    const sessions = this.listSessions({ ownerId, limit });
    const runs = this.store
      .allRows(
        `SELECT r.*
         FROM runs r
         JOIN sessions s ON s.session_id = r.session_id
         WHERE s.owner_id = ?
         ORDER BY r.updated_at_ms DESC
         LIMIT ?`,
        [ownerId, limit],
      )
      .map(runFromRow);
    const dispatches = this.readDesktopDispatches(ownerId, limit);
    const artifactDeliveries = this.readDesktopArtifactDeliveries(ownerId, limit);
    const memoryCandidates = this.readDesktopMemoryCandidates(ownerId, limit);
    const taskCandidates = this.readDesktopTaskCandidates(ownerId, limit);
    return {
      ownerId,
      generatedAtMs: Date.now(),
      sessions,
      runs,
      dispatches,
      artifactDeliveries,
      memoryCandidates,
      taskCandidates,
      actionQueue: this.listDesktopActionQueue({ ownerId, limit }),
      runtime: {
        activeExecutionCount: this.activeExecutions.size,
        registeredAdapters: this.registry.adapterIds(),
      },
    };
  }

  listDesktopActionQueue(input: DesktopActionQueueInput): DesktopActionQueueItem[] {
    const ownerId = input.ownerId ?? "desktop-local-user";
    const limit = boundedLimit(input.limit, 50, 200);
    const nowMs = Date.now();
    const runWindow = this.readDesktopQueueRuns(ownerId, Math.max(limit * 5, 200));
    const queue = buildDesktopActionQueue({
      nowMs,
      staleAfterMs: input.staleAfterMs,
      dispatches: this.readDesktopDispatches(ownerId, limit).map(dispatchToQueueInput),
      runs: runWindow,
      runItemLimit: limit,
      runSuppressionContext: runWindow,
      artifactDeliveries: this.readDesktopArtifactDeliveries(ownerId, limit).map(deliveryToQueueInput),
      candidates: [
        ...this.readDesktopMemoryCandidates(ownerId, limit).map(memoryCandidateToQueueInput),
        ...this.readDesktopTaskCandidates(ownerId, limit).map(taskCandidateToQueueInput),
      ],
      overrides: this.readDesktopAttentionOverrides(ownerId).map(overrideToQueueInput),
    });
    return queue.slice(0, limit);
  }

  listDesktopAttentionOverrides(ownerId: string): DesktopAttentionOverride[] {
    return this.readDesktopAttentionOverrides(ownerId);
  }

  setDesktopAttentionOverride(input: {
    ownerId: string;
    subjectKind: string;
    subjectId: string;
    dismissedAtMs?: number | null;
    hiddenUntilMs?: number | null;
    reason?: string | null;
  }): DesktopAttentionOverride {
    return this.store.upsertDesktopAttentionOverride({
      ownerId: input.ownerId,
      subjectKind: input.subjectKind,
      subjectId: input.subjectId,
      dismissedAtMs: input.dismissedAtMs ?? null,
      hiddenUntilMs: input.hiddenUntilMs ?? null,
      reason: input.reason ?? null,
    });
  }

  getDesktopOpenLoops(input: DesktopOpenLoopsInput): WorkstreamOpenLoopSnapshot {
    return this.buildWorkstreamOpenLoopSnapshot(input);
  }

  persistDesktopContextPacket(input: DesktopContextPacketPersistInput): BuiltDesktopContextPacket {
    const ownerId = input.ownerId ?? "desktop-local-user";
    this.validateSensitiveContextDispatches({ ...input, ownerId });
    const built = buildDesktopContextPacket({ ...input, ownerId });
    this.withTransaction(() => {
      this.store.insertDesktopContextPacket({
        ...(built.packet as unknown as NewDesktopContextPacket),
        packetJson: JSON.stringify(built.packet.packetJson),
        redactedPreviewJson: JSON.stringify(built.packet.redactedPreviewJson),
      });
      for (const accessLog of built.accessLogs) {
        this.store.insertDesktopContextAccessLog(accessLog);
      }
    });
    return built;
  }

  routeDesktopIntent(input: DesktopIntentRouteRequest & { ownerId?: string; callerSessionId?: string }): DesktopIntentRoute {
    const ownerId = input.ownerId ?? "desktop-local-user";
    const caller = this.desktopIntentCallerAuthority({
      ownerId,
      callerSessionId: input.callerSessionId,
      requestedSurfaceKind: input.surfaceKind,
    });
    const request = this.desktopIntentRequest(input, caller.surfaceKind);
    return this.desktopIntentRouter.route(request, this.desktopIntentAuthority(ownerId, caller.executionRole, request.syntaxFacts));
  }

  async applyDesktopIntentEffect<T>(
    input: {
      ownerId?: string;
      callerSessionId?: string;
      restrictiveCallerExecutionRole?: "coordinator" | "leaf";
      surfaceKind: string;
      snapshotVersion?: string;
      utterance: string;
      effect: DesktopIntentEffectKind;
      syntaxFacts?: DesktopIntentSyntaxFacts;
    },
    effect: (decision: Extract<DesktopIntentRoute, { intent: DesktopIntentEffectKind }>) => T | Promise<T>,
  ): Promise<{ decision: Extract<DesktopIntentRoute, { intent: DesktopIntentEffectKind }>; result: T }> {
    const ownerId = input.ownerId ?? "desktop-local-user";
    const caller = this.desktopIntentCallerAuthority({
      ownerId,
      callerSessionId: input.callerSessionId,
      requestedSurfaceKind: input.surfaceKind,
      restrictiveCallerExecutionRole: input.restrictiveCallerExecutionRole,
    });
    const request: DesktopIntentRouteRequest = {
      utterance: input.utterance,
      surfaceKind: caller.surfaceKind,
      snapshotVersion: input.snapshotVersion,
      syntaxFacts: input.syntaxFacts,
      proposal: { intent: input.effect },
    };
    const applied = await this.desktopIntentRouter.routeAndApply(
      request,
      this.desktopIntentAuthority(ownerId, caller.executionRole, input.syntaxFacts),
      input.effect,
      effect,
    );
    return applied as {
      decision: Extract<DesktopIntentRoute, { intent: DesktopIntentEffectKind }>;
      result: T;
    };
  }

  private desktopIntentRequest(
    input: DesktopIntentRouteRequest & { callerSessionId?: string },
    surfaceKind: string,
  ): DesktopIntentRouteRequest {
    return {
      utterance: input.utterance,
      surfaceKind,
      taskId: input.taskId,
      snapshotVersion: input.snapshotVersion,
      syntaxFacts: input.syntaxFacts,
      proposal: input.proposal,
    };
  }

  private desktopIntentCallerAuthority(input: {
    ownerId: string;
    callerSessionId?: string;
    requestedSurfaceKind: string;
    restrictiveCallerExecutionRole?: "coordinator" | "leaf";
  }): { executionRole: "coordinator" | "leaf"; surfaceKind: string } {
    let executionRole: "coordinator" | "leaf" = "coordinator";
    let surfaceKind = input.requestedSurfaceKind;
    if (input.callerSessionId) {
      const session = this.readSession(input.callerSessionId);
      this.assertSessionOwner(session, input.ownerId);
      executionRole = session.executionRole;
      surfaceKind = session.surfaceKind;
    }
    // A call-site hint can only reduce authority. It can never promote a
    // persisted leaf session into a coordinator.
    if (input.restrictiveCallerExecutionRole === "leaf") {
      executionRole = "leaf";
    }
    return { executionRole, surfaceKind };
  }

  private desktopIntentAuthority(
    ownerId: string,
    callerExecutionRole: "coordinator" | "leaf",
    syntaxFacts: DesktopIntentSyntaxFacts | undefined,
  ): DesktopIntentRouteAuthority {
    return {
      ownerId,
      callerExecutionRole,
      availableAdapterIds: this.registry.adapterIds(),
      continuationTarget: this.desktopIntentContinuationTarget(ownerId, syntaxFacts),
      parentRunAvailable: this.desktopIntentParentRunAvailable(ownerId, syntaxFacts?.parentRunId),
      nowMs: Date.now(),
    };
  }

  private desktopIntentContinuationTarget(
    ownerId: string,
    syntaxFacts: DesktopIntentSyntaxFacts | undefined,
  ): DesktopIntentTarget | null {
    const requestedSessionId = syntaxFacts?.explicitSessionId?.trim() || null;
    const requestedRunId = syntaxFacts?.explicitRunId?.trim() || null;
    if (!requestedSessionId && !requestedRunId) return null;
    try {
      const run = requestedRunId ? this.readRun(requestedRunId) : null;
      const sessionId = requestedSessionId ?? run?.sessionId ?? null;
      if (!sessionId || (run && run.sessionId !== sessionId)) return null;
      const session = this.readSession(sessionId);
      this.assertSessionOwner(session, ownerId);
      return {
        sessionId,
        runId: run?.runId ?? null,
        status: session.status === "open" ? "open" : "closed",
      };
    } catch {
      return null;
    }
  }

  private desktopIntentParentRunAvailable(ownerId: string, parentRunId: string | null | undefined): boolean | undefined {
    const normalizedParentRunId = parentRunId?.trim();
    if (!normalizedParentRunId) return undefined;
    try {
      this.assertRunOwner(this.readRun(normalizedParentRunId), ownerId);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Dispatches created through the control tool are ordinary decision items.
   * Only the capability broker binds a dispatch to a prepared tool invocation,
   * so the binding key is stripped here: a forged one would otherwise be
   * treated as a tool approval that no live invocation can ever resolve.
   */
  createDesktopDispatch(input: NewDesktopCoordinatorDispatch): DesktopCoordinatorDispatch {
    const payload = parseJsonObject(input.payloadJson);
    if (TOOL_APPROVAL_BINDING_PAYLOAD_KEY in payload) {
      const { [TOOL_APPROVAL_BINDING_PAYLOAD_KEY]: _binding, ...rest } = payload;
      return this.store.insertDesktopDispatch({ ...input, payloadJson: JSON.stringify(rest) });
    }
    return this.store.insertDesktopDispatch(input);
  }

  /**
   * Interim gate, see `AgentRuntimeKernelOptions.desktopToolApprovalsEnabled`.
   * The relay turns it on when a connected client declares it can render the
   * approval card.
   */
  setDesktopToolApprovalsEnabled(enabled: boolean): void {
    this.desktopToolApprovalsEnabled = enabled;
  }

  /**
   * Relay authorization for the stdio tool lane. A sensitive device tool
   * without a covering grant is parked: its `prepared` ledger row, the
   * approval dispatch, the run/attempt `waiting_approval` transition, and the
   * `run.waiting_approval` + `approval.requested` events commit together.
   * With the gate off, this is exactly `authorizeRelayedRunToolInvocation`.
   */
  authorizeRelayedRunToolInvocationOrRequestApproval(input: {
    capabilityRef: string;
    invocationId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): RunToolAuthorizationOutcome & { event?: AgentEvent } {
    if (!this.desktopToolApprovalsEnabled) {
      return { kind: "authorized", invocation: this.toolCapabilities.authorizeRelayInvocation(input) };
    }
    return this.withTransaction(() => {
      const outcome = this.toolCapabilities.authorizeRelayInvocationOrRequestApproval(input);
      if (outcome.kind === "authorized") return outcome;
      const { invocation, dispatch, request } = outcome;
      const now = dispatch.createdAtMs;
      this.updateRun(invocation.runId, { status: "waiting_approval", updatedAtMs: now });
      this.updateAttempt(invocation.attemptId, { status: "waiting_approval", updatedAtMs: now });
      this.appendEvent({
        sessionId: invocation.sessionId,
        runId: invocation.runId,
        attemptId: invocation.attemptId,
        type: "run.waiting_approval",
        payload: { runId: invocation.runId, attemptId: invocation.attemptId, approvalId: dispatch.dispatchId },
      });
      const event = this.appendEvent({
        sessionId: invocation.sessionId,
        runId: invocation.runId,
        attemptId: invocation.attemptId,
        type: "approval.requested",
        payload: {
          approvalId: dispatch.dispatchId,
          dispatchId: dispatch.dispatchId,
          policy: request.policy,
          adapterId: invocation.adapterId,
          surfaceKind: invocation.surfaceKind,
          invocationId: invocation.invocationId,
          toolName: invocation.canonicalToolName,
          capability: request.capability,
          operation: request.operation,
          resourceRef: request.resourceRef,
          resourcePattern: request.resourceRef,
          inputHash: invocation.inputHash,
          effectClass: invocation.effectClass,
          title: request.title,
          decisionPrompt: request.decisionPrompt,
          preview: request.preview,
          previewTruncated: request.previewTruncated,
          reason: request.reason,
          options: request.options,
          defaultOptionId: request.defaultOptionId,
          requestedAtMs: request.requestedAtMs,
          expiresAtMs: request.expiresAtMs,
        },
      });
      return { ...outcome, event };
    });
  }

  resolveDesktopDispatch(dispatchId: string, input: ResolveDesktopDispatchInput): ResolveDesktopDispatchResult {
    const resolution = parseJsonObject(input.resolutionJson);
    // Decide the tool-approval question before any row changes. An authority
    // failure here may revoke the capability, and that revocation (which
    // cancels the dispatch row) must commit on its own rather than roll back
    // together with the resolution it refused.
    const pendingRow = this.store.getOptionalRow(
      "SELECT * FROM desktop_dispatches WHERE dispatch_id = ? AND status = 'pending'",
      [dispatchId],
    );
    const pendingBinding = pendingRow ? toolApprovalInvocationBinding(desktopDispatchFromRow(pendingRow)) : null;
    let decision: DesktopApprovalDecision | null = null;
    if (pendingBinding) {
      // An invocation-bound approval is a yes/no about one physical effect;
      // a free-form resolution cannot leave the parked invocation undecided.
      decision = input.status === "cancelled"
        ? "deny"
        : resolution.decision === "allow" || resolution.decision === "deny"
          ? resolution.decision
          : null;
      if (!decision) {
        throw new Error("Tool approval resolution requires resolution.decision of allow or deny");
      }
      if (decision === "allow") {
        this.toolCapabilities.assertApprovalAuthority({ dispatchId, binding: pendingBinding, activeOwnerId: input.ownerId });
      }
    }
    let released: ReleasedToolApproval | null = null;
    try {
      return this.withTransaction(() => {
        const dispatch = this.store.resolveDesktopDispatch(dispatchId, input);
        const binding = toolApprovalInvocationBinding(dispatch);
        let grant: AgentGrant | null = null;
        if (input.status === "resolved" && input.grant && input.grant.effect === "allow") {
          if (dispatch.kind !== "approval") {
            throw new Error("Only approval dispatches can mint grants");
          }
          if (resolution.decision !== "allow") {
            throw new Error("Resolved dispatch grants require an allow resolution");
          }
          if (binding && !toolApprovalOffersSessionGrant(dispatch)) {
            throw new Error("This approval offers no session grant; it can only be allowed once");
          }
          if (!dispatch.capability || input.grant.capability !== dispatch.capability) {
            throw new Error("Resolved dispatch grant capability must match the approval request");
          }
          if (!dispatch.operation || input.grant.operation !== dispatch.operation) {
            throw new Error("Resolved dispatch grant operation must match the approval request");
          }
          if (!dispatch.resourceRef || input.grant.resourcePattern !== dispatch.resourceRef) {
            throw new Error("Resolved dispatch grant resource must match the approval request");
          }
          const grantExpiresAtMs = input.grant.expiresAtMs;
          if (typeof grantExpiresAtMs !== "number" || !Number.isFinite(grantExpiresAtMs)) {
            throw new Error("Resolved dispatch grants require a finite expiry");
          }
          const resolvedAtMs = dispatch.resolvedAtMs ?? Date.now();
          if (grantExpiresAtMs <= resolvedAtMs) {
            throw new Error("Resolved dispatch grants must expire in the future");
          }
          if (grantExpiresAtMs - resolvedAtMs > MAX_DESKTOP_DISPATCH_GRANT_TTL_MS) {
            throw new Error("Resolved dispatch grants may last at most 24 hours");
          }
          const sessionId = input.grant.sessionId ?? dispatch.sourceSessionId;
          if (!sessionId) {
            throw new Error("Resolved dispatch grants require a session scope");
          }
          this.assertSessionOwner(this.readSession(sessionId), input.ownerId);
          grant = this.store.insertGrant({
            ...input.grant,
            sessionId,
            // An explicit null scopes the grant to the whole session ("allow for
            // this chat"); an omitted runId keeps the historical run-scoped default.
            runId: input.grant.runId !== undefined ? input.grant.runId : dispatch.sourceRunId,
            source: input.grant.source ?? "user",
          });
        }
        let selectedOptionId: string | null = null;
        if (binding && decision) {
          if (decision === "allow") {
            released = this.toolCapabilities.approveInvocation({ dispatchId, binding, activeOwnerId: input.ownerId }).released;
            selectedOptionId = grant ? "allow_session" : "allow_once";
          } else {
            released = this.toolCapabilities.denyInvocation({ dispatchId, binding, code: "approval_denied" }).released;
            selectedOptionId = "deny";
          }
        }
        const event = dispatch.sourceSessionId
          ? this.appendEvent({
              sessionId: dispatch.sourceSessionId,
              runId: dispatch.sourceRunId,
              attemptId: dispatch.sourceAttemptId,
              type: "approval.resolved",
              payload: {
                dispatchId: dispatch.dispatchId,
                status: dispatch.status,
                resolvedBy: dispatch.resolvedBy,
                resolution: parseJsonObject(dispatch.resolutionJson),
                grantId: grant?.grantId ?? null,
                ...(binding
                  ? {
                      approvalId: dispatch.dispatchId,
                      policy: DESKTOP_APPROVAL_POLICY,
                      adapterId: binding.adapterId,
                      invocationId: binding.invocationId,
                      toolName: binding.toolName,
                      decision,
                      selectedOptionId,
                      automatic: false,
                      resolvedAtMs: dispatch.resolvedAtMs,
                    }
                  : {}),
              },
            })
          : null;
        // The decision is recorded first; the run resuming is its consequence.
        if (binding && decision) this.resumeRunAfterApproval(dispatch);
        return { dispatch, grant, event };
      });
    } catch (error) {
      // The rows rolled back; the broker's memory must say "still parked" too.
      if (released) this.toolCapabilities.restorePendingApproval(released);
      throw error;
    }
  }

  /**
   * Close a parked approval without a user decision: the wait expired, or the
   * relay client that was waiting for the result went away. The invocation
   * fails closed and the run resumes so the model receives `approval_denied`.
   */
  terminateDesktopToolApproval(input: {
    dispatchId: string;
    status: "expired" | "cancelled";
    reason: string;
    nowMs?: number;
  }): ResolveDesktopDispatchResult {
    let released: ReleasedToolApproval | null = null;
    try {
      return this.withTransaction(() => {
        const row = this.store.getOptionalRow(
          "SELECT * FROM desktop_dispatches WHERE dispatch_id = ? AND status = 'pending'",
          [input.dispatchId],
        );
        if (!row) throw new Error(`Desktop dispatch ${input.dispatchId} is not pending`);
        const pending = desktopDispatchFromRow(row);
        const binding = toolApprovalInvocationBinding(pending);
        if (!binding) throw new Error(`Desktop dispatch ${input.dispatchId} is not bound to a tool invocation`);
        const now = input.nowMs ?? Date.now();
        const decision: DesktopApprovalDecision = input.status;
        const resolutionJson = JSON.stringify({ decision, reason: input.reason });
        const changed = this.store.execute(
          `UPDATE desktop_dispatches
           SET status = ?, resolved_at_ms = ?, resolved_by = 'system', resolution_json = ?
           WHERE dispatch_id = ? AND status = 'pending'`,
          [input.status, now, resolutionJson, input.dispatchId],
        );
        if (changed !== 1) throw new Error(`Desktop dispatch ${input.dispatchId} is not pending`);
        const code: ToolApprovalDenialCode = input.status === "expired" ? "approval_expired" : "approval_cancelled";
        released = this.toolCapabilities.denyInvocation({ dispatchId: input.dispatchId, binding, code }).released;
        const dispatch = desktopDispatchFromRow(
          this.store.getRow("SELECT * FROM desktop_dispatches WHERE dispatch_id = ?", [input.dispatchId]),
        );
        const event = dispatch.sourceSessionId
          ? this.appendEvent({
              sessionId: dispatch.sourceSessionId,
              runId: dispatch.sourceRunId,
              attemptId: dispatch.sourceAttemptId,
              type: "approval.resolved",
              payload: {
                approvalId: dispatch.dispatchId,
                dispatchId: dispatch.dispatchId,
                policy: DESKTOP_APPROVAL_POLICY,
                adapterId: binding.adapterId,
                invocationId: binding.invocationId,
                toolName: binding.toolName,
                status: dispatch.status,
                decision,
                selectedOptionId: null,
                grantId: null,
                automatic: true,
                resolvedBy: dispatch.resolvedBy,
                resolvedAtMs: dispatch.resolvedAtMs,
                resolution: parseJsonObject(dispatch.resolutionJson),
              },
            })
          : null;
        this.resumeRunAfterApproval(dispatch);
        return { dispatch, grant: null, event };
      });
    } catch (error) {
      if (released) this.toolCapabilities.restorePendingApproval(released);
      throw error;
    }
  }

  /** The run was parked only for approvals; once none remain it is running again. */
  private resumeRunAfterApproval(dispatch: DesktopCoordinatorDispatch): void {
    if (!dispatch.sourceRunId || !dispatch.sourceAttemptId) return;
    if (this.toolCapabilities.hasPendingApprovals(dispatch.sourceRunId)) return;
    const run = this.store.getOptionalRow("SELECT status FROM runs WHERE run_id = ?", [dispatch.sourceRunId]);
    const attempt = this.store.getOptionalRow(
      "SELECT status FROM run_attempts WHERE attempt_id = ?",
      [dispatch.sourceAttemptId],
    );
    if (run?.status !== "waiting_approval" || attempt?.status !== "waiting_approval") return;
    const now = dispatch.resolvedAtMs ?? Date.now();
    this.updateRun(dispatch.sourceRunId, { status: "running", updatedAtMs: now });
    this.updateAttempt(dispatch.sourceAttemptId, { status: "running", updatedAtMs: now });
    if (dispatch.sourceSessionId) {
      this.appendEvent({
        sessionId: dispatch.sourceSessionId,
        runId: dispatch.sourceRunId,
        attemptId: dispatch.sourceAttemptId,
        type: "run.running",
        payload: { runId: dispatch.sourceRunId, attemptId: dispatch.sourceAttemptId, resumedAfterApprovalId: dispatch.dispatchId },
      });
    }
  }
}
