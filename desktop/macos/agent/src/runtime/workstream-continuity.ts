import { createHash } from "node:crypto";

import type { DesktopActionQueueItem } from "./desktop-action-queue.js";
import { buildDesktopContextPacket, type BuiltDesktopContextPacket } from "./desktop-context-packet.js";
import { generateAgentId } from "./sqlite-store.js";
import { artifactFromRow } from "./kernel-support.js";
import { resolveSurfaceSession, type ResolveSurfaceSessionResult } from "./surface-session.js";
import type {
  AgentArtifact,
  AgentStore,
  DesktopTaskCandidate,
  DesktopTaskCandidateAction,
  DesktopTaskCandidateStatus,
  NewAgentArtifact,
  NewDesktopContextPacket,
} from "./types.js";

const DEFAULT_CONTEXT_TTL_MS = 30 * 60 * 1_000;
const DEFAULT_OPEN_LOOP_TTL_MS = 5 * 60 * 1_000;
const MAX_SUMMARY_CHARS = 8_000;
const MAX_TASK_CHARS = 4_000;
const MAX_EVENT_COUNT = 20;
const MAX_ARTIFACT_HEAD_COUNT = 10;
const MAX_EVIDENCE_REFS = 20;
const MAX_RECEIPT_CHARS = 8_000;
const MAX_CONTINUATION_TTL_MS = 7 * 24 * 60 * 60 * 1_000;

export interface WorkstreamSessionInput {
  ownerId: string;
  workstreamId: string;
  defaultAdapterId?: string;
  title?: string | null;
}

export interface WorkstreamEventContext {
  eventId: string;
  type: string;
  summary: string;
  occurredAtMs: number;
  evidenceRefs?: EvidenceRef[];
  sensitivityTier?: ContextSensitivityTier;
  redactedSummary?: string;
  policyDecision?: "allowed" | "dispatch_created";
  dispatchId?: string;
}

export interface WorkstreamArtifactHeadContext {
  logicalKey: string;
  artifactId: string;
  version: number;
  displayName?: string | null;
  contentHash?: string | null;
  evidenceRefs?: EvidenceRef[];
  sensitivityTier?: ContextSensitivityTier;
}

export type EvidenceKind =
  | "conversation"
  | "memory_item"
  | "workstream_event"
  | "artifact"
  | "chat_message"
  | "local_screen"
  | "external";

export interface EvidenceRef {
  kind: EvidenceKind;
  id: string;
  version?: string;
  scope: "canonical" | "device_local";
  device_id?: string;
  excerpt_hash?: string;
}

export type ContextSensitivityTier = "low" | "private" | "sensitive";

export interface WorkstreamProductContext {
  canonicalSummary: string;
  redactedCanonicalSummary?: string;
  summarySensitivityTier?: ContextSensitivityTier;
  latestEventSequence: number;
  selectedEvents?: WorkstreamEventContext[];
  currentTask?: {
    taskId: string;
    title: string;
    status: string;
    dueAtMs?: number | null;
    summary?: string | null;
    sensitivityTier?: ContextSensitivityTier;
    policyDecision?: "allowed" | "dispatch_created";
    dispatchId?: string;
  } | null;
  artifactHeads?: WorkstreamArtifactHeadContext[];
  provenance: {
    snapshotVersion: string;
    fetchedAtMs: number;
    source: string;
  };
}

export interface PersistWorkstreamContextInput extends WorkstreamSessionInput {
  runId?: string | null;
  objective: string;
  context: WorkstreamProductContext;
  ttlMs?: number;
  nowMs?: number;
}

export interface PersistWorkstreamArtifactVersionInput extends WorkstreamSessionInput {
  logicalKey: string;
  evidenceRefs: EvidenceRef[];
  sourceArtifactId?: string;
  artifact: Omit<NewAgentArtifact, "sessionId">;
  nowMs?: number;
}

export interface PersistAuthorizedPreparedArtifactInput extends PersistWorkstreamArtifactVersionInput {
  grantId: string;
}

export interface WorkstreamArtifactVersion {
  logicalKey: string;
  version: number;
  artifact: AgentArtifact;
  supersedesArtifactId: string | null;
  evidenceRefs: EvidenceRef[];
}

export interface WorkstreamContinuityProjection {
  agentSessionId: string | null;
  artifactVersions: WorkstreamArtifactVersion[];
  checkpoint: WorkstreamContinuationCheckpoint | null;
}

export interface WorkstreamContinuationCheckpoint {
  checkpointId: string;
  ownerId: string;
  workstreamId: string;
  sourceRuntimeId: string;
  canonicalSummary: string;
  redactedCanonicalSummary: string;
  summarySensitivityTier: ContextSensitivityTier;
  currentTask: WorkstreamProductContext["currentTask"];
  selectedEvents: WorkstreamEventContext[];
  artifactHeads: WorkstreamArtifactHeadContext[];
  provenance: WorkstreamProductContext["provenance"];
  evidenceRefs: EvidenceRef[];
  lastEventSequence: number;
  createdAtMs: number;
  expiresAtMs: number;
}

export interface CanonicalCandidatePayload {
  idempotencyKey: string;
  accountGeneration: number;
  proposal: {
    subject_kind: "task";
    proposed_action: "create" | "update" | "complete" | "cancel" | "supersede";
    task_id?: string;
    task_change: Record<string, unknown>;
    capture_confidence: number;
    ownership_confidence: number;
    goal_id?: string;
    workstream_id?: string;
    evidence_refs: EvidenceRef[];
    source_surface: string;
  };
}

export interface CanonicalCandidateReceipt {
  candidateId: string;
  status: "pending" | "accepted" | "rejected" | "expired";
  receipt: Record<string, unknown>;
}

export interface CanonicalCandidateTransport {
  createCandidate(payload: CanonicalCandidatePayload): Promise<CanonicalCandidateReceipt>;
}

export interface WorkstreamOpenLoopSnapshot {
  ownerId: string;
  sourceRuntimeId: string;
  deviceScoped: true;
  generatedAtMs: number;
  expiresAtMs: number;
  loops: Array<{
    itemKind: DesktopActionQueueItem["kind"];
    subjectKind: string;
    subjectId: string;
    title: string;
    reason: string;
    workstreamId: string | null;
    sourceSessionId: string | null;
    sourceRunId: string | null;
  }>;
}

export interface TaskSessionMigrationReport {
  migratedTaskMappings: number;
  copiedTurns: number;
  migratedArtifacts: number;
  invalidatedBindingIds: string[];
  legacySessionIds: string[];
  skippedMappings: number;
  compatibilityMappings: Array<{ taskId: string; workstreamId: string; agentSessionId: string }>;
}

