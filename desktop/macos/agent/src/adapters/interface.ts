// HarnessAdapter interface — harness-agnostic abstraction for AI harnesses
//
// Issue #6592: Support multiple AI harnesses via common interface.
// Issue #6594: Pi-mono harness with Omi API proxy.

import type { OutboundMessage, WarmupSessionConfig } from "../protocol.js";
import type { ArtifactRole, ResumeFidelity, RunMode } from "../runtime/types.js";

/**
 * Configuration for creating a harness adapter.
 */
export interface HarnessConfig {
  /** Omi API base URL for pi-mono provider */
  omiApiBaseUrl?: string;
  /** Firebase auth token for Omi API authentication */
  authToken?: string;
}

/**
 * Options for creating a new session.
 */
export interface SessionOpts {
  cwd: string;
  model?: string;
  systemPrompt?: string;
  mcpServers?: Record<string, unknown>[];
}

/**
 * Result of a prompt execution.
 */
export interface PromptResult {
  text: string;
  sessionId: string;
  costUsd?: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
}

/**
 * Prompt content block (text or image).
 */
export type PromptBlock =
  | { type: "text"; text: string }
  | { type: "image"; data: string; mimeType: string };

/**
 * Tool definition for the harness.
 */
export interface ToolDef {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

/**
 * Callback for tool execution — harness calls this, host returns the result.
 */
export type ToolExecutor = (
  name: string,
  input: Record<string, unknown>
) => Promise<string>;

/**
 * Event callback for streaming updates.
 */
export type EventCallback = (event: OutboundMessage) => void;

/**
 * Features that a harness may or may not support.
 */
export enum HarnessFeature {
  MCP_CLIENT = "mcp_client",
  BIDIRECTIONAL_RPC = "bidirectional_rpc",
  SESSION_RESUME = "session_resume",
  COST_TRACKING = "cost_tracking",
  OAUTH = "oauth",
  MODEL_SWITCH = "model_switch",
}

/**
 * Common interface for all AI harness adapters.
 *
 * Implementations translate between the harness-specific protocol
 * and the normalized bridge protocol (OutboundMessage events).
 */
export interface HarnessAdapter {
  /** Human-readable name of the harness */
  readonly name: string;

  /** Start the harness subprocess/connection */
  start(): Promise<void>;

  /** Stop the harness and clean up resources */
  stop(): Promise<void>;

  /** Create a new session, returns session ID */
  createSession(opts: SessionOpts): Promise<string>;

  /**
   * Send a prompt and stream events via the callback.
   * Returns the final result when complete.
   */
  sendPrompt(
    sessionId: string,
    prompt: PromptBlock[],
    tools: ToolDef[],
    mode: "ask" | "act",
    onEvent: EventCallback,
    onToolCall: ToolExecutor,
    signal?: AbortSignal
  ): Promise<PromptResult>;

  /** Abort the current prompt execution */
  abort(sessionId: string): void;

  /** Switch the model for a session (if supported) */
  setModel?(sessionId: string, model: string): Promise<void>;

  /** Pre-warm sessions in the background */
  warmup?(cwd: string, sessions: WarmupSessionConfig[]): Promise<void>;

  /** Invalidate a cached session */
  invalidateSession?(sessionKey: string): void;

