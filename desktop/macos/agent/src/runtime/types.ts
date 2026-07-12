export type SessionStatus = "open" | "archived" | "closed";

export type RunStatus =
  | "queued"
  | "starting"
  | "running"
  | "waiting_input"
  | "waiting_approval"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "orphaned";

export type AttemptStatus = RunStatus;

export type RunMode = "ask" | "act";

export type AgentExecutionRole = "coordinator" | "leaf";

export type ProviderBoundary = "managed_cloud" | `local_user:${string}`;
export type SessionCredentialScope = "managed_cloud" | "local_user";
export type SessionExecutionProfileSource = "creation" | "migration" | "child_derivation" | "legacy_backfill";

export type ResumeFidelity = "native" | "reconstructed" | "none";

export type AdapterBindingStatus = "active" | "stale" | "invalid" | "closed";

export type EventRetentionClass = "core" | "transient";

export type EventVisibility = "ui" | "internal";

export type ArtifactRole = "input" | "result" | "checkpoint" | "tool_output" | "log" | "other";

export type ArtifactLifecycleState = "retained" | "dismissed" | "opened";

export type DelegationMode = "call" | "spawn" | "continue";

export type DelegationStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export type GrantEffect = "allow" | "deny";

// TODO(desktop-agent-platonic-gap-closure G6): delete legacy_default after ship+2 releases post-platonic.
export type GrantSource = "legacy_default" | "policy" | "user" | "system";

export interface SurfaceConversation {
  ownerId: string;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  conversationId: string;
  agentSessionId: string;
  createdAtMs: number;
  lastActiveAtMs: number;
}

export type NewSurfaceConversation = Pick<
  SurfaceConversation,
  | "ownerId"
  | "surfaceKind"
  | "externalRefKind"
  | "externalRefId"
  | "conversationId"
  | "agentSessionId"
  | "createdAtMs"
  | "lastActiveAtMs"
>;

export type ConversationTurnRole = "user" | "assistant";

export type ConversationTurnOrigin =
  | "typed_chat"
  | "floating_chat"
  | "realtime_voice"
  | "agent_runtime"
  | "notification"
  | "tool_runtime"
  | "backend_import"
  | "task_chat"
  | "workstream"
  | "swift_backfill"
  | "legacy";

export type ConversationTurnStatus = "pending" | "streaming" | "completed" | "failed";

export type ConversationToolCallStatus = "running" | "completed" | "failed";

/**
 * Kernel-owned chat content. The wire keys intentionally match
 * ChatContentBlockCodec so Swift can remain a projection rather than a second
 * persistence owner.
 */
export type ConversationContentBlock =
  | { type: "text"; id: string; text: string }
  | {
      type: "toolCall";
      id: string;
      name: string;
      status: ConversationToolCallStatus;
      toolUseId?: string;
      inputSummary?: string;
      inputDetails?: string;
      output?: string;
    }
  | { type: "thinking"; id: string; text: string }
  | { type: "discoveryCard"; id: string; title: string; summary: string; fullText: string }
  | {
      type: "agentSpawn";
      id: string;
      pillId?: string;
      sessionId: string;
      runId: string;
      title: string;
      objective: string;
    }
  | {
      type: "agentCompletion";
      id: string;
      pillId?: string;
      sessionId?: string;
      runId?: string;
      title: string;
      promptSnippet: string;
      output: string;
      status: string;
    };

export type ConversationResourceOrigin = "userAttachment" | "generatedArtifact";
export type ConversationResourceState =
  | "uploading"
  | "ready"
  | "retained"
  | "opened"
  | "dismissed"
  | `failed:${string}`;

/** Surface-neutral resource shape shared with Swift's ChatResource codec. */
export interface ConversationResource {
  id: string;
  origin: ConversationResourceOrigin;
  title: string;
  state: ConversationResourceState;
  subtitle?: string;
  mimeType?: string;
  thumbnailURL?: string;
  uri?: string;
  artifactId?: string;
  sessionId?: string;
  runId?: string;
}

