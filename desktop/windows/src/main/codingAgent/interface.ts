// Coding-agent adapter contract — Windows port of the macOS agent runtime's
// adapter layer (desktop/macos/agent/src/adapters/interface.ts), trimmed to the
// adapters that exist on Windows: Claude Code (adapter id "acp", built-in ACP
// bridge, no external install) plus three user-connected external ACP commands
// (OpenClaw, Hermes, Codex). The macOS kernel/session-store, worker pools, and
// placeholder adapters (pi-mono, a2a) are deliberately not ported — Windows has
// no kernel; callers hold bindings in memory for the life of a task.

/** How a run's tool use is gated: "ask" surfaces approvals, "act" auto-approves. */
export type RunMode = 'ask' | 'act'

/** Whether an adapter's native session survives an adapter process restart. */
export type ResumeFidelity = 'native' | 'reconstructed' | 'none'

export type ArtifactRole = 'input' | 'result' | 'checkpoint' | 'tool_output' | 'log' | 'other'

import type { RuntimeFailure } from './failures'

// === Streaming events ========================================================
// Trimmed port of macOS protocol.ts's OutboundMessageDraft: only the event
// shapes the ACP client actually emits while an attempt streams. Field names
// match macOS exactly so PR2's IPC layer can stay wire-compatible if we ever
// share tooling.

export interface TextDeltaEvent {
  type: 'text_delta'
  text: string
}

export interface ThinkingDeltaEvent {
  type: 'thinking_delta'
  text: string
}

export interface ToolActivityEvent {
  type: 'tool_activity'
  name: string
  status: 'started' | 'completed' | 'failed'
  toolUseId?: string
  input?: Record<string, unknown>
}

export interface ToolResultDisplayEvent {
  type: 'tool_result_display'
  toolUseId: string
  name: string
  output: string
}

export type AdapterStreamEvent =
  | TextDeltaEvent
  | ThinkingDeltaEvent
  | ToolActivityEvent
  | ToolResultDisplayEvent

export type AdapterEventSink = (event: AdapterStreamEvent) => void

// === Capabilities ============================================================

export interface AdapterCapabilities {
  readonly resumeFidelity: ResumeFidelity
  readonly supportsNativeResume: boolean
  readonly supportsCancellation: boolean
  readonly acknowledgesCancellation: boolean
  readonly requiresPinnedWorker: boolean
  readonly supportsModelSwitching: boolean
  readonly supportsArtifactEmission: boolean
  readonly supportsTools: boolean
  readonly restartBehavior:
    | 'native_bindings_survive'
    | 'process_local_bindings_stale'
    | 'attempts_orphaned'
}

export type AdapterCapabilityKey =
  | 'nativeResume'
  | 'cancellationDispatch'
  | 'cancellationAck'
  | 'pinnedWorker'
  | 'modelSwitching'
  | 'artifactEmission'
  | 'toolSupport'
  | 'restartOrphanSemantics'

export type AdapterCapabilityExpectationStatus = 'required' | 'unsupported' | 'known_limitation'

export interface AdapterCapabilityExpectation {
  readonly status: AdapterCapabilityExpectationStatus
  readonly reason: string
  readonly followUpTicket?: string
}

/**
 * Where an adapter's credentials come from. Windows only ships local-user
 * adapters (Claude Code plus user-connected external ACP commands); the macOS
 * `managed_cloud` scope (pi-mono) has no Windows adapter. The kernel's
 * execution-policy boundary checks read this so a session pinned to a local
 * provider can never be rerouted to a managed one.
 */
export type AdapterCredentialScope = 'managed_cloud' | 'local_user'

export interface AdapterCapabilityMatrixEntry {
  readonly adapterId: string
  readonly credentialScope: AdapterCredentialScope
  readonly expectations: Record<AdapterCapabilityKey, AdapterCapabilityExpectation>
}

const required = (reason: string): AdapterCapabilityExpectation => ({ status: 'required', reason })
const unsupported = (reason: string): AdapterCapabilityExpectation => ({
  status: 'unsupported',
  reason
})
const knownLimitation = (reason: string, followUpTicket: string): AdapterCapabilityExpectation => ({
  status: 'known_limitation',
  reason,
  followUpTicket
})

