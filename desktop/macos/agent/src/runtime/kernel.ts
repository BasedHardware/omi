import type {
  AdapterAttemptResult,
  AdapterBindingHandle,
  CancelDispatchResult,
  OpenedBinding,
  PromptBlock,
  RuntimeAdapter,
  ToolDef,
} from "../adapters/interface.js";
import type { OutboundMessage } from "../protocol.js";
import { AdapterRegistry } from "./adapter-registry.js";
import { generateAgentId } from "./sqlite-store.js";
import { AdapterRuntimeError, failureFromError, type RuntimeFailure } from "./failures.js";
import type {
  AdapterBinding,
  AgentEvent,
  AgentArtifact,
  AgentDelegation,
  AgentRun,
  AgentSession,
  AgentStore,
  AgentGrant,
  ArtifactLifecycleState,
  ArtifactRole,
  AttemptStatus,
  NewAgentArtifact,
  NewAgentGrant,
  ResumeFidelity,
  RunAttempt,
  RunMode,
  RunStatus,
  DelegationMode,
  DelegationStatus,
  DesktopArtifactDelivery,
  DesktopAttentionOverride,
  DesktopCandidateStatus,
  DesktopCoordinatorDispatch,
  DesktopMemoryCandidate,
  DesktopTaskCandidate,
  NewDesktopContextAccessLog,
  NewDesktopContextPacket,
  NewDesktopCoordinatorDispatch,
} from "./types.js";
import { buildDesktopActionQueue, type DesktopActionQueueItem, type QueueArtifactDeliveryInput, type QueueCandidateInput, type QueueDispatchInput, type QueueOverrideInput, type QueueRunInput } from "./desktop-action-queue.js";
import { buildDesktopContextPacket, type DesktopContextPacketBuildInput, type BuiltDesktopContextPacket, type DesktopContextSnippetInput } from "./desktop-context-packet.js";
import { routeDesktopIntent, type DesktopIntentRoute, type DesktopIntentRouteInput, type DesktopIntentSessionCandidate } from "./desktop-intent-router.js";
import { OmiArtifactStorage } from "./artifact-storage.js";
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

const ACTIVE_STATUSES: readonly RunStatus[] = ["queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling"];
const TERMINAL_STATUSES: readonly RunStatus[] = ["succeeded", "failed", "cancelled", "timed_out", "orphaned"];
const DEFAULT_DELEGATION_MAX_DEPTH = 3;
const HARD_DELEGATION_MAX_DEPTH = 5;
const DEFAULT_DELEGATION_MAX_BUDGET_USD = 5;

function requiresVerifiedContextDispatch(snippet: DesktopContextSnippetInput): boolean {
  const tier = snippet.sensitivityTier.toLowerCase();
  if (snippet.sourceKind === "screenshot_image") return true;
  if (snippet.sourceKind === "rewind_timeline") return true;
  if (snippet.sourceKind === "screen_current" && tier !== "low") return true;
  return tier === "sensitive";
}
const HARD_DELEGATION_MAX_BUDGET_USD = 10;

function stableHash(value: string | undefined): string {
  return createHash("sha256").update(value ?? "").digest("hex");
}

const REQUEST_SCOPED_MCP_ENV_KEYS = new Set([
  "OMI_BRIDGE_PIPE",
  "OMI_CONTEXT_FILE",
  "OMI_REQUEST_ID",
  "OMI_CLIENT_ID",
  "OMI_PROTOCOL_VERSION",
  "OMI_SESSION_ID",
  "OMI_RUN_ID",
  "OMI_ATTEMPT_ID",
  "OMI_ADAPTER_SESSION_ID",
  "OMI_LEGACY_ADAPTER_SESSION_ID",
]);

function stableJsonStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value) ?? "undefined";
  }
  if (Array.isArray(value)) {
    return `[${value.map((entry) => stableJsonStringify(entry)).join(",")}]`;
  }
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJsonStringify(object[key])}`)
    .join(",")}}`;
}

function stableMcpServerConfig(value: unknown): unknown {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((server) => {
    if (!server || typeof server !== "object" || Array.isArray(server)) {
      return server;
    }
    const normalized: Record<string, unknown> = { ...(server as Record<string, unknown>) };
    if (Array.isArray(normalized.env)) {
      normalized.env = normalized.env
        .filter((entry) => {
          if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
            return true;
          }
          const name = (entry as Record<string, unknown>).name;
          return typeof name !== "string" || !REQUEST_SCOPED_MCP_ENV_KEYS.has(name);
        })
        .sort((left, right) => {
          const leftName =
            left && typeof left === "object" && !Array.isArray(left)
              ? String((left as Record<string, unknown>).name ?? "")
              : "";
          const rightName =
            right && typeof right === "object" && !Array.isArray(right)
              ? String((right as Record<string, unknown>).name ?? "")
              : "";
          return leftName.localeCompare(rightName);
        });
    }
    return normalized;
  });
}

