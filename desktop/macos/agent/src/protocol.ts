// JSON lines protocol between Swift app and Node.js agent runtime
// Extended from agent protocol with authentication message types

// === Swift → Bridge (stdin) ===

export const PROTOCOL_VERSION = 2 as const;
export const RUNTIME_CAPABILITIES = [
  "journal_import_remote_turn",
  "runtime_adapter_availability",
  "chat_first_capability_projection",
] as const;
export type ProtocolVersion = typeof PROTOCOL_VERSION;

export interface ProtocolEnvelope {
  protocolVersion: ProtocolVersion;
  requestId: string;
  clientId: string;
  /** Signed-in Omi/Firebase uid used to scope persisted runtime state. */
  ownerId?: string;
}

export interface CanonicalCorrelation {
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  eventId?: string;
}

export interface QueryMessage extends ProtocolEnvelope {
  type: "query";
  sessionId: string;
  producingTurnId?: string;
  prompt: string;
  mode?: "ask" | "act";
  imageBase64?: string;
  attachments?: QueryAttachment[];
  /** Freshness precondition only; it cannot select or mutate context. */
  expectedContextSnapshotVersion?: string;
  expectedContextSnapshotGeneration?: number;
  expectedContextRendererFingerprint?: string;
  expectedCapabilityVersion?: string;
  /**
   * Per-turn reasoning-effort lane: "adaptive" for typed chat (model decides
   * its own thinking depth), "fast" for PTT/voice (speed-optimized, no
   * thinking). Relayed opaquely to the desktop backend as the
   * x-omi-reasoning-effort header; never interpreted by the runtime.
   */
  reasoningEffort?: string;
}

export interface QueryAttachment {
  attachmentId: string;
  displayName: string;
  mimeType: string;
  sizeBytes?: number;
  uri?: string;
}

export interface AuthorizedToolExecutionResultMessage {
  type: "authorized_tool_execution_result";
  protocolVersion: ProtocolVersion;
  invocationId: string;
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  profileGeneration: number;
  manifestVersion: number;
  manifestDigest: string;
  daemonBootEpoch: string;
  executionGeneration: number;
  inputHash: string;
  outcome: "succeeded" | "failed";
  result: string;
}

export interface ControlToolRequestMessage extends ProtocolEnvelope {
  type: "control_tool";
  name: string;
  input: Record<string, unknown>;
}