export function workstreamSurfaceRef(workstreamId: string) {
  const id = requiredText(workstreamId, "workstreamId");
  return { surfaceKind: "workstream", externalRefKind: "workstream", externalRefId: id } as const;
}

export function resolveWorkstreamSession(
  store: AgentStore,
  input: WorkstreamSessionInput,
  nowMs: () => number = Date.now,
): ResolveSurfaceSessionResult {
  return resolveSurfaceSession(
    store,
    {
      ownerId: requiredText(input.ownerId, "ownerId"),
      surfaceRef: workstreamSurfaceRef(input.workstreamId),
      defaultAdapterId: input.defaultAdapterId,
      title: input.title,
    },
    nowMs,
  );
}

export function persistWorkstreamContextPacket(
  store: AgentStore,
  input: PersistWorkstreamContextInput,
): BuiltDesktopContextPacket {
  const now = input.nowMs ?? Date.now();
  const resolved = resolveWorkstreamSession(store, input, () => now);
  const context = minimizeProductContext(input.context);
  validateSensitiveWorkstreamContext(store, input.ownerId, context);
  const built = buildDesktopContextPacket({
    ownerId: input.ownerId,
    sessionId: resolved.agentSessionId,
    runId: input.runId ?? undefined,
    surfaceKind: "workstream",
    objective: input.objective,
    retentionClass: "ephemeral",
    ttlMs: input.ttlMs ?? DEFAULT_CONTEXT_TTL_MS,
    nowMs: now,
    selectedToolBundles: ["desktop.context.local_read"],
    snippets: [
      snippet(
        "canonical-summary",
        "canonical_summary",
        { workstreamId: input.workstreamId, ...context.provenance },
        context.canonicalSummary,
        context.redactedCanonicalSummary,
        context.summarySensitivityTier,
      ),
      ...(context.currentTask
        ? [snippet(
            "current-task",
            "current_task",
            { taskId: context.currentTask.taskId, ...context.provenance },
            JSON.stringify(context.currentTask),
            JSON.stringify({ taskId: context.currentTask.taskId, status: context.currentTask.status, dueAtMs: context.currentTask.dueAtMs ?? null }),
            context.currentTask.sensitivityTier ?? "private",
            context.currentTask.policyDecision,
            context.currentTask.dispatchId,
          )]
        : []),
      ...context.selectedEvents.map((event) =>
        snippet(
          `event-${event.eventId}`,
          "selected_workstream_event",
          { eventId: event.eventId, evidenceRefs: event.evidenceRefs ?? [] },
          JSON.stringify(event),
          event.redactedSummary ?? (event.sensitivityTier === "low" ? event.summary : "[private workstream event]"),
          event.sensitivityTier ?? "private",
          event.policyDecision,
          event.dispatchId,
        ),
      ),
      ...context.artifactHeads.map((head) =>
        snippet(
          `artifact-${head.artifactId}`,
          "artifact_head",
          { artifactId: head.artifactId, evidenceRefs: head.evidenceRefs ?? [] },
          JSON.stringify(head),
          JSON.stringify({ logicalKey: head.logicalKey, artifactId: head.artifactId, version: head.version }),
          head.sensitivityTier ?? "private",
        ),
      ),
    ],
  });

  store.withTransaction(() => {
    store.insertDesktopContextPacket({
      ...(built.packet as unknown as NewDesktopContextPacket),
      packetJson: JSON.stringify(built.packet.packetJson),
      redactedPreviewJson: JSON.stringify(built.packet.redactedPreviewJson),
    });
    for (const accessLog of built.accessLogs) store.insertDesktopContextAccessLog(accessLog);
  });
  return built;
}

export function persistAuthorizedPreparedArtifact(
  store: AgentStore,
  input: PersistAuthorizedPreparedArtifactInput,
): WorkstreamArtifactVersion {
  const session = resolveWorkstreamSession(store, input);
  const now = input.nowMs ?? Date.now();
  const grant = store.getOptionalRow(
    `SELECT g.grant_id, g.session_id, g.capability, g.operation, g.resource_pattern,
            g.effect, g.expires_at_ms, g.revoked_at_ms, s.owner_id
       FROM grants g
       JOIN sessions s ON s.session_id = g.session_id
      WHERE g.grant_id = ?`,
    [input.grantId],
  );
  if (!grant || grant.owner_id !== input.ownerId) {
    throw new Error("Prepared artifact grant was not found for owner");
  }
  if (
    grant.session_id !== session.agentSessionId
    || grant.effect !== "allow"
    || grant.capability !== "desktop.workstream.artifact.prepare"
    || grant.operation !== "prepare_artifact"
    || grant.resource_pattern !== `workstream:${input.workstreamId}`
    || grant.revoked_at_ms != null
    || typeof grant.expires_at_ms !== "number"
    || grant.expires_at_ms <= now
  ) {
    throw new Error("Prepared artifact grant is invalid, expired, or out of scope");
  }
  return persistWorkstreamArtifactVersion(store, input);
}

