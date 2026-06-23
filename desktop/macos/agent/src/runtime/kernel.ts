import type {
  AdapterAttemptResult,
  AdapterBindingHandle,
  OpenedBinding,
  PromptBlock,
  RuntimeAdapter,
  ToolDef,
} from "../adapters/interface.js";
import type { OutboundMessage } from "../protocol.js";
import { AdapterRegistry } from "./adapter-registry.js";
import { generateAgentId } from "./sqlite-store.js";
import type {
  AdapterBinding,
  AgentEvent,
  AgentArtifact,
  AgentDelegation,
  AgentRun,
  AgentSession,
  AgentStore,
  ArtifactRole,
  AttemptStatus,
  ResumeFidelity,
  RunAttempt,
  RunMode,
  RunStatus,
  DelegationMode,
  DelegationStatus,
} from "./types.js";

const ACTIVE_STATUSES: readonly RunStatus[] = ["queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling"];
const TERMINAL_STATUSES: readonly RunStatus[] = ["succeeded", "failed", "cancelled", "timed_out", "orphaned"];
const DEFAULT_DELEGATION_MAX_DEPTH = 3;
const HARD_DELEGATION_MAX_DEPTH = 5;
const DEFAULT_DELEGATION_MAX_BUDGET_USD = 5;
const HARD_DELEGATION_MAX_BUDGET_USD = 10;

export interface KernelSessionResolutionInput {
  sessionId?: string;
  ownerId: string;
  surfaceKind: string;
  externalRefKind?: string;
  externalRefId?: string;
  legacyClientScope?: string;
  legacySessionKey?: string;
  title?: string;
  defaultAdapterId?: string;
}

export interface ExecuteAgentRunInput extends KernelSessionResolutionInput {
  clientId: string;
  requestId: string;
  prompt: string;
  promptBlocks?: PromptBlock[];
  systemPrompt?: string;
  mode?: RunMode;
  adapterId?: string;
  cwd?: string;
  model?: string;
  mcpServers?: Record<string, unknown>[];
  legacyAdapterSessionId?: string;
  maxAttempts?: number;
  tools?: ToolDef[];
  metadata?: Record<string, unknown>;
  parentRunId?: string;
  recoverAfterError?: (error: unknown) => Promise<boolean>;
}

export interface KernelRunResult {
  session: AgentSession;
  run: AgentRun;
  attempt: RunAttempt;
  adapterSessionId: string | null;
  terminalStatus: "succeeded" | "failed" | "cancelled";
  text: string;
}

export interface CancelRunResult {
  accepted: boolean;
  dispatchAttempted: boolean;
  adapterAcknowledged: boolean;
  runId: string;
  attemptId?: string;
}

export interface ListSessionsInput {
  ownerId?: string;
  status?: AgentSession["status"];
  surfaceKind?: string;
  limit?: number;
  beforeUpdatedAtMs?: number;
}

export interface KernelSessionSummary {
  session: AgentSession;
  latestRun?: AgentRun;
  activeRun?: AgentRun;
  adapterBindings: AdapterBinding[];
}

export interface GetRunInput {
  runId: string;
  includeEvents?: boolean;
  eventLimit?: number;
}

export interface KernelRunDetails {
  session: AgentSession;
  run: AgentRun;
  attempts: RunAttempt[];
  adapterBindings: AdapterBinding[];
  artifacts: AgentArtifact[];
  events: AgentEvent[];
  parentDelegations: AgentDelegation[];
  childDelegations: AgentDelegation[];
}

export interface InspectArtifactsInput {
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  role?: ArtifactRole;
  limit?: number;
}

export interface InvalidateBindingsInput extends KernelSessionResolutionInput {
  adapterId?: string;
  reason?: string;
}

export interface InvalidateBindingsResult {
  sessionId?: string;
  invalidatedBindingIds: string[];
}

export interface SendAgentMessageInput {
  sessionId: string;
  ownerId: string;
  clientId: string;
  requestId: string;
  prompt: string;
  promptBlocks?: PromptBlock[];
  mode?: RunMode;
  adapterId?: string;
  cwd?: string;
  model?: string;
  metadata?: Record<string, unknown>;
}

export interface DelegateAgentInput {
  mode: DelegationMode;
  parentRunId: string;
  objective: string;
  ownerId?: string;
  clientId: string;
  requestId: string;
  childSessionId?: string;
  childSurfaceKind?: string;
  childExternalRefKind?: string;
  childExternalRefId?: string;
  childTitle?: string;
  adapterId?: string;
  defaultAdapterId?: string;
  cwd?: string;
  model?: string;
  runMode?: RunMode;
  context?: string;
  maxDepth?: number;
  maxBudgetUsd?: number;
  metadata?: Record<string, unknown>;
}

export interface DelegateAgentResult {
  delegation: AgentDelegation;
  childSession: AgentSession;
  childRun: AgentRun;
  childAttempt?: RunAttempt;
  adapterSessionId?: string | null;
  terminalStatus?: KernelRunResult["terminalStatus"];
  result?: {
    summary: string;
    artifacts: AgentArtifact[];
    verifiedEffects: unknown[];
    openQuestions: unknown[];
    usage: {
      inputTokens: number | null;
      outputTokens: number | null;
      cacheReadTokens: number | null;
      cacheWriteTokens: number | null;
      costUsd: number | null;
    };
  };
}

export type KernelEventSubscriber = (event: AgentEvent) => void;

export class StaleAdapterBindingError extends Error {
  constructor(message = "Adapter binding is stale") {
    super(message);
    this.name = "StaleAdapterBindingError";
  }
}

export interface AgentRuntimeKernelOptions {
  store: AgentStore;
  registry: AdapterRegistry;
  runtimeNodeId?: string;
}

interface ActiveExecution {
  adapter: RuntimeAdapter;
  abortController: AbortController;
  binding: AdapterBindingHandle;
  attemptId: string;
  sessionId: string;
}

export class AgentRuntimeKernel {
  private readonly store: AgentStore;
  private readonly registry: AdapterRegistry;
  private readonly runtimeNodeId: string;
  private readonly subscribers = new Set<KernelEventSubscriber>();
  private readonly activeExecutions = new Map<string, ActiveExecution>();

