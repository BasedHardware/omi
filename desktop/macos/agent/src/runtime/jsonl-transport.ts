import { randomUUID } from "node:crypto";
import type { PromptBlock } from "../adapters/interface.js";
import { detectImageMimeType } from "../mime-detect.js";
import type {
  CancelAckMessage,
  ErrorMessage,
  InvalidateSessionMessage,
  OutboundMessage,
  OutboundMessageDraft,
  ProtocolVersion,
  QueryMessage,
  QueryScopedOutbound,
  ResultMessage,
  WarmupMessage,
} from "../protocol.js";
import { PROTOCOL_VERSION } from "../protocol.js";
import { serializeArtifact } from "./artifact-serialization.js";
import { failureFromError, normalizeRuntimeFailure, sanitizeProcessDiagnostic, type RuntimeFailure } from "./failures.js";
import type { AgentEvent, RunMode } from "./types.js";
import { AgentRuntimeKernel, type ExecuteAgentRunInput } from "./kernel.js";
import { kernelSystemPolicy } from "./context-snapshot.js";

export type JsonlTransportSend = (message: OutboundMessageDraft) => void;
export type JsonlTransportLog = (message: string) => void;

export interface McpServerBuildContext {
  ownerId: string;
  requestId: string;
  clientId: string;
  protocolVersion: ProtocolVersion;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  surfaceKind?: string;
  externalRefKind?: string;
  externalRefId?: string;
  adapterId?: string;
  includeSwiftBackedTools?: boolean;
  screenContext?: boolean;
  executionRole?: "coordinator" | "leaf";
}

export type McpServerBuilder = (
  mode: RunMode,
  cwd: string,
  sessionKey: string | undefined,
  context: McpServerBuildContext
) => Record<string, unknown>[];

export type RecoverableErrorPredicate = (error: unknown, adapterId: string) => boolean;
export type RecoverableErrorHandler = (error: unknown, adapterId: string) => Promise<void>;

export interface JsonlTransportOptions {
  kernel: AgentRuntimeKernel;
  send: JsonlTransportSend;
  log?: JsonlTransportLog;
  ownerId?: string;
  defaultAdapterId?: string;
  defaultCwd?: () => string;
  buildMcpServers?: McpServerBuilder;
  suppressToolUseEvents?: boolean;
  isRecoverableError?: RecoverableErrorPredicate;
  onRecoverableError?: RecoverableErrorHandler;
  maxRecoverableRetries?: number;
  activeOwnerId?: () => string;
}

interface ActiveRequestContext {
  requestId: string;
  clientId: string;
  ownerId: string;
  adapterId: string;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  adapterSessionId?: string;
  isRunning?: boolean;
  authorityController?: AbortController;
  revoked?: boolean;
}

const TERMINAL_RUN_EVENT_STATUSES = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
  "orphaned",
]);

const QUERY_WIRE_FIELDS = new Set([
  "type",
  "protocolVersion",
  "requestId",
  "clientId",
  "ownerId",
  "sessionId",
  "producingTurnId",
  "prompt",
  "mode",
  "imageBase64",
  "attachments",
  "expectedContextSnapshotVersion",
  "expectedContextSnapshotGeneration",
  "expectedContextRendererFingerprint",
  "expectedCapabilityVersion",
]);

export class JsonlTransport {
  private readonly kernel: AgentRuntimeKernel;
  private readonly send: JsonlTransportSend;
  private readonly log: JsonlTransportLog;
  private readonly ownerId: string;
  private readonly defaultAdapterId: string;
  private readonly defaultCwd: () => string;
  private readonly buildMcpServers?: McpServerBuilder;
  private readonly suppressToolUseEvents: boolean;
  private readonly isRecoverableError?: RecoverableErrorPredicate;
  private readonly onRecoverableError?: RecoverableErrorHandler;
  private readonly maxRecoverableRetries: number;
  private readonly activeOwnerId: () => string;
  private readonly activeByRequest = new Map<string, ActiveRequestContext>();
  private readonly activeByRun = new Map<string, ActiveRequestContext>();
  private readonly latestRunByClient = new Map<string, string>();
  private readonly latestRunByOwner = new Map<string, string>();

