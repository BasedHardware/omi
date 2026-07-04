import { randomUUID } from "node:crypto";
import type { PromptBlock, ToolDef } from "../adapters/interface.js";
import { detectImageMimeType } from "../mime-detect.js";
import type {
  CancelAckMessage,
  ErrorMessage,
  InvalidateSessionMessage,
  OutboundMessage,
  ProtocolVersion,
  QueryMessage,
  QueryScopedOutbound,
  ResultMessage,
  WarmupMessage,
  WarmupSessionConfig,
} from "../protocol.js";
import { requestIdFor } from "../protocol.js";
import { serializeArtifact } from "./artifact-serialization.js";
import type { RuntimeFailure } from "./failures.js";
import type { AgentEvent, RunMode } from "./types.js";
import { AgentRuntimeKernel, type ExecuteAgentRunInput } from "./kernel.js";

export type CompatibilitySend = (message: OutboundMessage) => void;
export type CompatibilityLog = (message: string) => void;
export interface McpServerBuildContext {
  ownerId: string;
  requestId: string;
  clientId: string;
  protocolVersion?: ProtocolVersion;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  adapterId?: string;
  includeSwiftBackedTools?: boolean;
}
export type McpServerBuilder = (
  mode: RunMode,
  cwd: string,
  sessionKey: string | undefined,
  context: McpServerBuildContext
) => Record<string, unknown>[];
export type RecoverableErrorPredicate = (error: unknown) => boolean;
export type RecoverableErrorHandler = (error: unknown) => Promise<void>;

export interface CompatibilityFacadeOptions {
  kernel: AgentRuntimeKernel;
  send: CompatibilitySend;
  log?: CompatibilityLog;
  ownerId?: string;
  defaultAdapterId?: string;
  defaultClientId?: string;
  defaultCwd?: () => string;
  buildMcpServers?: McpServerBuilder;
  suppressToolUseEvents?: boolean;
  isRecoverableError?: RecoverableErrorPredicate;
  onRecoverableError?: RecoverableErrorHandler;
  maxRecoverableRetries?: number;
}

interface ActiveRequestContext {
  protocolVersion?: ProtocolVersion;
  requestId: string;
  clientId: string;
  ownerId: string;
  adapterId: string;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  adapterSessionId?: string;
  legacyAdapterSessionId?: string;
  isRunning?: boolean;
}

export interface UnscopedToolCallContext {
  protocolVersion?: ProtocolVersion;
  requestId: string;
  clientId: string;
  adapterId?: string;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  adapterSessionId?: string;
  legacyAdapterSessionId?: string;
  isRunning?: boolean;
}

export interface ExternalRequestContextInput {
  protocolVersion?: ProtocolVersion;
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
  let selected: UnscopedToolCallContext | undefined;
  if (runningContexts.length > 0) {
    if (runningContexts.length === 1 && runningContexts[0].protocolVersion === 2) {
      selected = runningContexts[0];
    }
  } else if (allContexts.length === 1 && allContexts[0].protocolVersion === 2) {
    selected = allContexts[0];
  }
  if (!selected) return {};
  return {
    protocolVersion: 2,
    requestId: selected.requestId,
    clientId: selected.clientId,
    sessionId: selected.sessionId,
    runId: selected.runId,
    attemptId: selected.attemptId,
    adapterSessionId: selected.adapterSessionId,
    legacyAdapterSessionId: selected.legacyAdapterSessionId,
  };
}

export function selectAdapterScopedToolCallCorrelation(
  contexts: Iterable<UnscopedToolCallContext>,
  adapterId: string
): Partial<QueryScopedOutbound> {
  const runningContexts = Array.from(contexts).filter(
    (context) => context.isRunning && context.adapterId === adapterId && context.protocolVersion === 2
  );
  return runningContexts.length === 1 ? selectUnscopedToolCallCorrelation(runningContexts) : {};
}

export class JsonlCompatibilityFacade {
  private readonly kernel: AgentRuntimeKernel;
  private readonly send: CompatibilitySend;
  private readonly log: CompatibilityLog;
  private readonly ownerId: string;
  private readonly defaultAdapterId: string;
  private readonly defaultClientId: string;
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

