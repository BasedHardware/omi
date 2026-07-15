// Agent-kernel persistence types (Windows port of the macOS agent runtime's
// `types.ts`). This is the kernel's internal, main-process type surface: entity
// interfaces, the closed-set enums their columns validate against, the `New*`
// insert-input shapes, and the `AgentStore` contract implemented by
// `SqliteAgentStore` in `store.ts`.
//
// Ported faithfully from the frozen macOS reference (tag v0.12.72). The store is
// a DEDICATED SQLite database, isolated from the app's existing chat store
// (`omi.db`) — this satisfies INV-CHAT-1 (kernel-owned transcript store). The
// control-plane single-authority constraints these types back are INV-AGENT-*.
//
// These types are INERT this PR: nothing constructs or drives the store yet
// (PR #3 / kernel-core does). Keep this file additive — do not wire it in.

/** Lifecycle state of an agent session. */
export type SessionStatus = 'open' | 'archived' | 'closed'

/** Lifecycle state of a run or attempt (active states precede the terminal set). */
export type RunStatus =
  | 'queued'
  | 'starting'
  | 'running'
  | 'waiting_input'
  | 'waiting_approval'
  | 'cancelling'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'timed_out'
  | 'orphaned'

/** Attempt lifecycle state — same closed set as {@link RunStatus}. */
export type AttemptStatus = RunStatus

/** Whether a run only answers (`ask`) or may take actions (`act`). */
export type RunMode = 'ask' | 'act'

/** Whether a session may orchestrate sub-agents (`coordinator`) or is a leaf. */
export type AgentExecutionRole = 'coordinator' | 'leaf'

/** Provider trust boundary: Omi-managed cloud, or a user-local adapter. */
export type ProviderBoundary = 'managed_cloud' | `local_user:${string}`

/** How faithfully an adapter binding can resume prior native session state. */
export type ResumeFidelity = 'native' | 'reconstructed' | 'none'

/** Lifecycle state of an adapter binding. */
export type AdapterBindingStatus = 'active' | 'stale' | 'invalid' | 'closed'

/** Retention tier for an appended event. */
export type EventRetentionClass = 'core' | 'transient'

/** Whether an event is user-facing (`ui`) or internal bookkeeping. */
export type EventVisibility = 'ui' | 'internal'

/** Role an artifact plays relative to its run. */
export type ArtifactRole = 'input' | 'result' | 'checkpoint' | 'tool_output' | 'log' | 'other'

/** UI lifecycle state of an artifact (added by the artifact-lifecycle migration). */
export type ArtifactLifecycleState = 'retained' | 'dismissed' | 'opened'

/** How a delegation relates parent and child runs. */
export type DelegationMode = 'call' | 'spawn' | 'continue'

/** Lifecycle state of a delegation. */
export type DelegationStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'

/** Whether a grant allows or denies a capability. */
export type GrantEffect = 'allow' | 'deny'

/** Origin of a grant. `legacy_default` is legacy debt slated for removal. */
// TODO(desktop-agent-platonic-gap-closure G6): delete legacy_default after ship+2 releases post-platonic.
export type GrantSource = 'legacy_default' | 'policy' | 'user' | 'system'

/** Speaker role of a conversation turn. */
export type ConversationTurnRole = 'user' | 'assistant'

/** Discriminator for {@link generateAgentId} id prefixes. */
export type AgentIdKind =
  | 'session'
  | 'conversation'
  | 'turn'
  | 'run'
  | 'attempt'
  | 'event'
  | 'binding'
  | 'artifact'
  | 'delegation'
  | 'grant'
  | 'contextPacket'
  | 'dispatch'
  | 'artifactDelivery'
  | 'memoryCandidate'
  | 'taskCandidate'
  | 'contextAccess'

/** Retention tier for a desktop context packet. */
export type DesktopContextRetentionClass = 'ephemeral' | 'debug' | 'core'

/** Kind of coordinator decision surfaced to the user. */
export type DesktopDispatchKind =
  | 'approval'
  | 'routing_choice'
  | 'failure_recovery'
  | 'artifact_review'
  | 'memory_candidate'
  | 'task_candidate'
  | 'external_draft'
  | 'screen_context'