export const ADAPTER_CAPABILITY_MATRIX = {
  // "acp" is Claude Code: the bundled @agentclientprotocol/claude-agent-acp bridge
  // spawned as a node subprocess. The id stays "acp" for parity with macOS.
  acp: {
    adapterId: 'acp',
    credentialScope: 'local_user',
    expectations: {
      nativeResume: required('ACP exposes native session ids and session/resume.'),
      cancellationDispatch: required('ACP exposes session/cancel dispatch.'),
      cancellationAck: knownLimitation(
        'ACP cancellation is fire-and-forget; no terminal ack is exposed yet.',
        'win-agents-cancel-ack'
      ),
      pinnedWorker: unsupported(
        'ACP bindings are resumable by native session id and do not require process-local pinning.'
      ),
      modelSwitching: required('ACP supports session/set_model during open and resume.'),
      artifactEmission: unsupported('ACP adapter does not emit artifact references yet.'),
      toolSupport: required(
        'ACP session/update tool events are projected into canonical adapter events.'
      ),
      restartOrphanSemantics: required(
        'Native-resumable bindings survive adapter restarts; active attempts are abandoned.'
      )
    }
  },
  openclaw: {
    adapterId: 'openclaw',
    credentialScope: 'local_user',
    expectations: {
      nativeResume: required(
        'OpenClaw ACP exposes native sessions through the Gateway-backed ACP bridge.'
      ),
      cancellationDispatch: required(
        'OpenClaw ACP accepts cancellation through the shared ACP interrupt path.'
      ),
      cancellationAck: knownLimitation(
        'OpenClaw cancellation resolves locally without an independent adapter ack.',
        'win-agents-cancel-ack'
      ),
      pinnedWorker: unsupported(
        'OpenClaw ACP sessions are native and do not require process-local pinned workers.'
      ),
      modelSwitching: unsupported(
        'OpenClaw ACP does not expose session/set_model; model selection is configured in the OpenClaw gateway/agent.'
      ),
      artifactEmission: unsupported('OpenClaw ACP adapter does not emit artifact references yet.'),
      toolSupport: unsupported(
        'OpenClaw ACP rejects per-session MCP servers; Omi tools are unavailable until configured through the OpenClaw gateway/agent.'
      ),
      restartOrphanSemantics: required(
        'Native-resumable OpenClaw bindings survive adapter restarts; active attempts are abandoned.'
      )
    }
  },
  hermes: {
    adapterId: 'hermes',
    credentialScope: 'local_user',
    expectations: {
      // Hermes ACP sessions live in the running server's in-memory session
      // manager and are only valid for that process.
      nativeResume: unsupported(
        'Hermes ACP session ids are process-local and are stale after adapter process restart.'
      ),
      cancellationDispatch: required('Hermes supports cancellation dispatch for active attempts.'),
      cancellationAck: knownLimitation(
        'Hermes cancellation is dispatchable but no terminal adapter ack is exposed yet.',
        'win-agents-cancel-ack'
      ),
      pinnedWorker: required(
        'Hermes keeps session state in the adapter process and must stay worker-pinned while active.'
      ),
      modelSwitching: required('Hermes supports model selection during session open and resume.'),
      artifactEmission: unsupported('Hermes ACP adapter does not emit artifact references yet.'),
      toolSupport: required('Hermes projects tool calls through canonical adapter tool events.'),
      restartOrphanSemantics: required(
        'Process-local Hermes bindings are stale after adapter restarts; active attempts are abandoned.'
      )
    }
  },
  // Codex is net-new on Windows (no macOS precedent). Driven through the
  // official ACP bridge (@agentclientprotocol/codex-acp) as a user-configured
  // external command. Capabilities are conservative until verified against the
  // real bridge — treat sessions as process-local like Hermes.
  codex: {
    adapterId: 'codex',
    credentialScope: 'local_user',
    expectations: {
      nativeResume: knownLimitation(
        'Codex ACP session persistence across bridge restarts is unverified; treated as process-local.',
        'win-agents-codex-verify'
      ),
      cancellationDispatch: required('Codex ACP accepts session/cancel dispatch.'),
      cancellationAck: knownLimitation(
        'Codex cancellation resolves locally without an independent adapter ack.',
        'win-agents-cancel-ack'
      ),
      pinnedWorker: required(
        'Codex sessions are treated as process-local and must stay worker-pinned while active.'
      ),
      modelSwitching: knownLimitation(
        'Codex ACP session/set_model support is unverified; model selection is configured in the Codex CLI.',
        'win-agents-codex-verify'
      ),
      artifactEmission: unsupported('Codex ACP adapter does not emit artifact references yet.'),
      toolSupport: required('Codex projects tool calls through canonical adapter tool events.'),
      restartOrphanSemantics: required(
        'Process-local Codex bindings are stale after adapter restarts; active attempts are abandoned.'
      )
    }
  }
} as const satisfies Record<string, AdapterCapabilityMatrixEntry>