export interface ConversationTurn {
  conversationId: string;
  turnId: string;
  turnSeq: number;
  producerId: string;
  payloadHash: string;
  role: ConversationTurnRole;
  surfaceKind: string;
  content: string;
  origin: ConversationTurnOrigin;
  status: ConversationTurnStatus;
  contentBlocks: ConversationContentBlock[];
  resources: ConversationResource[];
  producingRunId: string | null;
  remoteId: string | null;
  createdAtMs: number;
  updatedAtMs: number;
  completedAtMs: number | null;
  metadataJson: string;
}

export type NewConversationTurn = Pick<
  ConversationTurn,
  "conversationId" | "role" | "surfaceKind" | "content" | "createdAtMs"
> &
  Partial<Pick<
    ConversationTurn,
    | "turnId"
    | "turnSeq"
    | "producerId"
    | "payloadHash"
    | "origin"
    | "status"
    | "contentBlocks"
    | "resources"
    | "producingRunId"
    | "remoteId"
    | "updatedAtMs"
    | "completedAtMs"
    | "metadataJson"
  >>;

export type BackendTurnOutboxStatus = "pending" | "delivering" | "retrying" | "delivered" | "failed";

export interface BackendTurnOutboxRecord {
  turnId: string;
  conversationId: string;
  ownerId: string;
  status: BackendTurnOutboxStatus;
  attemptCount: number;
  deliveryGeneration: number;
  conversationGeneration: number;
  payloadHash: string;
  availableAtMs: number;
  leaseExpiresAtMs: number | null;
  remoteId: string | null;
  lastErrorCode: string | null;
  createdAtMs: number;
  updatedAtMs: number;
  deliveredAtMs: number | null;
}

export interface CompletionDeltaCheckpoint {
  ownerId: string;
  surfaceKey: string;
  seenIdsJson: string;
  highWaterMs: number;
  updatedAtMs: number;
}

export type AgentIdKind =
  | "session"
  | "conversation"
  | "turn"
  | "run"
  | "attempt"
  | "event"
  | "binding"
  | "artifact"
  | "delegation"
  | "grant"
  | "contextPacket"
  | "dispatch"
  | "artifactDelivery"
  | "memoryCandidate"
  | "taskCandidate"
  | "contextAccess";

export type DesktopContextRetentionClass = "ephemeral" | "debug" | "core";
export type DesktopDispatchKind =
  | "approval"
  | "routing_choice"
  | "failure_recovery"
  | "artifact_review"
  | "memory_candidate"
  | "task_candidate"
  | "external_draft"
  | "screen_context";
export type DesktopDispatchStatus = "pending" | "resolved" | "expired" | "cancelled";
export type DesktopArtifactDeliveryTargetKind = "ask_omi" | "task_chat" | "local_file" | "external_draft";
export type DesktopArtifactDeliveryReviewStatus = "not_required" | "pending" | "approved" | "rejected";
export type DesktopArtifactDeliveryStatus = "pending" | "delivered" | "failed" | "retrying" | "cancelled";
export type DesktopCandidateStatus = "pending" | "accepted" | "rejected" | "expired";
export type DesktopTaskCandidateStatus = DesktopCandidateStatus | "forwarded";
export type DesktopTaskCandidateAction = "create" | "update" | "complete" | "delete" | "supersede";
export type DesktopTaskCandidateDeliveryStatus = "pending" | "delivering" | "delivered" | "failed" | "blocked";
export type DesktopContextSourceKind =
  | "omi_db"
  | "rewind_timeline"
  | "screen_current"
  | "screenshot_image"
  | "local_agent_api"
  | "automation_bridge"
  | "chat_surface"
  | "task_chat";
export type DesktopContextPolicyDecision = "allowed" | "denied" | "dispatch_created";