  constructor(options: JsonlTransportOptions) {
    this.kernel = options.kernel;
    this.send = options.send;
    this.log = options.log ?? (() => {});
    this.ownerId = options.ownerId ?? "desktop-local-user";
    this.defaultAdapterId = options.defaultAdapterId ?? "acp";
    this.defaultCwd = options.defaultCwd ?? (() => process.env.HOME ?? "/");
    this.buildMcpServers = options.buildMcpServers;
    this.suppressToolUseEvents = options.suppressToolUseEvents ?? false;
    this.isRecoverableError = options.isRecoverableError;
    this.onRecoverableError = options.onRecoverableError;
    this.maxRecoverableRetries = Math.max(0, options.maxRecoverableRetries ?? 0);
    this.activeOwnerId = options.activeOwnerId ?? (() => this.ownerId);
    this.kernel.subscribe((event) => this.handleKernelEvent(event));
  }

  async handleQuery(message: QueryMessage): Promise<void> {
    const input = this.buildRunInput(message);
    const key = this.activeRequestKey(input.requestId, input.clientId);
    if (this.activeByRequest.has(key)) {
      throw new Error("Request context already active for clientId/requestId");
    }
    const authorityController = new AbortController();
    input.authoritySignal = authorityController.signal;
    const context: ActiveRequestContext = {
      requestId: input.requestId,
      clientId: input.clientId,
      ownerId: input.ownerId,
      adapterId: input.adapterId ?? this.defaultAdapterId,
      sessionId: input.sessionId,
      authorityController,
      revoked: false,
    };
    this.activeByRequest.set(key, context);

    try {
      const result = await this.kernel.executeRun(input);
      context.sessionId = result.session.sessionId;
      context.runId = result.run.runId;
      context.attemptId = result.attempt.attemptId;
      context.adapterSessionId = result.adapterSessionId ?? undefined;
      if (context.revoked) return;

      const resultMessage = {
        type: "result" as const,
        text: result.text,
        sessionId: result.session.sessionId,
        adapterSessionId: result.adapterSessionId ?? undefined,
        terminalStatus: result.terminalStatus,
        failure: boundedTerminalFailure(result),
        costUsd: result.run.costUsd ?? 0,
        inputTokens: result.run.inputTokens ?? Math.ceil(input.prompt.length / 4),
        outputTokens: result.run.outputTokens ?? Math.ceil(result.text.length / 4),
        cacheReadTokens: result.run.cacheReadTokens ?? 0,
        cacheWriteTokens: result.run.cacheWriteTokens ?? 0,
        artifacts: result.artifacts.map(serializeArtifact),
        completionDeltaArtifacts: result.completionDeltaArtifacts?.map(serializeArtifact),
      };
      this.send(this.withCorrelation(resultMessage, context));
    } catch (error) {
      if (context.revoked) return;
      const failure = failureFromError(error, {
        code: "runtime_query_failed",
        source: "runtime",
        userMessage: error instanceof Error ? error.message : String(error),
      });
      this.log(`Jsonl transport query error: ${failure.userMessage}`);
      const errorMessage = {
        type: "error" as const,
        message: failure.userMessage,
        failure,
      };
      this.send(this.withCorrelation(errorMessage, context));
    } finally {
      this.activeByRequest.delete(this.activeRequestKey(context.requestId, context.clientId));
      if (context.runId) {
        this.activeByRun.delete(context.runId);
        const clientKey = this.latestRunByClientKey(context.ownerId, context.clientId);
        if (this.latestRunByClient.get(clientKey) === context.runId) {
          this.latestRunByClient.delete(clientKey);
        }
        if (this.latestRunByOwner.get(context.ownerId) === context.runId) {
          this.latestRunByOwner.delete(context.ownerId);
        }
      }
    }
  }

  /**
   * Revokes every foreground request admitted for one immutable owner. Kernel
   * terminalization is synchronous, so a new owner is never admitted while an
   * old owner's deferred adapter can still claim success.
   */
  revokeOwner(ownerId: string, reason: "owner_changed" | "owner_state_cleared"): string[] {
    const normalizedOwnerId = ownerId.trim();
    if (!normalizedOwnerId) return [];
    const error = new Error(`Foreground query authority was revoked: ${reason}`);
    const contexts = new Set(
      [...this.activeByRequest.values()].filter((context) => context.ownerId === normalizedOwnerId),
    );
    for (const context of contexts) {
      context.revoked = true;
      if (context.authorityController && !context.authorityController.signal.aborted) {
        context.authorityController.abort(error);
      }
    }
    return this.kernel.revokeActiveRunsForOwner(normalizedOwnerId, reason).runIds;
  }