export type ProductionAdapterId = keyof typeof ADAPTER_CAPABILITY_MATRIX

export const PRODUCTION_ADAPTER_IDS = [
  'acp',
  'openclaw',
  'hermes',
  'codex'
] as const satisfies readonly ProductionAdapterId[]

export function isProductionAdapterId(adapterId: string): adapterId is ProductionAdapterId {
  return Object.prototype.hasOwnProperty.call(ADAPTER_CAPABILITY_MATRIX, adapterId)
}

/**
 * Windows ships no placeholder adapters (macOS's `a2a`/`pi-mono` scaffolds are
 * not ported). The kernel adapter-registry still calls this guard before
 * registering a factory, so it exists for parity and always returns false.
 */
export function isPlaceholderAdapterId(_adapterId: string): boolean {
  return false
}

export function adapterCredentialScopeFor(adapterId: ProductionAdapterId): AdapterCredentialScope {
  return ADAPTER_CAPABILITY_MATRIX[adapterId].credentialScope
}

function restartBehaviorFor(
  expectations: Record<AdapterCapabilityKey, AdapterCapabilityExpectation>
): AdapterCapabilities['restartBehavior'] {
  if (expectations.nativeResume.status === 'required') return 'native_bindings_survive'
  if (expectations.pinnedWorker.status === 'required') return 'process_local_bindings_stale'
  return 'attempts_orphaned'
}

export function adapterCapabilitiesFor(adapterId: ProductionAdapterId): AdapterCapabilities {
  const expectations = ADAPTER_CAPABILITY_MATRIX[adapterId].expectations
  return {
    resumeFidelity: expectations.nativeResume.status === 'required' ? 'native' : 'none',
    supportsNativeResume: expectations.nativeResume.status === 'required',
    supportsCancellation: expectations.cancellationDispatch.status === 'required',
    acknowledgesCancellation: expectations.cancellationAck.status === 'required',
    requiresPinnedWorker: expectations.pinnedWorker.status === 'required',
    supportsModelSwitching: expectations.modelSwitching.status === 'required',
    supportsArtifactEmission: expectations.artifactEmission.status === 'required',
    supportsTools: expectations.toolSupport.status === 'required',
    restartBehavior: restartBehaviorFor(expectations)
  }
}

// === Prompt & tool shapes ====================================================

export type PromptBlock =
  | { type: 'text'; text: string }
  | { type: 'image'; data: string; mimeType: string }

export interface ToolDef {
  name: string
  description: string
  inputSchema: Record<string, unknown>
}

// === Binding / attempt contracts =============================================

export interface OpenBindingInput {
  /** Omi-owned correlation id. Adapters must not treat this as their native session id. */
  sessionId: string
  cwd: string
  model?: string
  systemPrompt?: string
  mcpServers?: Record<string, unknown>[]
  metadata?: Record<string, unknown>
}

export interface ResumeBindingInput extends OpenBindingInput {
  /** Adapter-owned native session id recovered from the active binding. */
  adapterNativeSessionId: string
}

export interface AdapterBindingHandle {
  /**
   * Kernel-owned persistent binding row id. Populated once the kernel
   * (agentKernel/) persists a binding; unset for the pre-kernel in-memory task
   * path and for freshly-opened handles the adapter returns. The worker pool
   * keys pinned-worker reuse on this.
   */
  bindingId?: string
  /** Omi-owned correlation id. */
  sessionId: string
  adapterId: string
  /** Adapter-owned native session id. */
  adapterNativeSessionId: string
  resumeFidelity: ResumeFidelity
  cwd: string
  model?: string
  metadata?: Record<string, unknown>
}

