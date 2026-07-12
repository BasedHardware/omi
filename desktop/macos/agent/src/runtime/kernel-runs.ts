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
} from "./surface-session.js";
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
} from "./types.js";
import { buildDesktopActionQueue } from "./desktop-action-queue.js";
import { buildDesktopContextPacket, type DesktopContextPacketBuildInput } from "./desktop-context-packet.js";
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

import { KernelCore } from "./kernel-core.js";
import { ensureAgentSpawnJournalIfPresent } from "./agent-spawn-journal.js";

export class KernelRuns extends KernelCore {
  async executeRun(input: ExecuteAgentRunInput): Promise<KernelRunResult> {
    const accepted = this.createAcceptedRun(input);
    return this.executeAcceptedRun(input, accepted);
  }

  async sendAgentMessage(input: SendAgentMessageInput): Promise<KernelRunResult> {
    const session = this.readSession(input.sessionId);
    if (input.adapterId !== undefined && input.adapterId !== session.defaultAdapterId) {
      throw new Error("Existing session execution profile rejects adapter override");
    }
    if (input.model !== undefined && input.model !== session.modelProfile) {
      throw new Error("Existing session execution profile rejects model override");
    }
    if (input.cwd !== undefined && input.cwd !== session.defaultCwd) {
      throw new Error("Existing session execution profile rejects cwd override");
    }
    return this.executeRun({
      ownerId: input.ownerId,
      sessionId: input.sessionId,
      surfaceKind: session.surfaceKind,
      defaultAdapterId: session.defaultAdapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: input.prompt,
      promptBlocks: input.promptBlocks,
      mode: input.mode,
      adapterId: session.defaultAdapterId,
      cwd: session.defaultCwd ?? undefined,
      model: session.modelProfile ?? undefined,
      mcpServers: input.mcpServers,
      maxAttempts: input.maxAttempts,
      recoverAfterError: input.recoverAfterError,
      metadata: input.metadata,
    });
  }

  async spawnBackgroundAgent(input: SpawnBackgroundAgentInput): Promise<SpawnBackgroundAgentResult> {
    let owningSession: AgentSession | undefined;
    if (input.callerSessionId) {
      const callerSession = this.readSession(input.callerSessionId);
      owningSession = callerSession;
      this.assertSessionOwner(callerSession, input.ownerId);
      if (callerSession.executionRole === "leaf") {
        throw new Error("Leaf workers cannot create background agents.");
      }
    } else if (!input.trustedUserSpawn) {
      throw new Error("Background agent spawn requires a coordinator caller session.");
    }
    const adapterId = owningSession?.defaultAdapterId ?? input.adapterId ?? input.defaultAdapterId ?? "pi-mono";
    const modelProfile = owningSession ? owningSession.modelProfile : (input.model ?? null);
    if (owningSession && input.adapterId !== undefined && input.adapterId !== adapterId) {
      throw new Error("Child execution profile must inherit the coordinator adapter");
    }
    if (owningSession && input.model !== undefined && input.model !== modelProfile) {
      throw new Error("Child execution profile must inherit the coordinator model profile");
    }
    const runInput: ExecuteAgentRunInput = {
      ownerId: input.ownerId,
      surfaceKind: input.surfaceKind ?? "floating_bar",
      executionRole: "leaf",
      executionProfileSource: "child_derivation",
      externalRefKind: input.externalRefKind,
      externalRefId: input.externalRefId,
      title: input.title ?? `Background: ${input.prompt.slice(0, 80)}`,
      defaultAdapterId: adapterId,
      adapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: input.prompt,
      mode: input.mode ?? "act",
      cwd: owningSession?.defaultCwd ?? input.cwd,
      model: modelProfile ?? undefined,
      mcpServers: input.mcpServers,
      maxAttempts: input.maxAttempts,
      recoverAfterError: input.recoverAfterError,
      metadata: {
        ...(input.metadata ?? {}),
        spawnKind: "background_agent",
      },
      admittedContextSnapshot: input.admittedContextSnapshot,
    };
    const accepted = this.createAcceptedRun(runInput);
    const producerJournal = ensureAgentSpawnJournalIfPresent(this.store, {
      ownerId: input.ownerId,
      sessionId: accepted.session.sessionId,
      runId: accepted.run.runId,
    });
    void this.executeAcceptedRun(runInput, accepted)
      .then(() => {
        if (!producerJournal) return;
        try {
          ensureAgentSpawnJournalIfPresent(this.store, {
            ownerId: input.ownerId,
            sessionId: accepted.session.sessionId,
            runId: accepted.run.runId,
          });
        } catch {
          // Startup metadata repair closes a process-exit race after acceptance.
        }
      })
      .catch(() => {
        // executeAcceptedRun records the failed run/attempt and emits events.
        if (!producerJournal) return;
        try {
          ensureAgentSpawnJournalIfPresent(this.store, {
            ownerId: input.ownerId,
            sessionId: accepted.session.sessionId,
            runId: accepted.run.runId,
          });
        } catch {
          // Startup metadata repair closes a process-exit race after acceptance.
        }
      });
    return {
      session: accepted.session,
      run: accepted.run,
    };
  }