export interface AgentSession {
  sessionId: string;
  ownerId: string;
  agentDefinitionId: string;
  title: string | null;
  status: SessionStatus;
  surfaceKind: string;
  executionRole: AgentExecutionRole;
  providerBoundary: ProviderBoundary;
  externalRefKind: string | null;
  externalRefId: string | null;
  defaultAdapterId: string;
  defaultCwd: string | null;
  modelProfile: string | null;
  executionProfileGeneration: number;
  metadataJson: string;
  createdAtMs: number;
  updatedAtMs: number;
  lastActivityAtMs: number;
}

export interface AgentRun {
  runId: string;
  sessionId: string;
  parentRunId: string | null;
  clientId: string;
  requestId: string;
  idempotencyKey: string | null;
  status: RunStatus;
  mode: RunMode;
  profileGeneration: number;
  inputJson: string;
  systemPromptHash: string | null;
  modelProfile: string | null;
  requestedModelId: string | null;
  cwd: string | null;
  finalText: string | null;
  resultJson: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  inputTokens: number | null;
  outputTokens: number | null;
  cacheReadTokens: number | null;
  cacheWriteTokens: number | null;
  costUsd: number | null;
  createdAtMs: number;
  startedAtMs: number | null;
  completedAtMs: number | null;
  updatedAtMs: number;
}

export interface RunAttempt {
  attemptId: string;
  runId: string;
  attemptNo: number;
  profileGeneration: number;
  status: AttemptStatus;
  adapterId: string;
  adapterInstanceId: string;
  runtimeNodeId: string;
  bindingId: string | null;
  adapterNativeRunId: string | null;
  resumeFromAttemptId: string | null;
  checkpointArtifactId: string | null;
  retryReason: string | null;
  retryable: 0 | 1;
  cancellationRequestedAtMs: number | null;
  cancellationDispatchedAtMs: number | null;
  cancellationAcknowledgedAtMs: number | null;
  startedAtMs: number | null;
  completedAtMs: number | null;
  errorCode: string | null;
  errorMessage: string | null;
  metadataJson: string;
  createdAtMs: number;
  updatedAtMs: number;
}

export interface AdapterBinding {
  bindingId: string;
  sessionId: string;
  adapterId: string;
  bindingGeneration: number;
  profileGeneration: number;
  adapterNativeSessionId: string | null;
  adapterInstanceId: string | null;
  resumeFidelity: ResumeFidelity;
  status: AdapterBindingStatus;
  cwd: string | null;
  modelId: string | null;
  systemPromptHash: string | null;
  metadataJson: string;
  createdAtMs: number;
  updatedAtMs: number;
  lastUsedAtMs: number | null;
  invalidatedAtMs: number | null;
}

export interface SessionExecutionProfile {
  sessionId: string;
  generation: number;
  adapterId: string;
  credentialScope: SessionCredentialScope;
  modelProfile: string | null;
  workingDirectory: string;
  executionRole: AgentExecutionRole;
  source: SessionExecutionProfileSource;
  auditJson: string;
  createdAtMs: number;
}

export interface DefaultExecutionProfilePreference {
  ownerId: string;
  generation: number;
  adapterId: string;
  credentialScope: SessionCredentialScope;
  modelProfile: string | null;
  workingDirectory: string;
  updatedAtMs: number;
}

export interface AgentEvent {
  eventSeq?: number;
  eventId: string;
  sessionId: string;
  runId: string | null;
  attemptId: string | null;
  type: string;
  retentionClass: EventRetentionClass;
  visibility: EventVisibility;
  payloadJson: string;
  createdAtMs: number;
}

export interface AgentArtifact {
  artifactId: string;
  sessionId: string;
  runId: string | null;
  attemptId: string | null;
  kind: string;
  role: ArtifactRole;
  uri: string;
  displayName: string | null;
  mimeType: string | null;
  contentHash: string | null;
  sizeBytes: number | null;
  lifecycleState: ArtifactLifecycleState;
  lifecycleUpdatedAtMs: number | null;
  metadataJson: string;
  createdAtMs: number;
}