export interface DirectControlToolRequestMessage extends ProtocolEnvelope {
  type: "direct_control_tool";
  ownerId: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ExternalSurfaceRunBeginMessage extends ProtocolEnvelope {
  type: "external_surface_run_begin";
  ownerId: string;
  sessionId: string;
  turnId: string;
  prompt: string;
  mode: "ask" | "act";
}

export interface ExternalSurfaceToolInvokeMessage extends ProtocolEnvelope {
  type: "external_surface_tool_invoke";
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  invocationId: string;
  toolName: string;
  input: Record<string, unknown>;
}

export interface ExternalSurfaceRunCompleteMessage extends ProtocolEnvelope {
  type: "external_surface_run_complete";
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  terminalStatus: "completed" | "failed" | "cancelled";
  errorCode?: string;
}

export interface StopMessage {
  type: "stop";
}

export interface InterruptMessage extends ProtocolEnvelope, CanonicalCorrelation {
  type: "interrupt";
}

export interface InvalidateSessionMessage extends ProtocolEnvelope {
  type: "invalidate_session";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
}

/**
 * Pre-visibility owner barrier. Swift sends this only while holding the exact
 * previous-owner transition cleanup capability and waits for the correlated
 * receipt before exposing the replacement owner.
 */
export interface RevokeOwnerRuntimeMessage extends ProtocolEnvelope {
  type: "revoke_owner_runtime";
  ownerId: string;
}

export interface ImportLegacyMainChatSessionsMessage extends ProtocolEnvelope {
  type: "import_legacy_main_chat_sessions";
  entries: Array<{ chatId: string; agentSessionId: string }>;
}

/** A warmup can identify a pinned session/profile, but cannot configure it. */
export interface WarmupMessage extends ProtocolEnvelope {
  type: "warmup";
  sessionId: string;
  profileGeneration: number;
}

export interface ConfigureDefaultExecutionProfileMessage extends ProtocolEnvelope {
  type: "configure_default_execution_profile";
  adapterId: string;
  modelProfile: string | null;
  workingDirectory: string;
  expectedPreferenceGeneration?: number;
}

export interface ResolveSurfaceSessionMessage extends ProtocolEnvelope {
  type: "resolve_surface_session";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  title?: string;
  /** Applied atomically only when this resolve creates the surface session. */
  creationProfile?: {
    adapterId: string;
    modelProfile: string | null;
    workingDirectory: string;
  };
  /**
   * Ephemeral server-derived capability, accepted only for the main Chat
   * surface.  It is never persisted to the kernel journal or preferences.
   */
  chatFirstCapability?: {
    chatFirstUi: boolean;
    controlGeneration: number;
  };
}

export interface MigrateSessionExecutionProfileMessage extends ProtocolEnvelope {
  type: "migrate_session_execution_profile";
  sessionId: string;
  expectedProfileGeneration: number;
  adapterId: string;
  modelProfile: string | null;
  workingDirectory: string;
  reason: "user_requested";
}

export type ContextSourceKind =
  | "identity"
  | "memories"
  | "goals"
  | "tasks"
  | "screen"
  | "workspace"
  | "surface";

export type ContextSourceOutcome = "available" | "empty" | "unavailable" | "redacted";

export interface ContextSourceUpdateMessage extends ProtocolEnvelope {
  type: "context_source_update";
  sessionId: string;
  surfaceKind: string;
  source: ContextSourceKind;
  sourceRevision: string;
  outcome: ContextSourceOutcome;
  capturedAtMs: number;
  expiresAtMs?: number;
  payload: Record<string, unknown>;
}

export interface GetContextSnapshotMessage extends ProtocolEnvelope {
  type: "get_context_snapshot";
  sessionId: string;
  surfaceKind: string;
}

export interface JournalTurnWireInput {
  turnId?: string;
  producerId?: string;
  role?: "user" | "assistant";
  origin?: string;
  status?: string;
  content?: string;
  contentBlocks?: unknown[];
  resources?: unknown[];
  metadataJson?: string;
  createdAtMs?: number;
}

export function assertPublicJournalRecordAuthority(input: unknown): asserts input is JournalTurnWireInput {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Journal turn input must be an object");
  }
  for (const field of ["delivery", "producingRunId", "producingAttemptId"] as const) {
    if (Object.prototype.hasOwnProperty.call(input, field)) {
      throw new Error(`Journal ${field} is kernel-owned`);
    }
  }
}

export function assertPublicJournalUpdateAuthority(input: unknown): asserts input is Record<string, unknown> {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Journal update input must be an object");
  }
  for (const field of ["producingRunId", "producingAttemptId"] as const) {
    if (Object.prototype.hasOwnProperty.call(input, field)) {
      throw new Error(`Journal ${field} is kernel-owned`);
    }
  }
}

export interface JournalRecordTurnMessage extends ProtocolEnvelope {
  type: "journal_record_turn";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turn: JournalTurnWireInput;
}

export interface JournalRecordExchangeMessage extends ProtocolEnvelope {
  type: "journal_record_exchange";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turns: JournalTurnWireInput[];
}

export interface JournalRemoteTurnWireInput {
  remoteId: string;
  canonicalTurnId?: string;
  role: "user" | "assistant";
  content: string;
  contentBlocks: unknown[];
  resources: unknown[];
  metadataJson: string;
  createdAtMs: number;
}

/**
 * Bounded upgrade input for backend rows written before the kernel journal was
 * authoritative. The runtime, not Swift, resolves the canonical conversation
 * and owns the imported turn projection.
 */
export interface JournalImportRemoteTurnMessage extends ProtocolEnvelope {
  type: "journal_import_remote_turn";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turn: JournalRemoteTurnWireInput;
}

export function assertJournalRemoteTurnInput(
  input: unknown,
): asserts input is JournalRemoteTurnWireInput {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Remote journal turn input must be an object");
  }
  const turn = input as Partial<JournalRemoteTurnWireInput>;
  if (typeof turn.remoteId !== "string" || !turn.remoteId.trim()) {
    throw new Error("Remote journal turn requires remoteId");
  }
  if (turn.canonicalTurnId !== undefined
      && (typeof turn.canonicalTurnId !== "string" || !turn.canonicalTurnId.trim())) {
    throw new Error("Remote journal canonicalTurnId must be non-empty when provided");
  }
  if (turn.role !== "user" && turn.role !== "assistant") {
    throw new Error("Remote journal turn requires a valid role");
  }
  if (typeof turn.content !== "string"
      || !Array.isArray(turn.contentBlocks)
      || !Array.isArray(turn.resources)
      || typeof turn.metadataJson !== "string"
      || typeof turn.createdAtMs !== "number"
      || !Number.isFinite(turn.createdAtMs)) {
    throw new Error("Remote journal turn has an invalid payload");
  }
}

