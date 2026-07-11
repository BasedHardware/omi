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
import {
  appendConversationTurn,
  conversationIdForSession,
  importConversationTurnsForSurface,
  recordSurfaceTurn as persistSurfaceTurn,
} from "./conversation-turns.js";
import {
  acknowledgeCompletionDelta,
  assembleTurnContext,
  bindingCarriesNativeHistory,
  getVoiceSeedContext,
} from "./turn-context.js";
import type {
  AdapterBinding,
  AgentArtifact,
  AgentDelegation,
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
import { routeDesktopIntent, type DesktopIntentRoute, type DesktopIntentRouteInput } from "./desktop-intent-router.js";
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

export class AgentRuntimeKernel extends KernelSessions {
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

  routeDesktopIntent(input: Omit<DesktopIntentRouteInput, "nowMs" | "actionQueue" | "sessionCandidates"> & { ownerId?: string }): DesktopIntentRoute {
    const ownerId = input.ownerId ?? "desktop-local-user";
    return routeDesktopIntent({
      ...input,
      nowMs: Date.now(),
      actionQueue: this.listDesktopActionQueue({ ownerId, limit: 50 }),
      sessionCandidates: this.desktopIntentSessionCandidates(ownerId, input.surfaceKind, input.taskId ?? null),
    });
  }

  createDesktopDispatch(input: NewDesktopCoordinatorDispatch): DesktopCoordinatorDispatch {
    return this.store.insertDesktopDispatch(input);
  }

  resolveDesktopDispatch(dispatchId: string, input: ResolveDesktopDispatchInput): ResolveDesktopDispatchResult {
    return this.withTransaction(() => {
      const dispatch = this.store.resolveDesktopDispatch(dispatchId, input);
      let grant: AgentGrant | null = null;
      if (input.status === "resolved" && input.grant && input.grant.effect === "allow") {
        const resolution = parseJsonObject(input.resolutionJson);
        if (dispatch.kind !== "approval") {
          throw new Error("Only approval dispatches can mint grants");
        }
        if (resolution.decision !== "allow") {
          throw new Error("Resolved dispatch grants require an allow resolution");
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
        if (!Number.isFinite(input.grant.expiresAtMs)) {
          throw new Error("Resolved dispatch grants require a finite expiry");
        }
        const sessionId = input.grant.sessionId ?? dispatch.sourceSessionId;
        if (!sessionId) {
          throw new Error("Resolved dispatch grants require a session scope");
        }
        this.assertSessionOwner(this.readSession(sessionId), input.ownerId);
        grant = this.store.insertGrant({
          ...input.grant,
          sessionId,
          runId: input.grant.runId ?? dispatch.sourceRunId,
          source: input.grant.source ?? "user",
        });
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
            },
          })
        : null;
      return { dispatch, grant, event };
    });
  }
}