/** Lifecycle state of a coordinator dispatch. */
export type DesktopDispatchStatus = 'pending' | 'resolved' | 'expired' | 'cancelled'

/** Destination surface for a delivered artifact. */
export type DesktopArtifactDeliveryTargetKind =
  | 'ask_omi'
  | 'task_chat'
  | 'local_file'
  | 'external_draft'

/** Review gate state for an artifact delivery. */
export type DesktopArtifactDeliveryReviewStatus =
  | 'not_required'
  | 'pending'
  | 'approved'
  | 'rejected'

/** Delivery attempt state for an artifact delivery. */
export type DesktopArtifactDeliveryStatus =
  | 'pending'
  | 'delivered'
  | 'failed'
  | 'retrying'
  | 'cancelled'

/** Resolution state shared by memory/task candidates. */
export type DesktopCandidateStatus = 'pending' | 'accepted' | 'rejected' | 'expired'

/** Task-candidate resolution state (adds `forwarded` to {@link DesktopCandidateStatus}). */
export type DesktopTaskCandidateStatus = DesktopCandidateStatus | 'forwarded'

/** Action a task candidate proposes against a task. */
export type DesktopTaskCandidateAction = 'create' | 'update' | 'complete' | 'delete' | 'supersede'

/** Backend-delivery state of a task candidate. */
export type DesktopTaskCandidateDeliveryStatus =
  | 'pending'
  | 'delivering'
  | 'delivered'
  | 'failed'
  | 'blocked'

/** Source a context-access log entry read from. */
export type DesktopContextSourceKind =
  | 'omi_db'
  | 'rewind_timeline'
  | 'screen_current'
  | 'screenshot_image'
  | 'local_agent_api'
  | 'automation_bridge'
  | 'chat_surface'
  | 'task_chat'

/** Policy outcome recorded for a context access. */
export type DesktopContextPolicyDecision = 'allowed' | 'denied' | 'dispatch_created'

/** A surface-scoped conversation that maps an external ref to an agent session. */
export interface SurfaceConversation {
  ownerId: string
  surfaceKind: string
  externalRefKind: string
  externalRefId: string
  conversationId: string
  agentSessionId: string
  createdAtMs: number
  lastActiveAtMs: number
}

/** Insert input for a {@link SurfaceConversation} (all fields required). */
export type NewSurfaceConversation = Pick<
  SurfaceConversation,
  | 'ownerId'
  | 'surfaceKind'
  | 'externalRefKind'
  | 'externalRefId'
  | 'conversationId'
  | 'agentSessionId'
  | 'createdAtMs'
  | 'lastActiveAtMs'
>

/** A single user/assistant turn within a surface conversation. */
export interface ConversationTurn {
  conversationId: string
  turnId: string
  role: ConversationTurnRole
  surfaceKind: string
  content: string
  createdAtMs: number
  metadataJson: string
}

/** Insert input for a {@link ConversationTurn} (turnId/metadata defaulted). */
export type NewConversationTurn = Pick<
  ConversationTurn,
  'conversationId' | 'role' | 'surfaceKind' | 'content' | 'createdAtMs'
> &
  Partial<Pick<ConversationTurn, 'turnId' | 'metadataJson'>>

/** Per-surface high-water mark used to compute completion deltas. */
export interface CompletionDeltaCheckpoint {
  ownerId: string
  surfaceKey: string
  seenIdsJson: string
  highWaterMs: number
  updatedAtMs: number
}

/** A versioned workstream artifact (append-only version history per logical key). */
export interface WorkstreamArtifactVersion {
  sessionId: string
  logicalKey: string
  version: number
  artifactId: string
  supersedesArtifactId: string | null
  evidenceRefsJson: string
  createdAtMs: number
}

/** The current head version for a workstream logical key. */
export interface WorkstreamArtifactHead {
  sessionId: string
  logicalKey: string
  artifactId: string
  version: number
  updatedAtMs: number
}