export interface JournalUpdateTurnMessage extends ProtocolEnvelope {
  type: "journal_update_turn";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  update: Record<string, unknown>;
}

export interface JournalTerminalizeTurnMessage extends ProtocolEnvelope {
  type: "journal_terminalize_turn";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  terminalization: {
    turnId: string;
    producingRunId: string;
    producingAttemptId: string;
    disposition: "accept" | "discard";
    content?: string;
    replaceContentBlocks?: unknown[];
    replaceResources?: unknown[];
  };
}

export function journalTerminalizationDisposition(input: unknown): "accept" | "discard" {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Journal terminalization input must be an object");
  }
  const disposition = (input as { disposition?: unknown }).disposition;
  if (disposition !== "accept" && disposition !== "discard") {
    throw new Error("Journal terminalization requires an explicit accept or discard disposition");
  }
  return disposition;
}

export interface JournalListTurnsMessage extends ProtocolEnvelope {
  type: "journal_list_turns";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  afterTurnSeq?: number;
  limit?: number;
}

export interface JournalClearTurnsMessage extends ProtocolEnvelope {
  type: "journal_clear_turns";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  expectedGeneration: number;
}

/**
 * Privileged local-only append for server-validated chat-first blocks. The
 * capability and producing run/attempt bind this mutation to the assistant
 * turn that invoked `render_chat_blocks`; Swift cannot select an arbitrary
 * journal turn.
 */
export interface AppendChatFirstBlocksMessage extends ProtocolEnvelope {
  type: "append_chat_first_blocks";
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  capabilityRef: string;
  controlGeneration: number;
  blocks: unknown[];
}

/** Kernel-owned selection for one persisted, tail-actionable question card. */
export interface RecordQuestionInteractionReplyMessage extends ProtocolEnvelope {
  type: "record_question_interaction_reply";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  ownerId: string;
  sessionId: string;
  questionId: string;
  optionId: string;
  controlGeneration: number;
}

/**
 * Privileged local receipt for an ordered server-owned deterministic-tier
 * batch. Swift only transports typed server responses; the kernel derives
 * journal identities and enforces tail suppression in one transaction.
 */
export interface MaterializeChatFirstIntentsMessage extends ProtocolEnvelope {
  type: "materialize_chat_first_intents";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  ownerId: string;
  sessionId: string;
  controlGeneration: number;
  intents: Array<{
    intentId: string;
    continuityKey: string;
    source: "daily_opener" | "capture_arrival" | "deferral_reraise" | "agent_judgment";
    blocks: unknown[];
  }>;
}

/** Read restart-safe kernel receipts to include in the next server fetch/ack. */
export interface ListChatFirstMaterializationReceiptsMessage extends ProtocolEnvelope {
  type: "list_chat_first_materialization_receipts";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  ownerId: string;
  sessionId: string;
  controlGeneration: number;
  limit?: number;
}

/** Drop only receipts that the server accepted in a successful fetch/ack call. */
export interface AcknowledgeChatFirstMaterializationReceiptsMessage extends ProtocolEnvelope {
  type: "acknowledge_chat_first_materialization_receipts";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  ownerId: string;
  sessionId: string;
  controlGeneration: number;
  receipts: Array<{ intentId: string; receiptId: string }>;
}

export interface EnsureAgentSpawnJournalMessage extends ProtocolEnvelope {
  type: "ensure_agent_spawn_journal";
  ownerId: string;
  sessionId: string;
  runId: string;
}

export interface JournalBackendSyncResultMessage extends ProtocolEnvelope {
  type: "journal_backend_sync_result";
  ownerId: string;
  turnId: string;
  conversationId: string;
  conversationGeneration: number;
  attemptCount: number;
  deliveryGeneration: number;
  payloadHash: string;
  ok: boolean;
  remoteId?: string;
  errorCode?: string;
}

export interface JournalBackendDeleteResultMessage extends ProtocolEnvelope {
  type: "journal_backend_delete_result";
  ownerId: string;
  operationId: string;
  conversationId: string;
  conversationGeneration: number;
  attemptCount: number;
  deliveryGeneration: number;
  payloadHash: string;
  ok: boolean;
  errorCode?: string;
}

