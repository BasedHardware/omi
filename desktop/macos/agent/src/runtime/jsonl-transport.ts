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
  WarmupSessionConfig,
} from "../protocol.js";
import { PROTOCOL_VERSION } from "../protocol.js";
import { serializeArtifact } from "./artifact-serialization.js";
import { failureFromError, type RuntimeFailure } from "./failures.js";
import type { AgentEvent, RunMode } from "./types.js";
import { AgentRuntimeKernel, type ExecuteAgentRunInput } from "./kernel.js";
import { executionRoleForSurface } from "./execution-policy.js";

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
}

export interface UnscopedToolCallContext {
  requestId: string;
  clientId: string;
  adapterId?: string;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  adapterSessionId?: string;
  isRunning?: boolean;
}

export interface ExternalRequestContextInput {
  requestId: string;
  clientId: string;
  ownerId: string;
  adapterId: string;
  sessionId?: string;
}

interface WarmupHint {
  cwd?: string;
  model?: string;
  systemPrompt?: string;
}

const TERMINAL_RUN_EVENT_STATUSES = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
  "orphaned",
]);

export function selectUnscopedToolCallCorrelation(
  contexts: Iterable<UnscopedToolCallContext>
): Partial<QueryScopedOutbound> {
  const allContexts = Array.from(contexts);
  const runningContexts = allContexts.filter((context) => context.isRunning);
  const selected =
    runningContexts.length === 1
      ? runningContexts[0]
      : allContexts.length === 1
        ? allContexts[0]
        : undefined;
  if (!selected) return {};
  return toolCallCorrelationForContext(selected);
}