export function persistWorkstreamArtifactVersion(
  store: AgentStore,
  input: PersistWorkstreamArtifactVersionInput,
): WorkstreamArtifactVersion {
  const now = input.nowMs ?? Date.now();
  const logicalKey = requiredText(input.logicalKey, "logicalKey");
  const evidenceRefs = boundedEvidenceRefs(input.evidenceRefs, MAX_EVIDENCE_REFS);
  if (evidenceRefs.length === 0) throw new Error("Workstream artifact versions require cited evidence");
  return store.withTransaction(() => {
    const resolved = resolveWorkstreamSession(store, input, () => now);
    const sourceArtifactId = input.sourceArtifactId?.trim();
    if (sourceArtifactId) {
      const existing = store.getOptionalRow(
        `SELECT v.version, v.supersedes_artifact_id, v.evidence_refs_json, a.*
         FROM workstream_artifact_versions v
         JOIN artifacts a ON a.artifact_id = v.artifact_id
         WHERE v.session_id = ? AND v.logical_key = ?
           AND json_extract(a.metadata_json, '$.sourceArtifactId') = ?
         ORDER BY v.version DESC LIMIT 1`,
        [resolved.agentSessionId, logicalKey, sourceArtifactId],
      );
      if (existing) {
        return {
          logicalKey,
          version: Number(existing.version),
          artifact: artifactFromRow(existing),
          supersedesArtifactId: nullableText(existing.supersedes_artifact_id),
          evidenceRefs: parseEvidenceRefs(String(existing.evidence_refs_json)),
        };
      }
    }
    const executionScope = resolveArtifactExecutionScope(
      store,
      resolved.agentSessionId,
      input.artifact.runId ?? null,
      input.artifact.attemptId ?? null,
    );
    const prior = store.getOptionalRow(
      `SELECT h.artifact_id, h.version
       FROM workstream_artifact_heads h
       WHERE h.session_id = ? AND h.logical_key = ?`,
      [resolved.agentSessionId, logicalKey],
    );
    const version = prior ? Number(prior.version) + 1 : 1;
    const supersedesArtifactId = prior ? String(prior.artifact_id) : null;
    const artifact = store.insertArtifact({
      ...input.artifact,
      sessionId: resolved.agentSessionId,
      runId: executionScope.runId,
      attemptId: executionScope.attemptId,
      createdAtMs: input.artifact.createdAtMs ?? now,
      metadataJson: JSON.stringify({
        ...parseObject(input.artifact.metadataJson),
        ...(sourceArtifactId ? { sourceArtifactId } : {}),
        workstreamId: input.workstreamId,
        logicalKey,
        logicalVersion: version,
        supersedesArtifactId,
        evidenceRefs,
      }),
    });
    store.execute(
      `INSERT INTO workstream_artifact_versions (
        session_id, logical_key, version, artifact_id, supersedes_artifact_id,
        evidence_refs_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [resolved.agentSessionId, logicalKey, version, artifact.artifactId, supersedesArtifactId, JSON.stringify(evidenceRefs), now],
    );
    store.execute(
      `INSERT INTO workstream_artifact_heads (session_id, logical_key, artifact_id, version, updated_at_ms)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(session_id, logical_key) DO UPDATE SET
         artifact_id = excluded.artifact_id,
         version = excluded.version,
         updated_at_ms = excluded.updated_at_ms`,
      [resolved.agentSessionId, logicalKey, artifact.artifactId, version, now],
    );
    store.appendEvent({
      sessionId: resolved.agentSessionId,
      runId: artifact.runId,
      attemptId: artifact.attemptId,
      type: "workstream.artifact_version_persisted",
      payloadJson: JSON.stringify({ artifactId: artifact.artifactId, logicalKey, version, supersedesArtifactId, evidenceRefs }),
      createdAtMs: now,
    });
    return { logicalKey, version, artifact, supersedesArtifactId, evidenceRefs };
  });
}

export function projectWorkstreamContinuity(
  store: AgentStore,
  input: { ownerId: string; workstreamId: string; nowMs?: number },
): WorkstreamContinuityProjection {
  const mapping = store.getOptionalRow(
    `SELECT agent_session_id FROM surface_conversations
     WHERE owner_id = ? AND surface_kind = 'workstream'
       AND external_ref_kind = 'workstream' AND external_ref_id = ?`,
    [input.ownerId, input.workstreamId],
  );
  if (!mapping) return { agentSessionId: null, artifactVersions: [], checkpoint: null };
  const agentSessionId = String(mapping.agent_session_id);
  const artifactVersions = store.allRows(
    `SELECT v.logical_key, v.version, v.supersedes_artifact_id, v.evidence_refs_json, a.*
     FROM workstream_artifact_versions v
     JOIN artifacts a ON a.artifact_id = v.artifact_id
     WHERE v.session_id = ? ORDER BY v.logical_key ASC, v.version ASC`,
    [agentSessionId],
  ).map((row) => ({
    logicalKey: String(row.logical_key),
    version: Number(row.version),
    artifact: artifactFromRow(row),
    supersedesArtifactId: nullableText(row.supersedes_artifact_id),
    evidenceRefs: parseEvidenceRefs(String(row.evidence_refs_json)),
  }));
  return {
    agentSessionId,
    artifactVersions,
    checkpoint: readWorkstreamContinuationCheckpoint(store, {
      ownerId: input.ownerId,
      workstreamId: input.workstreamId,
      nowMs: input.nowMs,
    }),
  };
}

export function exportWorkstreamContinuationCheckpoint(
  store: AgentStore,
  input: WorkstreamSessionInput & {
    sourceRuntimeId: string;
    context: WorkstreamProductContext;
    ttlMs: number;
    nowMs?: number;
    exportDispatchId?: string;
  },
): WorkstreamContinuationCheckpoint {
  const now = input.nowMs ?? Date.now();
  if (!Number.isFinite(input.ttlMs) || input.ttlMs <= 0 || input.ttlMs > MAX_CONTINUATION_TTL_MS) {
    throw new Error("Continuation checkpoint TTL must be positive and at most seven days");
  }
  const resolved = resolveWorkstreamSession(store, input, () => now);
  const context = minimizeProductContext(input.context);
  validateSensitiveWorkstreamContext(store, input.ownerId, context);
  const requiresExportApproval =
    contextEvidenceRefs(context).some((ref) => ref.scope === "device_local") ||
    contextHasSensitiveContent(context);
  if (requiresExportApproval) {
    assertApprovedContextDispatch(
      store,
      input.ownerId,
      input.exportDispatchId,
      "export_workstream_continuation",
    );
  }
  const exportContext = targetSafeCheckpointContext(context);
  const lastEventSequence = context.latestEventSequence;
  const checkpoint: WorkstreamContinuationCheckpoint = {
    checkpointId: `wcp_${hash(`${input.ownerId}:${input.workstreamId}:${input.sourceRuntimeId}:${lastEventSequence}:${now}`).slice(0, 24)}`,
    ownerId: input.ownerId,
    workstreamId: input.workstreamId,
    sourceRuntimeId: requiredText(input.sourceRuntimeId, "sourceRuntimeId"),
    canonicalSummary: exportContext.canonicalSummary,
    redactedCanonicalSummary: exportContext.redactedCanonicalSummary,
    summarySensitivityTier: exportContext.summarySensitivityTier,
    currentTask: exportContext.currentTask,
    selectedEvents: exportContext.selectedEvents,
    artifactHeads: exportContext.artifactHeads,
    provenance: exportContext.provenance,
    evidenceRefs: boundedEvidenceRefs(
      [...exportContext.selectedEvents.flatMap((event) => event.evidenceRefs ?? []), ...exportContext.artifactHeads.flatMap((head) => head.evidenceRefs ?? [])],
      MAX_EVIDENCE_REFS,
    ),
    lastEventSequence,
    createdAtMs: now,
    expiresAtMs: now + input.ttlMs,
  };
  upsertCheckpoint(store, checkpoint, now);
  const stored = store.getRow(
    `SELECT checkpoint_json FROM workstream_continuation_checkpoints
     WHERE owner_id = ? AND workstream_id = ? AND source_runtime_id = ?`,
    [checkpoint.ownerId, checkpoint.workstreamId, checkpoint.sourceRuntimeId],
  );
  return normalizeCheckpoint(JSON.parse(String(stored.checkpoint_json)) as WorkstreamContinuationCheckpoint);
}

export function importWorkstreamContinuationCheckpoint(
  store: AgentStore,
  checkpoint: WorkstreamContinuationCheckpoint,
  input: { targetRuntimeId: string; nowMs?: number },
): ResolveSurfaceSessionResult {
  const now = input.nowMs ?? Date.now();
  const normalized = normalizeCheckpoint(checkpoint);
  if (normalized.expiresAtMs <= now) throw new Error("Continuation checkpoint has expired");
  if (normalized.expiresAtMs - normalized.createdAtMs > MAX_CONTINUATION_TTL_MS) {
    throw new Error("Continuation checkpoint exceeds the maximum TTL");
  }
  requiredText(input.targetRuntimeId, "targetRuntimeId");
  return store.withTransaction(() => {
    const resolved = resolveWorkstreamSession(store, normalized, () => now);
    upsertCheckpoint(store, normalized, now);
    const effective = readWorkstreamContinuationCheckpoint(store, {
      ownerId: normalized.ownerId,
      workstreamId: normalized.workstreamId,
      nowMs: now,
    }) ?? normalized;
    persistWorkstreamContextPacket(store, {
      ownerId: effective.ownerId,
      workstreamId: effective.workstreamId,
      objective: "Resume imported workstream context",
      context: {
        canonicalSummary: effective.canonicalSummary,
        redactedCanonicalSummary: effective.redactedCanonicalSummary,
        summarySensitivityTier: effective.summarySensitivityTier,
        latestEventSequence: effective.lastEventSequence,
        currentTask: effective.currentTask,
        selectedEvents: effective.selectedEvents,
        artifactHeads: effective.artifactHeads,
        provenance: effective.provenance,
      },
      ttlMs: effective.expiresAtMs - now,
      nowMs: now,
    });
    store.appendEvent({
      sessionId: resolved.agentSessionId,
      type: "workstream.continuation_imported",
      visibility: "internal",
      payloadJson: JSON.stringify({
        checkpointId: effective.checkpointId,
        sourceRuntimeId: effective.sourceRuntimeId,
        targetRuntimeId: input.targetRuntimeId,
        lastEventSequence: effective.lastEventSequence,
      }),
      createdAtMs: now,
    });
    return resolved;
  });
}

export async function deliverDesktopTaskCandidate(
  store: AgentStore,
  input: { ownerId: string; candidateId: string; transport: CanonicalCandidateTransport; nowMs?: () => number },
): Promise<DesktopTaskCandidate> {
  const nowMs = input.nowMs ?? Date.now;
  const current = readTaskCandidate(store, input.ownerId, input.candidateId);
  if (current.deliveryStatus === "delivered") return current;
  if (current.status !== "pending") throw new Error(`Only pending local Candidates can be delivered; got ${current.status}`);
  if (!["pending", "failed"].includes(current.deliveryStatus)) {
    throw new Error(`Candidate delivery is not eligible from ${current.deliveryStatus}`);
  }
  if (current.generationReconciled !== 1) throw new Error("Candidate account generation must be reconciled before delivery");
  const payload = canonicalCandidatePayload(current);
  store.execute(
    `UPDATE desktop_task_candidates
     SET delivery_status = 'delivering', delivery_attempt_count = delivery_attempt_count + 1,
         last_delivery_error_json = NULL, updated_at_ms = ?
     WHERE candidate_id = ? AND owner_id = ? AND delivery_status != 'delivered'`,
    [nowMs(), current.candidateId, current.ownerId],
  );
  try {
    const receipt = normalizeCandidateReceipt(await input.transport.createCandidate(payload));
    const boundedReceipt = boundedJson(receipt.receipt, MAX_RECEIPT_CHARS);
    return store.withTransaction(() => {
      const deliveredAtMs = nowMs();
      store.execute(
        `UPDATE desktop_task_candidates
         SET status = ?, delivery_status = 'delivered', backend_candidate_id = ?,
             backend_receipt_json = ?, backend_resolution_status = ?,
             last_delivery_error_json = NULL, delivered_at_ms = ?, updated_at_ms = ?,
             resolved_at_ms = ?
         WHERE candidate_id = ? AND owner_id = ?`,
        [
          localCandidateStatus(receipt.status),
          receipt.candidateId,
          JSON.stringify(boundedReceipt),
          receipt.status,
          deliveredAtMs,
          deliveredAtMs,
          receipt.status === "pending" ? null : deliveredAtMs,
          current.candidateId,
          current.ownerId,
        ],
      );
      if (current.sourceSessionId) {
        store.appendEvent({
          sessionId: current.sourceSessionId,
          runId: current.sourceRunId,
          type: "task_candidate.delivered",
          payloadJson: JSON.stringify({
            localCandidateId: current.candidateId,
            backendCandidateId: receipt.candidateId,
            backendStatus: receipt.status,
            receiptHash: `sha256:${hash(JSON.stringify(boundedReceipt))}`,
          }),
          createdAtMs: deliveredAtMs,
        });
      }
      return readTaskCandidate(store, current.ownerId, current.candidateId);
    });
  } catch (error) {
    const failedAtMs = nowMs();
    store.execute(
      `UPDATE desktop_task_candidates
       SET delivery_status = 'failed', last_delivery_error_json = ?, updated_at_ms = ?
       WHERE candidate_id = ? AND owner_id = ? AND delivery_status != 'delivered'`,
      [JSON.stringify({ message: error instanceof Error ? error.message.slice(0, 500) : "Candidate delivery failed" }), failedAtMs, current.candidateId, current.ownerId],
    );
    throw error;
  }
}

export function projectCanonicalCandidateResolution(
  store: AgentStore,
  input: {
    ownerId: string;
    backendCandidateId: string;
    status: Exclude<CanonicalCandidateReceipt["status"], "pending">;
    receipt?: Record<string, unknown>;
    nowMs?: number;
  },
): DesktopTaskCandidate {
  const now = input.nowMs ?? Date.now();
  const row = store.getRow(
    `SELECT candidate_id, source_session_id, source_run_id, status
     FROM desktop_task_candidates WHERE owner_id = ? AND backend_candidate_id = ?`,
    [input.ownerId, input.backendCandidateId],
  );
  const currentStatus = String(row.status) as DesktopTaskCandidateStatus;
  if (currentStatus !== "forwarded" && currentStatus !== input.status) {
    throw new Error(`Cannot replace terminal Candidate status ${currentStatus} with ${input.status}`);
  }
  return store.withTransaction(() => {
    store.execute(
      `UPDATE desktop_task_candidates
       SET status = ?, backend_resolution_status = ?, backend_resolution_receipt_json = COALESCE(?, backend_resolution_receipt_json),
           resolved_at_ms = ?, updated_at_ms = ?
       WHERE owner_id = ? AND backend_candidate_id = ?`,
      [input.status, input.status, input.receipt ? JSON.stringify(boundedJson(input.receipt, MAX_RECEIPT_CHARS)) : null, now, now, input.ownerId, input.backendCandidateId],
    );
    if (row.source_session_id) {
      store.appendEvent({
        sessionId: String(row.source_session_id),
        runId: nullableText(row.source_run_id),
        type: "task_candidate.resolution_projected",
        payloadJson: JSON.stringify({ backendCandidateId: input.backendCandidateId, status: input.status }),
        createdAtMs: now,
      });
    }
    return readTaskCandidate(store, input.ownerId, String(row.candidate_id));
  });
}

export function reconcileLegacyTaskCandidateOutbox(
  store: AgentStore,
  input: { ownerId: string; accountGeneration: number; candidateIds?: string[]; nowMs?: number },
): { eligibleCandidateIds: string[]; terminalCandidateIds: string[] } {
  if (!Number.isInteger(input.accountGeneration) || input.accountGeneration < 0) {
    throw new Error("accountGeneration must be a non-negative integer");
  }
  const rows = store.allRows(
    `SELECT candidate_id, status FROM desktop_task_candidates
     WHERE owner_id = ? AND generation_reconciled = 0
       ${input.candidateIds?.length ? `AND candidate_id IN (${input.candidateIds.map(() => "?").join(",")})` : ""}`,
    [input.ownerId, ...(input.candidateIds ?? [])],
  );
  const eligibleCandidateIds = rows.filter((row) => row.status === "pending").map((row) => String(row.candidate_id));
  const terminalCandidateIds = rows.filter((row) => row.status !== "pending").map((row) => String(row.candidate_id));
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    for (const candidateId of eligibleCandidateIds) {
      store.execute(
        `UPDATE desktop_task_candidates SET account_generation = ?, generation_reconciled = 1,
         delivery_status = 'pending', updated_at_ms = ?
         WHERE owner_id = ? AND candidate_id = ? AND status = 'pending' AND generation_reconciled = 0`,
        [input.accountGeneration, now, input.ownerId, candidateId],
      );
    }
    for (const candidateId of terminalCandidateIds) {
      store.execute(
        `UPDATE desktop_task_candidates SET account_generation = ?, generation_reconciled = 1,
         delivery_status = 'blocked', updated_at_ms = ?
         WHERE owner_id = ? AND candidate_id = ? AND generation_reconciled = 0`,
        [input.accountGeneration, now, input.ownerId, candidateId],
      );
    }
    return { eligibleCandidateIds, terminalCandidateIds };
  });
}

export function readWorkstreamContinuationCheckpoint(
  store: AgentStore,
  input: { ownerId: string; workstreamId: string; nowMs?: number },
): WorkstreamContinuationCheckpoint | null {
  const row = store.getOptionalRow(
    `SELECT checkpoint_json FROM workstream_continuation_checkpoints
     WHERE owner_id = ? AND workstream_id = ? AND expires_at_ms > ?
     ORDER BY last_event_sequence DESC, updated_at_ms DESC LIMIT 1`,
    [input.ownerId, input.workstreamId, input.nowMs ?? Date.now()],
  );
  return row
    ? normalizeCheckpoint(JSON.parse(String(row.checkpoint_json)) as WorkstreamContinuationCheckpoint)
    : null;
}

export function buildWorkstreamOpenLoopSnapshot(input: {
  ownerId: string;
  sourceRuntimeId: string;
  actionQueue: readonly DesktopActionQueueItem[];
  sessionWorkstreamIds?: ReadonlyMap<string, string>;
  ttlMs?: number;
  nowMs?: number;
}): WorkstreamOpenLoopSnapshot {
  const now = input.nowMs ?? Date.now();
  const ttl = input.ttlMs ?? DEFAULT_OPEN_LOOP_TTL_MS;
  if (!Number.isFinite(ttl) || ttl <= 0) throw new Error("Open-loop snapshot TTL must be positive");
  return {
    ownerId: input.ownerId,
    sourceRuntimeId: requiredText(input.sourceRuntimeId, "sourceRuntimeId"),
    deviceScoped: true,
    generatedAtMs: now,
    expiresAtMs: now + ttl,
    loops: input.actionQueue
      .filter((item) => ["dispatch", "failed_run", "artifact_delivery", "stale_run", "candidate_review"].includes(item.kind))
      .map((item) => ({
        itemKind: item.kind,
        subjectKind: item.subjectKind,
        subjectId: item.subjectId,
        title: item.title,
        reason: item.reason,
        workstreamId: item.sourceSessionId ? input.sessionWorkstreamIds?.get(item.sourceSessionId) ?? null : null,
        sourceSessionId: item.sourceSessionId ?? null,
        sourceRunId: item.sourceRunId ?? null,
      })),
  };
}

export function migrateTaskSessionsToWorkstreams(
  store: AgentStore,
  input: { ownerId: string; mappings: Array<{ taskId: string; workstreamId: string }>; nowMs?: number },
): TaskSessionMigrationReport {
  const now = input.nowMs ?? Date.now();
  return store.withTransaction(() => {
    const report: TaskSessionMigrationReport = {
      migratedTaskMappings: 0,
      copiedTurns: 0,
      migratedArtifacts: 0,
      invalidatedBindingIds: [],
      legacySessionIds: [],
      skippedMappings: 0,
      compatibilityMappings: [],
    };
    for (const mapping of input.mappings) {
      const taskId = requiredText(mapping.taskId, "taskId");
      const workstreamId = requiredText(mapping.workstreamId, "workstreamId");
      const canonical = resolveWorkstreamSession(store, { ownerId: input.ownerId, workstreamId }, () => now);
      const taskRows = store.allRows(
        `SELECT conversation_id, agent_session_id, surface_kind, external_ref_kind, external_ref_id
         FROM surface_conversations
         WHERE owner_id = ? AND external_ref_id = ?
           AND (external_ref_kind = 'task' OR surface_kind = 'task_chat')`,
        [input.ownerId, taskId],
      );
      if (taskRows.length === 0) {
        report.skippedMappings += 1;
        continue;
      }
      for (const row of taskRows) {
        const sourceConversationId = String(row.conversation_id);
        const sourceSessionId = String(row.agent_session_id);
        if (sourceConversationId === canonical.conversationId && sourceSessionId === canonical.agentSessionId) {
          report.skippedMappings += 1;
          continue;
        }
        if (!report.legacySessionIds.includes(sourceSessionId)) report.legacySessionIds.push(sourceSessionId);
        const copied = store.execute(
          `INSERT INTO conversation_turns (
             conversation_id, turn_id, role, surface_kind, content, created_at_ms, metadata_json
           )
           SELECT ?, turn_id, role, surface_kind, content, created_at_ms, metadata_json
           FROM conversation_turns WHERE conversation_id = ?`,
          [canonical.conversationId, sourceConversationId],
        );
        report.copiedTurns += copied;
        store.execute("DELETE FROM conversation_turns WHERE conversation_id = ?", [sourceConversationId]);
        const sourceArtifacts = store.allRows("SELECT * FROM artifacts WHERE session_id = ?", [sourceSessionId]);
        for (const artifact of sourceArtifacts) {
          const migratedArtifactId = `art_${hash(`${input.ownerId}:${workstreamId}:${String(artifact.artifact_id)}`).slice(0, 32)}`;
          report.migratedArtifacts += store.execute(
            `INSERT OR IGNORE INTO artifacts (
               artifact_id, session_id, run_id, attempt_id, kind, role, uri, display_name,
               mime_type, content_hash, size_bytes, lifecycle_state, lifecycle_updated_at_ms,
               metadata_json, created_at_ms
             ) VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, json_set(?, '$.migratedFromArtifactId', ?, '$.migratedFromSessionId', ?), ?)`,
            [migratedArtifactId, canonical.agentSessionId, artifact.kind, artifact.role, artifact.uri,
             artifact.display_name, artifact.mime_type, artifact.content_hash, artifact.size_bytes,
             artifact.lifecycle_state, artifact.lifecycle_updated_at_ms, artifact.metadata_json,
             artifact.artifact_id, sourceSessionId, artifact.created_at_ms],
          );
        }
        const activeBindings = store.allRows(
          "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND status = 'active'",
          [sourceSessionId],
        );
        for (const binding of activeBindings) {
          const bindingId = String(binding.binding_id);
          store.execute(
            `UPDATE adapter_bindings SET status = 'stale', invalidated_at_ms = ?, updated_at_ms = ?
             WHERE binding_id = ? AND status = 'active'`,
            [now, now, bindingId],
          );
          report.invalidatedBindingIds.push(bindingId);
        }
        store.execute(
          `UPDATE surface_conversations
           SET conversation_id = ?, agent_session_id = ?, last_active_at_ms = ?
           WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
          [canonical.conversationId, canonical.agentSessionId, now, input.ownerId, row.surface_kind, row.external_ref_kind, row.external_ref_id],
        );
        report.migratedTaskMappings += 1;
        store.appendEvent({
          sessionId: canonical.agentSessionId,
          type: "workstream.task_session_migrated",
          visibility: "internal",
          payloadJson: JSON.stringify({
            taskId,
            workstreamId,
            legacySessionId: sourceSessionId,
            copiedTurns: copied,
            invalidatedBindingIds: report.invalidatedBindingIds,
          }),
          createdAtMs: now,
        });
      }
      report.compatibilityMappings.push({ taskId, workstreamId, agentSessionId: canonical.agentSessionId });
    }
    return report;
  });
}