  constructor(options: AgentRuntimeKernelOptions) {
    this.store = options.store;
    this.registry = options.registry;
    this.runtimeNodeId = options.runtimeNodeId ?? "desktop-local";
  }

  subscribe(subscriber: KernelEventSubscriber): () => void {
    this.subscribers.add(subscriber);
    return () => this.subscribers.delete(subscriber);
  }

  async executeRun(input: ExecuteAgentRunInput): Promise<KernelRunResult> {
    const accepted = this.createAcceptedRun(input);
    return this.executeAcceptedRun(input, accepted);
  }

  async sendAgentMessage(input: SendAgentMessageInput): Promise<KernelRunResult> {
    const session = this.readSession(input.sessionId);
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
      adapterId: input.adapterId ?? session.defaultAdapterId,
      cwd: input.cwd ?? session.defaultCwd ?? undefined,
      model: input.model,
      metadata: input.metadata,
    });
  }

  async delegateAgent(input: DelegateAgentInput): Promise<DelegateAgentResult> {
    this.assertDelegationConstraints(input);
    const parentRun = this.readRun(input.parentRunId);
    const parentSession = this.readSession(parentRun.sessionId);
    if (input.ownerId && parentSession.ownerId !== input.ownerId) {
      throw new Error(`Parent run ${input.parentRunId} does not belong to owner ${input.ownerId}`);
    }
    const ownerId = input.ownerId ?? parentSession.ownerId;
    const childPrompt = buildDelegatedPrompt(input.objective, input.context);
    const childRunInput: ExecuteAgentRunInput = {
      ownerId,
      sessionId: input.mode === "continue" ? requiredChildSessionId(input.childSessionId) : input.childSessionId,
      surfaceKind: input.childSurfaceKind ?? "delegated_agent",
      externalRefKind: input.childExternalRefKind,
      externalRefId: input.childExternalRefId,
      title: input.childTitle ?? `Delegated: ${input.objective.slice(0, 80)}`,
      defaultAdapterId: input.defaultAdapterId ?? input.adapterId ?? parentSession.defaultAdapterId,
      adapterId: input.adapterId ?? input.defaultAdapterId ?? parentSession.defaultAdapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: childPrompt,
      mode: input.runMode ?? "ask",
      cwd: input.cwd ?? parentRun.cwd ?? parentSession.defaultCwd ?? undefined,
      model: input.model,
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

    if (input.mode === "spawn") {
      const runningDelegation = this.updateDelegationStatus(created.delegation, "running");
      void this.executeDelegationAsync(childRunInput, { ...created, delegation: runningDelegation }, false).catch((error) => {
        this.updateDelegationStatus(runningDelegation, "failed", messageFrom(error));
      });
      return {
        delegation: runningDelegation,
        childSession: created.session,
        childRun: created.run,
      };
    }

    return this.executeDelegationAsync(childRunInput, created);
  }

  private createAcceptedRun(input: ExecuteAgentRunInput): { session: AgentSession; run: AgentRun } {
    return this.store.withTransaction(() => {
      const session = this.resolveSession(input);
      const run = this.store.insertRun({
        sessionId: session.sessionId,
        parentRunId: input.parentRunId ?? null,
        clientId: input.clientId,
        requestId: input.requestId,
        status: "queued",
        mode: input.mode ?? "ask",
        inputJson: JSON.stringify({
          prompt: input.prompt,
          systemPrompt: input.systemPrompt ?? "",
          metadata: input.metadata ?? {},
        }),
        requestedModelId: input.model ?? null,
        cwd: input.cwd ?? session.defaultCwd,
      });
      this.touchSession(session.sessionId);
      this.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: "run.created",
        payload: { runId: run.runId, requestId: run.requestId },
      });
      return { session, run };
    });
  }

  private async executeAcceptedRun(
    input: ExecuteAgentRunInput,
    accepted: { session: AgentSession; run: AgentRun }
  ): Promise<KernelRunResult> {

    const adapterId = input.adapterId ?? accepted.session.defaultAdapterId;
    const maxAttempts = Math.max(1, input.maxAttempts ?? 2);
    let retryReason: string | null = null;
    let resumeFromAttemptId: string | null = null;
    let lastAttempt: RunAttempt | undefined;

    for (let attemptNo = 1; attemptNo <= maxAttempts; attemptNo += 1) {
      const attempt = this.createAttempt({
        runId: accepted.run.runId,
        attemptNo,
        adapterId,
        retryReason,
        resumeFromAttemptId,
      });
      lastAttempt = attempt;

      const pool = this.registry.get(adapterId);

      let binding: AdapterBinding;
      let handle: AdapterBindingHandle;
      try {
        const existingBinding = this.readActiveBinding(accepted.session.sessionId, adapterId);
        const bindingQueueKey = existingBinding ? this.handleForExistingBinding(existingBinding) : undefined;
        const resolved = await pool.runExclusiveQueued(bindingQueueKey, `${attempt.attemptId}:binding`, (worker) =>
          this.resolveBindingForAttempt({
            input,
            session: accepted.session,
            adapter: worker.adapter,
            attempt,
            adapterId,
          })
        );
        binding = resolved.binding;
        handle = resolved.handle;
      } catch (error) {
        if (isStaleBindingError(error)) {
          this.failAttemptBeforeExecution(attempt, "stale_binding", messageFrom(error), attemptNo < maxAttempts);
          retryReason = "stale_binding";
          resumeFromAttemptId = attempt.attemptId;
          continue;
        }
        if (await this.tryRecoverAttempt(input, attempt, error, "binding_failed", attemptNo < maxAttempts)) {
          retryReason = "recoverable_error";
          resumeFromAttemptId = attempt.attemptId;
          continue;
        }
        this.failAttemptBeforeExecution(attempt, "binding_failed", messageFrom(error), false);
        break;
      }

      const abortController = new AbortController();

      try {
        const result = await pool.runExclusiveQueued(handle, attempt.attemptId, async (worker) => {
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
          this.markAttemptRunning(attempt, binding);
          return worker.adapter.executeAttempt(
            {
              sessionId: accepted.session.sessionId,
              runId: accepted.run.runId,
              attemptId: attempt.attemptId,
              binding: handle,
              prompt: input.promptBlocks ?? [{ type: "text", text: input.prompt }],
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
        return this.completeAttemptAndRun(accepted.session, accepted.run.runId, attempt, binding, result);
      } catch (error) {
        this.activeExecutions.delete(accepted.run.runId);
        if (isStaleBindingError(error)) {
          this.markBindingStale(binding, attempt, messageFrom(error));
          this.failAttemptBeforeExecution(attempt, "stale_binding", messageFrom(error), attemptNo < maxAttempts);
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
        this.finishAttemptAndRun({
          sessionId: accepted.session.sessionId,
          runId: accepted.run.runId,
          attemptId: attempt.attemptId,
          status,
          finalText: null,
          errorCode: wasCancelling ? null : "adapter_execution_failed",
          errorMessage: wasCancelling ? null : messageFrom(error),
        });
        break;
      }
    }

    const finalRun = this.readRun(accepted.run.runId);
    const attempt = lastAttempt ?? this.readLatestAttempt(accepted.run.runId);
    return {
      session: accepted.session,
      run: finalRun,
      attempt,
      adapterSessionId: null,
      terminalStatus: finalRun.status === "cancelled" ? "cancelled" : "failed",
      text: finalRun.finalText ?? "",
    };
  }

  async cancelRun(runId: string): Promise<CancelRunResult> {
    const active = this.activeExecutions.get(runId);
    const run = this.readRun(runId);
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

    this.store.withTransaction(() => {
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
      const dispatch = await active.adapter.cancelAttempt({
        sessionId: active.sessionId,
        runId,
        attemptId: attempt.attemptId,
        binding: active.binding,
      });
      dispatchAttempted = dispatch.dispatchAttempted;
      adapterAcknowledged = dispatch.adapterAcknowledged;
      const now = Date.now();
      this.store.withTransaction(() => {
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
        this.appendEvent({
          sessionId: run.sessionId,
          runId,
          attemptId: attempt.attemptId,
          type: "run.cancel_ack",
          payload: {
            accepted: true,
            dispatchAttempted,
            adapterAcknowledged,
          },
        });
      });
      active.abortController.abort();
    }

    return {
      accepted: true,
      dispatchAttempted,
      adapterAcknowledged,
      runId,
      attemptId: attempt?.attemptId,
    };
  }

  listSessions(input: ListSessionsInput = {}): KernelSessionSummary[] {
    const where: string[] = [];
    const values: unknown[] = [];
    if (input.ownerId) {
      where.push("owner_id = ?");
      values.push(input.ownerId);
    }
    if (input.status) {
      where.push("status = ?");
      values.push(input.status);
    }
    if (input.surfaceKind) {
      where.push("surface_kind = ?");
      values.push(input.surfaceKind);
    }
    if (input.beforeUpdatedAtMs !== undefined) {
      where.push("updated_at_ms < ?");
      values.push(input.beforeUpdatedAtMs);
    }
    const limit = boundedLimit(input.limit, 50, 200);
    const sessions = this.store
      .allRows(
        `SELECT * FROM sessions
         ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
         ORDER BY last_activity_at_ms DESC, created_at_ms DESC
         LIMIT ?`,
        [...values, limit],
      )
      .map(sessionFromRow);

    return sessions.map((session) => ({
      session,
      latestRun: this.readLatestRunForSession(session.sessionId),
      activeRun: this.readActiveRunForSession(session.sessionId),
      adapterBindings: this.readBindingsForSession(session.sessionId),
    }));
  }

  getRun(input: GetRunInput): KernelRunDetails {
    const run = this.readRun(input.runId);
    const session = this.readSession(run.sessionId);
    return {
      session,
      run,
      attempts: this.readAttemptsForRun(run.runId),
      adapterBindings: this.readBindingsForSession(session.sessionId),
      artifacts: this.readArtifacts({ runId: run.runId, limit: 100 }),
      events: input.includeEvents ? this.readEventsForRun(run.runId, boundedLimit(input.eventLimit, 100, 500)) : [],
      parentDelegations: this.readParentDelegationsForRun(run.runId),
      childDelegations: this.readChildDelegationsForRun(run.runId),
    };
  }

  inspectArtifacts(input: InspectArtifactsInput): AgentArtifact[] {
    return this.readArtifacts(input);
  }

  invalidateBindings(input: InvalidateBindingsInput): InvalidateBindingsResult {
    const session = this.findExistingSession(input);
    const sessionIds = session ? [session.sessionId] : this.findInvalidationSessionIds(input);
    if (sessionIds.length === 0) {
      return { invalidatedBindingIds: [] };
    }

    const rows = this.store.allRows(
      `SELECT binding_id, session_id
       FROM adapter_bindings
       WHERE session_id IN (${placeholders(sessionIds.length)})
         AND status = ?
         ${input.adapterId ? "AND adapter_id = ?" : ""}`,
      input.adapterId ? [...sessionIds, "active", input.adapterId] : [...sessionIds, "active"],
    );
    const invalidatedBindingIds = rows.map((row) => String(row.binding_id));
    if (invalidatedBindingIds.length === 0) {
      return { sessionId: session?.sessionId, invalidatedBindingIds };
    }

    const now = Date.now();
    this.store.withTransaction(() => {
      for (const bindingId of invalidatedBindingIds) {
        this.updateBinding(bindingId, {
          status: "invalid",
          invalidatedAtMs: now,
          updatedAtMs: now,
        });
        this.appendEvent({
          sessionId: String(rows.find((row) => String(row.binding_id) === bindingId)?.session_id),
          runId: null,
          attemptId: null,
          type: "binding.invalidated",
          payload: {
            bindingId,
            adapterId: input.adapterId,
            reason: input.reason ?? "compatibility_invalidate_session",
          },
        });
      }
    });

    return { sessionId: session?.sessionId, invalidatedBindingIds };
  }

  private createDelegatedRun(
    parentSession: AgentSession,
    parentRun: AgentRun,
    childRunInput: ExecuteAgentRunInput,
    input: DelegateAgentInput
  ): { session: AgentSession; run: AgentRun; delegation: AgentDelegation } {
    return this.store.withTransaction(() => {
      const session = this.resolveSession(childRunInput);
      if (session.sessionId === parentSession.sessionId) {
        throw new Error("Delegated child session must be distinct from parent session");
      }
      const run = this.store.insertRun({
        sessionId: session.sessionId,
        parentRunId: parentRun.runId,
        clientId: childRunInput.clientId,
        requestId: childRunInput.requestId,
        status: "queued",
        mode: childRunInput.mode ?? "ask",
        inputJson: JSON.stringify({
          prompt: childRunInput.prompt,
          systemPrompt: childRunInput.systemPrompt ?? "",
          metadata: childRunInput.metadata ?? {},
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
      this.touchSession(session.sessionId);
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
        type: "run.created",
        payload: {
          runId: run.runId,
          requestId: run.requestId,
          parentRunId: parentRun.runId,
          delegationId: delegation.delegationId,
        },
      });
      return { session, run, delegation };
    });
  }

  private async executeDelegationAsync(
    childRunInput: ExecuteAgentRunInput,
    created: { session: AgentSession; run: AgentRun; delegation: AgentDelegation },
    markRunning = true
  ): Promise<DelegateAgentResult> {
    if (markRunning) {
      created = { ...created, delegation: this.updateDelegationStatus(created.delegation, "running") };
    }
    const result = await this.executeAcceptedRun(childRunInput, {
      session: created.session,
      run: created.run,
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

  private updateDelegationStatus(delegation: AgentDelegation, status: DelegationStatus, errorMessage?: string): AgentDelegation {
    const now = Date.now();
    this.store.withTransaction(() => {
      this.store.execute(
        `UPDATE delegations
         SET status = ?, completed_at_ms = ?, result_artifact_id = result_artifact_id
         WHERE delegation_id = ?`,
        [status, status === "running" || status === "pending" ? null : now, delegation.delegationId],
      );
      this.appendEvent({
        sessionId: delegation.parentSessionId,
        runId: delegation.parentRunId,
        type: status === "running" ? "delegation.running" : "delegation.completed",
        payload: {
          delegationId: delegation.delegationId,
          childSessionId: delegation.childSessionId,
          childRunId: delegation.childRunId,
          status,
          errorMessage,
        },
      });
    });
    return this.readDelegation(delegation.delegationId);
  }

  private assertDelegationConstraints(input: DelegateAgentInput): void {
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

  private resolveSession(input: KernelSessionResolutionInput): AgentSession {
    const existing = this.findExistingSession(input);
    if (existing) return existing;
    return this.store.insertSession({
      ownerId: input.ownerId,
      surfaceKind: input.surfaceKind,
      externalRefKind: input.externalRefKind ?? null,
      externalRefId: input.externalRefId ?? null,
      legacyClientScope: input.legacyClientScope ?? null,
      legacySessionKey: input.legacySessionKey ?? null,
      title: input.title ?? null,
      defaultAdapterId: input.defaultAdapterId ?? "acp",
    });
  }

  private findExistingSession(input: KernelSessionResolutionInput): AgentSession | undefined {
    if (input.sessionId) {
      const session = this.readSession(input.sessionId);
      if (session.ownerId !== input.ownerId) {
        throw new Error(`Session ${input.sessionId} does not belong to owner ${input.ownerId}`);
      }
      return session;
    }
    if (input.externalRefKind && input.externalRefId) {
      const row = this.store.getOptionalRow(
        "SELECT * FROM sessions WHERE owner_id = ? AND external_ref_kind = ? AND external_ref_id = ?",
        [input.ownerId, input.externalRefKind, input.externalRefId],
      );
      if (row) return sessionFromRow(row);
    }
    if (input.legacyClientScope && input.legacySessionKey) {
      const row = this.store.getOptionalRow(
        "SELECT * FROM sessions WHERE owner_id = ? AND legacy_client_scope = ? AND legacy_session_key = ?",
        [input.ownerId, input.legacyClientScope, input.legacySessionKey],
      );
      if (row) return sessionFromRow(row);
    }
    return undefined;
  }

  private findInvalidationSessionIds(input: KernelSessionResolutionInput): string[] {
    if (input.sessionId || input.externalRefKind || input.externalRefId || input.legacyClientScope || input.legacySessionKey) {
      return [];
    }
    return this.store
      .allRows("SELECT session_id FROM sessions WHERE owner_id = ?", [input.ownerId])
      .map((row) => String(row.session_id));
  }

  private createAttempt(input: {
    runId: string;
    attemptNo: number;
    adapterId: string;
    retryReason: string | null;
    resumeFromAttemptId: string | null;
  }): RunAttempt {
    return this.store.withTransaction(() => {
      const active = this.readActiveAttempt(input.runId);
      if (active) {
        throw new Error(`Run ${input.runId} already has active attempt ${active.attemptId}`);
      }
      this.updateRun(input.runId, {
        status: "starting",
        startedAtMs: input.attemptNo === 1 ? Date.now() : undefined,
        updatedAtMs: Date.now(),
      });
      const attempt = this.store.insertAttempt({
        runId: input.runId,
        attemptNo: input.attemptNo,
        status: "starting",
        adapterId: input.adapterId,
        adapterInstanceId: "",
        runtimeNodeId: this.runtimeNodeId,
        retryReason: input.retryReason,
        resumeFromAttemptId: input.resumeFromAttemptId,
        retryable: input.retryReason ? 1 : 0,
      });
      const run = this.readRun(input.runId);
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

  private async resolveBindingForAttempt(input: {
    input: ExecuteAgentRunInput;
    session: AgentSession;
    adapter: RuntimeAdapter;
    attempt: RunAttempt;
    adapterId: string;
  }): Promise<{ binding: AdapterBinding; handle: AdapterBindingHandle }> {
    const active = this.readActiveBinding(input.session.sessionId, input.adapterId);
    if (active) {
      const handle = await this.resumeOrReplaceBinding(active, input);
      return { binding: this.readBinding(handle.bindingId!), handle };
    }

    const nextGeneration = this.nextBindingGeneration(input.session.sessionId, input.adapterId);
    if (input.input.legacyAdapterSessionId && input.adapter.capabilities.supportsNativeResume && nextGeneration === 1) {
      const adopted = this.store.withTransaction(() => {
        const binding = this.store.insertAdapterBinding({
          sessionId: input.session.sessionId,
          adapterId: input.adapterId,
          bindingGeneration: 1,
          adapterNativeSessionId: input.input.legacyAdapterSessionId,
          adapterInstanceId: this.runtimeNodeId,
          resumeFidelity: "native",
          status: "active",
          cwd: input.input.cwd ?? input.session.defaultCwd,
          modelId: input.input.model ?? null,
        });
        this.appendEvent({
          sessionId: input.session.sessionId,
          runId: input.attempt.runId,
          attemptId: input.attempt.attemptId,
          type: "binding.created",
          payload: {
            bindingId: binding.bindingId,
            bindingGeneration: binding.bindingGeneration,
            adapterId: input.adapterId,
            adoptedLegacyAdapterSessionId: true,
          },
        });
        return binding;
      });
      const handle = await this.resumeOrReplaceBinding(adopted, input);
      return { binding: this.readBinding(handle.bindingId!), handle };
    }

    const previousBinding = nextGeneration > 1 ? this.readLatestBinding(input.session.sessionId, input.adapterId) : undefined;
    return this.openNewBinding(input, nextGeneration, previousBinding?.bindingId ?? null);
  }

  private handleForExistingBinding(binding: AdapterBinding): AdapterBindingHandle {
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

  private async resumeOrReplaceBinding(
    binding: AdapterBinding,
    input: {
      input: ExecuteAgentRunInput;
      session: AgentSession;
      adapter: RuntimeAdapter;
      attempt: RunAttempt;
      adapterId: string;
    }
  ): Promise<AdapterBindingHandle> {
    const canUseProcessLocalBinding =
      binding.adapterInstanceId === this.runtimeNodeId &&
      binding.adapterNativeSessionId &&
      binding.resumeFidelity === "none";
    if (!binding.adapterNativeSessionId || (!input.adapter.capabilities.supportsNativeResume && !canUseProcessLocalBinding)) {
      this.markBindingStale(binding, input.attempt, "binding_not_resumable");
      const opened = await this.openNewBinding(input, binding.bindingGeneration + 1, binding.bindingId);
      return opened.handle;
    }
    try {
      const resumed = await input.adapter.resumeBinding({
        sessionId: input.session.sessionId,
        adapterNativeSessionId: binding.adapterNativeSessionId,
        cwd: input.input.cwd ?? binding.cwd ?? input.session.defaultCwd ?? process.cwd(),
        model: input.input.model ?? binding.modelId ?? undefined,
        systemPrompt: input.input.systemPrompt,
        mcpServers: input.input.mcpServers,
      });
      this.store.withTransaction(() => {
        this.updateBinding(binding.bindingId, {
          adapterInstanceId: this.runtimeNodeId,
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

  private async openNewBinding(
    input: {
      input: ExecuteAgentRunInput;
      session: AgentSession;
      adapter: RuntimeAdapter;
      attempt: RunAttempt;
      adapterId: string;
    },
    generation: number,
    replacesBindingId: string | null
  ): Promise<{ binding: AdapterBinding; handle: AdapterBindingHandle }> {
    const opened = await input.adapter.openBinding({
      sessionId: input.session.sessionId,
      cwd: input.input.cwd ?? input.session.defaultCwd ?? process.cwd(),
      model: input.input.model,
      systemPrompt: input.input.systemPrompt,
      mcpServers: input.input.mcpServers,
      metadata: input.input.metadata,
    });
    const binding = this.store.withTransaction(() => {
      const created = this.store.insertAdapterBinding({
        sessionId: input.session.sessionId,
        adapterId: input.adapterId,
        bindingGeneration: generation,
        adapterNativeSessionId: opened.adapterNativeSessionId,
        adapterInstanceId: this.runtimeNodeId,
        resumeFidelity: opened.resumeFidelity,
        status: "active",
        cwd: opened.cwd,
        modelId: opened.model ?? input.input.model ?? null,
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
        },
      });
      return created;
    });
    return {
      binding,
      handle: {
        ...opened,
        bindingId: binding.bindingId,
        sessionId: input.session.sessionId,
        adapterId: input.adapterId,
      },
    };
  }

  private markAttemptRunning(attempt: RunAttempt, binding: AdapterBinding): void {
    const run = this.readRun(attempt.runId);
    this.store.withTransaction(() => {
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

  private completeAttemptAndRun(
    session: AgentSession,
    runId: string,
    attempt: RunAttempt,
    binding: AdapterBinding,
    result: AdapterAttemptResult
  ): KernelRunResult {
    const status = result.terminalStatus;
    this.store.withTransaction(() => {
      this.updateBinding(binding.bindingId, {
        adapterNativeSessionId: result.adapterSessionId,
        lastUsedAtMs: Date.now(),
        updatedAtMs: Date.now(),
      });
      this.finishAttemptAndRun({
        sessionId: session.sessionId,
        runId,
        attemptId: attempt.attemptId,
        status,
        finalText: result.text,
        result,
      });
    });
    return {
      session,
      run: this.readRun(runId),
      attempt: this.readAttempt(attempt.attemptId),
      adapterSessionId: result.adapterSessionId,
      terminalStatus: status,
      text: result.text,
    };
  }

  private finishAttemptAndRun(input: {
    sessionId: string;
    runId: string;
    attemptId: string;
    status: AttemptStatus;
    finalText: string | null;
    result?: AdapterAttemptResult;
    errorCode?: string | null;
    errorMessage?: string | null;
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
      resultJson: input.result ? JSON.stringify(input.result) : null,
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
    this.appendEvent({
      sessionId: input.sessionId,
      runId: input.runId,
      attemptId: input.attemptId,
      type: `attempt.${completedStatus}`,
      payload: { attemptId: input.attemptId, status: completedStatus },
    });
    this.appendEvent({
      sessionId: input.sessionId,
      runId: input.runId,
      attemptId: input.attemptId,
      type: `run.${completedStatus}`,
      payload: { runId: input.runId, status: completedStatus },
    });
  }

  private failAttemptBeforeExecution(attempt: RunAttempt, errorCode: string, errorMessage: string, retryable: boolean): void {
    const run = this.readRun(attempt.runId);
    this.store.withTransaction(() => {
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
          completedAtMs: Date.now(),
          updatedAtMs: Date.now(),
        });
        this.appendEvent({
          sessionId: run.sessionId,
          runId: attempt.runId,
          attemptId: attempt.attemptId,
          type: "run.failed",
          payload: { runId: attempt.runId, errorCode, errorMessage },
        });
      }
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: "attempt.failed",
        payload: { attemptId: attempt.attemptId, errorCode, errorMessage, retryable },
      });
    });
  }

  private async tryRecoverAttempt(
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
    this.failAttemptBeforeExecution(attempt, errorCode, messageFrom(error), true);
    return true;
  }

  private persistAdapterEvent(sessionId: string, runId: string, attemptId: string, event: OutboundMessage): void {
    if (this.isTerminalAttempt(attemptId) || this.isTerminalRun(runId)) {
      return;
    }
    this.store.withTransaction(() => {
      if (this.isTerminalAttempt(attemptId) || this.isTerminalRun(runId)) {
        return;
      }
      this.appendEvent({
        sessionId,
        runId,
        attemptId,
        type: `adapter.${event.type}`,
        retentionClass: event.type === "text_delta" || event.type === "thinking_delta" ? "transient" : "core",
        payload: event,
      });
    });
  }

  private markBindingStale(binding: AdapterBinding, attempt: RunAttempt, reason: string): void {
    const run = this.readRun(attempt.runId);
    this.store.withTransaction(() => {
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

  private appendEvent(input: {
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
    for (const subscriber of this.subscribers) {
      subscriber(event);
    }
    return event;
  }

  private readSession(sessionId: string): AgentSession {
    return sessionFromRow(this.store.getRow("SELECT * FROM sessions WHERE session_id = ?", [sessionId]));
  }

  private readRun(runId: string): AgentRun {
    return runFromRow(this.store.getRow("SELECT * FROM runs WHERE run_id = ?", [runId]));
  }

  private readLatestRunForSession(sessionId: string): AgentRun | undefined {
    const row = this.store.getOptionalRow("SELECT * FROM runs WHERE session_id = ? ORDER BY created_at_ms DESC LIMIT 1", [sessionId]);
    return row ? runFromRow(row) : undefined;
  }

  private readActiveRunForSession(sessionId: string): AgentRun | undefined {
    const row = this.store.getOptionalRow(
      `SELECT * FROM runs WHERE session_id = ? AND status IN (${placeholders(ACTIVE_STATUSES.length)}) ORDER BY created_at_ms DESC LIMIT 1`,
      [sessionId, ...ACTIVE_STATUSES],
    );
    return row ? runFromRow(row) : undefined;
  }

  private readAttempt(attemptId: string): RunAttempt {
    return attemptFromRow(this.store.getRow("SELECT * FROM run_attempts WHERE attempt_id = ?", [attemptId]));
  }

  private readLatestAttempt(runId: string): RunAttempt {
    return attemptFromRow(this.store.getRow("SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1", [runId]));
  }

  private readAttemptsForRun(runId: string): RunAttempt[] {
    return this.store.allRows("SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no ASC", [runId]).map(attemptFromRow);
  }

  private readActiveAttempt(runId: string): RunAttempt | undefined {
    const row = this.store.getOptionalRow(
      `SELECT * FROM run_attempts WHERE run_id = ? AND status IN (${placeholders(ACTIVE_STATUSES.length)}) ORDER BY attempt_no DESC LIMIT 1`,
      [runId, ...ACTIVE_STATUSES],
    );
    return row ? attemptFromRow(row) : undefined;
  }

  private readBinding(bindingId: string): AdapterBinding {
    return bindingFromRow(this.store.getRow("SELECT * FROM adapter_bindings WHERE binding_id = ?", [bindingId]));
  }

  private readActiveBinding(sessionId: string, adapterId: string): AdapterBinding | undefined {
    const row = this.store.getOptionalRow(
      "SELECT * FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = ?",
      [sessionId, adapterId, "active"],
    );
    return row ? bindingFromRow(row) : undefined;
  }

  private readLatestBinding(sessionId: string, adapterId: string): AdapterBinding | undefined {
    const row = this.store.getOptionalRow(
      "SELECT * FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? ORDER BY binding_generation DESC LIMIT 1",
      [sessionId, adapterId],
    );
    return row ? bindingFromRow(row) : undefined;
  }

  private readBindingsForSession(sessionId: string): AdapterBinding[] {
    return this.store
      .allRows("SELECT * FROM adapter_bindings WHERE session_id = ? ORDER BY adapter_id ASC, binding_generation DESC", [sessionId])
      .map(bindingFromRow);
  }

  private readEventsForRun(runId: string, limit: number): AgentEvent[] {
    return this.store
      .allRows("SELECT * FROM events WHERE run_id = ? ORDER BY event_seq ASC LIMIT ?", [runId, limit])
      .map(eventFromRow);
  }

  private readArtifacts(input: InspectArtifactsInput): AgentArtifact[] {
    const where: string[] = [];
    const values: unknown[] = [];
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

  private readDelegation(delegationId: string): AgentDelegation {
    return delegationFromRow(this.store.getRow("SELECT * FROM delegations WHERE delegation_id = ?", [delegationId]));
  }

  private readParentDelegationsForRun(runId: string): AgentDelegation[] {
    return this.store
      .allRows("SELECT * FROM delegations WHERE parent_run_id = ? ORDER BY created_at_ms ASC", [runId])
      .map(delegationFromRow);
  }

  private readChildDelegationsForRun(runId: string): AgentDelegation[] {
    return this.store
      .allRows("SELECT * FROM delegations WHERE child_run_id = ? ORDER BY created_at_ms ASC", [runId])
      .map(delegationFromRow);
  }

  private delegationDepth(parentRunId: string): number {
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

  private nextBindingGeneration(sessionId: string, adapterId: string): number {
    const row = this.store.getRow(
      "SELECT COALESCE(MAX(binding_generation), 0) AS max_generation FROM adapter_bindings WHERE session_id = ? AND adapter_id = ?",
      [sessionId, adapterId],
    );
    return Number(row.max_generation) + 1;
  }

  private runStatus(runId: string): RunStatus {
    return String(this.store.getRow("SELECT status FROM runs WHERE run_id = ?", [runId]).status) as RunStatus;
  }

  private isTerminalRun(runId: string): boolean {
    return TERMINAL_STATUSES.includes(this.runStatus(runId));
  }

  private isTerminalAttempt(attemptId: string): boolean {
    const status = String(this.store.getRow("SELECT status FROM run_attempts WHERE attempt_id = ?", [attemptId]).status) as AttemptStatus;
    return TERMINAL_STATUSES.includes(status);
  }

  private touchSession(sessionId: string): void {
    this.store.execute("UPDATE sessions SET updated_at_ms = ?, last_activity_at_ms = ? WHERE session_id = ?", [Date.now(), Date.now(), sessionId]);
  }

  private updateRun(runId: string, patch: Partial<AgentRun>): void {
    updateByColumns(this.store, "runs", "run_id", runId, runColumnMap, patch);
  }

  private updateAttempt(attemptId: string, patch: Partial<RunAttempt>): void {
    updateByColumns(this.store, "run_attempts", "attempt_id", attemptId, attemptColumnMap, patch);
  }

  private updateBinding(bindingId: string, patch: Partial<AdapterBinding>): void {
    updateByColumns(this.store, "adapter_bindings", "binding_id", bindingId, bindingColumnMap, patch);
  }
}

function updateByColumns<T extends Record<string, unknown>>(
  store: AgentStore,
  table: string,
  idColumn: string,
  idValue: string,
  columnMap: Record<string, string>,
  patch: Partial<T>
): void {
  const entries = Object.entries(patch).filter(([, value]) => value !== undefined);
  if (entries.length === 0) return;
  const assignments = entries.map(([key]) => `${columnMap[key] ?? key} = ?`).join(", ");
  store.execute(`UPDATE ${table} SET ${assignments} WHERE ${idColumn} = ?`, [...entries.map(([, value]) => value), idValue]);
}

function placeholders(count: number): string {
  return Array.from({ length: count }, () => "?").join(", ");
}

function isStaleBindingError(error: unknown): boolean {
  return error instanceof StaleAdapterBindingError || (error instanceof Error && error.name === "StaleAdapterBindingError");
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function text(value: unknown): string {
  return String(value);
}

function nullableText(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

function nullableNumber(value: unknown): number | null {
  return value === null || value === undefined ? null : Number(value);
}

function boundedLimit(value: number | undefined, fallback: number, max: number): number {
  if (value === undefined || !Number.isFinite(value)) return fallback;
  return Math.max(1, Math.min(max, Math.floor(value)));
}

function sessionFromRow(row: Record<string, unknown>): AgentSession {
  return {
    sessionId: text(row.session_id),
    ownerId: text(row.owner_id),
    agentDefinitionId: text(row.agent_definition_id),
    title: nullableText(row.title),
    status: text(row.status) as AgentSession["status"],
    surfaceKind: text(row.surface_kind),
    externalRefKind: nullableText(row.external_ref_kind),
    externalRefId: nullableText(row.external_ref_id),
    legacyClientScope: nullableText(row.legacy_client_scope),
    legacySessionKey: nullableText(row.legacy_session_key),
    defaultAdapterId: text(row.default_adapter_id),
    defaultCwd: nullableText(row.default_cwd),
    modelProfile: nullableText(row.model_profile),
    metadataJson: text(row.metadata_json),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
    lastActivityAtMs: Number(row.last_activity_at_ms),
  };
}

function runFromRow(row: Record<string, unknown>): AgentRun {
  return {
    runId: text(row.run_id),
    sessionId: text(row.session_id),
    parentRunId: nullableText(row.parent_run_id),
    clientId: text(row.client_id),
    requestId: text(row.request_id),
    idempotencyKey: nullableText(row.idempotency_key),
    status: text(row.status) as RunStatus,
    mode: text(row.mode) as RunMode,
    inputJson: text(row.input_json),
    systemPromptHash: nullableText(row.system_prompt_hash),
    modelProfile: nullableText(row.model_profile),
    requestedModelId: nullableText(row.requested_model_id),
    cwd: nullableText(row.cwd),
    finalText: nullableText(row.final_text),
    resultJson: nullableText(row.result_json),
    errorCode: nullableText(row.error_code),
    errorMessage: nullableText(row.error_message),
    inputTokens: nullableNumber(row.input_tokens),
    outputTokens: nullableNumber(row.output_tokens),
    cacheReadTokens: nullableNumber(row.cache_read_tokens),
    cacheWriteTokens: nullableNumber(row.cache_write_tokens),
    costUsd: nullableNumber(row.cost_usd),
    createdAtMs: Number(row.created_at_ms),
    startedAtMs: nullableNumber(row.started_at_ms),
    completedAtMs: nullableNumber(row.completed_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
  };
}

function delegationFromRow(row: Record<string, unknown>): AgentDelegation {
  return {
    delegationId: text(row.delegation_id),
    parentSessionId: text(row.parent_session_id),
    parentRunId: text(row.parent_run_id),
    childSessionId: text(row.child_session_id),
    childRunId: text(row.child_run_id),
    mode: text(row.mode) as DelegationMode,
    status: text(row.status) as DelegationStatus,
    objective: text(row.objective),
    requestJson: text(row.request_json),
    resultArtifactId: nullableText(row.result_artifact_id),
    createdAtMs: Number(row.created_at_ms),
    completedAtMs: nullableNumber(row.completed_at_ms),
  };
}

function delegationValues(delegation: AgentDelegation): unknown[] {
  return [
    delegation.delegationId,
    delegation.parentSessionId,
    delegation.parentRunId,
    delegation.childSessionId,
    delegation.childRunId,
    delegation.mode,
    delegation.status,
    delegation.objective,
    delegation.requestJson,
    delegation.resultArtifactId,
    delegation.createdAtMs,
    delegation.completedAtMs,
  ];
}

function buildDelegatedPrompt(objective: string, context: string | undefined): string {
  const trimmedObjective = objective.trim();
  const trimmedContext = context?.trim();
  if (!trimmedContext) {
    return trimmedObjective;
  }
  return `Objective:\n${trimmedObjective}\n\nContext:\n${trimmedContext}`;
}

function requiredChildSessionId(sessionId: string | undefined): string {
  if (!sessionId) {
    throw new Error("delegate_agent continue mode requires childSessionId");
  }
  return sessionId;
}

function attemptFromRow(row: Record<string, unknown>): RunAttempt {
  return {
    attemptId: text(row.attempt_id),
    runId: text(row.run_id),
    attemptNo: Number(row.attempt_no),
    status: text(row.status) as AttemptStatus,
    adapterId: text(row.adapter_id),
    adapterInstanceId: text(row.adapter_instance_id),
    runtimeNodeId: text(row.runtime_node_id),
    bindingId: nullableText(row.binding_id),
    adapterNativeRunId: nullableText(row.adapter_native_run_id),
    resumeFromAttemptId: nullableText(row.resume_from_attempt_id),
    checkpointArtifactId: nullableText(row.checkpoint_artifact_id),
    retryReason: nullableText(row.retry_reason),
    retryable: Number(row.retryable) as 0 | 1,
    cancellationRequestedAtMs: nullableNumber(row.cancellation_requested_at_ms),
    cancellationDispatchedAtMs: nullableNumber(row.cancellation_dispatched_at_ms),
    cancellationAcknowledgedAtMs: nullableNumber(row.cancellation_acknowledged_at_ms),
    startedAtMs: nullableNumber(row.started_at_ms),
    completedAtMs: nullableNumber(row.completed_at_ms),
    errorCode: nullableText(row.error_code),
    errorMessage: nullableText(row.error_message),
    metadataJson: text(row.metadata_json),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
  };
}

function bindingFromRow(row: Record<string, unknown>): AdapterBinding {
  return {
    bindingId: text(row.binding_id),
    sessionId: text(row.session_id),
    adapterId: text(row.adapter_id),
    bindingGeneration: Number(row.binding_generation),
    adapterNativeSessionId: nullableText(row.adapter_native_session_id),
    adapterInstanceId: nullableText(row.adapter_instance_id),
    resumeFidelity: text(row.resume_fidelity) as ResumeFidelity,
    status: text(row.status) as AdapterBinding["status"],
    cwd: nullableText(row.cwd),
    modelId: nullableText(row.model_id),
    systemPromptHash: nullableText(row.system_prompt_hash),
    metadataJson: text(row.metadata_json),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
    lastUsedAtMs: nullableNumber(row.last_used_at_ms),
    invalidatedAtMs: nullableNumber(row.invalidated_at_ms),
  };
}

function eventFromRow(row: Record<string, unknown>): AgentEvent {
  return {
    eventSeq: Number(row.event_seq),
    eventId: text(row.event_id),
    sessionId: text(row.session_id),
    runId: nullableText(row.run_id),
    attemptId: nullableText(row.attempt_id),
    type: text(row.type),
    retentionClass: text(row.retention_class) as AgentEvent["retentionClass"],
    visibility: text(row.visibility) as AgentEvent["visibility"],
    payloadJson: text(row.payload_json),
    createdAtMs: Number(row.created_at_ms),
  };
}

function artifactFromRow(row: Record<string, unknown>): AgentArtifact {
  return {
    artifactId: text(row.artifact_id),
    sessionId: text(row.session_id),
    runId: nullableText(row.run_id),
    attemptId: nullableText(row.attempt_id),
    kind: text(row.kind),
    role: text(row.role) as ArtifactRole,
    uri: text(row.uri),
    displayName: nullableText(row.display_name),
    mimeType: nullableText(row.mime_type),
    contentHash: nullableText(row.content_hash),
    sizeBytes: nullableNumber(row.size_bytes),
    metadataJson: text(row.metadata_json),
    createdAtMs: Number(row.created_at_ms),
  };
}

const runColumnMap: Record<string, string> = {
  runId: "run_id",
  sessionId: "session_id",
  parentRunId: "parent_run_id",
  clientId: "client_id",
  requestId: "request_id",
  idempotencyKey: "idempotency_key",
  inputJson: "input_json",
  systemPromptHash: "system_prompt_hash",
  modelProfile: "model_profile",
  requestedModelId: "requested_model_id",
  finalText: "final_text",
  resultJson: "result_json",
  errorCode: "error_code",
  errorMessage: "error_message",
  inputTokens: "input_tokens",
  outputTokens: "output_tokens",
  cacheReadTokens: "cache_read_tokens",
  cacheWriteTokens: "cache_write_tokens",
  costUsd: "cost_usd",
  createdAtMs: "created_at_ms",
  startedAtMs: "started_at_ms",
  completedAtMs: "completed_at_ms",
  updatedAtMs: "updated_at_ms",
};

const attemptColumnMap: Record<string, string> = {
  attemptId: "attempt_id",
  runId: "run_id",
  attemptNo: "attempt_no",
  adapterId: "adapter_id",
  adapterInstanceId: "adapter_instance_id",
  runtimeNodeId: "runtime_node_id",
  bindingId: "binding_id",
  adapterNativeRunId: "adapter_native_run_id",
  resumeFromAttemptId: "resume_from_attempt_id",
  checkpointArtifactId: "checkpoint_artifact_id",
  retryReason: "retry_reason",
  cancellationRequestedAtMs: "cancellation_requested_at_ms",
  cancellationDispatchedAtMs: "cancellation_dispatched_at_ms",
  cancellationAcknowledgedAtMs: "cancellation_acknowledged_at_ms",
  startedAtMs: "started_at_ms",
  completedAtMs: "completed_at_ms",
  errorCode: "error_code",
  errorMessage: "error_message",
  metadataJson: "metadata_json",
  createdAtMs: "created_at_ms",
  updatedAtMs: "updated_at_ms",
};

const bindingColumnMap: Record<string, string> = {
  bindingId: "binding_id",
  sessionId: "session_id",
  adapterId: "adapter_id",
  bindingGeneration: "binding_generation",
  adapterNativeSessionId: "adapter_native_session_id",
  adapterInstanceId: "adapter_instance_id",
  resumeFidelity: "resume_fidelity",
  modelId: "model_id",
  systemPromptHash: "system_prompt_hash",
  metadataJson: "metadata_json",
  createdAtMs: "created_at_ms",
  updatedAtMs: "updated_at_ms",
  lastUsedAtMs: "last_used_at_ms",
  invalidatedAtMs: "invalidated_at_ms",
};