  async handleInterrupt(message: {
    requestId?: string;
    clientId?: string;
    ownerId?: string;
    sessionId?: string;
    runId?: string;
    attemptId?: string;
  }): Promise<void> {
    const requestId = message.requestId?.trim() ?? "";
    const clientId = message.clientId?.trim();
    const explicitRunId = message.runId?.trim();
    if (!clientId && !explicitRunId) {
      this.send({
        type: "cancel_ack",
        protocolVersion: PROTOCOL_VERSION,
        ...(requestId ? { requestId } : {}),
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      } as CancelAckMessage);
      return;
    }
    if (!requestId && !explicitRunId) {
      this.send({
        type: "cancel_ack",
        protocolVersion: PROTOCOL_VERSION,
        clientId: clientId!,
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      } as CancelAckMessage);
      return;
    }
    const effectiveClientId = clientId!;
    const activeRequestContext = requestId
      ? this.activeByRequest.get(this.activeRequestKey(requestId, effectiveClientId))
      : undefined;
    const ownerId = this.requireActiveOwner(message.ownerId);
    if (requestId && !activeRequestContext && !message.runId && !message.attemptId) {
      const cancelAck = {
        type: "cancel_ack" as const,
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      };
      this.send(this.withCorrelation(cancelAck, {
        requestId,
        clientId: effectiveClientId,
        ownerId,
        adapterId: this.defaultAdapterId,
        sessionId: message.sessionId,
        attemptId: message.attemptId,
      }));
      return;
    }
    const runId =
      explicitRunId ??
      activeRequestContext?.runId ??
      this.latestRunByClient.get(this.latestRunByClientKey(ownerId, effectiveClientId)) ??
      this.latestRunByOwner.get(ownerId);
    const context =
      activeRequestContext ??
      (runId ? this.activeByRun.get(runId) : undefined) ?? {
        requestId: requestId || randomUUID(),
        clientId: effectiveClientId,
        ownerId,
        adapterId: this.defaultAdapterId,
        sessionId: message.sessionId,
        runId,
        attemptId: message.attemptId,
      };

    if (!runId) {
      const cancelAck = {
        type: "cancel_ack" as const,
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      };
      this.send(this.withCorrelation(cancelAck, context));
      return;
    }

    let cancellationOwnerId: string;
    try {
      cancellationOwnerId = this.kernel.getRun({ runId }).session.ownerId;
    } catch {
      const cancelAck = {
        type: "cancel_ack" as const,
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      };
      this.send(this.withCorrelation(cancelAck, context));
      return;
    }
    if (cancellationOwnerId !== ownerId || (activeRequestContext && activeRequestContext.ownerId !== ownerId)) {
      const cancelAck = {
        type: "cancel_ack" as const,
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      };
      this.send(this.withCorrelation(cancelAck, context));
      return;
    }
    let ack: Awaited<ReturnType<AgentRuntimeKernel["cancelRun"]>>;
    try {
      ack = await this.kernel.cancelRun(runId, { ownerId: cancellationOwnerId });
      context.runId = ack.runId;
      context.attemptId = ack.attemptId ?? context.attemptId;
    } catch (error) {
      this.log(`Jsonl transport interrupt error: ${error instanceof Error ? error.message : String(error)}`);
      ack = {
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        runId,
      };
    }
    const cancelAck = {
      type: "cancel_ack" as const,
      accepted: ack.accepted,
      dispatchAttempted: ack.dispatchAttempted,
      adapterAcknowledged: ack.adapterAcknowledged,
    };
    this.send(this.withCorrelation(cancelAck, context));
  }

  handleWarmup(message: WarmupMessage): void {
    const ownerId = this.requireActiveOwner(message.ownerId);
    const profile = this.kernel.sessionExecutionProfile(message.sessionId, ownerId);
    if (profile.generation !== message.profileGeneration) {
      throw new Error("Warmup profileGeneration does not match the pinned session profile");
    }
    this.log(`Validated warmup for session ${message.sessionId} profile ${profile.generation}`);
  }