function canonicalCandidatePayload(candidate: DesktopTaskCandidate): CanonicalCandidatePayload {
  if (candidate.action !== "create" && !candidate.taskRef) throw new Error(`${candidate.action} candidates require taskRef`);
  const evidenceRefs = parseEvidenceRefs(candidate.evidenceRefsJson);
  return {
    idempotencyKey: candidate.deliveryKey,
    accountGeneration: candidate.accountGeneration,
      proposal: {
      subject_kind: "task",
      proposed_action: canonicalAction(candidate.action),
      ...(candidate.action !== "create" && candidate.taskRef ? { task_id: candidate.taskRef } : {}),
      task_change: parseObject(candidate.proposedChangeJson),
      capture_confidence: candidate.confidence,
      ownership_confidence: candidate.ownershipConfidence,
      ...(candidate.goalRef ? { goal_id: candidate.goalRef } : {}),
      ...(candidate.workstreamRef ? { workstream_id: candidate.workstreamRef } : {}),
      evidence_refs: evidenceRefs,
      source_surface: candidate.sourceSurface,
    },
  };
}

function canonicalAction(action: DesktopTaskCandidateAction): CanonicalCandidatePayload["proposal"]["proposed_action"] {
  return action === "delete" ? "cancel" : action;
}

function localCandidateStatus(status: CanonicalCandidateReceipt["status"]): DesktopTaskCandidateStatus {
  return status === "pending" ? "forwarded" : status;
}