/** A cross-runtime continuation checkpoint used to resume a workstream. */
export interface WorkstreamContinuationCheckpoint {
  ownerId: string
  workstreamId: string
  sourceRuntimeId: string
  checkpointId: string
  checkpointJson: string
  lastEventSequence: number
  expiresAtMs: number
  createdAtMs: number
  updatedAtMs: number
}

/** An agent session — the root grouping for runs, bindings, and events. */
export interface AgentSession {
  sessionId: string
  ownerId: string
  agentDefinitionId: string
  title: string | null
  status: SessionStatus
  surfaceKind: string
  executionRole: AgentExecutionRole
  providerBoundary: ProviderBoundary
  externalRefKind: string | null
  externalRefId: string | null
  defaultAdapterId: string
  defaultCwd: string | null
  modelProfile: string | null
  metadataJson: string
  createdAtMs: number
  updatedAtMs: number
  lastActivityAtMs: number
}

/** A single agent run within a session. */
export interface AgentRun {
  runId: string
  sessionId: string
  parentRunId: string | null
  clientId: string
  requestId: string
  idempotencyKey: string | null
  status: RunStatus
  mode: RunMode
  inputJson: string
  systemPromptHash: string | null
  modelProfile: string | null
  requestedModelId: string | null
  cwd: string | null
  finalText: string | null
  resultJson: string | null
  errorCode: string | null
  errorMessage: string | null
  inputTokens: number | null
  outputTokens: number | null
  cacheReadTokens: number | null
  cacheWriteTokens: number | null
  costUsd: number | null
  createdAtMs: number
  startedAtMs: number | null
  completedAtMs: number | null
  updatedAtMs: number
}

/** One execution attempt of a run (single active attempt per run — INV-AGENT). */
export interface RunAttempt {
  attemptId: string
  runId: string
  attemptNo: number
  status: AttemptStatus
  adapterId: string
  adapterInstanceId: string
  runtimeNodeId: string
  bindingId: string | null
  adapterNativeRunId: string | null
  resumeFromAttemptId: string | null
  checkpointArtifactId: string | null
  retryReason: string | null
  retryable: 0 | 1
  cancellationRequestedAtMs: number | null
  cancellationDispatchedAtMs: number | null
  cancellationAcknowledgedAtMs: number | null
  startedAtMs: number | null
  completedAtMs: number | null
  errorCode: string | null
  errorMessage: string | null
  metadataJson: string
  createdAtMs: number
  updatedAtMs: number
}

/** A binding from a session to an adapter's native session (one active per pair). */
export interface AdapterBinding {
  bindingId: string
  sessionId: string
  adapterId: string
  bindingGeneration: number
  adapterNativeSessionId: string | null
  adapterInstanceId: string | null
  resumeFidelity: ResumeFidelity
  status: AdapterBindingStatus
  cwd: string | null
  modelId: string | null
  systemPromptHash: string | null
  metadataJson: string
  createdAtMs: number
  updatedAtMs: number
  lastUsedAtMs: number | null
  invalidatedAtMs: number | null
  lastDeliveredTurnCreatedAtMs: number
}

/** An append-only event on the session/run/attempt timeline. */
export interface AgentEvent {
  eventSeq?: number
  eventId: string
  sessionId: string
  runId: string | null
  attemptId: string | null
  type: string
  retentionClass: EventRetentionClass
  visibility: EventVisibility
  payloadJson: string
  createdAtMs: number
}

/** A reference-only artifact record (blobs live in the artifact storage layer). */
export interface AgentArtifact {
  artifactId: string
  sessionId: string
  runId: string | null
  attemptId: string | null
  kind: string
  role: ArtifactRole
  uri: string
  displayName: string | null
  mimeType: string | null
  contentHash: string | null
  sizeBytes: number | null
  lifecycleState: ArtifactLifecycleState
  lifecycleUpdatedAtMs: number | null
  metadataJson: string
  createdAtMs: number
}

