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

export type ResumeFidelity = "native" | "reconstructed" | "none";

export type AdapterBindingStatus = "active" | "stale" | "invalid" | "closed";

export type EventRetentionClass = "core" | "transient";

export type EventVisibility = "ui" | "internal";

export type ArtifactRole = "input" | "result" | "checkpoint" | "tool_output" | "log" | "other";

export type DelegationMode = "call" | "spawn" | "continue";

export type DelegationStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export type GrantEffect = "allow" | "deny";

export type GrantSource = "legacy_default" | "policy" | "user" | "system";

export type AgentIdKind = "session" | "run" | "attempt" | "event" | "binding" | "artifact" | "delegation" | "grant";

export interface AgentSession {
  sessionId: string;
  ownerId: string;
  agentDefinitionId: string;
  title: string | null;
  status: SessionStatus;
  surfaceKind: string;
  externalRefKind: string | null;
  externalRefId: string | null;
  legacyClientScope: string | null;
  legacySessionKey: string | null;
  defaultAdapterId: string;
  defaultCwd: string | null;
  modelProfile: string | null;
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
  metadataJson: string;
  createdAtMs: number;
}

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

export type NewAgentSession = Partial<AgentSession> & Pick<AgentSession, "ownerId" | "surfaceKind" | "defaultAdapterId">;

export type NewAgentRun = Partial<AgentRun> &
  Pick<AgentRun, "sessionId" | "clientId" | "requestId" | "status" | "mode"> & {
    inputJson?: string;
  };

export type NewRunAttempt = Partial<RunAttempt> &
  Pick<RunAttempt, "runId" | "attemptNo" | "status" | "adapterId" | "adapterInstanceId">;

export type NewAdapterBinding = Partial<AdapterBinding> &
  Pick<AdapterBinding, "sessionId" | "adapterId" | "bindingGeneration" | "resumeFidelity" | "status">;

export type NewAgentEvent = Partial<AgentEvent> & Pick<AgentEvent, "sessionId" | "type">;

export interface StartupReconciliationResult {
  orphanedAttemptIds: string[];
  orphanedRunIds: string[];
  staleBindingIds: string[];
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
  insertRun(input: NewAgentRun): AgentRun;
  insertAttempt(input: NewRunAttempt): RunAttempt;
  insertAdapterBinding(input: NewAdapterBinding): AdapterBinding;
  appendEvent(input: NewAgentEvent): AgentEvent;
  execute(sql: string, values?: unknown[]): number;
  getOptionalRow(sql: string, values?: unknown[]): Record<string, unknown> | undefined;
  getRow(sql: string, values?: unknown[]): Record<string, unknown>;
  allRows(sql: string, values?: unknown[]): Record<string, unknown>[];
}