  /** Check if this harness supports a given feature */
  supportsFeature(feature: HarnessFeature): boolean;
}

export interface AdapterCapabilities {
  readonly resumeFidelity: ResumeFidelity;
  readonly supportsNativeResume: boolean;
  readonly supportsCancellation: boolean;
  readonly acknowledgesCancellation: boolean;
  readonly requiresPinnedWorker: boolean;
  readonly supportsModelSwitching: boolean;
  readonly supportsArtifactEmission: boolean;
  readonly supportsTools: boolean;
  readonly restartBehavior: "native_bindings_survive" | "process_local_bindings_stale" | "attempts_orphaned";
}

export type AdapterCapabilityKey =
  | "nativeResume"
  | "cancellationDispatch"
  | "cancellationAck"
  | "pinnedWorker"
  | "modelSwitching"
  | "artifactEmission"
  | "toolSupport"
  | "restartOrphanSemantics";

export type AdapterCapabilityExpectationStatus = "required" | "unsupported" | "known_limitation";

export interface AdapterCapabilityExpectation {
  readonly status: AdapterCapabilityExpectationStatus;
  readonly reason: string;
  readonly followUpTicket?: string;
}

export interface AdapterCapabilityMatrixEntry {
  readonly adapterId: string;
  readonly productionAdapter: boolean;
  readonly expectations: Record<AdapterCapabilityKey, AdapterCapabilityExpectation>;
}

const required = (reason: string): AdapterCapabilityExpectation => ({ status: "required", reason });
const unsupported = (reason: string): AdapterCapabilityExpectation => ({ status: "unsupported", reason });
const knownLimitation = (reason: string, followUpTicket: string): AdapterCapabilityExpectation => ({
  status: "known_limitation",
  reason,
  followUpTicket,
});

export const ADAPTER_CAPABILITY_MATRIX = {
  acp: {
    adapterId: "acp",
    productionAdapter: true,
    expectations: {
      nativeResume: required("ACP exposes native session ids and session/resume."),
      cancellationDispatch: required("ACP exposes session/cancel dispatch."),
      cancellationAck: knownLimitation("ACP cancellation is fire-and-forget; no terminal ack is exposed yet.", "TICKET-03-follow-up-cancel-ack"),
      pinnedWorker: unsupported("ACP bindings are resumable by native session id and do not require process-local pinning."),
      modelSwitching: required("ACP supports session/set_model during open and resume."),
      artifactEmission: unsupported("ACP adapter does not emit artifact references yet."),
      toolSupport: required("ACP session/update tool events are projected into canonical adapter events."),
      restartOrphanSemantics: required("Startup reconciliation orphans active attempts while preserving native-resumable bindings."),
    },
  },
  "pi-mono": {
    adapterId: "pi-mono",
    productionAdapter: true,
    expectations: {
      nativeResume: unsupported("pi-mono session ids are process-local and are stale after daemon restart."),
      cancellationDispatch: required("pi-mono supports abort dispatch for the active prompt."),
      cancellationAck: knownLimitation("pi-mono abort resolves locally without an independent adapter ack.", "TICKET-03-follow-up-cancel-ack"),
      pinnedWorker: required("pi-mono keeps session state in the adapter process and must stay worker-pinned while active."),
      modelSwitching: required("pi-mono maps desktop model ids and sends set_model."),
      artifactEmission: unsupported("pi-mono runtime does not emit artifact references yet."),
      toolSupport: required("pi-mono uses the Omi extension/tool relay path for tools."),
      restartOrphanSemantics: required("Startup reconciliation orphans active attempts and marks non-resumable bindings stale."),
    },
  },
  hermes: {
    adapterId: "hermes",
    productionAdapter: false,
    expectations: {
      nativeResume: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
      cancellationDispatch: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
      cancellationAck: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
      pinnedWorker: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
      modelSwitching: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
      artifactEmission: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
      toolSupport: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
      restartOrphanSemantics: knownLimitation("No production Hermes adapter exists in this ticket.", "TICKET-hermes-adapter"),
    },
  },
  openclaw: {
    adapterId: "openclaw",
    productionAdapter: false,
    expectations: {
      nativeResume: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
      cancellationDispatch: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
      cancellationAck: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
      pinnedWorker: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
      modelSwitching: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
      artifactEmission: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
      toolSupport: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
      restartOrphanSemantics: knownLimitation("No production OpenClaw adapter exists in this ticket.", "TICKET-openclaw-adapter"),
    },
  },
  a2a: {
    adapterId: "a2a",
    productionAdapter: false,
    expectations: {
      nativeResume: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
      cancellationDispatch: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
      cancellationAck: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
      pinnedWorker: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
      modelSwitching: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
      artifactEmission: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
      toolSupport: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
      restartOrphanSemantics: knownLimitation("No production A2A adapter exists in this ticket.", "TICKET-a2a-adapter"),
    },
  },
} as const satisfies Record<string, AdapterCapabilityMatrixEntry>;

export type KnownAdapterId = keyof typeof ADAPTER_CAPABILITY_MATRIX;
export type ProductionAdapterId = "acp" | "pi-mono";

const PRODUCTION_ADAPTER_RESTART_BEHAVIOR: Record<ProductionAdapterId, AdapterCapabilities["restartBehavior"]> = {
  acp: "native_bindings_survive",
  "pi-mono": "process_local_bindings_stale",
};

export function adapterCapabilitiesFor(adapterId: ProductionAdapterId): AdapterCapabilities {
  const expectations = ADAPTER_CAPABILITY_MATRIX[adapterId].expectations;
  return {
    resumeFidelity: expectations.nativeResume.status === "required" ? "native" : "none",
    supportsNativeResume: expectations.nativeResume.status === "required",
    supportsCancellation: expectations.cancellationDispatch.status === "required",
    acknowledgesCancellation: expectations.cancellationAck.status === "required",
    requiresPinnedWorker: expectations.pinnedWorker.status === "required",
    supportsModelSwitching: expectations.modelSwitching.status === "required",
    supportsArtifactEmission: expectations.artifactEmission.status === "required",
    supportsTools: expectations.toolSupport.status === "required",
    restartBehavior: PRODUCTION_ADAPTER_RESTART_BEHAVIOR[adapterId],
  };
}

export interface OpenBindingInput {
  sessionId: string;
  cwd: string;
  model?: string;
  systemPrompt?: string;
  mcpServers?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
}

export interface ResumeBindingInput extends OpenBindingInput {
  adapterNativeSessionId: string;
}

export interface AdapterBindingHandle {
  bindingId?: string;
  sessionId: string;
  adapterId: string;
  adapterNativeSessionId: string;
  resumeFidelity: ResumeFidelity;
  cwd: string;
  model?: string;
  metadata?: Record<string, unknown>;
}

export type OpenedBinding = AdapterBindingHandle;

export interface AdapterAttemptContext {
  sessionId: string;
  runId: string;
  attemptId: string;
  binding: AdapterBindingHandle;
  prompt: PromptBlock[];
  mode: RunMode;
  model?: string;
  tools?: ToolDef[];
  metadata?: Record<string, unknown>;
}

export type AdapterEventSink = (event: OutboundMessage) => void;

export interface AdapterArtifactReference {
  kind: string;
  role: ArtifactRole;
  uri: string;
  displayName?: string | null;
  mimeType?: string | null;
  contentHash?: string | null;
  sizeBytes?: number | null;
  metadata?: Record<string, unknown>;
}

export interface AdapterAttemptResult extends PromptResult {
  adapterSessionId: string;
  terminalStatus: "succeeded" | "failed" | "cancelled";
  artifacts?: AdapterArtifactReference[];
}

export interface CancelAttemptContext {
  sessionId: string;
  runId?: string;
  attemptId?: string;
  binding?: AdapterBindingHandle;
}

export interface CancelDispatchResult {
  accepted: boolean;
  dispatchAttempted: boolean;
  adapterAcknowledged: boolean;
  message?: string;
}

export interface RuntimeAdapter {
  readonly adapterId: string;
  readonly capabilities: AdapterCapabilities;

  start(): Promise<void>;
  stop(): Promise<void>;

  openBinding(input: OpenBindingInput): Promise<OpenedBinding>;
  resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding>;

  executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult>;

  cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult>;
  closeBinding?(binding: AdapterBindingHandle): Promise<void>;
}