/** A redacted, TTL-bound packet of desktop context offered to a coordinator. */
export interface DesktopContextPacket {
  packetId: string
  ownerId: string
  sessionId: string | null
  runId: string | null
  surfaceKind: string
  objective: string
  packetJson: string
  redactedPreviewJson: string
  contextHash: string
  tokenEstimate: number | null
  retentionClass: DesktopContextRetentionClass
  expiresAtMs: number | null
  createdAtMs: number
}

/** Insert input for a {@link DesktopContextPacket}; `expiresAtMs` is required and must be future. */
export type NewDesktopContextPacket = Partial<Omit<DesktopContextPacket, 'expiresAtMs'>> &
  Pick<
    DesktopContextPacket,
    | 'ownerId'
    | 'surfaceKind'
    | 'objective'
    | 'packetJson'
    | 'redactedPreviewJson'
    | 'contextHash'
    | 'retentionClass'
  > & {
    expiresAtMs: number
  }

/** A user-facing coordinator decision (approval, routing, recovery, review, …). */
export interface DesktopCoordinatorDispatch {
  dispatchId: string
  ownerId: string
  kind: DesktopDispatchKind
  priority: number
  status: DesktopDispatchStatus
  title: string
  decisionPrompt: string
  recommendedDefault: string | null
  sourceSessionId: string | null
  sourceRunId: string | null
  sourceAttemptId: string | null
  sourceArtifactId: string | null
  capability: string | null
  operation: string | null
  resourceRef: string | null
  payloadJson: string
  createdAtMs: number
  expiresAtMs: number | null
  resolvedAtMs: number | null
  resolvedBy: string | null
  resolutionJson: string | null
}

/** Insert input for a {@link DesktopCoordinatorDispatch}. */
export type NewDesktopCoordinatorDispatch = Partial<DesktopCoordinatorDispatch> &
  Pick<DesktopCoordinatorDispatch, 'ownerId' | 'kind' | 'priority' | 'title' | 'decisionPrompt'>

/** A pending/attempted delivery of an artifact to a destination surface. */
export interface DesktopArtifactDelivery {
  deliveryId: string
  artifactId: string
  ownerId: string
  sourceSessionId: string
  sourceRunId: string | null
  sourceAttemptId: string | null
  intendedSurface: string
  targetKind: DesktopArtifactDeliveryTargetKind
  targetRef: string | null
  contentHash: string | null
  reviewStatus: DesktopArtifactDeliveryReviewStatus
  deliveryStatus: DesktopArtifactDeliveryStatus
  attemptCount: number
  receiptJson: string | null
  errorJson: string | null
  createdAtMs: number
  updatedAtMs: number
  deliveredAtMs: number | null
}

/** Insert input for a {@link DesktopArtifactDelivery}. */
export type NewDesktopArtifactDelivery = Partial<DesktopArtifactDelivery> &
  Pick<
    DesktopArtifactDelivery,
    'artifactId' | 'ownerId' | 'sourceSessionId' | 'intendedSurface' | 'targetKind'
  >

/** A proposed memory fact awaiting user resolution. */
export interface DesktopMemoryCandidate {
  candidateId: string
  ownerId: string
  sourceSessionId: string
  sourceRunId: string | null
  sourceArtifactId: string | null
  proposedFact: string
  evidenceRefsJson: string
  confidence: number
  sensitivityTier: string
  status: DesktopCandidateStatus
  createdAtMs: number
  resolvedAtMs: number | null
}

/** Insert input for a {@link DesktopMemoryCandidate}. */
export type NewDesktopMemoryCandidate = Partial<DesktopMemoryCandidate> &
  Pick<
    DesktopMemoryCandidate,
    | 'ownerId'
    | 'sourceSessionId'
    | 'proposedFact'
    | 'evidenceRefsJson'
    | 'confidence'
    | 'sensitivityTier'
  >