function stableJsonHash(value: unknown): string {
  return stableHash(stableJsonStringify(value ?? null));
}

function parseJsonObject(value: string | null | undefined): Record<string, unknown> {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function bindingMetadata(input: ExecuteAgentRunInput, adapter?: RuntimeAdapter): string {
  const effectiveMcpServers = adapter?.effectiveMcpServers
    ? adapter.effectiveMcpServers(input.mcpServers ?? [])
    : input.mcpServers ?? [];
  return JSON.stringify({
    mcpServersHash: stableJsonHash(stableMcpServerConfig(effectiveMcpServers)),
  });
}

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
  artifacts: AgentArtifact[];
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
  ownerId?: string;
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
  artifactId?: string;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  ownerId?: string;
  role?: ArtifactRole;
  limit?: number;
}

export interface DesktopAwarenessSnapshotInput {
  ownerId?: string;
  limit?: number;
}

export interface DesktopAwarenessSnapshot {
  ownerId: string;
  generatedAtMs: number;
  sessions: KernelSessionSummary[];
  runs: AgentRun[];
  dispatches: DesktopCoordinatorDispatch[];
  artifactDeliveries: DesktopArtifactDelivery[];
  memoryCandidates: DesktopMemoryCandidate[];
  taskCandidates: DesktopTaskCandidate[];
  actionQueue: DesktopActionQueueItem[];
  runtime: {
    activeExecutionCount: number;
    registeredAdapters: string[];
  };
}

export interface DesktopActionQueueInput {
  ownerId?: string;
  staleAfterMs?: number;
  limit?: number;
}

export interface DesktopOpenLoopsInput {
  ownerId?: string;
  limit?: number;
}

export interface DesktopContextPacketPersistInput extends Omit<DesktopContextPacketBuildInput, "ownerId"> {
  ownerId?: string;
}

export interface ResolveDesktopDispatchInput {
  ownerId: string;
  status: "resolved" | "cancelled";
  resolvedBy?: string | null;
  resolutionJson?: string | null;
  resolvedAtMs?: number;
  grant?: Omit<NewAgentGrant, "sessionId"> & { sessionId?: string };
}

export interface ResolveDesktopDispatchResult {
  dispatch: DesktopCoordinatorDispatch;
  grant: AgentGrant | null;
  event: AgentEvent | null;
}

export interface UpdateArtifactLifecycleInput {
  artifactId: string;
  state: ArtifactLifecycleState;
  ownerId?: string;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  reason?: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateArtifactLifecycleResult {
  artifact: AgentArtifact;
  changed: boolean;
  event: AgentEvent | null;
}

export interface PersistArtifactInput {
  sessionId?: string;
  runId?: string | null;
  attemptId?: string | null;
  kind: string;
  role: ArtifactRole;
  uri: string;
  displayName?: string | null;
  mimeType?: string | null;
  contentHash?: string | null;
  sizeBytes?: number | null;
  metadata?: Record<string, unknown>;
  metadataJson?: string;
  artifactId?: string;
  createdAtMs?: number;
}

export interface InvalidateBindingsInput extends KernelSessionResolutionInput {
  adapterId?: string;
  reason?: string;
}

export interface InvalidateBindingsResult {
  sessionId?: string;
  invalidatedBindingIds: string[];
}

export interface StaleProcessLocalBindingsInput {
  adapterId: string;
  reason: string;
}

export interface StaleProcessLocalBindingsResult {
  staleBindingIds: string[];
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
  mcpServers?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
}

export interface SpawnBackgroundAgentInput {
  ownerId: string;
  clientId: string;
  requestId: string;
  prompt: string;
  title?: string;
  surfaceKind?: string;
  externalRefKind?: string;
  externalRefId?: string;
  adapterId?: string;
  defaultAdapterId?: string;
  cwd?: string;
  model?: string;
  mcpServers?: Record<string, unknown>[];
  mode?: RunMode;
  metadata?: Record<string, unknown>;
}

export interface SpawnBackgroundAgentResult {
  session: AgentSession;
  run: AgentRun;
  attempt?: RunAttempt;
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
  mcpServers?: Record<string, unknown>[];
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
  artifactStorage?: OmiArtifactStorage;
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
  private readonly artifactStorage?: OmiArtifactStorage;
  private readonly subscribers = new Set<KernelEventSubscriber>();
  private readonly activeExecutions = new Map<string, ActiveExecution>();
  private readonly bindingResolutionLocks = new Map<string, Promise<void>>();
  private transactionDepth = 0;
  private pendingSubscriberEvents: AgentEvent[] = [];