export interface JournalBackendReconcileResultMessage extends ProtocolEnvelope {
  type: "journal_backend_reconcile_result";
  ownerId: string;
  reconcileId: string;
  conversationId: string;
  pageCursor: string | null;
  nextCursor?: string | null;
  ok: boolean;
  turns?: Record<string, unknown>[];
  hasMore?: boolean;
  errorCode?: string;
}

/** Swift's physical transport result for the separate deferral outbox. */
export interface ChatFirstDeferralDeliveryResultMessage extends ProtocolEnvelope {
  type: "chat_first_deferral_delivery_result";
  ownerId: string;
  continuityKey: string;
  deliveryGeneration: number;
  payloadHash: string;
  ok: boolean;
  errorCode?: string;
}

/** Swift pushes a refreshed Firebase ID token to the bridge (piMono mode) */
export interface RefreshTokenMessage {
  type: "refresh_token";
  token: string;
  ownerId: string;
}

/** Swift establishes the signed-in owner even when a local adapter needs no Firebase token. */
export interface RefreshOwnerMessage {
  type: "refresh_owner";
  ownerId: string;
}

export type InboundMessage =
  | QueryMessage
  | AuthorizedToolExecutionResultMessage
  | ControlToolRequestMessage
  | DirectControlToolRequestMessage
  | ExternalSurfaceRunBeginMessage
  | ExternalSurfaceToolInvokeMessage
  | ExternalSurfaceRunCompleteMessage
  | StopMessage
  | InterruptMessage
  | InvalidateSessionMessage
  | RevokeOwnerRuntimeMessage
  | ImportLegacyMainChatSessionsMessage
  | WarmupMessage
  | ConfigureDefaultExecutionProfileMessage
  | ResolveSurfaceSessionMessage
  | MigrateSessionExecutionProfileMessage
  | ContextSourceUpdateMessage
  | GetContextSnapshotMessage
  | JournalRecordTurnMessage
  | JournalRecordExchangeMessage
  | JournalImportRemoteTurnMessage
  | JournalUpdateTurnMessage
  | JournalTerminalizeTurnMessage
  | JournalListTurnsMessage
  | JournalClearTurnsMessage
  | AppendChatFirstBlocksMessage
  | RecordQuestionInteractionReplyMessage
  | MaterializeChatFirstIntentsMessage
  | ListChatFirstMaterializationReceiptsMessage
  | AcknowledgeChatFirstMaterializationReceiptsMessage
  | EnsureAgentSpawnJournalMessage
  | JournalBackendSyncResultMessage
  | JournalBackendDeleteResultMessage
  | JournalBackendReconcileResultMessage
  | ChatFirstDeferralDeliveryResultMessage
  | RefreshTokenMessage
  | RefreshOwnerMessage;

const INBOUND_RESPONSE_MESSAGE_TYPES = new Set<InboundMessage["type"]>([
  "authorized_tool_execution_result",
  "journal_backend_sync_result",
  "journal_backend_delete_result",
  "journal_backend_reconcile_result",
  "chat_first_deferral_delivery_result",
]);

/** Response handlers log invalid replies locally; they never echo request errors back to Swift. */
export function isInboundResponseMessage(message: Pick<InboundMessage, "type">): boolean {
  return INBOUND_RESPONSE_MESSAGE_TYPES.has(message.type);
}

// === Bridge → Swift (stdout) ===

export interface OutboundEnvelope {
  protocolVersion: ProtocolVersion;
  requestId?: string;
  clientId?: string;
}

export interface QueryScopedOutbound extends OutboundEnvelope, CanonicalCorrelation {
  adapterSessionId?: string;
}

export interface InitMessage extends OutboundEnvelope {
  type: "init";
  sessionId: string;
  agentControlTools: string[];
  runtimeVersion: string;
  runtimeCapabilities: string[];
  /** Exact registry projection used by Swift to build local-provider schemas. */
  runtimeAdapterIds: string[];
}

export interface TextDeltaMessage extends QueryScopedOutbound {
  type: "text_delta";
  text: string;
}

export interface ToolUseMessage extends QueryScopedOutbound {
  type: "tool_use";
  callId: string;
  /** Required together for executable Omi/Swift tool invocations; absent on display-only adapter events. */
  invocationId?: string;
  capabilityRef?: string;
  ownerId?: string;
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  name: string;
  input: Record<string, unknown>;
}