  async delegateAgent(input: DelegateAgentInput): Promise<DelegateAgentResult> {
    this.assertDelegationConstraints(input);
    const parentRun = this.readRun(input.parentRunId);
    const parentSession = this.readSession(parentRun.sessionId);
    if (parentSession.executionRole === "leaf") {
      throw new Error("Leaf workers cannot create delegated agents.");
    }
    if (input.ownerId && parentSession.ownerId !== input.ownerId) {
      throw new Error(`Parent run ${input.parentRunId} does not belong to owner ${input.ownerId}`);
    }
    const ownerId = input.ownerId ?? parentSession.ownerId;
    const childPrompt = buildDelegatedPrompt(input.objective, input.context);
    if (input.adapterId !== undefined && input.adapterId !== parentSession.defaultAdapterId) {
      throw new Error("Delegated execution profile must inherit the parent adapter");
    }
    if (input.model !== undefined && input.model !== parentSession.modelProfile) {
      throw new Error("Delegated execution profile must inherit the parent model profile");
    }
    const childRunInput: ExecuteAgentRunInput = {
      ownerId,
      sessionId: input.mode === "continue" ? requiredChildSessionId(input.childSessionId) : input.childSessionId,
      surfaceKind: input.childSurfaceKind ?? "delegated_agent",
      executionRole: "leaf",
      executionProfileSource: "child_derivation",
      providerBoundary: parentSession.providerBoundary,
      externalRefKind: input.childExternalRefKind,
      externalRefId: input.childExternalRefId,
      title: input.childTitle ?? `Delegated: ${input.objective.slice(0, 80)}`,
      defaultAdapterId: parentSession.defaultAdapterId,
      adapterId: parentSession.defaultAdapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: childPrompt,
      mode: input.runMode ?? "ask",
      cwd: parentSession.defaultCwd ?? parentRun.cwd ?? undefined,
      model: parentSession.modelProfile ?? undefined,
      mcpServers: input.mcpServers,
      maxAttempts: input.maxAttempts,
      recoverAfterError: input.recoverAfterError,
      parentRunId: parentRun.runId,
      metadata: {
        ...(input.metadata ?? {}),
        delegationMode: input.mode,
        parentRunId: parentRun.runId,
        maxDepth: input.maxDepth ?? DEFAULT_DELEGATION_MAX_DEPTH,
        maxBudgetUsd: input.maxBudgetUsd ?? DEFAULT_DELEGATION_MAX_BUDGET_USD,
      },
    };
    const created = this.createDelegatedRun(parentSession, parentRun, childRunInput, input);
    const producerJournal = ensureAgentSpawnJournalIfPresent(this.store, {
      ownerId,
      sessionId: created.session.sessionId,
      runId: created.run.runId,
    });

    if (input.mode === "spawn") {
      const runningDelegation = this.updateDelegationStatus(created.delegation, "running");
      void this.executeDelegationAsync(childRunInput, { ...created, delegation: runningDelegation }, false)
        .then(() => {
          if (!producerJournal) return;
          try {
            ensureAgentSpawnJournalIfPresent(this.store, {
              ownerId,
              sessionId: created.session.sessionId,
              runId: created.run.runId,
            });
          } catch {
            // Startup metadata repair closes a process-exit race after acceptance.
          }
        })
        .catch((error) => {
          this.updateDelegationStatus(runningDelegation, "failed", messageFrom(error));
          if (!producerJournal) return;
          try {
            ensureAgentSpawnJournalIfPresent(this.store, {
              ownerId,
              sessionId: created.session.sessionId,
              runId: created.run.runId,
            });
          } catch {
            // Startup metadata repair closes a process-exit race after acceptance.
          }
        });
      return {
        delegation: runningDelegation,
        childSession: created.session,
        childRun: created.run,
      };
    }

    return this.executeDelegationAsync(childRunInput, created);
  }

