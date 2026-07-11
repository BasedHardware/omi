// HarnessAdapter interface — harness-agnostic abstraction for AI harnesses
//
// Issue #6592: Support multiple AI harnesses via common interface.
// Issue #6594: Pi-mono harness with Omi API proxy.

import type { OutboundMessageDraft, WarmupSessionConfig } from "../protocol.js";
import type { RuntimeFailure } from "../runtime/failures.js";
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
  executionRole?: "coordinator" | "leaf";
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
export type EventCallback = (event: OutboundMessageDraft) => void;

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
  readonly credentialScope: AdapterCredentialScope;
  readonly expectations: Record<AdapterCapabilityKey, AdapterCapabilityExpectation>;
}

export type AdapterCredentialScope = "managed_cloud" | "local_user";

const required = (reason: string): AdapterCapabilityExpectation => ({ status: "required", reason });
const unsupported = (reason: string): AdapterCapabilityExpectation => ({ status: "unsupported", reason });
const knownLimitation = (reason: string, followUpTicket: string): AdapterCapabilityExpectation => ({
  status: "known_limitation",
  reason,
  followUpTicket,
});

const placeholderExpectations = (
  adapterName: string,
  followUpTicket: string
): Record<AdapterCapabilityKey, AdapterCapabilityExpectation> => {
  const reason = `No production ${adapterName} adapter exists in this ticket.`;
  return {
    nativeResume: knownLimitation(reason, followUpTicket),
    cancellationDispatch: knownLimitation(reason, followUpTicket),
    cancellationAck: knownLimitation(reason, followUpTicket),
    pinnedWorker: knownLimitation(reason, followUpTicket),
    modelSwitching: knownLimitation(reason, followUpTicket),
    artifactEmission: knownLimitation(reason, followUpTicket),
    toolSupport: knownLimitation(reason, followUpTicket),
    restartOrphanSemantics: knownLimitation(reason, followUpTicket),
  };
};

export const ADAPTER_CAPABILITY_MATRIX = {
  acp: {
    adapterId: "acp",
    productionAdapter: true,
    credentialScope: "local_user",
    // Production ACP: native session ids survive adapter process restarts.
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
    credentialScope: "managed_cloud",
    // Production pi-mono: native ids are process-local and require worker pinning.
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
    productionAdapter: true,
    credentialScope: "local_user",
    expectations: {
      // Hermes ACP sessions are tracked by the running server's in-memory
      // session manager and are only valid for that process. After a restart
      // the old session ids are stale, so bindings must not be marked as
      // native-resumable. See https://hermes-agent.nousresearch.com/docs/user-guide/features/acp
      nativeResume: unsupported("Hermes ACP session ids are process-local and are stale after adapter process restart."),
      cancellationDispatch: required("Hermes supports cancellation dispatch for active attempts."),
      cancellationAck: knownLimitation("Hermes cancellation is dispatchable but no terminal adapter ack is exposed yet.", "TICKET-03-follow-up-cancel-ack"),
      pinnedWorker: required("Hermes keeps session state in the adapter process and must stay worker-pinned while active."),
      modelSwitching: required("Hermes supports model selection during session open and resume."),
      artifactEmission: unsupported("Hermes ACP adapter does not emit artifact references yet."),
      toolSupport: required("Hermes projects tool calls through canonical adapter tool events."),
      restartOrphanSemantics: required("Startup reconciliation orphans active attempts and marks process-local Hermes bindings stale."),
    },
  },
  openclaw: {
    adapterId: "openclaw",
    productionAdapter: true,
    credentialScope: "local_user",
    expectations: {
      nativeResume: required("OpenClaw ACP exposes native sessions through the Gateway-backed ACP bridge."),
      cancellationDispatch: required("OpenClaw ACP accepts cancellation through the shared ACP interrupt path."),
      cancellationAck: knownLimitation("OpenClaw cancellation resolves locally without an independent adapter ack.", "TICKET-03-follow-up-cancel-ack"),
      pinnedWorker: unsupported("OpenClaw ACP sessions are native and do not require process-local pinned workers."),
      modelSwitching: unsupported("OpenClaw ACP does not currently expose session/set_model; model selection is configured in the OpenClaw gateway/agent."),
      artifactEmission: unsupported("OpenClaw ACP adapter does not emit artifact references yet."),
      toolSupport: unsupported("OpenClaw ACP rejects per-session MCP servers; Omi tools are unavailable until configured through the OpenClaw gateway/agent."),
      restartOrphanSemantics: required("Startup reconciliation orphans active attempts while preserving native-resumable OpenClaw bindings."),
    },
  },
  a2a: {
    adapterId: "a2a",
    productionAdapter: false,
    credentialScope: "managed_cloud",
    expectations: placeholderExpectations("A2A", "TICKET-a2a-adapter"),
  },
} as const satisfies Record<string, AdapterCapabilityMatrixEntry>;

export type KnownAdapterId = keyof typeof ADAPTER_CAPABILITY_MATRIX;
export type ProductionAdapterId = "acp" | "pi-mono" | "hermes" | "openclaw";
export type PlaceholderAdapterId = Exclude<KnownAdapterId, ProductionAdapterId>;

export const PRODUCTION_ADAPTER_IDS = ["acp", "pi-mono", "hermes", "openclaw"] as const satisfies readonly ProductionAdapterId[];
export const PLACEHOLDER_ADAPTER_IDS = ["a2a"] as const satisfies readonly PlaceholderAdapterId[];

export function isKnownAdapterId(adapterId: string): adapterId is KnownAdapterId {
  return Object.prototype.hasOwnProperty.call(ADAPTER_CAPABILITY_MATRIX, adapterId);
}