  constructor(options: CompatibilityFacadeOptions) {
    this.kernel = options.kernel;
    this.send = options.send;
    this.log = options.log ?? (() => {});
    this.ownerId = options.ownerId ?? "desktop-local-user";
    this.defaultAdapterId = options.defaultAdapterId ?? "acp";
    this.defaultClientId = options.defaultClientId ?? "legacy-jsonl-client";
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
      protocolVersion: input.protocolVersion,
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
      protocolVersion: message.protocolVersion,
      requestId: input.requestId,
      clientId: input.clientId,
      ownerId: input.ownerId,
      adapterId: input.adapterId ?? this.defaultAdapterId,
      sessionId: input.sessionId,
      legacyAdapterSessionId: input.legacyAdapterSessionId,
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
        const message = failure?.userMessage ?? result.run.errorMessage ?? "Agent run failed";
        const errorMessage: ErrorMessage = {
          type: "error",
          message,
          failure,
        };
        this.send(this.withCorrelation(errorMessage, context));
        return;
      }

      const resultMessage: ResultMessage = {
        type: "result",
        text: result.text,
        sessionId: this.compatibilityResultSessionId(context, result.session.sessionId),
        adapterSessionId: result.adapterSessionId ?? undefined,
        terminalStatus: result.terminalStatus,
        failure: failureFromResultJson(result.run.resultJson),
        costUsd: result.run.costUsd ?? 0,
        inputTokens: result.run.inputTokens ?? Math.ceil(input.prompt.length / 4),
        outputTokens: result.run.outputTokens ?? Math.ceil(result.text.length / 4),
        cacheReadTokens: result.run.cacheReadTokens ?? 0,
        cacheWriteTokens: result.run.cacheWriteTokens ?? 0,
        artifacts: result.artifacts.map(serializeArtifact),
      };
      this.send(this.withCorrelation(resultMessage, context));
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      this.log(`Compatibility query error: ${messageText}`);
      const errorMessage: ErrorMessage = { type: "error", message: messageText };
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

