// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  normalizeChatGenerationContext,
  type ChatGenerationContextPacket,
  type ChatGenerationContextSource,
} from "./generation-context";
import type {
  ChatAttachmentContentPort,
  ChatGenerationAttachmentDescriptor,
} from "./attachment-content";
import {
  realtimeChatGenerationScheduler,
  readChatGenerationSourceCapability,
  type ChatGenerationProgress,
  type ChatGenerationScheduler,
  type ChatGenerationSource,
  type ChatGenerationSourceRun,
  type ChatGenerationUsage,
} from "./generation-source";
import {
  createAgentRunEventSupervisor,
  type AgentRunEventStore,
  type AgentRunEventSupervisor,
} from "./agent-run-events";
import type {
  ChatGenerationEvent,
  ChatGenerationEventsStore,
  ChatGenerationFrame,
  ChatGenerationTerminalFrame,
} from "../stores/chat-generation-events-store";
import type { ChatGenerationFinalization } from "../stores/chat-generation-finalization";
import type { ChatMessageRecord, ChatMessagesStore, StoredChatMessage } from "../stores/chat-messages-store";

export interface AdmittedChatGeneration {
  readonly accountId: string;
  readonly stored: StoredChatMessage;
  readonly acceptedEvent: ChatGenerationEvent;
  /** Ephemeral request credential used only by the injected context source. */
  readonly bearerToken: string;
}

export interface ChatGenerationSupervisor {
  onAdmitted(input: AdmittedChatGeneration): void;
  cancel(accountId: string, generationId: string): void;
  /** Optional fault-injection seam; production timeouts can adopt this later. */
  timeout?(accountId: string, generationId: string): void;
  recoverInterrupted(): void;
}

export interface ChatGenerationSupervisorDependencies {
  readonly source: ChatGenerationSource;
  readonly context: ChatGenerationContextSource;
  readonly messages: ChatMessagesStore;
  readonly events: ChatGenerationEventsStore;
  readonly finalization: ChatGenerationFinalization;
  readonly attachments: ChatAttachmentContentPort;
  readonly nowEpochMilliseconds: () => number;
  /** Optional virtual/realtime timer seam for provider liveness deadlines. */
  readonly scheduler?: ChatGenerationScheduler;
  /** Omitted for legacy text-only composition; supplied adapters get bounded liveness. */
  readonly liveness?: ChatGenerationLivenessPolicy;
  readonly assistantMessageId: (accountId: string, generationId: string) => string;
  readonly eventId: (
    accountId: string,
    generationId: string,
    kind: string,
    sequence: number,
  ) => string;
  readonly revision: (accountId: string, messageId: string, payloadHash: string) => string;
  /** Optional privacy-safe lifecycle ledger; text-generation remains authoritative. */
  readonly agentRunEvents?: AgentRunEventStore;
}

export interface ChatGenerationLivenessPolicy {
  readonly firstEventDeadlineMs: number;
  readonly maxRunDurationMs: number;
  readonly heartbeatIntervalMs: number;
  readonly cancelGraceMs: number;
}

/** Production-shaped bounded defaults; deterministic scenarios may override explicitly. */
export const DEFAULT_CHAT_GENERATION_LIVENESS: ChatGenerationLivenessPolicy = Object.freeze({
  firstEventDeadlineMs: 100,
  maxRunDurationMs: 1_000,
  heartbeatIntervalMs: 250,
  cancelGraceMs: 100,
});

interface ActiveGeneration {
  readonly accountId: string;
  readonly generationId: string;
  readonly admitted: StoredChatMessage;
  readonly attemptId: string;
  readonly admissionId: string;
  text: string;
  run: ChatGenerationSourceRun | null;
  runCancelled: boolean;
  terminal: boolean;
  failure: ChatGenerationFailure | null;
  providerStartedAt: number | null;
  providerEventSeen: boolean;
  cancelRequested: boolean;
  /** True when this state was reconstructed after a process/service restart. */
  recovered: boolean;
  firstEventTimer: unknown | null;
  maxDurationTimer: unknown | null;
  heartbeatTimer: unknown | null;
  cancelGraceTimer: unknown | null;
  progressPct: number | null;
  usage: ChatGenerationUsage | null;
}

const FALLBACK_TEXT = "I’m sorry, I couldn’t complete that response.";

export type ChatGenerationFailureCode =
  | "generation_provider_failed"
  | "generation_context_failed"
  | "generation_attachment_failed"
  | "generation_interrupted"
  | "generation_timeout";

export interface ChatGenerationFailure {
  readonly code: ChatGenerationFailureCode;
  readonly retryable: boolean;
}