/** A proposed task change awaiting resolution and backend delivery. */
export interface DesktopTaskCandidate {
  candidateId: string
  ownerId: string
  sourceSessionId: string | null
  sourceRunId: string | null
  action: DesktopTaskCandidateAction
  taskRef: string | null
  proposedChangeJson: string
  evidenceRefsJson: string
  confidence: number
  ownershipConfidence: number
  requiresApproval: 0 | 1
  goalRef: string | null
  workstreamRef: string | null
  sourceSurface: string
  accountGeneration: number
  generationReconciled: 0 | 1
  status: DesktopTaskCandidateStatus
  deliveryStatus: DesktopTaskCandidateDeliveryStatus
  deliveryAttemptCount: number
  deliveryKey: string
  backendCandidateId: string | null
  backendReceiptJson: string | null
  backendResolutionReceiptJson: string | null
  backendResolutionStatus: string | null
  lastDeliveryErrorJson: string | null
  createdAtMs: number
  updatedAtMs: number
  deliveredAtMs: number | null
  resolvedAtMs: number | null
}

/** Insert input for a {@link DesktopTaskCandidate}. */
export type NewDesktopTaskCandidate = Partial<DesktopTaskCandidate> &
  Pick<
    DesktopTaskCandidate,
    | 'ownerId'
    | 'action'
    | 'proposedChangeJson'
    | 'evidenceRefsJson'
    | 'confidence'
    | 'requiresApproval'
  >

/** An audit-log entry recording a context read and its policy decision. */
export interface DesktopContextAccessLog {
  accessId: string
  ownerId: string
  packetId: string | null
  runId: string | null
  sourceKind: DesktopContextSourceKind
  operation: string
  scopeJson: string
  sensitivityTier: string
  policyDecision: DesktopContextPolicyDecision
  dispatchId: string | null
  redactionSummaryJson: string
  createdAtMs: number
}

/** Insert input for a {@link DesktopContextAccessLog}. */
export type NewDesktopContextAccessLog = Partial<DesktopContextAccessLog> &
  Pick<
    DesktopContextAccessLog,
    'ownerId' | 'sourceKind' | 'operation' | 'scopeJson' | 'sensitivityTier' | 'policyDecision'
  >

/** A per-subject user override that hides or snoozes an attention surface. */
export interface DesktopAttentionOverride {
  ownerId: string
  subjectKind: string
  subjectId: string
  hiddenUntilMs: number | null
  dismissedAtMs: number | null
  reason: string | null
  createdAtMs: number
}

/** Upsert input for a {@link DesktopAttentionOverride}. */
export type NewDesktopAttentionOverride = Partial<DesktopAttentionOverride> &
  Pick<DesktopAttentionOverride, 'ownerId' | 'subjectKind' | 'subjectId'>

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
/** Insert input for an {@link AgentArtifact}. */
export type NewAgentArtifact = Partial<AgentArtifact> &
  Pick<AgentArtifact, 'sessionId' | 'kind' | 'role' | 'uri'>

/** A parent→child delegation edge between two runs. */
export interface AgentDelegation {
  delegationId: string
  parentSessionId: string
  parentRunId: string
  childSessionId: string
  childRunId: string
  mode: DelegationMode
  status: DelegationStatus
  objective: string
  requestJson: string
  resultArtifactId: string | null
  createdAtMs: number
  completedAtMs: number | null
}

/** A capability grant scoped to a session (and optionally a run). */
export interface AgentGrant {
  grantId: string
  sessionId: string
  runId: string | null
  capability: string
  operation: string
  resourcePattern: string
  effect: GrantEffect
  source: GrantSource
  constraintsJson: string
  createdAtMs: number
  expiresAtMs: number | null
  revokedAtMs: number | null
}

/** Insert input for an {@link AgentSession}. */
export type NewAgentSession = Partial<AgentSession> &
  Pick<AgentSession, 'ownerId' | 'surfaceKind' | 'defaultAdapterId'>

/** Insert input for an {@link AgentRun}. */
export type NewAgentRun = Partial<AgentRun> &
  Pick<AgentRun, 'sessionId' | 'clientId' | 'requestId' | 'status' | 'mode'> & {
    inputJson?: string
  }

/** Insert input for a {@link RunAttempt}. */
export type NewRunAttempt = Partial<RunAttempt> &
  Pick<RunAttempt, 'runId' | 'attemptNo' | 'status' | 'adapterId' | 'adapterInstanceId'>