export function isProductionAdapterId(adapterId: string): adapterId is ProductionAdapterId {
  return isKnownAdapterId(adapterId) && ADAPTER_CAPABILITY_MATRIX[adapterId].productionAdapter;
}

export function isPlaceholderAdapterId(adapterId: string): adapterId is PlaceholderAdapterId {
  return isKnownAdapterId(adapterId) && !ADAPTER_CAPABILITY_MATRIX[adapterId].productionAdapter;
}

function restartBehaviorFor(expectations: Record<AdapterCapabilityKey, AdapterCapabilityExpectation>): AdapterCapabilities["restartBehavior"] {
  if (expectations.nativeResume.status === "required") return "native_bindings_survive";
  if (expectations.pinnedWorker.status === "required") return "process_local_bindings_stale";
  return "attempts_orphaned";
}

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
    restartBehavior: restartBehaviorFor(expectations),
  };
}

export function adapterCredentialScopeFor(adapterId: ProductionAdapterId): AdapterCredentialScope {
  return ADAPTER_CAPABILITY_MATRIX[adapterId].credentialScope;
}

export interface OpenBindingInput {
  /** Omi-owned correlation id. Adapters must not treat this as their native session id. */
  sessionId: string;
  cwd: string;
  model?: string;
  systemPrompt?: string;
  mcpServers?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
}

export interface ResumeBindingInput extends OpenBindingInput {
  /** Adapter-owned native session id recovered from the active binding. */
  adapterNativeSessionId: string;
}

export interface AdapterBindingHandle {
  bindingId?: string;
  /** Omi-owned correlation id. Runtime state uses this to group runs and bindings. */
  sessionId: string;
  adapterId: string;
  /** Adapter-owned native session id. This is the only id adapters should send back to native runtimes. */
  adapterNativeSessionId: string;
  resumeFidelity: ResumeFidelity;
  cwd: string;
  model?: string;
  metadata?: Record<string, unknown>;
}

export type OpenedBinding = AdapterBindingHandle;

export interface AdapterAttemptContext {
  /** Omi-owned correlation id for host/runtime bookkeeping only. */
  sessionId: string;
  /** Omi/Firebase owner from the active Omi request context. Adapter payloads must not override this. */
  ownerId: string;
  /** Transport correlation for request-scoped tool relays. */
  requestId: string;
  clientId: string;
  runId: string;
  attemptId: string;
  binding: AdapterBindingHandle;
  prompt: PromptBlock[];
  mode: RunMode;
  model?: string;
  tools?: ToolDef[];
  metadata?: Record<string, unknown>;
}

export type AdapterEventSink = (event: OutboundMessageDraft) => void;

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

export interface AdapterAttemptResult {
  text: string;
  costUsd?: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
  /** Adapter-owned native session id for request-scoped tool relays. */
  adapterSessionId: string;
  terminalStatus: "succeeded" | "failed" | "cancelled";
  failure?: RuntimeFailure;
  artifacts?: AdapterArtifactReference[];
}

export interface CancelAttemptContext {
  sessionId: string;
  ownerId?: string;
  requestId?: string;
  clientId?: string;
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

  /**
   * Return the MCP server configuration this adapter actually passes to its
   * underlying session. Adapters that strip per-session MCP servers (e.g.
   * OpenClaw with {@code sessionMcpServersMode: "empty"}) should return an
   * empty array so the kernel's binding hash reflects what the
   * adapter truly saw, not the raw input. Adapters that pass MCP servers
   * through unchanged can omit this method; the kernel treats absent
   * implementations as identity (passthrough).
   *
   * @param mcpServers Raw MCP server list from the run input.
   */
  effectiveMcpServers?(mcpServers: Record<string, unknown>[]): Record<string, unknown>[];
}

export interface PlaceholderRuntimeAdapter {
  readonly adapterId: PlaceholderAdapterId;
  readonly productionAdapter: false;
  readonly implementationFactory: null;
  readonly followUpTicket: string;
}

export const PLACEHOLDER_RUNTIME_ADAPTERS = Object.fromEntries(
  (Object.entries(ADAPTER_CAPABILITY_MATRIX) as [KnownAdapterId, AdapterCapabilityMatrixEntry][])
    .filter(([, entry]) => !entry.productionAdapter)
    .map(([adapterId, entry]) => [
      adapterId,
      {
        adapterId,
        productionAdapter: false,
        implementationFactory: null,
        followUpTicket: entry.expectations.nativeResume.followUpTicket ?? `TICKET-${adapterId}-adapter`,
      },
    ])
) as Record<PlaceholderAdapterId, PlaceholderRuntimeAdapter>;

export function assertAdapterBindingContract(binding: AdapterBindingHandle, operation: string): void {
  if (!binding.adapterNativeSessionId) {
    throw new Error(`${operation} returned an empty adapterNativeSessionId`);
  }
  if (binding.adapterNativeSessionId === binding.sessionId) {
    throw new Error(
      `${operation} conflated Omi sessionId ${binding.sessionId} with adapterNativeSessionId`
    );
  }
}

export function assertAdapterAttemptResultContract(
  context: AdapterAttemptContext,
  result: AdapterAttemptResult,
  operation: string
): void {
  if (!result.adapterSessionId) {
    throw new Error(`${operation} returned an empty adapterSessionId`);
  }
  if (result.adapterSessionId === context.sessionId) {
    throw new Error(
      `${operation} conflated Omi sessionId ${context.sessionId} with adapter native session id`
    );
  }
  if (result.adapterSessionId !== context.binding.adapterNativeSessionId) {
    throw new Error(
      `${operation} returned adapterSessionId ${result.adapterSessionId} for binding ${context.binding.adapterNativeSessionId}`
    );
  }
}