  async cancelRun(runId: string, input: { ownerId?: string } = {}): Promise<CancelRunResult> {
    const active = this.activeExecutions.get(runId);
    const run = this.readRun(runId);
    if (input.ownerId) {
      this.assertRunOwner(run, input.ownerId);
    }
    if (TERMINAL_STATUSES.includes(run.status)) {
      return {
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        runId,
      };
    }
    const attempt = this.readActiveAttempt(runId);
    const requestedAt = Date.now();

    this.withTransaction(() => {
      this.updateRun(runId, { status: "cancelling", updatedAtMs: requestedAt });
      if (attempt) {
        this.updateAttempt(attempt.attemptId, {
          status: "cancelling",
          cancellationRequestedAtMs: requestedAt,
          updatedAtMs: requestedAt,
        });
      }
      this.appendEvent({
        sessionId: run.sessionId,
        runId,
        attemptId: attempt?.attemptId ?? null,
        type: "run.cancellation_requested",
        payload: { runId, attemptId: attempt?.attemptId ?? null },
      });
      this.appendEvent({
        sessionId: run.sessionId,
        runId,
        attemptId: attempt?.attemptId ?? null,
        type: "run.cancelling",
        payload: { runId, attemptId: attempt?.attemptId ?? null },
      });
    });

    let dispatchAttempted = false;
    let adapterAcknowledged = false;
    if (active && attempt) {
      let dispatch: CancelDispatchResult = {
        accepted: true,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        message: undefined as string | undefined,
      };
      try {
        dispatch = await active.adapter.cancelAttempt({
          sessionId: active.sessionId,
          ownerId: this.readSession(run.sessionId).ownerId,
          requestId: run.requestId,
          clientId: run.clientId,
          runId,
          attemptId: attempt.attemptId,
          binding: active.binding,
        });
      } catch (error) {
        dispatch = {
          accepted: true,
          dispatchAttempted: true,
          adapterAcknowledged: false,
          message: messageFrom(error),
        };
      } finally {
        active.abortController.abort();
      }
      dispatchAttempted = dispatch.dispatchAttempted;
      adapterAcknowledged = dispatch.adapterAcknowledged;
      const now = Date.now();
      this.withTransaction(() => {
        this.updateAttempt(attempt.attemptId, {
          cancellationDispatchedAtMs: dispatch.dispatchAttempted ? now : null,
          cancellationAcknowledgedAtMs: dispatch.adapterAcknowledged ? now : null,
          updatedAtMs: now,
        });
        this.appendEvent({
          sessionId: run.sessionId,
          runId,
          attemptId: attempt.attemptId,
          type: "attempt.cancel_dispatch",
          payload: dispatch,
        });
      });
    }

    return {
      accepted: true,
      dispatchAttempted,
      adapterAcknowledged,
      runId,
      attemptId: attempt?.attemptId,
    };
  }
}