  handleInvalidateSession(message: InvalidateSessionMessage): void {
    const ownerId = this.requireActiveOwner(message.ownerId);
    const result = this.kernel.invalidateBindings({
      ownerId,
      surfaceKind: message.surfaceKind,
      externalRefKind: message.externalRefKind,
      externalRefId: message.externalRefId,
      defaultAdapterId: this.defaultAdapterId,
      adapterId: this.defaultAdapterId,
      reason: "jsonl_invalidate_session",
    });
    this.log(
      `Invalidated ${result.invalidatedBindingIds.length} binding(s) for surface ${message.surfaceKind}/${message.externalRefKind}/${message.externalRefId}`,
    );
  }

  private buildRunInput(message: QueryMessage): ExecuteAgentRunInput {
    const unknownField = Object.keys(message).find((field) => !QUERY_WIRE_FIELDS.has(field));
    if (unknownField) {
      throw new Error(`query_wire_field_not_allowed:${unknownField}`);
    }
    const requestId = message.requestId.trim();
    if (!requestId) {
      throw new Error("query requires requestId");
    }
    const clientId = message.clientId.trim();
    if (!clientId) {
      throw new Error("query requires clientId");
    }
    const ownerId = this.requireActiveOwner(message.ownerId);
    const sessionId = message.sessionId.trim();
    if (!sessionId) throw new Error("query requires sessionId");
    const producingTurnId = message.producingTurnId?.trim();
    if (message.producingTurnId !== undefined && !producingTurnId) {
      throw new Error("query producingTurnId must not be empty");
    }
    const session = this.kernel.ownedSession(sessionId, ownerId);
    const surfaceKind = session.surfaceKind;
    if (!surfaceKind) throw new Error("canonical session requires surfaceKind");
    const profile = this.kernel.sessionExecutionProfile(sessionId, ownerId);
    const snapshot = this.kernel.contextSnapshot(sessionId, ownerId, surfaceKind);
    const expectationCount = [
      message.expectedContextSnapshotVersion,
      message.expectedContextSnapshotGeneration,
      message.expectedContextRendererFingerprint,
      message.expectedCapabilityVersion,
    ].filter((value) => value !== undefined).length;
    if (expectationCount !== 0 && expectationCount !== 4) {
      throw new Error("query context freshness requires version, generation, renderer, and capability");
    }
    if (
      expectationCount === 4
      && (
        message.expectedContextSnapshotVersion !== snapshot.version
        || message.expectedContextSnapshotGeneration !== snapshot.snapshotGeneration
        || message.expectedContextRendererFingerprint !== snapshot.rendererFingerprint
        || message.expectedCapabilityVersion !== snapshot.capabilityVersion
      )
    ) {
      throw new Error("context_snapshot_projection_mismatch");
    }
    const mode = message.mode ?? "act";
    const cwd = profile.workingDirectory || session.defaultCwd || this.defaultCwd();
    const executionRole = session.executionRole;

    return {
      ownerId,
      sessionId,
      surfaceKind,
      executionRole,
      externalRefKind: session.externalRefKind ?? undefined,
      externalRefId: session.externalRefId ?? undefined,
      defaultAdapterId: profile.adapterId,
      adapterId: profile.adapterId,
      clientId,
      requestId,
      producingTurnId,
      prompt: message.prompt,
      promptBlocks: this.promptBlocks(message),
      systemPrompt: kernelSystemPolicy(surfaceKind, executionRole, snapshot.contextPlan),
      systemPromptCacheIdentity: snapshot.contextPlan.stableCacheIdentity,
      dynamicContextIdentity: snapshot.contextPlan.dynamicContextIdentity,
      contextPlanId: snapshot.contextPlan.planId,
      admittedContextSnapshot: snapshot,
      mode,
      cwd,
      model: profile.modelProfile ?? undefined,
      mcpServers: this.buildMcpServers?.(mode, cwd, sessionId, {
        ownerId,
        requestId,
        clientId,
        protocolVersion: PROTOCOL_VERSION,
        sessionId,
        adapterId: profile.adapterId,
        executionRole,
      }),
      maxAttempts: this.maxRecoverableRetries > 0 ? this.maxRecoverableRetries + 1 : undefined,
      recoverAfterError: this.recoverAfterError(profile.adapterId),
      imagePresent: Boolean(message.imageBase64),
      attachments: message.attachments,
      expectedContextSnapshotVersion: message.expectedContextSnapshotVersion,
      expectedContextSnapshotGeneration: message.expectedContextSnapshotGeneration,
      expectedContextRendererFingerprint: message.expectedContextRendererFingerprint,
      expectedCapabilityVersion: message.expectedCapabilityVersion,
      metadata: {
        protocolVersion: PROTOCOL_VERSION,
        source: "jsonl_transport",
        contextSnapshotVersion: snapshot.version,
        contextSnapshotGeneration: snapshot.snapshotGeneration,
        contextRendererFingerprint: snapshot.rendererFingerprint,
        contextCapabilityVersion: snapshot.capabilityVersion,
      },
    };
  }

