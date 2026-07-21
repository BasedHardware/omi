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
import { discardProducingJournalTurnForRunAttempt } from "./conversation-journal.js";

export class KernelRuns extends KernelCore {
  async executeRun(input: ExecuteAgentRunInput): Promise<KernelRunResult> {
    const accepted = this.createAcceptedRun(input);
    try {
      return await this.executeAcceptedRun(input, accepted);
    } catch (error) {
      const latestAttemptRow = this.store.getOptionalRow(
        "SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1",
        [accepted.run.runId],
      );
      if (latestAttemptRow) {
        const attempt = attemptFromRow(latestAttemptRow);
        const run = this.readRun(accepted.run.runId);
        this.withTransaction(() => {
          if (!TERMINAL_STATUSES.includes(run.status) && !TERMINAL_STATUSES.includes(attempt.status)) {
            const failure = failureFromError(error, {
              code: "post_admission_execution_failed",
              source: "runtime",
              retryable: false,
            });
            this.finishAttemptAndRun({
              sessionId: accepted.session.sessionId,
              runId: run.runId,
              attemptId: attempt.attemptId,
              status: "failed",
              finalText: null,
              errorCode: failure.code,
              errorMessage: failure.userMessage,
              failure,
            });
          }
          discardProducingJournalTurnForRunAttempt(this.store, {
            ownerId: accepted.session.ownerId,
            runId: run.runId,
            attemptId: attempt.attemptId,
          });
        });
      }
      throw error;
    }
  }

  revokeActiveRunsForOwner(
    ownerId: string,
    reason: "owner_changed" | "owner_state_cleared",
  ): { runIds: string[] } {
    const rows = this.store.allRows(
      `SELECT r.run_id, r.session_id
       FROM runs r
       JOIN sessions s ON s.session_id = r.session_id
       WHERE s.owner_id = ? AND r.status IN (${placeholders(ACTIVE_STATUSES.length)})
       ORDER BY r.created_at_ms ASC, r.run_id ASC`,
      [ownerId, ...ACTIVE_STATUSES],
    );
    const runIds: string[] = [];
    for (const row of rows) {
      const runId = String(row.run_id);
      const sessionId = String(row.session_id);
      runIds.push(runId);
      this.activeExecutions.get(runId)?.abortController.abort(
        new Error(`Run owner authority was revoked: ${reason}`),
      );
      const attempt = this.readActiveAttempt(runId);
      this.withTransaction(() => {
        if (this.isTerminalRun(runId)) return;
        if (attempt && !this.isTerminalAttempt(attempt.attemptId)) {
          this.finishAttemptAndRun({
            sessionId,
            runId,
            attemptId: attempt.attemptId,
            status: "cancelled",
            finalText: null,
            errorCode: "owner_authority_revoked",
            errorMessage: `Run owner authority was revoked: ${reason}`,
            failure: null,
          });
          discardProducingJournalTurnForRunAttempt(this.store, {
            ownerId,
            runId,
            attemptId: attempt.attemptId,
          });
          return;
        }
        const now = Date.now();
        this.updateRun(runId, {
          status: "cancelled",
          finalText: null,
          resultJson: null,
          errorCode: "owner_authority_revoked",
          errorMessage: `Run owner authority was revoked: ${reason}`,
          completedAtMs: now,
          updatedAtMs: now,
        });
        this.appendEvent({
          sessionId,
          runId,
          attemptId: null,
          type: "run.cancelled",
          payload: { runId, status: "cancelled", reason },
        });
      });
    }
    return { runIds };
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
      authoritySignal: input.authoritySignal,
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
      authoritySignal: input.authoritySignal,
    };
    const accepted = this.createAcceptedRun(runInput);
    const producerJournal = ensureAgentSpawnJournalIfPresent(this.store, {
      ownerId: input.ownerId,
      sessionId: accepted.session.sessionId,
      runId: accepted.run.runId,
    });
    const execution = this.executeAcceptedRun(runInput, accepted);
    // `executeAcceptedRun` creates the durable first attempt before its first
    // asynchronous adapter boundary. Re-read that exact lifecycle snapshot so
    // realtime spawn receipts never report a queued parent run without the
    // admitted child attempt (and preserve an immediate pre-adapter failure).
    const receiptRun = this.readRun(accepted.run.runId);
    const receiptAttempt = this.readSpawnReceiptAttempt(accepted.run.runId);
    void execution
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
      run: receiptRun,
      attempt: receiptAttempt,
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
      authoritySignal: input.authoritySignal,
    };
    const created = this.createDelegatedRun(parentSession, parentRun, childRunInput, input);
    const producerJournal = ensureAgentSpawnJournalIfPresent(this.store, {
      ownerId,
      sessionId: created.session.sessionId,
      runId: created.run.runId,
    });

    if (input.mode === "spawn") {
      const runningDelegation = this.updateDelegationStatus(created.delegation, "running");
      const execution = this.executeDelegationAsync(
        childRunInput,
        { ...created, delegation: runningDelegation },
        false,
      );
      // The child attempt is created synchronously before the first adapter
      // await. Return the persisted lifecycle, rather than the stale accepted
      // objects, so realtime receives queued/started/failed truth.
      const receiptRun = this.readRun(created.run.runId);
      const receiptAttempt = this.readSpawnReceiptAttempt(created.run.runId);
      void execution
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
        childRun: receiptRun,
        childAttempt: receiptAttempt,
      };
    }

    return this.executeDelegationAsync(childRunInput, created);
  }

  /**
   * A background spawn may fail before `executeAcceptedRun` creates its first
   * attempt (for example, a revoked execution lease). The realtime boundary
   * must reject that incomplete receipt rather than throwing after the parent
   * run was accepted, so absence is represented explicitly here.
   */
  private readSpawnReceiptAttempt(runId: string): RunAttempt | undefined {
    const row = this.store.getOptionalRow(
      "SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1",
      [runId],
    );
    return row ? attemptFromRow(row) : undefined;
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
      if (attempt) {
        discardProducingJournalTurnForRunAttempt(this.store, {
          ownerId: this.readSession(run.sessionId).ownerId,
          runId,
          attemptId: attempt.attemptId,
          nowMs: requestedAt,
        });
      }
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