export type OpenedBinding = AdapterBindingHandle

export interface AdapterAttemptContext {
  /** Omi-owned correlation id for host bookkeeping only. */
  sessionId: string
  /**
   * Host-owned identity fields. Optional so the pre-kernel in-memory task path
   * (which has no owner/request/client context) still satisfies the contract;
   * the kernel (agentKernel/) always supplies them. Adapter payloads must never
   * override the ownerId — it is authoritative host identity (INV-AGENT).
   */
  ownerId?: string
  requestId?: string
  clientId?: string
  runId: string
  attemptId: string
  binding: AdapterBindingHandle
  prompt: PromptBlock[]
  mode: RunMode
  model?: string
  tools?: ToolDef[]
  metadata?: Record<string, unknown>
}

export interface AdapterArtifactReference {
  kind: string
  role: ArtifactRole
  uri: string
  displayName?: string | null
  mimeType?: string | null
  contentHash?: string | null
  sizeBytes?: number | null
  metadata?: Record<string, unknown>
}

export interface AdapterAttemptResult {
  text: string
  costUsd?: number
  inputTokens?: number
  outputTokens?: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
  /** Adapter-owned native session id. */
  adapterSessionId: string
  terminalStatus: 'succeeded' | 'failed' | 'cancelled'
  failure?: RuntimeFailure
  artifacts?: AdapterArtifactReference[]
}

export interface CancelAttemptContext {
  sessionId: string
  /**
   * Host-owned identity fields, same contract as AdapterAttemptContext: optional
   * so the pre-kernel in-memory task path still satisfies it, always supplied by
   * the kernel. Adapter payloads must never override the ownerId (INV-AGENT).
   */
  ownerId?: string
  requestId?: string
  clientId?: string
  runId?: string
  attemptId?: string
  binding?: AdapterBindingHandle
}

export interface CancelDispatchResult {
  accepted: boolean
  dispatchAttempted: boolean
  adapterAcknowledged: boolean
  message?: string
}

export interface RuntimeAdapter {
  readonly adapterId: string
  readonly capabilities: AdapterCapabilities

  start(): Promise<void>
  stop(): Promise<void>

  openBinding(input: OpenBindingInput): Promise<OpenedBinding>
  resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding>

  executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult>

  cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult>
  closeBinding?(binding: AdapterBindingHandle): Promise<void>

  /**
   * Return the MCP server configuration this adapter actually passes to its
   * underlying session. Adapters that strip per-session MCP servers (e.g.
   * OpenClaw, which rejects them) should return an empty array so the kernel's
   * binding-compatibility hash reflects what the adapter truly saw. Adapters
   * that pass MCP servers through unchanged omit this; the kernel treats an
   * absent implementation as identity (passthrough).
   */
  effectiveMcpServers?(mcpServers: Record<string, unknown>[]): Record<string, unknown>[]
}

// === Contract assertions =====================================================
// Guard against the id-conflation bugs macOS's tests caught: an adapter must
// never echo the Omi correlation id back as its native session id.

export function assertAdapterBindingContract(
  binding: AdapterBindingHandle,
  operation: string
): void {
  if (!binding.adapterNativeSessionId) {
    throw new Error(`${operation} returned an empty adapterNativeSessionId`)
  }
  if (binding.adapterNativeSessionId === binding.sessionId) {
    throw new Error(
      `${operation} conflated Omi sessionId ${binding.sessionId} with adapterNativeSessionId`
    )
  }
}

export function assertAdapterAttemptResultContract(
  context: AdapterAttemptContext,
  result: AdapterAttemptResult,
  operation: string
): void {
  if (!result.adapterSessionId) {
    throw new Error(`${operation} returned an empty adapterSessionId`)
  }
  if (result.adapterSessionId === context.sessionId) {
    throw new Error(
      `${operation} conflated Omi sessionId ${context.sessionId} with adapter native session id`
    )
  }
  if (result.adapterSessionId !== context.binding.adapterNativeSessionId) {
    throw new Error(
      `${operation} returned adapterSessionId ${result.adapterSessionId} for binding ${context.binding.adapterNativeSessionId}`
    )
  }
}