const defaultFailure = (
  stage: "provider" | "context" | "attachment" | "callback" | "timeout",
): ChatGenerationFailure => stage === "context"
  ? { code: "generation_context_failed", retryable: true }
  : stage === "attachment"
    ? { code: "generation_attachment_failed", retryable: true }
    : stage === "callback"
      ? { code: "generation_interrupted", retryable: true }
      : stage === "timeout"
        ? { code: "generation_timeout", retryable: true }
        : { code: "generation_provider_failed", retryable: true };

const validDeadline = (value: unknown, allowZero = false): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && (allowZero ? value >= 0 : value > 0);

const validateLivenessPolicy = (
  policy: ChatGenerationLivenessPolicy | undefined,
): ChatGenerationLivenessPolicy | undefined => {
  if (policy === undefined) return undefined;
  if (!validDeadline(policy.firstEventDeadlineMs)
    || !validDeadline(policy.maxRunDurationMs)
    || !validDeadline(policy.heartbeatIntervalMs, true)
    || !validDeadline(policy.cancelGraceMs, true)
    || policy.firstEventDeadlineMs > policy.maxRunDurationMs
    || policy.firstEventDeadlineMs > 86_400_000
    || policy.maxRunDurationMs > 86_400_000
    || policy.heartbeatIntervalMs > 300_000
    || policy.cancelGraceMs > 300_000) {
    throw new TypeError("invalid Chat generation liveness policy");
  }
  return Object.freeze({ ...policy });
};

const readPlainDataRecord = (value: unknown): Record<string, unknown> | null => {
  try {
    if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) return null;
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const keys = Reflect.ownKeys(value);
    if (keys.some((key) => typeof key !== "string")) return null;
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const record = Object.create(null) as Record<string, unknown>;
    for (const key of keys) {
      const descriptor = descriptors[key as string];
      if (descriptor === undefined || !("value" in descriptor)) return null;
      record[key as string] = descriptor.value;
    }
    return record;
  } catch {
    return null;
  }
};

const validateUsage = (value: unknown): ChatGenerationUsage | null => {
  const usage = readPlainDataRecord(value);
  if (usage === null) return null;
  try {
    if (Object.keys(usage).length !== 6
      || Object.keys(usage).some((key) => !["usageId", "provider", "model", "inputTokens", "outputTokens", "totalTokens"].includes(key))) return null;
    const bounded = (candidate: unknown): candidate is string => {
      if (typeof candidate !== "string" || candidate.length === 0 || candidate.length > 128
        || !/^[A-Za-z0-9._:/-]+$/u.test(candidate)) return false;
      const normalized = candidate.toLowerCase().replace(/[^a-z0-9]/gu, "");
      return !/(?:sk(?:live)?|api(?:key)?|accesstoken|bearer|authorization|password|secret|token|jwt|credential|oauth\d*|attachment(?:id|ref|reference)?|file(?:id|ref|reference)?|opaque(?:id|ref|reference)?|reference(?:id|ref)?)/u.test(normalized);
    };
    const tokens = (candidate: unknown): candidate is number =>
      typeof candidate === "number" && Number.isSafeInteger(candidate) && candidate >= 0;
    if (!bounded(usage.usageId) || !bounded(usage.provider) || !bounded(usage.model)
      || !tokens(usage.inputTokens) || !tokens(usage.outputTokens) || !tokens(usage.totalTokens)
      || usage.totalTokens !== (usage.inputTokens as number) + (usage.outputTokens as number)) return null;
    return Object.freeze({
      usageId: usage.usageId as string,
      provider: usage.provider,
      model: usage.model,
      inputTokens: usage.inputTokens,
      outputTokens: usage.outputTokens,
      totalTokens: usage.totalTokens,
    });
  } catch {
    return null;
  }
};

const validateProgress = (value: unknown): ChatGenerationProgress | null => {
  const progress = readPlainDataRecord(value);
  if (progress === null) return null;
  try {
    if (Object.keys(progress).length !== 2 || Object.keys(progress).some((key) => key !== "progressPct" && key !== "usage")) return null;
    if (!(progress.progressPct === null
      || (typeof progress.progressPct === "number" && Number.isSafeInteger(progress.progressPct)
        && progress.progressPct >= 0 && progress.progressPct <= 100))) return null;
    const usage = progress.usage === null ? null : validateUsage(progress.usage);
    if (progress.usage !== null && usage === null) return null;
    return Object.freeze({ progressPct: progress.progressPct as number | null, usage });
  } catch {
    return null;
  }
};