export interface AuthorizedToolExecutionMessage extends OutboundEnvelope {
  type: "authorized_tool_execution";
  invocationId: string;
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  profileGeneration: number;
  manifestVersion: number;
  manifestDigest: string;
  daemonBootEpoch: string;
  executionGeneration: number;
  capabilityRef: string;
  toolName: string;
  input: Record<string, unknown>;
  inputHash: string;
  effectClass: "read_only" | "idempotent_write" | "non_idempotent_write";
  retryPolicy: "safe_retry" | "never_auto_retry";
  surfaceKind: string;
  externalRefKind: string | null;
  externalRefId: string | null;
  originatingUserText: string;
  precedingAssistantText: string | null;
  runMode: "ask" | "act";
  chatMode: string | null;
  /** Present only for the server-authorized Main Chat structured-block tool. */
  chatFirstControlGeneration?: number;
  /** Bounded policy recovery telemetry; absent for ordinary authorized calls. */
  policyRecovery?: "permission_delegation_to_native";
}

export interface ExternalAuthorityError {
  code: string;
  message: string;
}

export interface ExternalSurfaceRunBeginResultMessage extends OutboundEnvelope {
  type: "external_surface_run_begin_result";
  ownerId: string;
  sessionId: string;
  turnId: string;
  ok: boolean;
  runId?: string;
  attemptId?: string;
  duplicate?: boolean;
  error?: ExternalAuthorityError;
}

export interface ExternalSurfaceToolResultMessage extends OutboundEnvelope {
  type: "external_surface_tool_result";
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  invocationId: string;
  ok: boolean;
  result?: string;
  error?: ExternalAuthorityError;
}

export interface ExternalSurfaceRunCompleteResultMessage extends OutboundEnvelope {
  type: "external_surface_run_complete_result";
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  ok: boolean;
  terminalStatus?: "completed" | "failed" | "cancelled";
  duplicate?: boolean;
  error?: ExternalAuthorityError;
}

export interface OwnerRuntimeRevokedMessage extends OutboundEnvelope {
  type: "owner_runtime_revoked";
  ownerId: string;
  ok: boolean;
  duplicate: boolean;
  revokedRunIds: string[];
  invalidatedBindingIds: string[];
  error?: ExternalAuthorityError;
}

export interface ResultMessage extends QueryScopedOutbound {
  type: "result";
  text: string;
  sessionId: string;
  terminalStatus?: "succeeded" | "failed" | "cancelled";
  failure?: RuntimeFailurePayload;
  costUsd?: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
  artifacts?: SerializedArtifact[];
  completionDeltaArtifacts?: SerializedArtifact[];
}

export interface SerializedArtifact {
  artifactId: string;
  sessionId: string;
  runId: string | null;
  attemptId: string | null;
  kind: string;
  role: string;
  uri: string;
  displayName: string | null;
  mimeType: string | null;
  contentHash: string | null;
  sizeBytes: number | null;
  lifecycleState: string;
  lifecycleUpdatedAtMs: number | null;
  metadata: Record<string, unknown>;
  createdAtMs: number;
}

export interface RuntimeFailurePayload {
  code: string;
  /** Closed failure taxonomy; `code` remains the detailed diagnostic key. */
  failureCode?: "authentication" | "quota_exceeded" | "invalid_request" | "timeout" | "transport_interruption" | "adapter_unavailable" | "adapter_incompatible" | "bridge_start_failed" | "provider_setup_needed" | "malformed_or_oversized_tool_result" | "cancelled" | "stale_owner" | "policy_denied" | "unknown";
  userMessage: string;
  technicalMessage?: string;
  source?: string;
  adapterId?: string;
  provider?: string;
  retryable?: boolean;
}

export interface ToolActivityMessage extends QueryScopedOutbound {
  type: "tool_activity";
  name: string;
  status: "started" | "progress" | "completed" | "failed";
  toolUseId?: string;
  input?: Record<string, unknown>;
}

export interface ToolResultDisplayMessage extends QueryScopedOutbound {
  type: "tool_result_display";
  toolUseId: string;
  name: string;
  output: string;
}

export interface ThinkingDeltaMessage extends QueryScopedOutbound {
  type: "thinking_delta";
  text: string;
}