export interface DesktopContextPacket {
  packetId: string;
  ownerId: string;
  sessionId: string | null;
  runId: string | null;
  surfaceKind: string;
  objective: string;
  packetJson: string;
  redactedPreviewJson: string;
  contextHash: string;
  tokenEstimate: number | null;
  retentionClass: DesktopContextRetentionClass;
  expiresAtMs: number | null;
  createdAtMs: number;
}

export type NewDesktopContextPacket = Partial<Omit<DesktopContextPacket, "expiresAtMs">> &
  Pick<DesktopContextPacket, "ownerId" | "surfaceKind" | "objective" | "packetJson" | "redactedPreviewJson" | "contextHash" | "retentionClass"> & {
    expiresAtMs: number;
  };

export interface DesktopCoordinatorDispatch {
  dispatchId: string;
  ownerId: string;
  kind: DesktopDispatchKind;
  priority: number;
  status: DesktopDispatchStatus;
  title: string;
  decisionPrompt: string;
  recommendedDefault: string | null;
  sourceSessionId: string | null;
  sourceRunId: string | null;
  sourceAttemptId: string | null;
  sourceArtifactId: string | null;
  capability: string | null;
  operation: string | null;
  resourceRef: string | null;
  payloadJson: string;
  createdAtMs: number;
  expiresAtMs: number | null;
  resolvedAtMs: number | null;
  resolvedBy: string | null;
  resolutionJson: string | null;
}

export type NewDesktopCoordinatorDispatch = Partial<DesktopCoordinatorDispatch> &
  Pick<DesktopCoordinatorDispatch, "ownerId" | "kind" | "priority" | "title" | "decisionPrompt">;

export interface DesktopArtifactDelivery {
  deliveryId: string;
  artifactId: string;
  ownerId: string;
  sourceSessionId: string;
  sourceRunId: string | null;
  sourceAttemptId: string | null;
  intendedSurface: string;
  targetKind: DesktopArtifactDeliveryTargetKind;
  targetRef: string | null;
  contentHash: string | null;
  reviewStatus: DesktopArtifactDeliveryReviewStatus;
  deliveryStatus: DesktopArtifactDeliveryStatus;
  attemptCount: number;
  receiptJson: string | null;
  errorJson: string | null;
  createdAtMs: number;
  updatedAtMs: number;
  deliveredAtMs: number | null;
}

export type NewDesktopArtifactDelivery = Partial<DesktopArtifactDelivery> &
  Pick<DesktopArtifactDelivery, "artifactId" | "ownerId" | "sourceSessionId" | "intendedSurface" | "targetKind">;

export interface DesktopMemoryCandidate {
  candidateId: string;
  ownerId: string;
  sourceSessionId: string;
  sourceRunId: string | null;
  sourceArtifactId: string | null;
  proposedFact: string;
  evidenceRefsJson: string;
  confidence: number;
  sensitivityTier: string;
  status: DesktopCandidateStatus;
  createdAtMs: number;
  resolvedAtMs: number | null;
}

export type NewDesktopMemoryCandidate = Partial<DesktopMemoryCandidate> &
  Pick<DesktopMemoryCandidate, "ownerId" | "sourceSessionId" | "proposedFact" | "evidenceRefsJson" | "confidence" | "sensitivityTier">;

