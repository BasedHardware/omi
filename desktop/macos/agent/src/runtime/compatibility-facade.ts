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
import type { AgentEvent, RunMode } from "./types.js";
import { AgentRuntimeKernel, type ExecuteAgentRunInput } from "./kernel.js";

export type CompatibilitySend = (message: OutboundMessage) => void;
export type CompatibilityLog = (message: string) => void;
export type McpServerBuilder = (mode: RunMode, cwd: string, sessionKey?: string) => Record<string, unknown>[];
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
}

interface WarmupHint {
  cwd?: string;
  model?: string;
  systemPrompt?: string;
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
  private readonly warmupHints = new Map<string, WarmupHint>();
  private latestRunId: string | undefined;

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

  async handleQuery(message: QueryMessage): Promise<void> {
    const input = this.buildRunInput(message);
    const context: ActiveRequestContext = {
      protocolVersion: message.protocolVersion,
      requestId: input.requestId,
      clientId: input.clientId,
      ownerId: input.ownerId,
      adapterId: input.adapterId ?? this.defaultAdapterId,
      sessionId: input.sessionId,
      legacyAdapterSessionId: input.legacyAdapterSessionId,
    };
    this.activeByRequest.set(context.requestId, context);

    try {
      const result = await this.kernel.executeRun(input);
      context.sessionId = result.session.sessionId;
      context.runId = result.run.runId;
      context.attemptId = result.attempt.attemptId;
      context.adapterSessionId = result.adapterSessionId ?? undefined;

      if (result.terminalStatus === "failed") {
        const errorMessage: ErrorMessage = {
          type: "error",
          message: result.run.errorMessage ?? "Agent run failed",
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
        costUsd: result.run.costUsd ?? 0,
        inputTokens: result.run.inputTokens ?? Math.ceil(input.prompt.length / 4),
        outputTokens: result.run.outputTokens ?? Math.ceil(result.text.length / 4),
        cacheReadTokens: result.run.cacheReadTokens ?? 0,
        cacheWriteTokens: result.run.cacheWriteTokens ?? 0,
      };
      this.send(this.withCorrelation(resultMessage, context));
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      this.log(`Compatibility query error: ${messageText}`);
      const errorMessage: ErrorMessage = { type: "error", message: messageText };
      this.send(this.withCorrelation(errorMessage, context));
    } finally {
      this.activeByRequest.delete(context.requestId);
      if (context.runId) {
        this.activeByRun.delete(context.runId);
        if (this.latestRunByClient.get(context.clientId) === context.runId) {
          this.latestRunByClient.delete(context.clientId);
        }
        if (this.latestRunId === context.runId) {
          this.latestRunId = undefined;
        }
      }
    }
  }

  async handleInterrupt(message: { protocolVersion?: ProtocolVersion; requestId?: string; id?: string; clientId?: string; ownerId?: string; sessionId?: string; runId?: string; attemptId?: string }): Promise<void> {
    const requestId = requestIdFor(message);
    const clientId = message.clientId ?? this.defaultClientId;
    const runId =
      message.runId ??
      (requestId ? this.activeByRequest.get(requestId)?.runId : undefined) ??
      this.latestRunByClient.get(clientId) ??
      this.latestRunId;
    const context =
      (requestId ? this.activeByRequest.get(requestId) : undefined) ??
      (runId ? this.activeByRun.get(runId) : undefined) ?? {
        protocolVersion: message.protocolVersion,
        requestId: requestId ?? randomUUID(),
        clientId,
        ownerId: message.ownerId ?? this.ownerId,
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

    const ack = await this.kernel.cancelRun(runId);
    context.runId = ack.runId;
    context.attemptId = ack.attemptId ?? context.attemptId;
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
    const requestId = requestIdFor(message) ?? randomUUID();
    const clientId = message.clientId ?? this.defaultClientId;
    const mode = message.mode ?? "act";
    const requestedModel = message.model ?? this.defaultModel();
    const legacySessionKey = message.legacySessionKey ?? message.sessionKey ?? requestedModel;
    const hint = legacySessionKey ? this.warmupHints.get(legacySessionKey) : undefined;
    const cwd = message.cwd ?? hint?.cwd ?? this.defaultCwd();

    return {
      ownerId: message.ownerId ?? this.ownerId,
      sessionId: message.protocolVersion === 2 ? message.sessionId : undefined,
      surfaceKind: message.surfaceKind ?? "legacy_jsonl",
      externalRefKind: message.externalRefKind,
      externalRefId: message.externalRefId,
      legacyClientScope: this.legacyClientScope(message),
      legacySessionKey,
      defaultAdapterId: message.adapterId ?? this.defaultAdapterId,
      adapterId: message.adapterId ?? this.defaultAdapterId,
      clientId,
      requestId,
      prompt: message.prompt,
      promptBlocks: this.promptBlocks(message),
      systemPrompt: message.systemPrompt || hint?.systemPrompt,
      mode,
      cwd,
      model: message.model ?? hint?.model ?? requestedModel,
      mcpServers: this.buildMcpServers?.(mode, cwd, legacySessionKey),
      legacyAdapterSessionId: message.legacyAdapterSessionId ?? message.resume,
      maxAttempts: this.maxRecoverableRetries > 0 ? this.maxRecoverableRetries + 1 : undefined,
      recoverAfterError: this.recoverAfterError(),
      metadata: {
        protocolVersion: message.protocolVersion ?? 1,
        source: "jsonl_compatibility_facade",
      },
    };
  }

  unscopedToolCallCorrelation(): Partial<QueryScopedOutbound> {
    if (this.activeByRequest.size !== 1) return {};
    const context = this.activeByRequest.values().next().value as ActiveRequestContext | undefined;
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
    if (event.type === "run.created") {
      const requestId = typeof payload.requestId === "string" ? payload.requestId : undefined;
      const context = requestId ? this.activeByRequest.get(requestId) : undefined;
      if (context) {
        context.sessionId = event.sessionId;
        context.runId = event.runId;
        this.activeByRun.set(event.runId, context);
        this.latestRunByClient.set(context.clientId, event.runId);
        this.latestRunId = event.runId;
      }
      return;
    }

    const context = this.activeByRun.get(event.runId);
    if (!context) return;
    if (event.attemptId) {
      context.attemptId = event.attemptId;
    }
    if (!event.type.startsWith("adapter.")) return;

    const adapterEvent = payload as Partial<OutboundMessage> & { sessionId?: string; adapterSessionId?: string };
    const type = event.type.slice("adapter.".length);
    context.adapterSessionId = adapterEvent.adapterSessionId ?? adapterEvent.sessionId ?? context.adapterSessionId;

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

  private warmupSessions(message: WarmupMessage): WarmupSessionConfig[] {
    if (message.sessions && message.sessions.length > 0) {
      return message.sessions;
    }
    const models = message.models ?? (message.model ? [message.model] : [this.defaultModel()]);
    return models.map((model) => ({ key: model, model }));
  }

  private legacyClientScope(message: QueryMessage | undefined): string {
    return message?.legacyClientScope ?? "default";
  }

  private defaultModel(): string {
    return this.defaultAdapterId === "pi-mono" ? "omi-sonnet" : "claude-sonnet-4-6";
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

function parsePayload(payloadJson: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(payloadJson) as unknown;
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}