export interface ErrorMessage extends QueryScopedOutbound {
  type: "error";
  message: string;
  failure?: RuntimeFailurePayload;
}

/** Sent when ACP requires user authentication (OAuth) */
export interface AuthRequiredMessage {
  type: "auth_required";
  methods: AuthMethod[];
  authUrl?: string;
}

export interface AuthMethod {
  id: string;
  type: "agent_auth" | "env_var" | "terminal";
  displayName?: string;
  args?: string[];
  env?: Record<string, string>;
}

/** Sent after successful authentication */
export interface AuthSuccessMessage {
  type: "auth_success";
}

export interface CancelAckMessage extends QueryScopedOutbound {
  type: "cancel_ack";
  accepted: boolean;
  dispatchAttempted: boolean;
  adapterAcknowledged: boolean;
}

export interface ControlToolResultMessage extends OutboundEnvelope {
  type: "control_tool_result";
  /** Required for direct desktop control; legacy rejection receipts omit it. */
  ownerId?: string;
  name: string;
  result: string;
}

export interface ExecutionProfileProjection {
  profileGeneration: number;
  adapterId: string;
  credentialScope: "managed_cloud" | "local_user";
  modelProfile: string | null;
  workingDirectory: string;
  executionRole: "coordinator" | "leaf";
}

export interface DefaultExecutionProfileConfiguredMessage extends OutboundEnvelope {
  type: "default_execution_profile_configured";
  preferenceGeneration: number;
  adapterId: string;
  credentialScope: "managed_cloud" | "local_user";
  modelProfile: string | null;
  workingDirectory: string;
  appliesTo: "new_sessions";
}

export interface SurfaceSessionResolvedMessage extends OutboundEnvelope {
  type: "surface_session_resolved";
  created: boolean;
  conversationId: string;
  sessionId: string;
  profile: ExecutionProfileProjection;
}

export interface SessionExecutionProfileMigratedMessage extends OutboundEnvelope {
  type: "session_execution_profile_migrated";
  sessionId: string;
  previousProfileGeneration: number;
  profile: ExecutionProfileProjection;
  staleBindingIds: string[];
}

export interface ContextSourceOutcomeProjection {
  source: ContextSourceKind;
  sourceRevision: string;
  outcome: ContextSourceOutcome;
  capturedAtMs: number;
  expiresAtMs: number | null;
  payloadHash: string;
  payload: Record<string, unknown>;
}

export interface ContextSnapshotProjection {
  snapshotId: string;
  version: string;
  snapshotGeneration: number;
  rendererFingerprint: string;
  rendererPolicyVersion: string;
  capabilityVersion: string;
  /** Canonical, surface-specific context material rendered by the kernel. */
  renderedContext: string;
  /**
   * Kernel-owned history/cache plan shared by typed chat and realtime voice.
   * Older history is intentionally not implied by a 64-turn window: callers
   * must honor the declared handoff strategy rather than pretending it exists.
   */
  contextPlan: {
    version: 1;
    planId: string;
    semanticGuidanceVersion: string;
    semanticGuidance: string;
    retainedTurnStartSeq: number | null;
    retainedTurnEndSeq: number | null;
    retainedTurnCount: number;
    totalTurnCount: number;
    omittedTurnCount: number;
    olderHistoryStrategy: "none" | "truncated";
    stableCacheIdentity: string;
    dynamicContextIdentity: string;
  };
  ownerId: string;
  sessionId: string;
  conversationId: string;
  recentTurns: Array<{
    turnId: string;
    turnSeq: number;
    role: string;
    content: string;
    status: string;
    origin: string;
    createdAtMs: number;
  }>;
  sourceOutcomes: ContextSourceOutcomeProjection[];
  activeRuns: Array<{
    sessionId: string;
    runId: string;
    status: string;
    title: string;
    surfaceKind: string;
    updatedAtMs: number;
    finalText: string | null;
  }>;
  /**
   * Bounded, kernel-owned terminal child runs. These are contextual status
   * records, not tool receipts: use get_agent_run before claiming a side
   * effect beyond the recorded final output.
   */
  recentCompletedRuns: Array<{
    sessionId: string;
    runId: string;
    parentRunId: string;
    status: string;
    title: string;
    surfaceKind: string;
    completedAtMs: number;
    finalText: string | null;
    errorMessage: string | null;
  }>;
  capabilities: {
    executionRole: "coordinator" | "leaf";
    manifestVersion: number;
    manifestDigest: string;
    allowedToolNames: string[];
    chatFirstUi: boolean;
    chatFirstControlGeneration: number | null;
  };
}