function readTaskCandidate(store: AgentStore, ownerId: string, candidateId: string): DesktopTaskCandidate {
  const row = store.getRow("SELECT * FROM desktop_task_candidates WHERE owner_id = ? AND candidate_id = ?", [ownerId, candidateId]);
  return {
    candidateId: String(row.candidate_id), ownerId: String(row.owner_id),
    sourceSessionId: nullableText(row.source_session_id), sourceRunId: nullableText(row.source_run_id),
    action: String(row.action) as DesktopTaskCandidateAction, taskRef: nullableText(row.task_ref),
    proposedChangeJson: String(row.proposed_change_json), evidenceRefsJson: String(row.evidence_refs_json),
    confidence: Number(row.confidence), requiresApproval: Number(row.requires_approval) as 0 | 1,
    ownershipConfidence: Number(row.ownership_confidence), goalRef: nullableText(row.goal_ref),
    workstreamRef: nullableText(row.workstream_ref), sourceSurface: String(row.source_surface),
    accountGeneration: Number(row.account_generation),
    generationReconciled: Number(row.generation_reconciled) === 1 ? 1 : 0,
    status: String(row.status) as DesktopTaskCandidateStatus,
    deliveryStatus: String(row.delivery_status) as DesktopTaskCandidate["deliveryStatus"],
    deliveryAttemptCount: Number(row.delivery_attempt_count), deliveryKey: String(row.delivery_key),
    backendCandidateId: nullableText(row.backend_candidate_id), backendReceiptJson: nullableText(row.backend_receipt_json),
    backendResolutionReceiptJson: nullableText(row.backend_resolution_receipt_json),
    backendResolutionStatus: nullableText(row.backend_resolution_status), lastDeliveryErrorJson: nullableText(row.last_delivery_error_json),
    createdAtMs: Number(row.created_at_ms), updatedAtMs: Number(row.updated_at_ms),
    deliveredAtMs: nullableNumber(row.delivered_at_ms), resolvedAtMs: nullableNumber(row.resolved_at_ms),
  };
}