export interface DesktopTaskCandidate {
  candidateId: string;
  ownerId: string;
  sourceSessionId: string | null;
  sourceRunId: string | null;
  action: DesktopTaskCandidateAction;
  taskRef: string | null;
  proposedChangeJson: string;
  evidenceRefsJson: string;
  confidence: number;
  ownershipConfidence: number;
  requiresApproval: 0 | 1;
  goalRef: string | null;
  workstreamRef: string | null;
  sourceSurface: string;
  accountGeneration: number;
  generationReconciled: 0 | 1;
  status: DesktopTaskCandidateStatus;
  deliveryStatus: DesktopTaskCandidateDeliveryStatus;
  deliveryAttemptCount: number;
  deliveryKey: string;
  backendCandidateId: string | null;
  backendReceiptJson: string | null;
  backendResolutionReceiptJson: string | null;
  backendResolutionStatus: string | null;
  lastDeliveryErrorJson: string | null;
  createdAtMs: number;
  updatedAtMs: number;
  deliveredAtMs: number | null;
  resolvedAtMs: number | null;
}

export type NewDesktopTaskCandidate = Partial<DesktopTaskCandidate> &
  Pick<DesktopTaskCandidate, "ownerId" | "action" | "proposedChangeJson" | "evidenceRefsJson" | "confidence" | "requiresApproval">;

export interface DesktopContextAccessLog {
  accessId: string;
  ownerId: string;
  packetId: string | null;
  runId: string | null;
  sourceKind: DesktopContextSourceKind;
  operation: string;
  scopeJson: string;
  sensitivityTier: string;
  policyDecision: DesktopContextPolicyDecision;
  dispatchId: string | null;
  redactionSummaryJson: string;
  createdAtMs: number;
}

export type NewDesktopContextAccessLog = Partial<DesktopContextAccessLog> &
  Pick<DesktopContextAccessLog, "ownerId" | "sourceKind" | "operation" | "scopeJson" | "sensitivityTier" | "policyDecision">;

export interface DesktopAttentionOverride {
  ownerId: string;
  subjectKind: string;
  subjectId: string;
  hiddenUntilMs: number | null;
  dismissedAtMs: number | null;
  reason: string | null;
  createdAtMs: number;
}

export type NewDesktopAttentionOverride = Partial<DesktopAttentionOverride> &
  Pick<DesktopAttentionOverride, "ownerId" | "subjectKind" | "subjectId">;

// Artifact lifecycle records store references, not blobs. Keep adapter-native
// references in `uri` or `metadataJson`, never in adapter_bindings:
// - roles: input, result, checkpoint, tool_output, log, other
// - common kinds: json, text, markdown, image, file, directory, transcript
// - uri schemes: omi-artifact:// for local runtime-managed artifacts; file://
//   for local files; adapter:// or provider-specific schemes for native refs
// - metadataJson carries adapter/provider ids and projection hints
// - contentHash is preferably sha256:<hex>; sizeBytes is advisory metadata
// - retention is currently local SQLite metadata only; blob retention/sync is
//   deferred to the artifact storage layer.
export type NewAgentArtifact = Partial<AgentArtifact> &
  Pick<AgentArtifact, "sessionId" | "kind" | "role" | "uri">;

export interface AgentDelegation {
  delegationId: string;
  parentSessionId: string;
  parentRunId: string;
  childSessionId: string;
  childRunId: string;
  mode: DelegationMode;
  status: DelegationStatus;
  objective: string;
  requestJson: string;
  resultArtifactId: string | null;
  createdAtMs: number;
  completedAtMs: number | null;
}

export interface AgentGrant {
  grantId: string;
  sessionId: string;
  runId: string | null;
  capability: string;
  operation: string;
  resourcePattern: string;
  effect: GrantEffect;
  source: GrantSource;
  constraintsJson: string;
  createdAtMs: number;
  expiresAtMs: number | null;
  revokedAtMs: number | null;
}

export type NewAgentSession = Partial<AgentSession>
  & Pick<AgentSession, "ownerId" | "surfaceKind" | "defaultAdapterId">
  & { executionProfileSource?: SessionExecutionProfileSource };

export type NewAgentRun = Partial<AgentRun> &
  Pick<AgentRun, "sessionId" | "clientId" | "requestId" | "status" | "mode"> & {
    inputJson?: string;
  };

