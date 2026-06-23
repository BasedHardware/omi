// HarnessAdapter interface — harness-agnostic abstraction for AI harnesses
//
// Issue #6592: Support multiple AI harnesses via common interface.
// Issue #6594: Pi-mono harness with Omi API proxy.

import type { OutboundMessage, WarmupSessionConfig } from "../protocol.js";
import type { ResumeFidelity, RunMode } from "../runtime/types.js";

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
  readonly requiresPinnedWorker?: boolean;
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

export interface AdapterAttemptResult extends PromptResult {
  adapterSessionId: string;
  terminalStatus: "succeeded" | "failed" | "cancelled";
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