function upsertCheckpoint(store: AgentStore, checkpoint: WorkstreamContinuationCheckpoint, updatedAtMs: number): void {
  store.execute(
    `INSERT INTO workstream_continuation_checkpoints (
       owner_id, workstream_id, source_runtime_id, checkpoint_id, checkpoint_json,
       last_event_sequence, expires_at_ms, created_at_ms, updated_at_ms
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(owner_id, workstream_id, source_runtime_id) DO UPDATE SET
       checkpoint_id = excluded.checkpoint_id,
       checkpoint_json = excluded.checkpoint_json,
       last_event_sequence = excluded.last_event_sequence,
       expires_at_ms = excluded.expires_at_ms,
       updated_at_ms = excluded.updated_at_ms
     WHERE excluded.last_event_sequence >= workstream_continuation_checkpoints.last_event_sequence`,
    [checkpoint.ownerId, checkpoint.workstreamId, checkpoint.sourceRuntimeId, checkpoint.checkpointId, JSON.stringify(checkpoint), checkpoint.lastEventSequence, checkpoint.expiresAtMs, checkpoint.createdAtMs, updatedAtMs],
  );
}

function resolveArtifactExecutionScope(
  store: AgentStore,
  sessionId: string,
  runId: string | null,
  attemptId: string | null,
): { runId: string | null; attemptId: string | null } {
  let normalizedRunId = runId;
  if (runId) {
    const run = store.getOptionalRow("SELECT session_id FROM runs WHERE run_id = ?", [runId]);
    if (!run || String(run.session_id) !== sessionId) {
      throw new Error("Artifact run does not belong to the resolved workstream session");
    }
  }
  if (attemptId) {
    const attempt = store.getOptionalRow(
      `SELECT a.run_id, r.session_id
       FROM run_attempts a JOIN runs r ON r.run_id = a.run_id
       WHERE a.attempt_id = ?`,
      [attemptId],
    );
    if (!attempt || String(attempt.session_id) !== sessionId) {
      throw new Error("Artifact attempt does not belong to the resolved workstream session");
    }
    if (runId && String(attempt.run_id) !== runId) {
      throw new Error("Artifact attempt does not belong to the supplied run");
    }
    normalizedRunId = String(attempt.run_id);
  }
  return { runId: normalizedRunId, attemptId };
}

