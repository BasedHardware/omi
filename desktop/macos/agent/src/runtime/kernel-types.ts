import type {
  AdapterBinding,
  AgentArtifact,
  AgentDelegation,
  AgentEvent,
  AgentGrant,
  AgentRun,
  AgentSession,
  ArtifactLifecycleState,
  ArtifactRole,
  AttemptStatus,
  NewAgentGrant,
  RunAttempt,
  RunMode,
  AgentExecutionRole,
  ProviderBoundary,
  RunStatus,
  DelegationMode,
} from "./types.js";
import type {
  RunToolCapabilityRejectCode,
} from "./run-tool-capability.js";
import type { ToolInvocationSummary } from "./tool-invocation-ledger.js";
import type { PromptBlock, ToolDef, RuntimeAdapter, AdapterBindingHandle } from "../adapters/interface.js";
import type { AdapterRegistry } from "./adapter-registry.js";
import type { OmiArtifactStorage } from "./artifact-storage.js";
import type { DesktopActionQueueItem } from "./desktop-action-queue.js";
import type { DesktopContextPacketBuildInput } from "./desktop-context-packet.js";
import type { ResolveSurfaceSessionResult, SurfaceRef } from "./surface-session.js";
import type { AgentStore } from "./types.js";
import type { ContextSnapshotProjection } from "../protocol.js";
import type {
  DesktopArtifactDelivery,
  DesktopAttentionOverride,
  DesktopCoordinatorDispatch,
  DesktopMemoryCandidate,
  DesktopTaskCandidate,
  NewDesktopCoordinatorDispatch,
} from "./types.js";

export type { ResolveSurfaceSessionResult, SurfaceRef };

export interface KernelSessionResolutionInput {
  sessionId?: string;
  ownerId: string;
  surfaceKind: string;
  executionRole?: AgentExecutionRole;
  providerBoundary?: ProviderBoundary;
  externalRefKind?: string;
  externalRefId?: string;
  title?: string;
  defaultAdapterId?: string;
  modelProfile?: string | null;
  executionProfileSource?: "creation" | "child_derivation";
}

export interface ExecuteAgentRunInput extends KernelSessionResolutionInput {
  clientId: string;
  requestId: string;
  producingTurnId?: string;
  idempotencyKey?: string;
  prompt: string;
  promptBlocks?: PromptBlock[];
  systemPrompt?: string;
  /** Stable cache key for the process-local provider binding; never includes turn history. */
  systemPromptCacheIdentity?: string;
  /** Privacy-safe, per-turn context identity carried in binding/usage diagnostics. */
  dynamicContextIdentity?: string;
  /** Privacy-safe plan identity used to correlate cache behavior across surfaces. */
  contextPlanId?: string;
  mode?: RunMode;
  adapterId?: string;
  cwd?: string;
  model?: string;
  mcpServers?: Record<string, unknown>[];
  maxAttempts?: number;
  tools?: ToolDef[];
  metadata?: Record<string, unknown>;
  parentRunId?: string;
  recoverAfterError?: (error: unknown) => Promise<boolean>;
  attachmentMetadataJson?: string | null;
  surfaceContextJson?: string | null;
  imagePresent?: boolean;
  attachments?: Array<{
    attachmentId: string;
    displayName: string;
    mimeType: string;
    sizeBytes?: number;
    uri?: string;
  }>;
  expectedContextSnapshotVersion?: string;
  expectedContextSnapshotGeneration?: number;
  expectedContextRendererFingerprint?: string;
  expectedCapabilityVersion?: string;
  /** Kernel-populated immutable admission snapshot; callers cannot select it. */
  admittedContextSnapshot?: ContextSnapshotProjection;
  /** Revokes adapter execution when the authorizing parent invocation expires. */
  authoritySignal?: AbortSignal;
}

export interface BeginExternalSurfaceRunInput {
  ownerId: string;
  sessionId: string;
  turnId: string;
  prompt: string;
  mode: RunMode;
  clientId: string;
  requestId: string;
}