/** Reads only own data properties; hostile getters/proxies fail closed. */
const readFailureDeclaration = (
  error: unknown,
): Readonly<{ readonly code: unknown; readonly retryable: unknown }> | null => {
  try {
    if (error === null || typeof error !== "object") return null;
    // A Proxy can forge own descriptors (and even paired get results) while
    // retaining an ordinary prototype. Detect it before any reflective read;
    // no provider-controlled trap should run at this boundary.
    if (isProxy(error)) return null;
    const prototype = Object.getPrototypeOf(error);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const keys = Reflect.ownKeys(error);
    if (keys.length !== 2 || keys.some((key) => key !== "code" && key !== "retryable")) return null;
    const code = Object.getOwnPropertyDescriptor(error, "code");
    const retryable = Object.getOwnPropertyDescriptor(error, "retryable");
    if (code === undefined || retryable === undefined
      || !("value" in code) || !("value" in retryable)) return null;
    // Compare descriptor values with ordinary reads. A Proxy that forges only
    // descriptor traps cannot smuggle a typed declaration through this gate;
    // any accessor/get trap failure is contained by the surrounding catch.
    if (Reflect.get(error, "code") !== code.value || Reflect.get(error, "retryable") !== retryable.value) return null;
    return Object.freeze({ code: code.value, retryable: retryable.value });
  } catch {
    return null;
  }
};

const classifyFailure = (
  error: unknown,
  stage: "provider" | "context" | "attachment" | "callback" | "timeout",
): ChatGenerationFailure => {
  try {
    const candidate = readFailureDeclaration(error);
    const allowed = stage === "provider"
      ? ["generation_provider_failed", "generation_timeout"]
      : stage === "context"
        ? ["generation_context_failed", "generation_timeout"]
        : stage === "attachment"
          ? ["generation_attachment_failed", "generation_timeout"]
          : stage === "callback"
            ? ["generation_interrupted", "generation_timeout"]
            : ["generation_timeout"];
    if (candidate !== null && typeof candidate.code === "string"
      && allowed.includes(candidate.code) && typeof candidate.retryable === "boolean") {
      return { code: candidate.code as ChatGenerationFailureCode, retryable: candidate.retryable };
    }
  } catch {
    // Treat all malformed declarations, including adversarial proxies, as an
    // untyped failure at the current boundary.
  }
  return defaultFailure(stage);
};

const accumulatedText = (events: readonly ChatGenerationEvent[]): string => {
  let text = "";
  for (const event of events) {
    if (event.frame.kind === "snapshot") text = event.frame.text;
    if (event.frame.kind === "delta") text += event.frame.text;
  }
  return text;
};

export const validateChatGenerationAttachmentDescriptors = (
  expected: readonly {
    readonly id: string;
    readonly displayName: string;
    readonly mediaType: string;
    readonly sizeBytes: number;
    readonly contentReference: string | null;
  }[],
  loaded: readonly ChatGenerationAttachmentDescriptor[],
): readonly ChatGenerationAttachmentDescriptor[] => {
  if (!Array.isArray(loaded) || loaded.length !== expected.length) throw new TypeError("invalid generation attachments");
  const seen = new Set<string>();
  return Object.freeze(loaded.map((descriptor, index) => {
    const source = expected[index];
    if (source === undefined || descriptor === null || typeof descriptor !== "object"
      || descriptor.id !== source.id || descriptor.displayName !== source.displayName
      || descriptor.mediaType !== source.mediaType || descriptor.sizeBytes !== source.sizeBytes
      || !(descriptor.contentReference === null || typeof descriptor.contentReference === "string")
      || seen.has(descriptor.id)
      || !(descriptor.content === null || descriptor.content instanceof Uint8Array)
      || (descriptor.content !== null && descriptor.content.byteLength !== descriptor.sizeBytes)) {
      throw new TypeError("invalid generation attachment descriptor");
    }
    seen.add(descriptor.id);
    return Object.freeze({
      id: descriptor.id,
      displayName: descriptor.displayName,
      mediaType: descriptor.mediaType,
      sizeBytes: descriptor.sizeBytes,
      contentReference: descriptor.contentReference,
      content: descriptor.content === null ? null : new Uint8Array(descriptor.content),
    });
  }));
};