export interface ContextSourceUpdatedMessage extends OutboundEnvelope {
  type: "context_source_updated";
  sessionId: string;
  source: ContextSourceKind;
  sourceRevision: string;
  changed: boolean;
  snapshotVersion: string;
  snapshotGeneration: number;
  rendererFingerprint: string;
  capabilityVersion: string;
}

export interface ContextSnapshotMessage extends OutboundEnvelope {
  type: "context_snapshot";
  snapshot: ContextSnapshotProjection;
}

export interface LegacyMainChatSessionsImportedMessage extends OutboundEnvelope {
  type: "legacy_main_chat_sessions_imported";
  ownerId: string;
  acceptedEntries: Array<{ chatId: string; agentSessionId: string }>;
  acceptedCount: number;
  importedCount: number;
}

export interface JournalTurnProjection {
  conversationId: string;
  turnId: string;
  turnSeq: number;
  producerId: string;
  payloadHash: string;
  role: string;
  surfaceKind: string;
  content: string;
  origin: string;
  status: string;
  contentBlocks: unknown[];
  resources: unknown[];
  producingRunId: string | null;
  producingAttemptId: string | null;
  remoteId: string | null;
  createdAtMs: number;
  updatedAtMs: number;
  completedAtMs: number | null;
  metadataJson: string;
}

export interface AgentSpawnJournalEnsuredMessage extends OutboundEnvelope {
  type: "agent_spawn_journal_ensured";
  ownerId: string;
  sessionId: string;
  runId: string;
  conversationId: string;
  userTurn: JournalTurnProjection | null;
  assistantTurn: JournalTurnProjection;
}

export interface JournalOperationResultMessage extends OutboundEnvelope {
  type: "journal_operation_result";
  operation: "record" | "record_exchange" | "import_remote" | "update" | "list" | "clear" | "append_chat_first_blocks" | "record_question_interaction_reply" | "materialize_chat_first_intents" | "list_chat_first_materialization_receipts" | "acknowledge_chat_first_materialization_receipts";
  conversationId: string;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turn?: JournalTurnProjection;
  turns: JournalTurnProjection[];
  clearedCount: number;
  highWaterTurnSeq: number;
  generationBaseTurnSeq: number;
  conversationGeneration: number;
  backendDeleteOperationId?: string;
  accepted?: boolean;
  duplicate?: boolean;
  continuityKey?: string | null;
  suppressedByTailQuestion?: boolean;
  suppressedByStreamingTail?: boolean;
  materializationStoppedByTail?: boolean;
  materializationReceipts?: Array<{ intentId: string; receiptId: string }>;
  acknowledgedReceiptCount?: number;
}

export interface JournalTurnChangedMessage extends OutboundEnvelope {
  type: "journal_turn_changed";
  ownerId: string;
  conversationGeneration: number;
  generationBaseTurnSeq: number;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turn: JournalTurnProjection;
}

export interface JournalBackendSyncMessage extends OutboundEnvelope {
  type: "journal_backend_sync";
  ownerId: string;
  turnId: string;
  conversationId: string;
  conversationGeneration: number;
  attemptCount: number;
  deliveryGeneration: number;
  payloadHash: string;
  clientMessageId: string;
  journalRevision: number;
  text: string;
  sender: "human" | "ai";
  appId: string | null;
  sessionId: string | null;
  metadata: string | null;
  messageSource: "desktop_chat" | "realtime_voice";
}

export interface JournalBackendDeleteMessage extends OutboundEnvelope {
  type: "journal_backend_delete";
  ownerId: string;
  operationId: string;
  conversationId: string;
  conversationGeneration: number;
  attemptCount: number;
  deliveryGeneration: number;
  payloadHash: string;
  targetKind: "messages" | "chat_session";
  targetId: string | null;
}

export interface JournalBackendReconcileMessage extends OutboundEnvelope {
  type: "journal_backend_reconcile";
  ownerId: string;
  reconcileId: string;
  conversationId: string;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  targetKind: "messages" | "chat_session";
  targetId: string | null;
  frontierRemoteId: string | null;
  pageCursor: string | null;
  pageLimit: number;
}