  private promptBlocks(message: QueryMessage): PromptBlock[] {
    const blocks: PromptBlock[] = [];
    if (message.imageBase64) {
      blocks.push({
        type: "image",
        data: message.imageBase64,
        mimeType: detectImageMimeType(message.imageBase64),
      });
    }
    blocks.push({ type: "text", text: message.prompt });
    return blocks;
  }

  private handleKernelEvent(event: AgentEvent): void {
    if (!event.runId) return;
    const payload = parsePayload(event.payloadJson);
    if (event.type === "run.queued") {
      const requestId = typeof payload.requestId === "string" ? payload.requestId : undefined;
      const clientId = typeof payload.clientId === "string" ? payload.clientId : undefined;
      const context =
        requestId && clientId
          ? this.activeByRequest.get(this.activeRequestKey(requestId, clientId))
          : undefined;
      if (context) {
        context.sessionId = event.sessionId;
        context.runId = event.runId;
        this.activeByRun.set(event.runId, context);
        this.latestRunByClient.set(this.latestRunByClientKey(context.ownerId, context.clientId), event.runId);
        this.latestRunByOwner.set(context.ownerId, event.runId);
      }
      return;
    }

    const context = this.activeByRun.get(event.runId);
    if (!context) return;
    if (event.attemptId) {
      context.attemptId = event.attemptId;
    }
    if (event.type === "attempt.started" || event.type === "run.running") {
      context.isRunning = true;
    }
    if (
      event.type.startsWith("run.") &&
      TERMINAL_RUN_EVENT_STATUSES.has(event.type.slice("run.".length))
    ) {
      context.isRunning = false;
      this.activeByRun.delete(event.runId);
      this.activeByRequest.delete(this.activeRequestKey(context.requestId, context.clientId));
      const clientKey = this.latestRunByClientKey(context.ownerId, context.clientId);
      if (this.latestRunByClient.get(clientKey) === event.runId) {
        this.latestRunByClient.delete(clientKey);
      }
      if (this.latestRunByOwner.get(context.ownerId) === event.runId) {
        this.latestRunByOwner.delete(context.ownerId);
      }
    }
    if (context.revoked) return;
    if (!isAdapterPayloadEvent(event.type)) return;

    const adapterEvent = payload as Partial<OutboundMessage> & { adapterSessionId?: string };
    const type = typeof adapterEvent.type === "string" ? adapterEvent.type : undefined;
    if (!type) return;
    context.adapterSessionId = adapterEvent.adapterSessionId ?? context.adapterSessionId;

    switch (type) {
      case "text_delta":
      case "tool_activity":
      case "tool_result_display":
      case "thinking_delta":
      case "error":
        this.send(this.withCorrelation({
          ...adapterEvent,
          type,
        } as OutboundMessage & QueryScopedOutbound, {
          ...context,
          eventId: event.eventId,
          sessionId: event.sessionId,
          runId: event.runId,
          attemptId: event.attemptId ?? context.attemptId,
        }));
        break;
      case "tool_use":
        if (!this.suppressToolUseEvents && context.adapterId !== "pi-mono") {
          this.send(this.withCorrelation({
            ...adapterEvent,
            type,
          } as OutboundMessage & QueryScopedOutbound, {
            ...context,
            eventId: event.eventId,
            sessionId: event.sessionId,
            runId: event.runId,
            attemptId: event.attemptId ?? context.attemptId,
          }));
        }
        break;
      default:
        this.log(`Ignoring unmapped adapter event type: ${type}`);
    }
  }