  async handleInterrupt(message: { protocolVersion?: ProtocolVersion; requestId?: string; id?: string; clientId?: string; ownerId?: string; sessionId?: string; runId?: string; attemptId?: string }): Promise<void> {
    const requestId = message.protocolVersion === 2 ? message.requestId?.trim() : requestIdFor(message);
    const clientId = message.protocolVersion === 2 ? message.clientId : message.clientId ?? this.defaultClientId;
    const explicitRunId = message.runId?.trim();
    if (message.protocolVersion === 2 && !clientId?.trim() && !explicitRunId) {
      this.send({
        type: "cancel_ack",
        protocolVersion: 2,
        ...(requestId ? { requestId } : {}),
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      } as CancelAckMessage & { protocolVersion: 2; requestId?: string });
      return;
    }
    if (message.protocolVersion === 2 && !requestId?.trim() && !explicitRunId) {
      this.send({
        type: "cancel_ack",
        protocolVersion: 2,
        clientId,
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      } as CancelAckMessage & { protocolVersion: 2; clientId: string });
      return;
    }
    const effectiveClientId = clientId ?? this.defaultClientId;
    const hasExplicitClientId = message.clientId !== undefined;
    const activeRequestContext = requestId
      ? (hasExplicitClientId
        ? this.activeByRequest.get(this.activeRequestKey(requestId, effectiveClientId))
        : message.protocolVersion === 2
          ? undefined
          : this.legacyUnscopedActiveRequestContext(requestId))
      : undefined;
    const ownerId = message.ownerId ?? activeRequestContext?.ownerId ?? this.ownerId;
    if (message.protocolVersion === 2 && explicitRunId && !activeRequestContext && !message.ownerId?.trim()) {
      const cancelAck: CancelAckMessage = {
        type: "cancel_ack",
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      };
      this.send(this.withCorrelation(cancelAck, {
        protocolVersion: message.protocolVersion,
        requestId: requestId ?? randomUUID(),
        clientId: effectiveClientId,
        ownerId,
        adapterId: this.defaultAdapterId,
        runId: explicitRunId,
        sessionId: message.sessionId,
        attemptId: message.attemptId,
      }));
      return;
    }
    if (message.protocolVersion === 2 && requestId && !activeRequestContext && !message.runId && !message.attemptId) {
      const cancelAck: CancelAckMessage = {
        type: "cancel_ack",
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
      };
      this.send(this.withCorrelation(cancelAck, {
        protocolVersion: message.protocolVersion,
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
        protocolVersion: message.protocolVersion,
        requestId: requestId ?? randomUUID(),
        clientId: effectiveClientId,
        ownerId,
        adapterId: this.defaultAdapterId,
        sessionId: message.sessionId,
        runId,
        attemptId: message.attemptId,
      };

    if (!runId) {
      if (message.protocolVersion === 2) {
        const cancelAck: CancelAckMessage = {
          type: "cancel_ack",
          accepted: false,
          dispatchAttempted: false,
          adapterAcknowledged: false,
        };
        this.send(this.withCorrelation(cancelAck, context));
      }
      return;
    }

    const cancellationOwnerId = message.ownerId ?? activeRequestContext?.ownerId ?? context.ownerId ?? ownerId;
    let ack: Awaited<ReturnType<AgentRuntimeKernel["cancelRun"]>>;
    try {
      ack = await this.kernel.cancelRun(runId, { ownerId: cancellationOwnerId });
      context.runId = ack.runId;
      context.attemptId = ack.attemptId ?? context.attemptId;
    } catch (error) {
      this.log(`Compatibility interrupt error: ${error instanceof Error ? error.message : String(error)}`);
      ack = {
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        runId,
      };
    }
    if (message.protocolVersion === 2) {
      const cancelAck: CancelAckMessage = {
        type: "cancel_ack",
        accepted: ack.accepted,
        dispatchAttempted: ack.dispatchAttempted,
        adapterAcknowledged: ack.adapterAcknowledged,
      };
      this.send(this.withCorrelation(cancelAck, context));
    }
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
    const legacySessionKey = message.sessionKey;
    const result = this.kernel.invalidateBindings({
      ownerId: message.ownerId ?? this.ownerId,
      surfaceKind: "legacy_jsonl",
      legacyClientScope: this.legacyClientScope(undefined),
      legacySessionKey,
      defaultAdapterId: this.defaultAdapterId,
      adapterId: this.defaultAdapterId,
      reason: "jsonl_invalidate_session",
    });
    this.warmupHints.delete(legacySessionKey);
    this.log(
      `Invalidated ${result.invalidatedBindingIds.length} binding(s) for legacy session key ${legacySessionKey}`
    );
  }

  private buildRunInput(message: QueryMessage): ExecuteAgentRunInput {
    const suppliedRequestId = message.protocolVersion === 2 ? message.requestId : requestIdFor(message);
    if (message.protocolVersion === 2 && !suppliedRequestId?.trim()) {
      throw new Error("protocol v2 query requires requestId");
    }
    const requestId = suppliedRequestId?.trim() || randomUUID();
    if (message.protocolVersion === 2 && !message.clientId?.trim()) {
      throw new Error("protocol v2 query requires clientId");
    }
    const clientId = message.clientId ?? this.defaultClientId;
    const mode = message.mode ?? "act";
    const requestedAdapterId = message.adapterId ?? this.defaultAdapterId;
    const requestedModel = message.model ?? this.defaultModel(requestedAdapterId);
    const legacySessionKey = message.legacySessionKey ?? message.sessionKey ?? requestedModel;
    const hint = legacySessionKey ? this.warmupHints.get(legacySessionKey) : undefined;
    const cwd = message.cwd ?? hint?.cwd ?? this.defaultCwd();

    const ownerId = message.ownerId ?? this.ownerId;
    const sessionId = message.protocolVersion === 2 ? message.sessionId : undefined;

    return {
      ownerId,
      sessionId,
      surfaceKind: message.surfaceKind ?? "legacy_jsonl",
      externalRefKind: message.externalRefKind,
      externalRefId: message.externalRefId,
      legacyClientScope: legacySessionKey ? this.legacyClientScope(message) : undefined,
      legacySessionKey,
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
      mcpServers: this.buildMcpServers?.(mode, cwd, legacySessionKey, {
        ownerId,
        requestId,
        clientId,
        protocolVersion: message.protocolVersion,
        sessionId,
        adapterId: requestedAdapterId,
      }),
      legacyAdapterSessionId: message.legacyAdapterSessionId ?? message.resume,
      maxAttempts: this.maxRecoverableRetries > 0 ? this.maxRecoverableRetries + 1 : undefined,
      recoverAfterError: this.recoverAfterError(),
      metadata: {
        protocolVersion: message.protocolVersion ?? 1,
        legacyAdapterSessionId: message.legacyAdapterSessionId ?? message.resume,
        source: "jsonl_compatibility_facade",
      },
    };
  }

  unscopedToolCallCorrelation(): Partial<QueryScopedOutbound> {
    return selectUnscopedToolCallCorrelation(this.activeByRequest.values());
  }

  toolCallCorrelationForRequest(requestId: string, clientId: string): Partial<QueryScopedOutbound> {
    const context = this.activeByRequest.get(this.activeRequestKey(requestId, clientId));
    return context ? this.toolCallCorrelationForContext(context) : {};
  }

  legacyUnscopedToolCallCorrelationForRequest(requestId: string): Partial<QueryScopedOutbound> {
    const context = this.legacyUnscopedActiveRequestContext(requestId);
    return context ? this.toolCallCorrelationForContext(context) : {};
  }

  private toolCallCorrelationForContext(context: ActiveRequestContext): Partial<QueryScopedOutbound> {
    if (!context || context.protocolVersion !== 2) return {};
    return {
      protocolVersion: 2,
      requestId: context.requestId,
      clientId: context.clientId,
      sessionId: context.sessionId,
      runId: context.runId,
      attemptId: context.attemptId,
      adapterSessionId: context.adapterSessionId,
      legacyAdapterSessionId: context.legacyAdapterSessionId,
    };
  }

  toolCallCorrelationForAdapter(adapterId: string): Partial<QueryScopedOutbound> {
    return selectAdapterScopedToolCallCorrelation(this.activeByRequest.values(), adapterId);
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
          : requestId && payload.protocolVersion !== 2
            ? this.legacyUnscopedActiveRequestContext(requestId)
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

  private withCorrelation<T extends OutboundMessage & QueryScopedOutbound>(
    message: T,
    context: ActiveRequestContext & { eventId?: string }
  ): T {
    if (context.protocolVersion !== 2) {
      return message;
    }
    return {
      ...message,
      protocolVersion: 2,
      requestId: context.requestId,
      clientId: context.clientId,
      sessionId: context.sessionId ?? message.sessionId,
      runId: context.runId,
      attemptId: context.attemptId,
      eventId: context.eventId,
      adapterSessionId: context.adapterSessionId ?? message.adapterSessionId,
      legacyAdapterSessionId: context.legacyAdapterSessionId,
    };
  }

  private compatibilityResultSessionId(context: ActiveRequestContext, canonicalSessionId: string): string {
    if (context.protocolVersion === 2) {
      return canonicalSessionId;
    }
    return context.adapterSessionId ?? context.legacyAdapterSessionId ?? canonicalSessionId;
  }

  private latestRunByClientKey(ownerId: string, clientId: string): string {
    return JSON.stringify([ownerId, clientId]);
  }

  private activeRequestKey(requestId: string, clientId: string): string {
    return JSON.stringify([clientId, requestId]);
  }

  private legacyUnscopedActiveRequestContext(requestId: string): ActiveRequestContext | undefined {
    const contexts = [...this.activeByRequest.values()].filter((context) => context.requestId === requestId);
    return contexts.length === 1 ? contexts[0] : undefined;
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

  private legacyClientScope(message: QueryMessage | undefined): string {
    return message?.legacyClientScope ?? "default";
  }

  private defaultModel(adapterId = this.defaultAdapterId): string | undefined {
    if (adapterId === "pi-mono") return "omi-sonnet";
    if (adapterId === "acp") return "claude-sonnet-4-6";
    return undefined;
  }

  private recoverAfterError(): ExecuteAgentRunInput["recoverAfterError"] | undefined {
    if (!this.isRecoverableError || !this.onRecoverableError || this.maxRecoverableRetries === 0) {
      return undefined;
    }
    let recoveries = 0;
    return async (error) => {
      if (recoveries >= this.maxRecoverableRetries || !this.isRecoverableError?.(error)) {
        return false;
      }
      recoveries += 1;
      await this.onRecoverableError?.(error);
      return true;
    };
  }
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