function validateSensitiveWorkstreamContext(
  store: AgentStore,
  ownerId: string,
  context: Required<WorkstreamProductContext>,
): void {
  if (context.summarySensitivityTier === "sensitive") {
    throw new Error("Sensitive canonical summaries must be minimized before workstream context persistence");
  }
  if (context.currentTask?.sensitivityTier === "sensitive") {
    assertApprovedContextDispatch(store, ownerId, context.currentTask.dispatchId, "current_task");
  }
  for (const event of context.selectedEvents) {
    if (event.sensitivityTier === "sensitive") {
      assertApprovedContextDispatch(store, ownerId, event.dispatchId, "selected_workstream_event");
    }
  }
  if (context.artifactHeads.some((head) => head.sensitivityTier === "sensitive")) {
    throw new Error("Sensitive artifact descriptors must be minimized before workstream context persistence");
  }
}

function assertApprovedContextDispatch(
  store: AgentStore,
  ownerId: string,
  dispatchId: string | undefined,
  operation: string,
): void {
  if (!dispatchId) throw new Error(`Sensitive workstream context operation ${operation} requires a dispatch id`);
  const row = store.getOptionalRow(
    "SELECT kind, status, operation, resolution_json FROM desktop_dispatches WHERE dispatch_id = ? AND owner_id = ?",
    [dispatchId, ownerId],
  );
  if (!row || !["approval", "screen_context"].includes(String(row.kind)) || row.status !== "resolved") {
    throw new Error(`Sensitive context dispatch ${dispatchId} is not approved for owner`);
  }
  const resolution = row.resolution_json ? parseObject(String(row.resolution_json)) : {};
  if (resolution.decision !== "allow") throw new Error(`Sensitive context dispatch ${dispatchId} is not approved`);
  if (String(row.operation) !== operation) {
    throw new Error(`Sensitive context dispatch ${dispatchId} operation does not match ${operation}`);
  }
}

function contextEvidenceRefs(context: Required<WorkstreamProductContext>): EvidenceRef[] {
  return [
    ...context.selectedEvents.flatMap((event) => event.evidenceRefs ?? []),
    ...context.artifactHeads.flatMap((head) => head.evidenceRefs ?? []),
  ];
}

function contextHasSensitiveContent(context: Required<WorkstreamProductContext>): boolean {
  return context.summarySensitivityTier === "sensitive"
    || context.currentTask?.sensitivityTier === "sensitive"
    || context.selectedEvents.some((event) => event.sensitivityTier === "sensitive")
    || context.artifactHeads.some((head) => head.sensitivityTier === "sensitive");
}

function targetSafeCheckpointContext(
  context: Required<WorkstreamProductContext>,
): Required<WorkstreamProductContext> {
  return {
    ...context,
    canonicalSummary: context.summarySensitivityTier === "sensitive"
      ? context.redactedCanonicalSummary
      : context.canonicalSummary,
    summarySensitivityTier: context.summarySensitivityTier === "sensitive" ? "private" : context.summarySensitivityTier,
    currentTask: context.currentTask
      ? {
          ...context.currentTask,
          ...(context.currentTask.sensitivityTier === "sensitive"
            ? { title: "[private task]", summary: null, sensitivityTier: "private" as const }
            : {}),
          policyDecision: undefined,
          dispatchId: undefined,
        }
      : null,
    selectedEvents: context.selectedEvents.map((event) => ({
      ...event,
      ...(event.sensitivityTier === "sensitive"
        ? {
            summary: event.redactedSummary ?? "[private workstream event]",
            sensitivityTier: "private" as const,
          }
        : {}),
      policyDecision: undefined,
      dispatchId: undefined,
    })),
    artifactHeads: context.artifactHeads.map((head) => ({
      ...head,
      sensitivityTier: head.sensitivityTier === "sensitive" ? "private" : head.sensitivityTier,
    })),
  };
}

function normalizeCheckpoint(checkpoint: WorkstreamContinuationCheckpoint): WorkstreamContinuationCheckpoint {
  const context = minimizeProductContext({
    canonicalSummary: checkpoint.canonicalSummary,
    redactedCanonicalSummary: checkpoint.redactedCanonicalSummary,
    summarySensitivityTier: checkpoint.summarySensitivityTier,
    latestEventSequence: checkpoint.lastEventSequence,
    currentTask: checkpoint.currentTask,
    selectedEvents: checkpoint.selectedEvents,
    artifactHeads: checkpoint.artifactHeads,
    provenance: checkpoint.provenance,
  });
  if (!Number.isInteger(checkpoint.lastEventSequence) || checkpoint.lastEventSequence < 0) {
    throw new Error("Continuation checkpoint event sequence must be a non-negative integer");
  }
  if (!Number.isFinite(checkpoint.createdAtMs) || !Number.isFinite(checkpoint.expiresAtMs)) {
    throw new Error("Continuation checkpoint timestamps must be finite");
  }
  return {
    checkpointId: requiredText(checkpoint.checkpointId, "checkpointId"),
    ownerId: requiredText(checkpoint.ownerId, "ownerId"),
    workstreamId: requiredText(checkpoint.workstreamId, "workstreamId"),
    sourceRuntimeId: requiredText(checkpoint.sourceRuntimeId, "sourceRuntimeId"),
    canonicalSummary: context.canonicalSummary,
    redactedCanonicalSummary: context.redactedCanonicalSummary,
    summarySensitivityTier: context.summarySensitivityTier,
    currentTask: context.currentTask,
    selectedEvents: context.selectedEvents,
    artifactHeads: context.artifactHeads,
    provenance: context.provenance,
    evidenceRefs: boundedEvidenceRefs(checkpoint.evidenceRefs ?? [], MAX_EVIDENCE_REFS),
    lastEventSequence: checkpoint.lastEventSequence,
    createdAtMs: checkpoint.createdAtMs,
    expiresAtMs: checkpoint.expiresAtMs,
  };
}