  constructor(options: AgentRuntimeKernelOptions) {
    this.store = options.store;
    this.registry = options.registry;
    this.runtimeNodeId = options.runtimeNodeId ?? "desktop-local";
    this.artifactStorage = options.artifactStorage;
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
      mcpServers: input.mcpServers,
      metadata: input.metadata,
    });
  }

  async spawnBackgroundAgent(input: SpawnBackgroundAgentInput): Promise<SpawnBackgroundAgentResult> {
    const runInput: ExecuteAgentRunInput = {
      ownerId: input.ownerId,
      surfaceKind: input.surfaceKind ?? "background_agent",
      externalRefKind: input.externalRefKind,
      externalRefId: input.externalRefId,
      title: input.title ?? `Background: ${input.prompt.slice(0, 80)}`,
      defaultAdapterId: input.defaultAdapterId ?? input.adapterId,
      adapterId: input.adapterId ?? input.defaultAdapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: input.prompt,
      mode: input.mode ?? "act",
      cwd: input.cwd,
      model: input.model,
      mcpServers: input.mcpServers,
      metadata: {
        ...(input.metadata ?? {}),
        spawnKind: "background_agent",
      },
    };
    const accepted = this.createAcceptedRun(runInput);
    void this.executeAcceptedRun(runInput, accepted).catch(() => {
      // executeAcceptedRun records the failed run/attempt and emits events.
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
      mcpServers: input.mcpServers,
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
    return this.withTransaction(() => {
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
      this.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: "run.queued",
        payload: { runId: run.runId, requestId: run.requestId, clientId: run.clientId },
      });
      this.touchSession(session.sessionId);
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
        bindingResolutionProtectedBindingId = pool.requiresPinnedWorkers ? (handle.bindingId ?? null) : null;
      } catch (error) {
        pool.unprotectPinnedBinding(bindingResolutionProtectedBindingId);
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
          refreshMcpAttemptContext(mcpServersForBinding(input.mcpServers ?? [], accepted.session.sessionId, adapterId, this.runtimeNodeId), {
            ownerId: input.ownerId,
            requestId: accepted.run.requestId,
            clientId: accepted.run.clientId,
            protocolVersion: input.metadata?.protocolVersion,
            sessionId: accepted.session.sessionId,
            runId: accepted.run.runId,
            attemptId: attempt.attemptId,
            adapterSessionId: handle.adapterNativeSessionId,
            legacyAdapterSessionId: input.legacyAdapterSessionId,
          });
          this.markAttemptRunning(attempt, binding);
          return worker.adapter.executeAttempt(
            {
              sessionId: accepted.session.sessionId,
              ownerId: input.ownerId,
              requestId: accepted.run.requestId,
              clientId: accepted.run.clientId,
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
    };
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

  getDesktopOpenLoops(input: DesktopOpenLoopsInput): DesktopActionQueueItem[] {
    return this.listDesktopActionQueue(input).filter((item) =>
      ["dispatch", "failed_run", "artifact_delivery", "stale_run", "candidate_review"].includes(item.kind)
    );
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

  private validateSensitiveContextDispatches(input: DesktopContextPacketBuildInput): void {
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

  getRun(input: GetRunInput): KernelRunDetails {
    const run = this.readRun(input.runId);
    const session = this.readSession(run.sessionId);
    if (input.ownerId) {
      this.assertSessionOwner(session, input.ownerId);
    }
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
    if (!input.artifactId && !input.sessionId && !input.runId && !input.attemptId) {
      throw new Error("Inspecting artifacts requires artifactId, sessionId, runId, or attemptId");
    }
    if (input.ownerId) {
      this.assertArtifactSelectorOwner(input, input.ownerId);
    }
    return this.readArtifacts(input);
  }

  updateArtifactLifecycle(input: UpdateArtifactLifecycleInput): UpdateArtifactLifecycleResult {
    return this.withTransaction(() => {
      const artifact = this.readArtifact(input.artifactId);
      this.assertArtifactScope(artifact, input);
      if (input.ownerId) {
        this.assertSessionOwner(this.readSession(artifact.sessionId), input.ownerId);
      }
      if (artifact.lifecycleState === input.state) {
        return { artifact, changed: false, event: null };
      }

      const now = Date.now();
      this.store.execute(
        "UPDATE artifacts SET lifecycle_state = ?, lifecycle_updated_at_ms = ? WHERE artifact_id = ?",
        [input.state, now, artifact.artifactId],
      );
      const updatedArtifact = this.readArtifact(artifact.artifactId);
      const event = this.appendEvent({
        sessionId: updatedArtifact.sessionId,
        runId: updatedArtifact.runId,
        attemptId: updatedArtifact.attemptId,
        type: "artifact.lifecycle_updated",
        payload: {
          artifactId: updatedArtifact.artifactId,
          previousState: artifact.lifecycleState,
          state: updatedArtifact.lifecycleState,
          reason: input.reason ?? null,
          metadata: input.metadata ?? {},
          lifecycleUpdatedAtMs: now,
        },
      });
      return { artifact: updatedArtifact, changed: true, event };
    });
  }

  persistArtifact(input: PersistArtifactInput): AgentArtifact {
    return this.withTransaction(() => this.persistArtifactInTransaction(input));
  }

  hasActiveExecutionForAdapter(adapterId: string): boolean {
    for (const active of this.activeExecutions.values()) {
      if (active.adapter.adapterId === adapterId) return true;
    }
    return false;
  }

  hasActiveExecutionForSessionAdapter(sessionId: string, adapterId: string): boolean {
    for (const active of this.activeExecutions.values()) {
      if (active.sessionId === sessionId && active.adapter.adapterId === adapterId) return true;
    }
    return false;
  }

  hasExecutionCapacityForAdapter(adapterId: string): boolean {
    if (!this.registry.has(adapterId)) return false;
    let activeCount = 0;
    for (const active of this.activeExecutions.values()) {
      if (active.adapter.adapterId === adapterId) activeCount += 1;
    }
    return activeCount < this.registry.capacity(adapterId);
  }

  isAdapterRegistered(adapterId: string): boolean {
    return this.registry.has(adapterId);
  }

  defaultAdapterIdForSession(sessionId: string): string {
    return this.readSession(sessionId).defaultAdapterId;
  }

  defaultAdapterIdForRun(runId: string): string {
    const run = this.readRun(runId);
    return this.readSession(run.sessionId).defaultAdapterId;
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
    this.withTransaction(() => {
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
          type: "binding.stale",
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

  staleProcessLocalBindings(input: StaleProcessLocalBindingsInput): StaleProcessLocalBindingsResult {
    const rows = this.store.allRows(
      `SELECT binding_id, session_id
       FROM adapter_bindings
       WHERE adapter_id = ?
         AND resume_fidelity = ?
         AND status = ?`,
      [input.adapterId, "none", "active"],
    );
    const staleBindingIds = rows.map((row) => String(row.binding_id));
    if (staleBindingIds.length === 0) {
      return { staleBindingIds };
    }

    const now = Date.now();
    this.withTransaction(() => {
      for (const row of rows) {
        const bindingId = String(row.binding_id);
        this.updateBinding(bindingId, {
          status: "stale",
          invalidatedAtMs: now,
          updatedAtMs: now,
        });
        this.appendEvent({
          sessionId: String(row.session_id),
          runId: null,
          attemptId: null,
          type: "binding.stale",
          payload: {
            bindingId,
            adapterId: input.adapterId,
            reason: input.reason,
          },
        });
      }
    });

    return { staleBindingIds };
  }

  private createDelegatedRun(
    parentSession: AgentSession,
    parentRun: AgentRun,
    childRunInput: ExecuteAgentRunInput,
    input: DelegateAgentInput
  ): { session: AgentSession; run: AgentRun; delegation: AgentDelegation } {
    return this.withTransaction(() => {
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
    const shouldStoreLegacyAlias = !(input.externalRefKind && input.externalRefId);
    const session = this.store.insertSession({
      ownerId: input.ownerId,
      surfaceKind: input.surfaceKind,
      externalRefKind: input.externalRefKind ?? null,
      externalRefId: input.externalRefId ?? null,
      legacyClientScope: shouldStoreLegacyAlias ? input.legacyClientScope ?? null : null,
      legacySessionKey: shouldStoreLegacyAlias ? input.legacySessionKey ?? null : null,
      title: input.title ?? null,
      defaultAdapterId: input.defaultAdapterId ?? "acp",
    });
    this.appendEvent({
      sessionId: session.sessionId,
      type: "session.created",
      payload: { sessionId: session.sessionId, ownerId: session.ownerId, surfaceKind: session.surfaceKind },
    });
    return session;
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
      return undefined;
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

  private async resolveBindingForAttempt(input: {
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
    if (input.input.legacyAdapterSessionId && input.adapter.capabilities.supportsNativeResume && nextGeneration === 1) {
      const adopted = this.withTransaction(() => {
        const binding = this.store.insertAdapterBinding({
          sessionId: input.session.sessionId,
          adapterId: input.adapterId,
          bindingGeneration: 1,
          adapterNativeSessionId: input.input.legacyAdapterSessionId,
          adapterInstanceId: this.runtimeNodeId,
          resumeFidelity: "native",
          status: "active",
          cwd: input.input.cwd ?? input.session.defaultCwd ?? process.cwd(),
          modelId: input.input.model ?? null,
          systemPromptHash: stableHash(input.input.systemPrompt),
          metadataJson: bindingMetadata(input.input, input.adapter),
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

  private isBindingCompatible(
    binding: AdapterBinding,
    input: {
      input: ExecuteAgentRunInput;
      session: AgentSession;
      adapter?: RuntimeAdapter;
    }
  ): boolean {
    const requestedCwd = input.input.cwd ?? input.session.defaultCwd ?? process.cwd();
    const bindingCwd = binding.cwd ?? process.cwd();
    if (bindingCwd !== requestedCwd) {
      return false;
    }
    if (input.input.model !== undefined && binding.modelId !== input.input.model) {
      return false;
    }
    const requestedSystemPromptHash = stableHash(input.input.systemPrompt);
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

  private async resumeOrReplaceBinding(
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
      });
      this.withTransaction(() => {
        this.updateBinding(binding.bindingId, {
          adapterInstanceId: this.runtimeNodeId,
          cwd: input.input.cwd ?? binding.cwd ?? input.session.defaultCwd ?? null,
          modelId: input.input.model ?? binding.modelId ?? null,
          systemPromptHash: stableHash(input.input.systemPrompt),
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
  ): Promise<{ binding: AdapterBinding; handle: AdapterBindingHandle; replacesBindingId?: string }> {
    const opened = await input.adapter.openBinding({
      sessionId: input.session.sessionId,
      cwd: input.input.cwd ?? input.session.defaultCwd ?? process.cwd(),
      model: input.input.model,
      systemPrompt: input.input.systemPrompt,
      mcpServers: mcpServersForBinding(input.input.mcpServers ?? [], input.session.sessionId, input.adapterId, this.runtimeNodeId),
      metadata: input.input.metadata,
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
        adapterNativeSessionId: opened.adapterNativeSessionId,
        adapterInstanceId: this.runtimeNodeId,
        resumeFidelity: opened.resumeFidelity,
        status: "active",
        cwd: opened.cwd,
        modelId: opened.model ?? input.input.model ?? null,
        systemPromptHash: stableHash(input.input.systemPrompt),
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

  private markAttemptRunning(attempt: RunAttempt, binding: AdapterBinding): void {
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

  private completeAttemptAndRun(
    session: AgentSession,
    runId: string,
    attempt: RunAttempt,
    binding: AdapterBinding,
    result: AdapterAttemptResult
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
      const artifacts = [
        ...emittedArtifacts,
        ...(this.artifactStorage?.discoverRunArtifacts({
          ownerId: session.ownerId,
          sessionId: session.sessionId,
          runId,
          attemptId: attempt.attemptId,
        }, [...emittedArtifacts, ...existingArtifacts]) ?? []),
      ];
      for (const rawArtifact of artifacts) {
        const artifact = this.artifactStorage?.normalizeArtifact(rawArtifact, {
          ownerId: session.ownerId,
          sessionId: session.sessionId,
          runId,
          attemptId: attempt.attemptId,
        }) ?? rawArtifact;
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

  private inputWithManagedArtifactCwd(
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

  private finishAttemptAndRun(input: {
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

  private failAttemptBeforeExecution(
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
    const failure = failureFromError(error, {
      code: errorCode,
      source: "adapter_process",
      adapterId: attempt.adapterId,
      retryable: true,
    });
    this.failAttemptBeforeExecution(attempt, errorCode, failure.userMessage, true, failure);
    return true;
  }

  private persistAdapterEvent(sessionId: string, runId: string, attemptId: string, event: OutboundMessage): void {
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

  private closeConflictingNativeBinding(
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

  private markBindingStale(binding: AdapterBinding, attempt: RunAttempt, reason: string): void {
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

  private markEvictedBindingStale(bindingId: string, reason: string): void {
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

  private persistArtifactInTransaction(input: PersistArtifactInput): AgentArtifact {
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

  private resolveArtifactScope(input: PersistArtifactInput): {
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
    if (this.transactionDepth > 0) {
      this.pendingSubscriberEvents.push(event);
      return event;
    }
    this.notifySubscribers(event);
    return event;
  }

  private withTransaction<T>(work: () => T): T {
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

  private notifySubscribers(event: AgentEvent): void {
    for (const subscriber of this.subscribers) {
      try {
        subscriber(event);
      } catch {
        // Subscribers are observers; event persistence must not be rolled back
        // by UI/projection listener failures.
      }
    }
  }

  private async withBindingResolutionLock<T>(
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

  private readSession(sessionId: string): AgentSession {
    return sessionFromRow(this.store.getRow("SELECT * FROM sessions WHERE session_id = ?", [sessionId]));
  }

  private readRun(runId: string): AgentRun {
    return runFromRow(this.store.getRow("SELECT * FROM runs WHERE run_id = ?", [runId]));
  }

  private assertSessionOwner(session: AgentSession, ownerId: string): void {
    if (session.ownerId !== ownerId) {
      throw new Error("Agent session is not visible to the active owner");
    }
  }

  private assertRunOwner(run: AgentRun, ownerId: string): void {
    this.assertSessionOwner(this.readSession(run.sessionId), ownerId);
  }

  private assertAttemptOwner(attempt: RunAttempt, ownerId: string): void {
    this.assertRunOwner(this.readRun(attempt.runId), ownerId);
  }

  private assertArtifactSelectorOwner(input: InspectArtifactsInput, ownerId: string): void {
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

  private readArtifact(artifactId: string): AgentArtifact {
    return artifactFromRow(this.store.getRow("SELECT * FROM artifacts WHERE artifact_id = ?", [artifactId]));
  }

  private assertArtifactScope(
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

  private readDesktopDispatches(ownerId: string, limit: number): DesktopCoordinatorDispatch[] {
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

  private readDesktopArtifactDeliveries(ownerId: string, limit: number): DesktopArtifactDelivery[] {
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

  private readDesktopMemoryCandidates(ownerId: string, limit: number): DesktopMemoryCandidate[] {
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

  private readDesktopTaskCandidates(ownerId: string, limit: number): DesktopTaskCandidate[] {
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

  private readDesktopAttentionOverrides(ownerId: string): DesktopAttentionOverride[] {
    return this.store
      .allRows("SELECT * FROM desktop_attention_overrides WHERE owner_id = ?", [ownerId])
      .map(desktopAttentionOverrideFromRow);
  }

  private readDesktopQueueRuns(ownerId: string, limit: number): QueueRunInput[] {
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

  private desktopIntentSessionCandidates(ownerId: string, surfaceKind: string, taskId: string | null): DesktopIntentSessionCandidate[] {
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
    this.appendEvent({
      sessionId,
      type: "session.updated",
      payload: { sessionId },
    });
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

function queueRunGoalText(row: Record<string, unknown>): string | null {
  const input = parseJsonObject(nullableString(row.input_json));
  const prompt = input.prompt;
  return typeof prompt === "string" && prompt.trim() ? prompt : null;
}

function messageFrom(error: unknown): string {
  if (error instanceof AdapterRuntimeError) {
    return error.failure.userMessage;
  }
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

function stringValue(value: unknown): string {
  return text(value);
}

function numberValue(value: unknown): number {
  return Number(value ?? 0);
}

function nullableString(value: unknown): string | null {
  return nullableText(value);
}

function desktopDispatchFromRow(row: Record<string, unknown>): DesktopCoordinatorDispatch {
  return {
    dispatchId: text(row.dispatch_id),
    ownerId: text(row.owner_id),
    kind: text(row.kind) as DesktopCoordinatorDispatch["kind"],
    priority: Number(row.priority),
    status: text(row.status) as DesktopCoordinatorDispatch["status"],
    title: text(row.title),
    decisionPrompt: text(row.decision_prompt),
    recommendedDefault: nullableText(row.recommended_default),
    sourceSessionId: nullableText(row.source_session_id),
    sourceRunId: nullableText(row.source_run_id),
    sourceAttemptId: nullableText(row.source_attempt_id),
    sourceArtifactId: nullableText(row.source_artifact_id),
    capability: nullableText(row.capability),
    operation: nullableText(row.operation),
    resourceRef: nullableText(row.resource_ref),
    payloadJson: text(row.payload_json),
    createdAtMs: Number(row.created_at_ms),
    expiresAtMs: nullableNumber(row.expires_at_ms),
    resolvedAtMs: nullableNumber(row.resolved_at_ms),
    resolvedBy: nullableText(row.resolved_by),
    resolutionJson: nullableText(row.resolution_json),
  };
}

function desktopArtifactDeliveryFromRow(row: Record<string, unknown>): DesktopArtifactDelivery {
  return {
    deliveryId: text(row.delivery_id),
    artifactId: text(row.artifact_id),
    ownerId: text(row.owner_id),
    sourceSessionId: text(row.source_session_id),
    sourceRunId: nullableText(row.source_run_id),
    sourceAttemptId: nullableText(row.source_attempt_id),
    intendedSurface: text(row.intended_surface),
    targetKind: text(row.target_kind) as DesktopArtifactDelivery["targetKind"],
    targetRef: nullableText(row.target_ref),
    contentHash: nullableText(row.content_hash),
    reviewStatus: text(row.review_status) as DesktopArtifactDelivery["reviewStatus"],
    deliveryStatus: text(row.delivery_status) as DesktopArtifactDelivery["deliveryStatus"],
    attemptCount: Number(row.attempt_count),
    receiptJson: nullableText(row.receipt_json),
    errorJson: nullableText(row.error_json),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
    deliveredAtMs: nullableNumber(row.delivered_at_ms),
  };
}

function desktopMemoryCandidateFromRow(row: Record<string, unknown>): DesktopMemoryCandidate {
  return {
    candidateId: text(row.candidate_id),
    ownerId: text(row.owner_id),
    sourceSessionId: text(row.source_session_id),
    sourceRunId: nullableText(row.source_run_id),
    sourceArtifactId: nullableText(row.source_artifact_id),
    proposedFact: text(row.proposed_fact),
    evidenceRefsJson: text(row.evidence_refs_json),
    confidence: Number(row.confidence),
    sensitivityTier: text(row.sensitivity_tier),
    status: text(row.status) as DesktopCandidateStatus,
    createdAtMs: Number(row.created_at_ms),
    resolvedAtMs: nullableNumber(row.resolved_at_ms),
  };
}

function desktopTaskCandidateFromRow(row: Record<string, unknown>): DesktopTaskCandidate {
  return {
    candidateId: text(row.candidate_id),
    ownerId: text(row.owner_id),
    sourceSessionId: nullableText(row.source_session_id),
    sourceRunId: nullableText(row.source_run_id),
    action: text(row.action) as DesktopTaskCandidate["action"],
    taskRef: nullableText(row.task_ref),
    proposedChangeJson: text(row.proposed_change_json),
    evidenceRefsJson: text(row.evidence_refs_json),
    confidence: Number(row.confidence),
    requiresApproval: Number(row.requires_approval) === 1 ? 1 : 0,
    status: text(row.status) as DesktopCandidateStatus,
    createdAtMs: Number(row.created_at_ms),
    resolvedAtMs: nullableNumber(row.resolved_at_ms),
  };
}

function desktopAttentionOverrideFromRow(row: Record<string, unknown>): DesktopAttentionOverride {
  return {
    ownerId: text(row.owner_id),
    subjectKind: text(row.subject_kind),
    subjectId: text(row.subject_id),
    hiddenUntilMs: nullableNumber(row.hidden_until_ms),
    dismissedAtMs: nullableNumber(row.dismissed_at_ms),
    reason: nullableText(row.reason),
    createdAtMs: Number(row.created_at_ms),
  };
}

function dispatchToQueueInput(dispatch: DesktopCoordinatorDispatch): QueueDispatchInput {
  return {
    dispatchId: dispatch.dispatchId,
    ownerId: dispatch.ownerId,
    kind: dispatch.kind,
    status: dispatch.status,
    title: dispatch.title,
    priority: dispatch.priority,
    createdAtMs: dispatch.createdAtMs,
    expiresAtMs: dispatch.expiresAtMs,
    sourceSessionId: dispatch.sourceSessionId,
    sourceRunId: dispatch.sourceRunId,
  };
}

function deliveryToQueueInput(delivery: DesktopArtifactDelivery): QueueArtifactDeliveryInput {
  return {
    deliveryId: delivery.deliveryId,
    artifactId: delivery.artifactId,
    ownerId: delivery.ownerId,
    sourceSessionId: delivery.sourceSessionId,
    sourceRunId: delivery.sourceRunId,
    deliveryStatus: delivery.deliveryStatus,
    reviewStatus: delivery.reviewStatus,
    createdAtMs: delivery.createdAtMs,
    updatedAtMs: delivery.updatedAtMs,
    targetKind: delivery.targetKind,
  };
}

function memoryCandidateToQueueInput(candidate: DesktopMemoryCandidate): QueueCandidateInput {
  return {
    candidateId: candidate.candidateId,
    ownerId: candidate.ownerId,
    kind: "memory_candidate",
    status: candidate.status,
    createdAtMs: candidate.createdAtMs,
    sourceSessionId: candidate.sourceSessionId,
    sourceRunId: candidate.sourceRunId,
  };
}

function taskCandidateToQueueInput(candidate: DesktopTaskCandidate): QueueCandidateInput {
  return {
    candidateId: candidate.candidateId,
    ownerId: candidate.ownerId,
    kind: "task_candidate",
    status: candidate.status,
    createdAtMs: candidate.createdAtMs,
    sourceSessionId: candidate.sourceSessionId,
    sourceRunId: candidate.sourceRunId,
  };
}

function overrideToQueueInput(override: DesktopAttentionOverride): QueueOverrideInput {
  return {
    ownerId: override.ownerId,
    subjectKind: override.subjectKind,
    subjectId: override.subjectId,
    hiddenUntilMs: override.hiddenUntilMs,
    dismissedAtMs: override.dismissedAtMs,
  };
}

function intentCandidateStatus(
  status: string | null,
  runUpdatedAtMs?: number,
  nowMs?: number,
  staleAfterMs?: number,
): DesktopIntentSessionCandidate["status"] {
  if (status === "failed" || status === "timed_out") return "failed";
  if (status === "orphaned") return "orphaned";
  if (status === "cancelled") return "closed";
  // An active run that has not advanced within the stale threshold should be
  // classified as stale so the router forks instead of resuming into a hung run.
  if (
    runUpdatedAtMs !== undefined &&
    nowMs !== undefined &&
    staleAfterMs !== undefined &&
    ACTIVE_STATUSES.includes((status ?? "") as RunStatus)
  ) {
    if (nowMs - runUpdatedAtMs >= staleAfterMs) return "stale";
  }
  return "healthy";
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
    lifecycleState: text(row.lifecycle_state) as ArtifactLifecycleState,
    lifecycleUpdatedAtMs: nullableNumber(row.lifecycle_updated_at_ms),
    metadataJson: text(row.metadata_json),
    createdAtMs: Number(row.created_at_ms),
  };
}

function canonicalAdapterEventType(event: OutboundMessage): string | undefined {
  switch (event.type) {
    case "text_delta":
      return "message.delta";
    case "thinking_delta":
      return "progress.updated";
    case "tool_activity":
      if (event.status === "started") return "tool.started";
      if (event.status === "completed") return "tool.completed";
      if (event.status === "failed") return "tool.failed";
      return "tool.updated";
    case "tool_use":
      return "tool.started";
    case "tool_result_display":
      return "tool.completed";
    case "error":
      return "progress.updated";
    default:
      return undefined;
  }
}

function refreshMcpAttemptContext(
  mcpServers: Record<string, unknown>[],
  context: {
    ownerId: string;
    requestId: string;
    clientId: string;
    protocolVersion?: unknown;
    sessionId: string;
    runId: string;
    attemptId: string;
    adapterSessionId?: string;
    legacyAdapterSessionId?: string;
  }
): void {
  for (const server of mcpServers) {
    const env = Array.isArray(server.env) ? server.env : [];
    const contextFile = env.find((entry) =>
      entry &&
      typeof entry === "object" &&
      !Array.isArray(entry) &&
      (entry as Record<string, unknown>).name === "OMI_CONTEXT_FILE"
    );
    const contextFilePath =
      contextFile && typeof contextFile === "object" && !Array.isArray(contextFile)
        ? (contextFile as Record<string, unknown>).value
        : undefined;
    if (typeof contextFilePath !== "string" || !contextFilePath.trim()) {
      continue;
    }
    writeFileSync(contextFilePath, JSON.stringify(context), { encoding: "utf8" });
  }
}

function mcpServersForBinding(
  mcpServers: Record<string, unknown>[],
  sessionId: string,
  adapterId: string,
  runtimeNodeId: string
): Record<string, unknown>[] {
  return mcpServers.map((server) => {
    if (!server || typeof server !== "object" || Array.isArray(server)) {
      return server;
    }
    const normalized: Record<string, unknown> = { ...server };
    const env = Array.isArray(normalized.env) ? normalized.env : [];
    normalized.env = upsertEnv(env, "OMI_CONTEXT_FILE", contextFileForBinding(sessionId, adapterId, runtimeNodeId));
    return normalized;
  });
}

function upsertEnv(env: unknown[], name: string, value: string): unknown[] {
  let replaced = false;
  const next = env.map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry) || (entry as Record<string, unknown>).name !== name) {
      return entry;
    }
    replaced = true;
    return { ...entry, value };
  });
  if (!replaced) {
    next.push({ name, value });
  }
  return next;
}

function contextFileForBinding(sessionId: string, adapterId: string, runtimeNodeId: string): string {
  return `${tmpdir()}/omi-tools-context-${process.pid}-${encodeURIComponent(runtimeNodeId)}-${encodeURIComponent(sessionId)}-${encodeURIComponent(adapterId)}.json`;
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