export interface BeginExternalSurfaceRunResult {
  ownerId: string;
  sessionId: string;
  turnId: string;
  runId: string;
  attemptId: string;
  duplicate: boolean;
}

export interface CompleteExternalSurfaceRunInput {
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  terminalStatus: "completed" | "failed" | "cancelled";
  errorCode?: string;
}

export interface CompleteExternalSurfaceRunResult {
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  terminalStatus: "completed" | "failed" | "cancelled";
  duplicate: boolean;
}

export type ExternalSurfaceAuthorityErrorCode =
  | "invalid_external_request"
  | "owner_mismatch"
  | "invalid_external_surface"
  | "external_run_identity_collision"
  | "run_mismatch"
  | "attempt_mismatch"
  | "attempt_superseded"
  | "run_terminal"
  | "attempt_terminal"
  | "external_invocations_pending"
  | "permission_target_rejected"
  | "permission_route_rejected"
  | "permission_request_not_authorized"
  | "pill_management_intent_required"
  | "sql_write_rejected";

export class ExternalSurfaceAuthorityError extends Error {
  constructor(
    readonly code: ExternalSurfaceAuthorityErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "ExternalSurfaceAuthorityError";
  }
}

export interface KernelRunResult {
  session: AgentSession;
  run: AgentRun;
  attempt: RunAttempt;
  artifacts: AgentArtifact[];
  adapterSessionId: string | null;
  terminalStatus: "succeeded" | "failed" | "cancelled";
  text: string;
  completionDeltaArtifacts?: AgentArtifact[];
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
  executionRole?: AgentExecutionRole;
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
  toolInvocations: ToolInvocationSummary[];
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
  maxAttempts?: number;
  recoverAfterError?: (error: unknown) => Promise<boolean>;
  metadata?: Record<string, unknown>;
  authoritySignal?: AbortSignal;
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
  /** When set, the caller session must be a coordinator owned by ownerId. */
  callerSessionId?: string;
  /**
   * Trusted desktop/user control may spawn without a caller session.
   * Agent-originated spawns must supply callerSessionId instead.
   */
  trustedUserSpawn?: boolean;
  cwd?: string;
  model?: string;
  mcpServers?: Record<string, unknown>[];
  mode?: RunMode;
  maxAttempts?: number;
  recoverAfterError?: (error: unknown) => Promise<boolean>;
  metadata?: Record<string, unknown>;
  /**
   * Restricts the child to the intersection of these canonical Omi tool
   * names with its role/adapter-computed tool set. Empty intersection =
   * no tools (fail closed).
   */
  toolPolicy?: { allowedToolNames: string[] };
  /** Kernel-admitted producer snapshot for trusted top-level surface spawns. */
  admittedContextSnapshot?: ContextSnapshotProjection;
  authoritySignal?: AbortSignal;
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
  maxAttempts?: number;
  recoverAfterError?: (error: unknown) => Promise<boolean>;
  metadata?: Record<string, unknown>;
  /**
   * Restricts the child to the intersection of these canonical Omi tool
   * names with its role/adapter-computed tool set. Empty intersection =
   * no tools (fail closed).
   */
  toolPolicy?: { allowedToolNames: string[] };
  authoritySignal?: AbortSignal;
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

/** Adapter-scoped recovery applied by the kernel to every run entry point. */
export type KernelRunRecoveryPolicy = (
  adapterId: string,
) => Pick<ExecuteAgentRunInput, "maxAttempts" | "recoverAfterError">;

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
  recoverRunInput?: KernelRunRecoveryPolicy;
  onToolCapabilityRejected?: (code: RunToolCapabilityRejectCode) => void;
  /**
   * Canonical execution-profile repository. Production uses the immutable
   * SQLite profile reader; tests with synthetic adapters may inject an
   * equivalent authoritative repository instead of reviving legacy columns.
   */
  toolCapabilityProfileForSession?: (sessionId: string) => {
    generation: number;
    adapterId: string;
    executionRole: AgentExecutionRole;
  };
}