function normalizeCandidateReceipt(receipt: CanonicalCandidateReceipt): CanonicalCandidateReceipt {
  const candidateId = requiredText(receipt.candidateId, "backend candidateId");
  if (!["pending", "accepted", "rejected", "expired"].includes(receipt.status)) {
    throw new Error("Backend Candidate receipt has an invalid status");
  }
  if (!receipt.receipt || Array.isArray(receipt.receipt) || typeof receipt.receipt !== "object") {
    throw new Error("Backend Candidate receipt payload must be an object");
  }
  return { candidateId, status: receipt.status, receipt: receipt.receipt };
}

function minimizeProductContext(context: WorkstreamProductContext): Required<WorkstreamProductContext> {
  if (!Number.isInteger(context.latestEventSequence) || context.latestEventSequence < 0) {
    throw new Error("Workstream latestEventSequence must be a non-negative integer");
  }
  return {
    canonicalSummary: boundedText(context.canonicalSummary, MAX_SUMMARY_CHARS),
    redactedCanonicalSummary: context.redactedCanonicalSummary
      ? boundedText(context.redactedCanonicalSummary, 1_000)
      : "[private workstream summary]",
    summarySensitivityTier: context.summarySensitivityTier ?? "private",
    latestEventSequence: context.latestEventSequence,
    currentTask: context.currentTask
      ? { ...context.currentTask, title: boundedText(context.currentTask.title, 500), summary: context.currentTask.summary ? boundedText(context.currentTask.summary, MAX_TASK_CHARS) : null }
      : null,
    selectedEvents: (context.selectedEvents ?? []).slice(-MAX_EVENT_COUNT).map((event) => ({
      ...event,
      summary: boundedText(event.summary, 1_000),
      redactedSummary: event.redactedSummary ? boundedText(event.redactedSummary, 500) : undefined,
      evidenceRefs: boundedEvidenceRefs(event.evidenceRefs ?? [], MAX_EVIDENCE_REFS),
    })),
    artifactHeads: (context.artifactHeads ?? []).slice(0, MAX_ARTIFACT_HEAD_COUNT).map((head) => ({
      ...head, evidenceRefs: boundedEvidenceRefs(head.evidenceRefs ?? [], MAX_EVIDENCE_REFS),
    })),
    provenance: context.provenance,
  };
}

function snippet(
  snippetId: string,
  operation: string,
  provenance: Record<string, unknown>,
  content: string,
  redactedContent: string,
  sensitivityTier: ContextSensitivityTier,
  policyDecision?: "allowed" | "dispatch_created",
  dispatchId?: string,
) {
  return {
    snippetId, sourceKind: "omi_db" as const, operation, provenance, content,
    redactedContent, sensitivityTier, policyDecision, dispatchId,
  };
}

function boundedJson(value: Record<string, unknown>, maxChars: number): Record<string, unknown> {
  const json = JSON.stringify(value);
  if (json.length <= maxChars) return value;
  return { truncated: true, receiptHash: `sha256:${hash(json)}` };
}

function parseObject(json: string | undefined): Record<string, unknown> {
  if (!json) return {};
  const value = JSON.parse(json) as unknown;
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error("Expected a JSON object");
  return value as Record<string, unknown>;
}

function parseEvidenceRefs(json: string): EvidenceRef[] {
  const value = JSON.parse(json) as unknown;
  if (!Array.isArray(value) || value.length === 0) throw new Error("Candidate evidence_refs must be a non-empty JSON array");
  if (value.some((ref) => !ref || Array.isArray(ref) || typeof ref !== "object")) {
    throw new Error("Candidate evidence_refs must contain typed reference objects");
  }
  return boundedEvidenceRefs(value as EvidenceRef[], MAX_EVIDENCE_REFS);
}

function boundedEvidenceRefs(values: readonly EvidenceRef[], limit: number): EvidenceRef[] {
  const refs = values.slice(0, limit).map(validateEvidenceRef);
  const seen = new Set<string>();
  return refs.filter((ref) => {
    const key = JSON.stringify(ref);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function validateEvidenceRef(value: EvidenceRef): EvidenceRef {
  const allowedKinds: EvidenceKind[] = ["conversation", "memory_item", "workstream_event", "artifact", "chat_message", "local_screen", "external"];
  if (!allowedKinds.includes(value.kind)) throw new Error("EvidenceRef kind is invalid");
  const id = requiredText(value.id, "EvidenceRef.id");
  if (value.scope === "device_local" && !value.device_id) throw new Error("device_local EvidenceRef requires device_id");
  if (value.scope === "canonical" && value.device_id) throw new Error("canonical EvidenceRef cannot carry device_id");
  if (value.scope !== "canonical" && value.scope !== "device_local") throw new Error("EvidenceRef scope is invalid");
  if (value.kind === "local_screen" && value.scope !== "device_local") throw new Error("local_screen EvidenceRef must be device_local");
  if (value.excerpt_hash && !/^[a-f0-9]{64}$/.test(value.excerpt_hash)) throw new Error("EvidenceRef excerpt_hash is invalid");
  return {
    kind: value.kind,
    id,
    ...(value.version ? { version: value.version.slice(0, 128) } : {}),
    scope: value.scope,
    ...(value.device_id ? { device_id: requiredText(value.device_id, "EvidenceRef.device_id") } : {}),
    ...(value.excerpt_hash ? { excerpt_hash: value.excerpt_hash } : {}),
  };
}

function boundedText(value: string, maxChars: number): string {
  const text = requiredText(value, "context text");
  return text.length <= maxChars ? text : `${text.slice(0, maxChars - 1)}…`;
}

function requiredText(value: string, field: string): string {
  const text = value.trim();
  if (!text) throw new Error(`${field} is required`);
  return text;
}

function nullableText(value: unknown): string | null {
  return value == null ? null : String(value);
}

function nullableNumber(value: unknown): number | null {
  return value == null ? null : Number(value);
}

function hash(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