export interface ChatFirstDeferralDeliveryMessage extends OutboundEnvelope {
  type: "chat_first_deferral_delivery";
  ownerId: string;
  continuityKey: string;
  controlGeneration: number;
  subject: { kind: "task" | "goal" | "capture"; id: string };
  question: {
    questionId: string;
    text: string;
    subject: { kind: "task" | "goal" | "capture"; id: string };
    options: Array<{ optionId: string; label: string; preparedAnswer: string; defer?: boolean }>;
  };
  attemptCount: number;
  deliveryGeneration: number;
  payloadHash: string;
}

export type OutboundMessage =
  | InitMessage
  | TextDeltaMessage
  | ToolUseMessage
  | ToolActivityMessage
  | ToolResultDisplayMessage
  | ThinkingDeltaMessage
  | ResultMessage
  | ErrorMessage
  | AuthRequiredMessage
  | AuthSuccessMessage
  | CancelAckMessage
  | AuthorizedToolExecutionMessage
  | ExternalSurfaceRunBeginResultMessage
  | ExternalSurfaceToolResultMessage
  | ExternalSurfaceRunCompleteResultMessage
  | OwnerRuntimeRevokedMessage
  | ControlToolResultMessage
  | DefaultExecutionProfileConfiguredMessage
  | SurfaceSessionResolvedMessage
  | SessionExecutionProfileMigratedMessage
  | ContextSourceUpdatedMessage
  | ContextSnapshotMessage
  | LegacyMainChatSessionsImportedMessage
  | JournalOperationResultMessage
  | AgentSpawnJournalEnsuredMessage
  | JournalTurnChangedMessage
  | JournalBackendSyncMessage
  | JournalBackendDeleteMessage
  | JournalBackendReconcileMessage
  | ChatFirstDeferralDeliveryMessage;

type OutboundWithEnvelope = Exclude<OutboundMessage, AuthRequiredMessage | AuthSuccessMessage>;

type DraftEnvelope<T extends OutboundWithEnvelope> = Omit<T, "protocolVersion"> & Partial<Pick<T, "protocolVersion">>;

/** Outbound payload before correlation / envelope enrichment (adapters, transport internals). */
export type OutboundMessageDraft =
  | DraftEnvelope<InitMessage>
  | AuthRequiredMessage
  | AuthSuccessMessage
  | DraftEnvelope<TextDeltaMessage>
  | DraftEnvelope<ToolUseMessage>
  | DraftEnvelope<ToolActivityMessage>
  | DraftEnvelope<ToolResultDisplayMessage>
  | DraftEnvelope<ThinkingDeltaMessage>
  | DraftEnvelope<ResultMessage>
  | DraftEnvelope<ErrorMessage>
  | DraftEnvelope<CancelAckMessage>
  | DraftEnvelope<AuthorizedToolExecutionMessage>
  | DraftEnvelope<ExternalSurfaceRunBeginResultMessage>
  | DraftEnvelope<ExternalSurfaceToolResultMessage>
  | DraftEnvelope<ExternalSurfaceRunCompleteResultMessage>
  | DraftEnvelope<OwnerRuntimeRevokedMessage>
  | DraftEnvelope<ControlToolResultMessage>
  | DraftEnvelope<DefaultExecutionProfileConfiguredMessage>
  | DraftEnvelope<SurfaceSessionResolvedMessage>
  | DraftEnvelope<SessionExecutionProfileMigratedMessage>
  | DraftEnvelope<ContextSourceUpdatedMessage>
  | DraftEnvelope<ContextSnapshotMessage>
  | DraftEnvelope<LegacyMainChatSessionsImportedMessage>
  | DraftEnvelope<JournalOperationResultMessage>
  | DraftEnvelope<AgentSpawnJournalEnsuredMessage>
  | DraftEnvelope<JournalTurnChangedMessage>
  | DraftEnvelope<JournalBackendSyncMessage>
  | DraftEnvelope<JournalBackendDeleteMessage>
  | DraftEnvelope<JournalBackendReconcileMessage>
  | DraftEnvelope<ChatFirstDeferralDeliveryMessage>;

export function ensureOutboundProtocolVersion(message: OutboundMessageDraft): OutboundMessage {
  if (message.type === "auth_required" || message.type === "auth_success") {
    return message;
  }
  if ("protocolVersion" in message && message.protocolVersion === PROTOCOL_VERSION) {
    return message as OutboundMessage;
  }
  return { ...message, protocolVersion: PROTOCOL_VERSION } as OutboundMessage;
}