export function selectAdapterScopedToolCallCorrelation(
  contexts: Iterable<UnscopedToolCallContext>,
  adapterId: string
): Partial<QueryScopedOutbound> {
  const runningContexts = Array.from(contexts).filter(
    (context) => context.isRunning && context.adapterId === adapterId
  );
  return runningContexts.length === 1 ? selectUnscopedToolCallCorrelation(runningContexts) : {};
}

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
  private readonly activeByRequest = new Map<string, ActiveRequestContext>();
  private readonly activeByRun = new Map<string, ActiveRequestContext>();
  private readonly latestRunByClient = new Map<string, string>();
  private readonly latestRunByOwner = new Map<string, string>();
  private readonly warmupHints = new Map<string, WarmupHint>();

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
    this.kernel.subscribe((event) => this.handleKernelEvent(event));
  }

  registerExternalRequestContext(input: ExternalRequestContextInput): void {
    const key = this.activeRequestKey(input.requestId, input.clientId);
    if (this.activeByRequest.has(key)) {
      throw new Error("Request context already active for clientId/requestId");
    }
    const context: ActiveRequestContext = {
      requestId: input.requestId,
      clientId: input.clientId,
      ownerId: input.ownerId,
      adapterId: input.adapterId,
      sessionId: input.sessionId,
    };
    this.activeByRequest.set(key, context);
  }

  releaseExternalRequestContext(requestId: string, clientId: string): void {
    const key = this.activeRequestKey(requestId, clientId);
    const context = this.activeByRequest.get(key);
    if (context && !context.runId) {
      this.activeByRequest.delete(key);
    }
  }

  async handleQuery(message: QueryMessage): Promise<void> {
    const input = this.buildRunInput(message);
    const key = this.activeRequestKey(input.requestId, input.clientId);
    if (this.activeByRequest.has(key)) {
      throw new Error("Request context already active for clientId/requestId");
    }
    const context: ActiveRequestContext = {
      requestId: input.requestId,
      clientId: input.clientId,
      ownerId: input.ownerId,
      adapterId: input.adapterId ?? this.defaultAdapterId,
      sessionId: input.sessionId,
    };
    this.activeByRequest.set(key, context);

    try {
      const result = await this.kernel.executeRun(input);
      context.sessionId = result.session.sessionId;
      context.runId = result.run.runId;
      context.attemptId = result.attempt.attemptId;
      context.adapterSessionId = result.adapterSessionId ?? undefined;

      if (result.terminalStatus === "failed") {
        const failure = failureFromResultJson(result.run.resultJson);
        const messageText = failure?.userMessage ?? result.run.errorMessage ?? "Agent run failed";
        const errorMessage = {
          type: "error" as const,
          message: messageText,
          failure,
        };
        this.send(this.withCorrelation(errorMessage, context));
        return;
      }

      const resultMessage = {
        type: "result" as const,
        text: result.text,
        sessionId: result.session.sessionId,
        adapterSessionId: result.adapterSessionId ?? undefined,
        terminalStatus: result.terminalStatus,
        failure: failureFromResultJson(result.run.resultJson),
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
    const ownerId = message.ownerId ?? activeRequestContext?.ownerId ?? this.ownerId;
    if (explicitRunId && !activeRequestContext && !message.ownerId?.trim()) {
      const cancelAck = {
        type: "cancel_ack" as const,
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      };
      this.send(this.withCorrelation(cancelAck, {
        requestId: requestId || randomUUID(),
        clientId: effectiveClientId,
        ownerId,
        adapterId: this.defaultAdapterId,
        runId: explicitRunId,
        sessionId: message.sessionId,
        attemptId: message.attemptId,
      }));
      return;
    }
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

    const cancellationOwnerId = message.ownerId ?? activeRequestContext?.ownerId ?? context.ownerId ?? ownerId;
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
    const cwd = message.cwd ?? this.defaultCwd();
    const sessions = this.warmupSessions(message);
    for (const session of sessions) {
      this.warmupHints.set(session.key, {
        cwd,
        model: session.model,
        systemPrompt: session.systemPrompt,
      });
    }
    this.log(`Recorded warmup hint(s): ${sessions.map((session) => session.key).join(", ") || "(none)"}`);
  }

  handleInvalidateSession(message: InvalidateSessionMessage): void {
    const result = this.kernel.invalidateBindings({
      ownerId: message.ownerId ?? this.ownerId,
      surfaceKind: message.surfaceKind,
      externalRefKind: message.externalRefKind,
      externalRefId: message.externalRefId,
      defaultAdapterId: this.defaultAdapterId,
      adapterId: this.defaultAdapterId,
      reason: "jsonl_invalidate_session",
    });
    this.warmupHints.delete(surfaceWarmupKey(message.surfaceKind, message.externalRefKind, message.externalRefId));
    this.log(
      `Invalidated ${result.invalidatedBindingIds.length} binding(s) for surface ${message.surfaceKind}/${message.externalRefKind}/${message.externalRefId}`,
    );
  }

  unscopedToolCallCorrelation(): Partial<QueryScopedOutbound> {
    return selectUnscopedToolCallCorrelation(this.activeByRequest.values());
  }

  toolCallCorrelationForRequest(requestId: string, clientId: string): Partial<QueryScopedOutbound> {
    const context = this.activeByRequest.get(this.activeRequestKey(requestId, clientId));
    return context ? toolCallCorrelationForContext(context) : {};
  }

  toolCallCorrelationForAdapter(adapterId: string): Partial<QueryScopedOutbound> {
    return selectAdapterScopedToolCallCorrelation(this.activeByRequest.values(), adapterId);
  }

  private buildRunInput(message: QueryMessage): ExecuteAgentRunInput {
    const requestId = message.requestId.trim();
    if (!requestId) {
      throw new Error("query requires requestId");
    }
    const clientId = message.clientId.trim();
    if (!clientId) {
      throw new Error("query requires clientId");
    }
    const mode = message.mode ?? "act";
    const requestedAdapterId = message.adapterId ?? this.defaultAdapterId;
    const requestedModel = message.model ?? this.defaultModel(requestedAdapterId);
    const warmupKey = surfaceWarmupKey(message.surfaceKind, message.externalRefKind, message.externalRefId);
    const hint = this.warmupHints.get(warmupKey);
    const cwd = message.cwd ?? hint?.cwd ?? this.defaultCwd();
    const ownerId = message.ownerId ?? this.ownerId;
    const executionRole = executionRoleForSurface(message);

    return {
      ownerId,
      sessionId: message.sessionId,
      surfaceKind: message.surfaceKind,
      executionRole,
      externalRefKind: message.externalRefKind,
      externalRefId: message.externalRefId,
      defaultAdapterId: requestedAdapterId,
      adapterId: requestedAdapterId,
      clientId,
      requestId,
      prompt: message.prompt,
      promptBlocks: this.promptBlocks(message),
      systemPrompt: message.systemPrompt || hint?.systemPrompt,
      mode,
      cwd,
      model: message.model ?? hint?.model ?? requestedModel,
      mcpServers: this.buildMcpServers?.(mode, cwd, warmupKey, {
        ownerId,
        requestId,
        clientId,
        protocolVersion: PROTOCOL_VERSION,
        sessionId: message.sessionId,
        adapterId: requestedAdapterId,
        executionRole,
      }),
      maxAttempts: this.maxRecoverableRetries > 0 ? this.maxRecoverableRetries + 1 : undefined,
      recoverAfterError: this.recoverAfterError(requestedAdapterId),
      attachmentMetadataJson: message.attachmentMetadataJson ?? null,
      surfaceContextJson: message.surfaceContextJson ?? null,
      imagePresent: Boolean(message.imageBase64),
      metadata: {
        protocolVersion: PROTOCOL_VERSION,
        source: "jsonl_transport",
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

  private activeRequestKey(requestId: string, clientId: string): string {
    return JSON.stringify([clientId, requestId]);
  }

  private warmupSessions(message: WarmupMessage): WarmupSessionConfig[] {
    if (message.sessions && message.sessions.length > 0) {
      return message.sessions;
    }
    const defaultModel = this.defaultModel();
    const models = message.models ?? (message.model ? [message.model] : defaultModel ? [defaultModel] : []);
    if (models.length === 0) {
      return [{ key: "default" }];
    }
    return models.map((model) => ({ key: model, model }));
  }

  private defaultModel(adapterId = this.defaultAdapterId): string | undefined {
    if (adapterId === "pi-mono") return "omi-sonnet";
    if (adapterId === "acp") return "claude-sonnet-4-6";
    return undefined;
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

function toolCallCorrelationForContext(context: UnscopedToolCallContext): Partial<QueryScopedOutbound> {
  return {
    protocolVersion: PROTOCOL_VERSION,
    requestId: context.requestId,
    clientId: context.clientId,
    sessionId: context.sessionId,
    runId: context.runId,
    attemptId: context.attemptId,
    adapterSessionId: context.adapterSessionId,
  };
}

function surfaceWarmupKey(surfaceKind: string, externalRefKind: string, externalRefId: string): string {
  return `${surfaceKind}|${externalRefKind}|${externalRefId}`;
}

function failureFromResultJson(resultJson: string | null): RuntimeFailure | undefined {
  if (!resultJson) return undefined;
  try {
    const parsed = JSON.parse(resultJson) as { failure?: RuntimeFailure };
    if (parsed.failure?.code && parsed.failure.userMessage) {
      return parsed.failure;
    }
  } catch {
    return undefined;
  }
  return undefined;
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