export type NewRunAttempt = Partial<RunAttempt> &
  Pick<RunAttempt, "runId" | "attemptNo" | "status" | "adapterId" | "adapterInstanceId">;

export type NewAdapterBinding = Partial<AdapterBinding> &
  Pick<AdapterBinding, "sessionId" | "adapterId" | "bindingGeneration" | "resumeFidelity" | "status">;

export type NewAgentEvent = Partial<AgentEvent> & Pick<AgentEvent, "sessionId" | "type">;

export type NewAgentGrant = Partial<AgentGrant> &
  Pick<AgentGrant, "sessionId" | "capability" | "operation" | "resourcePattern" | "effect" | "source">;

export interface StartupReconciliationResult {
  orphanedAttemptIds: string[];
  orphanedRunIds: string[];
  staleBindingIds: string[];
  expiredContextPacketIds: string[];
  expiredContinuationCheckpointIds: string[];
  failedArtifactDeliveryIds: string[];
  failedTaskCandidateDeliveryIds: string[];
  requeuedBackendTurnOutboxIds: string[];
  requeuedBackendConversationDeleteIds: string[];
  failedPreparedToolInvocationIds: string[];
  outcomeUnknownToolInvocationIds: string[];
  repairedSessionProfileIds: string[];
  repairedLegacyJournalTurnIds: string[];
  reconciledJournalTurnIds: string[];
  recoveryDispatchIds: string[];
  clearedAttemptInstanceIds: number;
  clearedBindingInstanceIds: number;
  eventIds: string[];
}

export interface AgentStore {
  close(): void;
  withTransaction<T>(work: () => T): T;
  migrate(): void;
  reconcileStartup(): StartupReconciliationResult;
  insertSession(input: NewAgentSession): AgentSession;
  insertSurfaceConversation(input: NewSurfaceConversation): SurfaceConversation;
  insertConversationTurn(input: NewConversationTurn): ConversationTurn;
  insertRun(input: NewAgentRun): AgentRun;
  insertAttempt(input: NewRunAttempt): RunAttempt;
  insertAdapterBinding(input: NewAdapterBinding): AdapterBinding;
  insertArtifact(input: NewAgentArtifact): AgentArtifact;
  appendEvent(input: NewAgentEvent): AgentEvent;
  insertGrant(input: NewAgentGrant): AgentGrant;
  insertDesktopContextPacket(input: NewDesktopContextPacket): DesktopContextPacket;
  insertDesktopDispatch(input: NewDesktopCoordinatorDispatch): DesktopCoordinatorDispatch;
  resolveDesktopDispatch(dispatchId: string, input: { ownerId: string; status: "resolved" | "cancelled"; resolvedBy?: string | null; resolutionJson?: string | null; resolvedAtMs?: number }): DesktopCoordinatorDispatch;
  insertDesktopArtifactDelivery(input: NewDesktopArtifactDelivery): DesktopArtifactDelivery;
  updateDesktopArtifactDelivery(deliveryId: string, input: { ownerId: string } & Partial<Pick<DesktopArtifactDelivery, "reviewStatus" | "deliveryStatus" | "attemptCount" | "receiptJson" | "errorJson" | "deliveredAtMs">>): DesktopArtifactDelivery;
  insertDesktopMemoryCandidate(input: NewDesktopMemoryCandidate): DesktopMemoryCandidate;
  insertDesktopTaskCandidate(input: NewDesktopTaskCandidate): DesktopTaskCandidate;
  insertDesktopContextAccessLog(input: NewDesktopContextAccessLog): DesktopContextAccessLog;
  upsertDesktopAttentionOverride(input: NewDesktopAttentionOverride): DesktopAttentionOverride;
  execute(sql: string, values?: unknown[]): number;
  getOptionalRow(sql: string, values?: unknown[]): Record<string, unknown> | undefined;
  getRow(sql: string, values?: unknown[]): Record<string, unknown>;
  allRows(sql: string, values?: unknown[]): Record<string, unknown>[];
}