export const createChatGenerationSupervisor = (
  deps: ChatGenerationSupervisorDependencies,
): ChatGenerationSupervisor => {
  const active = new Map<string, ActiveGeneration>();
  const scheduler = deps.scheduler ?? realtimeChatGenerationScheduler;
  const liveness = validateLivenessPolicy(deps.liveness);
  const agentEvents: AgentRunEventSupervisor | null = deps.agentRunEvents === undefined
    ? null
    : createAgentRunEventSupervisor({
        events: deps.agentRunEvents,
        nowEpochMilliseconds: deps.nowEpochMilliseconds,
        eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
      });
  const keyOf = (accountId: string, generationId: string): string =>
    `${accountId.length}:${accountId}:${generationId}`;

  const recordAgent = (
    operation: () => void,
  ): void => {
    if (agentEvents === null) return;
    try {
      operation();
    } catch {
      // The agent timeline is a privacy-safe observability sidecar. A malformed
      // or unavailable sidecar must never change canonical text-generation
      // admission, cancellation, or finalization semantics.
    }
  };

  const recordAgentAccepted = (state: ActiveGeneration): void => {
    recordAgent(() => agentEvents!.accepted({
      runId: state.generationId,
      attemptId: state.attemptId,
      admissionId: state.admissionId,
    }));
  };

  const recordAgentCapability = (state: ActiveGeneration): void => {
    const capability = readChatGenerationSourceCapability(deps.source);
    recordAgent(() => agentEvents!.capability({
      runId: state.generationId,
      attemptId: state.attemptId,
      capabilityId: `capability:${capability.tier}`,
      tier: capability.tier,
      adapter: capability.adapter,
      deterministic: capability.deterministic,
    }));
  };

  const recordAgentContext = (
    state: ActiveGeneration,
    packet: ChatGenerationContextPacket,
  ): void => {
    const policyDecision = packet.budget.usedTokens > 0 ? "included" : "degraded";
    recordAgent(() => agentEvents!.context({
      runId: state.generationId,
      attemptId: state.attemptId,
      contextReceiptId: packet.packetHash,
      sourceKind: "context-packet",
      sourceRef: packet.packetHash,
      sourceHash: packet.packetHash,
      ownerRef: packet.ownerAccountId,
      expiresAt: null,
      redactedPreview: "structured context packet",
      tokenEstimate: packet.budget.usedTokens,
      inclusionReason: "structured context packet",
      policyDecision,
    }));
  };

  const recordAgentStatus = (state: ActiveGeneration, status: "queued" | "gathering_context" | "generating",
    progressPct: number | null): void => {
    recordAgent(() => agentEvents!.status({
      runId: state.generationId,
      attemptId: state.attemptId,
      status,
      progressPct,
    }));
  };

  const recordAgentUsage = (state: ActiveGeneration, usage: ChatGenerationUsage): void => {
    recordAgent(() => agentEvents!.usage({
      runId: state.generationId,
      attemptId: state.attemptId,
      usageId: usage.usageId,
      inputTokens: usage.inputTokens,
      outputTokens: usage.outputTokens,
      totalTokens: usage.totalTokens,
      durationMs: Math.max(0, deps.nowEpochMilliseconds() - (state.providerStartedAt ?? deps.nowEpochMilliseconds())),
    }));
  };

  const recordAgentTerminal = (
    state: ActiveGeneration,
    kind: "done" | "cancelled" | "failed",
    failure: ChatGenerationFailure | null,
  ): void => {
    const terminalOutcome = kind === "done" ? "completed" : kind;
    const terminalCode = kind === "done"
      ? "completed"
      : kind === "cancelled"
        ? "cancelled"
        : (failure?.code ?? "generation_interrupted");
    recordAgent(() => agentEvents!.terminal({
      runId: state.generationId,
      attemptId: state.attemptId,
      terminalOutcome,
      terminalCode,
      retryable: kind === "failed" ? (failure?.retryable ?? true) : false,
      // No retry/recovery route exists at this layer; do not advertise one.
      recoveryAction: null,
    }));
  };

  const recordRecoveredAgentTerminal = (
    accountId: string,
    generationId: string,
    frame: ChatGenerationTerminalFrame,
  ): void => {
    if (agentEvents === null || deps.agentRunEvents === undefined) return;
    try {
      let prior = deps.agentRunEvents.list(generationId);
      let accepted = prior.find((event) => event.kind === "run_accepted");
      // A process may have crashed immediately after canonical admission and
      // before the sidecar append. Reconstruct only that safe first link from
      // the durable canonical accepted frame; otherwise fail closed without a
      // misleading terminal-only agent timeline.
      if (accepted === undefined) {
        const canonicalAccepted = deps.events.listAfter(accountId, generationId, null)
          ?.find((event) => event.frame.kind === "accepted");
        if (canonicalAccepted === undefined || canonicalAccepted.frame.kind !== "accepted") return;
        try {
          agentEvents.accepted({
            runId: generationId,
            attemptId: `${generationId}:attempt:recovery`,
            admissionId: canonicalAccepted.id,
          });
        } catch {
          return;
        }
        prior = deps.agentRunEvents.list(generationId);
        accepted = prior.find((event) => event.kind === "run_accepted");
      }
      if (accepted === undefined || prior.some((event) => event.kind === "terminal")) return;
      const recoveryAttemptId = `${generationId}:attempt:recovery`;
      if (!prior.some((event) => event.kind === "recovery")) {
        try {
          agentEvents.recovery({
            runId: generationId,
            attemptId: recoveryAttemptId,
            recoveryId: `${generationId}:recovery:reconnect`,
            action: "reconnect",
            reason: "process restarted before terminal",
            fromAttemptId: accepted.attemptId,
            toAttemptId: recoveryAttemptId,
          });
        } catch {
          // A recovery marker is useful but never substitutes for the
          // canonical terminal. Continue to the terminal append below.
        }
      }
      const latest = deps.agentRunEvents.list(generationId);
      if (latest.some((event) => event.kind === "terminal")) return;
      const failure = frame.kind === "failed" ? frame.error : null;
      agentEvents.terminal({
        runId: generationId,
        attemptId: recoveryAttemptId,
        terminalOutcome: frame.kind === "done" ? "completed" : frame.kind,
        terminalCode: frame.kind === "done"
          ? "completed"
          : frame.kind === "cancelled"
            ? "cancelled"
            : failure.code,
        retryable: frame.kind === "failed" ? failure.retryable : false,
        recoveryAction: null,
      });
    } catch {
      // The canonical generation ledger remains authoritative if the sidecar
      // is unavailable or corrupt during recovery.
    }
  };

  const append = (
    state: Pick<ActiveGeneration, "accountId" | "generationId">,
    frame: Exclude<ChatGenerationFrame, { readonly kind: "accepted" | "done" | "failed" | "cancelled" }>,
  ): void => {
    const prior = deps.events.listAfter(state.accountId, state.generationId, null);
    if (prior === null) throw new TypeError("chat generation event log disappeared");
    const appended = deps.events.append({
      accountId: state.accountId,
      generationId: state.generationId,
      eventId: deps.eventId(
        state.accountId,
        state.generationId,
        frame.kind,
        prior.length + 1,
      ),
      createdAt: deps.nowEpochMilliseconds(),
      frame,
    });
    if (appended.kind !== "appended") {
      throw new TypeError("chat generation event identity conflict");
    }
  };

  const clearTimer = (handle: unknown | null): void => {
    if (handle === null) return;
    try {
      scheduler.clearTimeout(handle);
    } catch {
      // A scheduler is an injected seam; timer cleanup must never escape a
      // provider callback or prevent durable terminalization.
    }
  };

  const clearLivenessTimers = (state: ActiveGeneration): void => {
    clearTimer(state.firstEventTimer);
    clearTimer(state.maxDurationTimer);
    clearTimer(state.heartbeatTimer);
    clearTimer(state.cancelGraceTimer);
    state.firstEventTimer = null;
    state.maxDurationTimer = null;
    state.heartbeatTimer = null;
    state.cancelGraceTimer = null;
  };

  const appendHeartbeat = (state: ActiveGeneration): void => {
    if (liveness?.heartbeatIntervalMs === 0 || state.terminal || state.cancelRequested) return;
    const startedAt = state.providerStartedAt;
    if (startedAt === null) return;
    append(state, {
      kind: "heartbeat",
      attemptId: state.attemptId,
      elapsedMs: Math.max(0, deps.nowEpochMilliseconds() - startedAt),
    });
  };

  const markProviderEvent = (state: ActiveGeneration): void => {
    state.providerEventSeen = true;
    clearTimer(state.firstEventTimer);
    state.firstEventTimer = null;
  };

  const armLiveness = (state: ActiveGeneration): void => {
    if (liveness === undefined || state.providerStartedAt === null || state.terminal || state.cancelRequested) return;
    state.firstEventTimer = scheduler.setTimeout(() => {
      if (state.terminal || state.providerEventSeen || state.cancelRequested) return;
      void finalize(state, "failed", "", { code: "generation_timeout", retryable: true });
    }, liveness.firstEventDeadlineMs);
    state.maxDurationTimer = scheduler.setTimeout(() => {
      if (state.terminal || state.cancelRequested) return;
      void finalize(state, "failed", "", { code: "generation_timeout", retryable: true });
    }, liveness.maxRunDurationMs);
    if (liveness.heartbeatIntervalMs > 0) {
      const heartbeat = (): void => {
        if (state.terminal || state.cancelRequested) return;
        try {
          appendHeartbeat(state);
        } catch {
          void finalize(state, "failed", "", defaultFailure("callback"));
          return;
        }
        try {
          state.heartbeatTimer = scheduler.setTimeout(heartbeat, liveness.heartbeatIntervalMs);
        } catch {
          void finalize(state, "failed", "", defaultFailure("callback"));
        }
      };
      state.heartbeatTimer = scheduler.setTimeout(heartbeat, liveness.heartbeatIntervalMs);
    }
  };

  const assistantMessage = (
    state: Pick<ActiveGeneration, "accountId" | "generationId" | "admitted">,
    text: string,
  ): ChatMessageRecord => {
    const id = deps.assistantMessageId(state.accountId, state.generationId);
    const payloadHash = `sha256:${createHash("sha256")
      .update(`assistant\0${text}`, "utf8")
      .digest("hex")}`;
    const authoredAt = state.admitted.message.createdAt;
    const createdAt = Math.max(
      deps.nowEpochMilliseconds(),
      Math.min(Number.MAX_SAFE_INTEGER, authoredAt + 1),
    );
    return Object.freeze({
      id,
      text,
      sender: "ai",
      type: "text",
      createdAt,
      updatedAt: createdAt,
      chatSessionId: state.admitted.message.chatSessionId,
      appId: state.admitted.message.appId,
      journalRevision: 1,
      payloadHash,
      messageSource: "chat_generation",
      rating: null,
      reported: false,
      revision: deps.revision(state.accountId, id, payloadHash),
      attachments: Object.freeze([]),
    });
  };

  const cancelRun = (state: ActiveGeneration): void => {
    if (state.run === null || state.runCancelled) return;
    state.runCancelled = true;
    try {
      state.run.cancel();
    } catch {
      // Provider cancellation is best effort. Durable finalization remains the authority.
    }
  };

  const finalize = (
    state: ActiveGeneration,
    kind: "done" | "cancelled" | "failed",
    text: string,
    failure: ChatGenerationFailure | null = null,
  ): boolean => {
    if (state.terminal) return true;
    if (state.cancelRequested && kind !== "cancelled") {
      kind = "cancelled";
      text = state.text;
      failure = null;
    }
    // A provider that completes without emitting any text has not produced a
    // truthful answer. Keep this terminal in the failed grammar so projection
    // cannot persist the apology fallback as a completed assistant message.
    if (kind === "done" && text.trim().length === 0) {
      kind = "failed";
      failure = state.failure ?? defaultFailure("provider");
    }
    if (kind === "done" && state.failure !== null) {
      kind = "failed";
      text = "";
      failure = state.failure;
    }
    if (kind === "failed") state.failure = failure ?? classifyFailure(null, "provider");
    state.terminal = true;
    clearLivenessTimers(state);
    cancelRun(state);
    try {
      const message = text.length === 0 ? null : assistantMessage(state, text);
      const prior = deps.events.listAfter(state.accountId, state.generationId, null);
      if (prior === null) throw new TypeError("chat generation event log disappeared");
      const finalized = deps.finalization.finalize({
        accountId: state.accountId,
        generationId: state.generationId,
        eventId: deps.eventId(state.accountId, state.generationId, kind, prior.length + 1),
        createdAt: deps.nowEpochMilliseconds(),
        frame: kind === "failed"
          ? {
              kind: "failed",
              error: state.failure!,
            }
          : kind === "done"
            ? { kind: "done", message: message ?? assistantMessage(state, FALLBACK_TEXT) }
            : { kind: "cancelled", message },
      });
      const canonicalKind = finalized.frame.kind;
      if (state.recovered) {
        recordRecoveredAgentTerminal(state.accountId, state.generationId, finalized.frame);
      } else {
        recordAgentTerminal(
          state,
          canonicalKind,
          canonicalKind === "failed" ? finalized.frame.error : null,
        );
      }
    } catch {
      state.terminal = false;
      return false;
    }
    active.delete(keyOf(state.accountId, state.generationId));
    return true;
  };

  const failInterrupted = (
    accountId: string,
    generationId: string,
    failure: ChatGenerationFailure = { code: "generation_interrupted", retryable: true },
  ): boolean => {
    try {
      const prior = deps.events.listAfter(accountId, generationId, null);
      // A timeout/recovery callback must never manufacture a terminal for a
      // generation that has no durable admission record.
      if (prior === null || !prior.some((event) => event.frame.kind === "accepted")) return false;
      const finalized = deps.finalization.finalize({
        accountId,
        generationId,
        eventId: deps.eventId(accountId, generationId, "failed", prior.length + 1),
        createdAt: deps.nowEpochMilliseconds(),
        frame: {
          kind: "failed",
          error: failure,
        },
      });
      recordRecoveredAgentTerminal(accountId, generationId, finalized.frame);
      return true;
    } catch {
      return false;
    }
  };

  const cancelFromDurableState = (accountId: string, generationId: string): boolean => {
    const admitted = deps.messages.readHumanByGeneration(accountId, generationId);
    const events = deps.events.listAfter(accountId, generationId, null);
    if (admitted === null || events === null) {
      return failInterrupted(accountId, generationId);
    }
    const state: ActiveGeneration = {
      accountId,
      generationId,
      admitted,
      attemptId: `${generationId}:attempt:recovery`,
      admissionId: admitted.message.id,
      text: accumulatedText(events),
      run: null,
      runCancelled: false,
      terminal: false,
      failure: null,
      providerStartedAt: null,
      providerEventSeen: true,
      cancelRequested: true,
      recovered: true,
      firstEventTimer: null,
      maxDurationTimer: null,
      heartbeatTimer: null,
      cancelGraceTimer: null,
      progressPct: null,
      usage: null,
    };
    return finalize(state, "cancelled", state.text);
  };

  const supervisor: ChatGenerationSupervisor = Object.freeze({
    onAdmitted(input): void {
      const generationId = input.acceptedEvent.generationId;
      const key = keyOf(input.accountId, generationId);
      const lifecycle = deps.events.readLifecycle(input.accountId, generationId);
      if (lifecycle === null) {
        throw new TypeError("admitted chat generation event log disappeared");
      }
      if (lifecycle.state === "terminal") return;
      if (lifecycle.state === "cancellation_requested") {
        void cancelFromDurableState(input.accountId, generationId);
        return;
      }
      if (active.has(key)) return;
      const state: ActiveGeneration = {
        accountId: input.accountId,
        generationId,
        admitted: input.stored,
        attemptId: `${generationId}:attempt:1`,
        admissionId: input.acceptedEvent.id,
        text: "",
        run: null,
        runCancelled: false,
        terminal: false,
        failure: null,
        providerStartedAt: null,
        providerEventSeen: false,
        cancelRequested: false,
        recovered: false,
        firstEventTimer: null,
        maxDurationTimer: null,
        heartbeatTimer: null,
        cancelGraceTimer: null,
        progressPct: null,
        usage: null,
      };
      active.set(key, state);
      recordAgentAccepted(state);
      recordAgentCapability(state);
      recordAgentStatus(state, "queued", 0);
      try {
        append(state, { kind: "snapshot", text: "" });
      } catch (error) {
        active.delete(key);
        throw error;
      }
      void (async (): Promise<void> => {
        recordAgentStatus(state, "gathering_context", null);
        let context: ChatGenerationContextPacket;
        try {
          const nowEpochMilliseconds = deps.nowEpochMilliseconds();
          const snapshotSequence = deps.messages.readSnapshotSequence(input.accountId);
          const historyPage = deps.messages.listHistory(input.accountId, {
            limit: 16,
            snapshotSequence,
            olderThan: null,
          });
          const history = historyPage.messages.filter((message) => message.id !== input.stored.message.id);
          const loaded = await deps.context.load({
            accountId: input.accountId,
            generationId,
            admitted: input.stored,
            nowEpochMilliseconds,
            history,
            bearerToken: input.bearerToken,
          });
          context = normalizeChatGenerationContext(loaded, {
            accountId: input.accountId,
            generationId,
            nowEpochMilliseconds,
          });
          recordAgentContext(state, context);
        } catch (error) {
          void finalize(state, "failed", "", classifyFailure(error, "context"));
          return;
        }
        if (state.terminal || state.cancelRequested) return;
        let attachments: readonly ChatGenerationAttachmentDescriptor[];
        try {
          const loadedAttachments = await deps.attachments.loadForGeneration({
            accountId: input.accountId,
            messageId: input.stored.message.id,
            attachments: input.stored.message.attachments ?? Object.freeze([]),
            nowEpochMilliseconds: deps.nowEpochMilliseconds(),
          });
          attachments = validateChatGenerationAttachmentDescriptors(input.stored.message.attachments ?? Object.freeze([]), loadedAttachments);
        } catch (error) {
          void finalize(state, "failed", "", classifyFailure(error, "attachment"));
          return;
        }
        if (state.terminal || state.cancelRequested) return;
        try {
          state.providerStartedAt = deps.nowEpochMilliseconds();
          recordAgentStatus(state, "generating", null);
          const run = deps.source.start({
            generationId,
            attemptId: state.attemptId,
            prompt: input.stored.message.text,
            context,
            attachments,
            onDelta(text): void {
              try {
                if (state.terminal) return;
                markProviderEvent(state);
                if (typeof text !== "string") {
                  void finalize(state, "failed", "", defaultFailure("provider"));
                  return;
                }
                if (text.length === 0) return;
                append(state, { kind: "delta", text });
                state.text += text;
              } catch {
                void finalize(state, "failed", "", classifyFailure(null, "callback"));
              }
            },
            onProgress(progress): void {
              try {
                if (state.terminal || state.cancelRequested) return;
                markProviderEvent(state);
                const safe = validateProgress(progress);
                if (safe === null) {
                  void finalize(state, "failed", "", defaultFailure("provider"));
                  return;
                }
                state.progressPct = safe.progressPct;
                if (safe.usage !== null) state.usage = safe.usage;
                recordAgentStatus(state, "generating", state.progressPct);
                if (safe.usage !== null) recordAgentUsage(state, safe.usage);
                append(state, {
                  kind: "progress",
                  attemptId: state.attemptId,
                  progressPct: state.progressPct,
                  elapsedMs: Math.max(0, deps.nowEpochMilliseconds() - (state.providerStartedAt ?? deps.nowEpochMilliseconds())),
                  usage: state.usage,
                });
              } catch {
                void finalize(state, "failed", "", defaultFailure("callback"));
              }
            },
            onUsage(usage): void {
              try {
                if (state.terminal || state.cancelRequested) return;
                markProviderEvent(state);
                const safe = validateUsage(usage);
                if (safe === null) {
                  void finalize(state, "failed", "", defaultFailure("provider"));
                  return;
                }
                state.usage = safe;
                recordAgentStatus(state, "generating", state.progressPct);
                recordAgentUsage(state, safe);
                append(state, {
                  kind: "progress",
                  attemptId: state.attemptId,
                  progressPct: state.progressPct,
                  elapsedMs: Math.max(0, deps.nowEpochMilliseconds() - (state.providerStartedAt ?? deps.nowEpochMilliseconds())),
                  usage: safe,
                });
              } catch {
                void finalize(state, "failed", "", defaultFailure("callback"));
              }
            },
            onComplete(): void {
              try {
                if (state.terminal) return;
                markProviderEvent(state);
                void finalize(state, "done", state.text);
              } catch {
                void finalize(state, "failed", "", defaultFailure("callback"));
              }
            },
            onError(error): void {
              try {
                if (state.terminal) return;
                markProviderEvent(state);
                void finalize(state, "failed", "", classifyFailure(error, "provider"));
              } catch {
                void finalize(state, "failed", "", defaultFailure("callback"));
              }
            },
          });
          state.run = run;
          armLiveness(state);
          if (state.terminal || state.cancelRequested) cancelRun(state);
        } catch (error) {
          void finalize(state, "failed", "", classifyFailure(error, "provider"));
        }
      })();
    },

    cancel(accountId: string, generationId: string): void {
      const state = active.get(keyOf(accountId, generationId));
      if (state !== undefined && !state.terminal) {
        state.cancelRequested = true;
        cancelRun(state);
        if (liveness !== undefined && liveness.cancelGraceMs > 0 && state.providerStartedAt !== null) {
          clearTimer(state.cancelGraceTimer);
          try {
            state.cancelGraceTimer = scheduler.setTimeout(() => {
              state.cancelGraceTimer = null;
              void finalize(state, "cancelled", state.text);
            }, liveness.cancelGraceMs);
          } catch {
            // If the injected scheduler cannot arm grace, cancellation still
            // owns the race and must terminalize synchronously.
            void finalize(state, "cancelled", state.text);
          }
          return;
        }
      }
      queueMicrotask(() => {
        if (state !== undefined) void finalize(state, "cancelled", state.text);
        else void cancelFromDurableState(accountId, generationId);
      });
    },

    timeout(accountId: string, generationId: string): void {
      const state = active.get(keyOf(accountId, generationId));
      queueMicrotask(() => {
        const lifecycle = deps.events.readLifecycle(accountId, generationId);
        if (lifecycle?.state === "cancellation_requested") {
          if (state !== undefined) {
            state.cancelRequested = true;
            cancelRun(state);
            if (liveness?.cancelGraceMs === undefined || liveness.cancelGraceMs === 0) {
              void finalize(state, "cancelled", state.text);
            }
          } else void cancelFromDurableState(accountId, generationId);
        } else if (state !== undefined && state.cancelRequested) {
          // A cancellation request owns the race; its grace timer (if any)
          // remains responsible for the terminal rather than a timeout.
          return;
        } else if (state !== undefined) {
          void finalize(
            state,
            "failed",
            "",
            { code: "generation_timeout", retryable: true },
          );
        } else {
          void failInterrupted(accountId, generationId, {
            code: "generation_timeout",
            retryable: true,
          });
        }
      });
    },

    recoverInterrupted(): void {
      for (const lifecycle of deps.events.listUnterminated()) {
        const recovered = lifecycle.state === "cancellation_requested"
          ? cancelFromDurableState(lifecycle.accountId, lifecycle.generationId)
          : failInterrupted(lifecycle.accountId, lifecycle.generationId);
        if (recovered) {
          const key = keyOf(lifecycle.accountId, lifecycle.generationId);
          const state = active.get(key);
          if (state !== undefined) {
            state.terminal = true;
            cancelRun(state);
            active.delete(key);
          }
        }
      }
    },
  });

  return supervisor;
};