/** Insert input for an {@link AdapterBinding}. */
export type NewAdapterBinding = Partial<AdapterBinding> &
  Pick<
    AdapterBinding,
    'sessionId' | 'adapterId' | 'bindingGeneration' | 'resumeFidelity' | 'status'
  >

/** Insert input for an {@link AgentEvent}. */
export type NewAgentEvent = Partial<AgentEvent> & Pick<AgentEvent, 'sessionId' | 'type'>

/** Insert input for an {@link AgentGrant}. */
export type NewAgentGrant = Partial<AgentGrant> &
  Pick<
    AgentGrant,
    'sessionId' | 'capability' | 'operation' | 'resourcePattern' | 'effect' | 'source'
  >

/** Summary of the work done by {@link AgentStore.reconcileStartup}. */
export interface StartupReconciliationResult {
  orphanedAttemptIds: string[]
  orphanedRunIds: string[]
  staleBindingIds: string[]
  expiredContextPacketIds: string[]
  expiredContinuationCheckpointIds: string[]
  failedArtifactDeliveryIds: string[]
  failedTaskCandidateDeliveryIds: string[]
  recoveryDispatchIds: string[]
  clearedAttemptInstanceIds: number
  clearedBindingInstanceIds: number
  eventIds: string[]
}

/**
 * The kernel persistence contract implemented by `SqliteAgentStore`. All methods
 * are synchronous. Transactional methods run under a single hand-tracked
 * transaction (see `withTransaction` in `store.ts`).
 */
export interface AgentStore {
  close(): void
  withTransaction<T>(work: () => T): T
  migrate(): void
  reconcileStartup(): StartupReconciliationResult
  insertSession(input: NewAgentSession): AgentSession
  insertSurfaceConversation(input: NewSurfaceConversation): SurfaceConversation
  insertConversationTurn(input: NewConversationTurn): ConversationTurn
  insertRun(input: NewAgentRun): AgentRun
  insertAttempt(input: NewRunAttempt): RunAttempt
  insertAdapterBinding(input: NewAdapterBinding): AdapterBinding
  insertArtifact(input: NewAgentArtifact): AgentArtifact
  appendEvent(input: NewAgentEvent): AgentEvent
  insertGrant(input: NewAgentGrant): AgentGrant
  insertDesktopContextPacket(input: NewDesktopContextPacket): DesktopContextPacket
  insertDesktopDispatch(input: NewDesktopCoordinatorDispatch): DesktopCoordinatorDispatch
  resolveDesktopDispatch(
    dispatchId: string,
    input: {
      ownerId: string
      status: 'resolved' | 'cancelled'
      resolvedBy?: string | null
      resolutionJson?: string | null
      resolvedAtMs?: number
    }
  ): DesktopCoordinatorDispatch
  insertDesktopArtifactDelivery(input: NewDesktopArtifactDelivery): DesktopArtifactDelivery
  updateDesktopArtifactDelivery(
    deliveryId: string,
    input: { ownerId: string } & Partial<
      Pick<
        DesktopArtifactDelivery,
        | 'reviewStatus'
        | 'deliveryStatus'
        | 'attemptCount'
        | 'receiptJson'
        | 'errorJson'
        | 'deliveredAtMs'
      >
    >
  ): DesktopArtifactDelivery
  insertDesktopMemoryCandidate(input: NewDesktopMemoryCandidate): DesktopMemoryCandidate
  insertDesktopTaskCandidate(input: NewDesktopTaskCandidate): DesktopTaskCandidate
  insertDesktopContextAccessLog(input: NewDesktopContextAccessLog): DesktopContextAccessLog
  upsertDesktopAttentionOverride(input: NewDesktopAttentionOverride): DesktopAttentionOverride
  execute(sql: string, values?: unknown[]): number
  getOptionalRow(sql: string, values?: unknown[]): Record<string, unknown> | undefined
  getRow(sql: string, values?: unknown[]): Record<string, unknown>
  allRows(sql: string, values?: unknown[]): Record<string, unknown>[]
}