  private withCorrelation<T extends OutboundMessageDraft & Partial<QueryScopedOutbound>>(
    message: T,
    context: ActiveRequestContext & { eventId?: string }
  ): T {
    return {
      ...message,
      protocolVersion: PROTOCOL_VERSION,
      requestId: context.requestId,
      clientId: context.clientId,
      ...(context.sessionId ?? message.sessionId ? { sessionId: context.sessionId ?? message.sessionId } : {}),
      ...(context.runId ? { runId: context.runId } : {}),
      ...(context.attemptId ? { attemptId: context.attemptId } : {}),
      ...(context.eventId ? { eventId: context.eventId } : {}),
      ...(context.adapterSessionId ?? message.adapterSessionId
        ? { adapterSessionId: context.adapterSessionId ?? message.adapterSessionId }
        : {}),
    };
  }

  private latestRunByClientKey(ownerId: string, clientId: string): string {
    return JSON.stringify([ownerId, clientId]);
  }

  private requireActiveOwner(requestedOwnerId: string | undefined): string {
    const activeOwnerId = this.activeOwnerId();
    const requested = requestedOwnerId?.trim() || activeOwnerId;
    if (!requested || requested !== activeOwnerId) {
      throw new Error("owner_mismatch: transport mutation owner is not active");
    }
    return requested;
  }

  private activeRequestKey(requestId: string, clientId: string): string {
    return JSON.stringify([clientId, requestId]);
  }

  private recoverAfterError(adapterId: string): ExecuteAgentRunInput["recoverAfterError"] | undefined {
    if (!this.isRecoverableError || !this.onRecoverableError || this.maxRecoverableRetries === 0) {
      return undefined;
    }
    let recoveries = 0;
    return async (error) => {
      if (recoveries >= this.maxRecoverableRetries || !this.isRecoverableError?.(error, adapterId)) {
        return false;
      }
      recoveries += 1;
      await this.onRecoverableError?.(error, adapterId);
      return true;
    };
  }
}

function failureFromResultJson(resultJson: string | null): RuntimeFailure | undefined {
  if (!resultJson) return undefined;
  try {
    const parsed = JSON.parse(resultJson) as { failure?: RuntimeFailure };
    if (parsed.failure?.code && parsed.failure.userMessage) {
      return normalizeRuntimeFailure(parsed.failure);
    }
  } catch {
    return undefined;
  }
  return undefined;
}

function boundedTerminalFailure(result: Awaited<ReturnType<AgentRuntimeKernel["executeRun"]>>): RuntimeFailure | undefined {
  if (result.terminalStatus === "succeeded") return undefined;
  const persisted = failureFromResultJson(result.run.resultJson);
  const fallbackCode = result.terminalStatus === "cancelled" ? "run_cancelled" : "runtime_run_failed";
  const rawCode = persisted?.code ?? result.run.errorCode ?? fallbackCode;
  const code = /^[a-z0-9_.:-]{1,64}$/i.test(rawCode) ? rawCode : fallbackCode;
  const fallbackMessage = result.terminalStatus === "cancelled" ? "Agent run was cancelled." : "Agent run failed.";
  const userMessage = sanitizeProcessDiagnostic(
    persisted?.userMessage ?? result.run.errorMessage ?? fallbackMessage,
  ) || fallbackMessage;
  return normalizeRuntimeFailure({
    code,
    failureCode: persisted?.failureCode,
    userMessage,
    technicalMessage: persisted?.technicalMessage,
    source: persisted?.source ?? "runtime",
    adapterId: persisted?.adapterId,
    provider: persisted?.provider,
    retryable: persisted?.retryable ?? false,
  });
}

function parsePayload(payloadJson: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(payloadJson) as unknown;
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function isAdapterPayloadEvent(type: string): boolean {
  return type === "message.delta" ||
    type === "progress.updated" ||
    type === "tool.started" ||
    type === "tool.updated" ||
    type === "tool.completed" ||
    type === "tool.failed";
}
