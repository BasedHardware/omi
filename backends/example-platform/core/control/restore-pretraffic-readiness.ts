import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId, type AccountControlProjection } from "./account-control";
import { evaluateAccountControlAdmission } from "./application-admission";
import {
  TOMBSTONE_REPLAY_CHECKPOINT_VERSION,
  type RestoreCoordinate,
  type RestoreScope,
  type TombstoneReplayCheckpoint,
} from "./tombstone-restore-replay";

export const RESTORE_GENERATION_COORDINATE_VERSION = "restore-generation-coordinate-v1" as const;
export const RESTORE_CHECKPOINT_CANDIDATE_VERSION = "restore-checkpoint-candidate-v1" as const;
export const RESTORE_GENERATION_ATTESTATION_VERSION = "restore-generation-attestation-v1" as const;
export const TERMINAL_FEED_APPLIED_COVERAGE_VERSION = "terminal-feed-applied-coverage-v1" as const;
export const RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION =
  "retained-terminal-fence-observation-v1" as const;
export const RETAINED_TERMINAL_FENCE_VERSION = "retained-terminal-fence-v1" as const;
export const RESTORE_PRETRAFFIC_READINESS_VERSION = "restore-pretraffic-readiness-v1" as const;

const DIGEST = /^[0-9a-f]{64}$/;
const MICROS = /^(?:0|[1-9][0-9]*)$/;
const MAX_COORDINATE_LENGTH = 256;

export interface RestoreGenerationCoordinate extends RestoreCoordinate {
  readonly version: typeof RESTORE_GENERATION_COORDINATE_VERSION;
  readonly restored_generation_digest: string;
  readonly target_identity_digest: string;
}

export interface PersistedRestoreCheckpointCandidate {
  readonly version: typeof RESTORE_CHECKPOINT_CANDIDATE_VERSION;
  readonly checkpoint: TombstoneReplayCheckpoint;
  readonly restored_generation_digest: string;
  readonly source_feed_generation_digest: string;
  readonly partition_topology_digest: string;
  readonly candidate_digest: string;
  readonly record_count: number;
  readonly recorded_at_epoch_micros: string;
  readonly persistence_receipt_digest: string;
}

export type RestoreGenerationAttestation =
  | Readonly<{
      version: typeof RESTORE_GENERATION_ATTESTATION_VERSION;
      state: "unavailable";
    }>
  | Readonly<{
      version: typeof RESTORE_GENERATION_ATTESTATION_VERSION;
      state: "current";
      restore_id: string;
      restore_scope: RestoreScope;
      restored_generation_digest: string;
      restored_snapshot_digest: string;
      target_identity_digest: string;
      attestation_receipt_digest: string;
    }>;

export interface TerminalFeedAppliedCoverage {
  readonly version: typeof TERMINAL_FEED_APPLIED_COVERAGE_VERSION;
  readonly state: "complete" | "incomplete";
  readonly restore_id: string;
  readonly restore_scope: RestoreScope;
  readonly restored_generation_digest: string;
  readonly restored_snapshot_digest: string;
  readonly source_snapshot_digest: string;
  readonly source_feed_generation_digest: string;
  readonly partition_topology_digest: string;
  readonly source_current_high_watermark: number;
  readonly gap_free_through_high_watermark: number;
  readonly applied_through_high_watermark: number;
  readonly checkpoint_digest: string;
  readonly coverage_receipt_digest: string;
}

export interface RetainedTerminalFence {
  readonly version: typeof RETAINED_TERMINAL_FENCE_VERSION;
  readonly account_id: string;
  readonly deletion_epoch: number;
  readonly control_revision: number;
  readonly terminal_record_digest: string;
  readonly source_restore_id: string;
  readonly restored_snapshot_digest: string;
  readonly fence_receipt_digest: string;
}

export type RetainedTerminalFenceObservation =
  | Readonly<{
      version: typeof RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION;
      state: "unavailable";
    }>
  | Readonly<{
      version: typeof RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION;
      state: "current";
      latest_fence: RetainedTerminalFence | null;
      observation_receipt_digest: string;
    }>;

export interface RestorePretrafficReadinessInput {
  readonly restore_generation: RestoreGenerationCoordinate;
  readonly generation_attestation: RestoreGenerationAttestation;
  readonly checkpoint_candidate: PersistedRestoreCheckpointCandidate | null;
  readonly terminal_feed_coverage: TerminalFeedAppliedCoverage | null;
  readonly control_projection: AccountControlProjection | null;
  readonly retained_fence_observation: RetainedTerminalFenceObservation;
}

export type RestorePretrafficBlocker =
  | "checkpoint_missing"
  | "checkpoint_coordinate_mismatch"
  | "generation_attestation_unavailable"
  | "generation_attestation_mismatch"
  | "terminal_feed_coverage_missing"
  | "terminal_feed_coverage_incomplete"
  | "terminal_feed_coverage_mismatch"
  | "control_state_absent"
  | "control_state_conflicting"
  | "control_state_not_activated"
  | "account_generation_legacy"
  | "account_generation_migrating"
  | "account_generation_rolled_back_stranded"
  | "account_lifecycle_not_active"
  | "retained_fence_unavailable"
  | "retained_terminal_fence_present";

export type RestorePretrafficReadiness =
  | Readonly<{
      version: typeof RESTORE_PRETRAFFIC_READINESS_VERSION;
      kind: "blocked";
      blockers: readonly RestorePretrafficBlocker[];
      readiness_evidence_digest: string;
    }>
  | Readonly<{
      version: typeof RESTORE_PRETRAFFIC_READINESS_VERSION;
      kind: "consistent_checkpoint_evidence";
      blockers: readonly [];
      readiness_evidence_digest: string;
    }>;

export class RestorePretrafficReadinessInputError extends TypeError {
  readonly code = "invalid_input" as const;
  constructor() {
    super("invalid_input");
    this.name = "RestorePretrafficReadinessInputError";
  }
}

type PlainRecord = Record<string, unknown>;
const fail = (): never => { throw new RestorePretrafficReadinessInputError(); };

const exactRecord = (value: unknown, keys: readonly string[]): PlainRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail();
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail();
  const detached: PlainRecord = {};
  for (const key of keys) {
    const descriptor = descriptors[key]!;
    if (descriptor === undefined || !descriptor.enumerable || !("value" in descriptor)) fail();
    detached[key] = descriptor.value;
  }
  return detached;
};

const plainDiscriminant = (value: unknown, key: string): unknown => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail();
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (descriptor === undefined) return fail();
  if (!descriptor.enumerable || !("value" in descriptor)) fail();
  return descriptor.value;
};

const safeInteger = (value: unknown): value is number => typeof value === "number"
  && Number.isSafeInteger(value) && value >= 0;
const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);
const coordinate = (value: unknown): value is string => typeof value === "string"
  && value.length > 0 && value.length <= MAX_COORDINATE_LENGTH && /^[\x21-\x7e]+$/.test(value);
const scope = (value: unknown): value is RestoreScope => value === "legacy" || value === "postgresql";
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const parseRestore = (value: unknown): RestoreGenerationCoordinate => {
  const row = exactRecord(value, [
    "version", "restore_id", "restore_scope", "restored_generation_digest",
    "restored_snapshot_digest", "restore_completed_at_epoch_seconds", "target_identity_digest",
  ]);
  if (row.version !== RESTORE_GENERATION_COORDINATE_VERSION || !coordinate(row.restore_id)
    || !scope(row.restore_scope) || !digest(row.restored_generation_digest)
    || !digest(row.restored_snapshot_digest)
    || !safeInteger(row.restore_completed_at_epoch_seconds) || !digest(row.target_identity_digest)) fail();
  return Object.freeze({
    version: RESTORE_GENERATION_COORDINATE_VERSION,
    restore_id: row.restore_id,
    restore_scope: row.restore_scope,
    restored_generation_digest: row.restored_generation_digest,
    restored_snapshot_digest: row.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: row.restore_completed_at_epoch_seconds,
    target_identity_digest: row.target_identity_digest,
  }) as RestoreGenerationCoordinate;
};

const parseCheckpoint = (value: unknown): TombstoneReplayCheckpoint => {
  const row = exactRecord(value, [
    "version", "restore_id", "restore_scope", "restored_snapshot_digest",
    "restore_completed_at_epoch_seconds", "source_snapshot_digest", "source_high_watermark",
    "manifest_digest", "terminal_source_receipt_binding_digest", "application_set_digest",
    "traffic_fence_receipt_digest", "checkpoint_digest",
  ]);
  if (row.version !== TOMBSTONE_REPLAY_CHECKPOINT_VERSION || !coordinate(row.restore_id)
    || !scope(row.restore_scope) || !digest(row.restored_snapshot_digest)
    || !safeInteger(row.restore_completed_at_epoch_seconds) || !digest(row.source_snapshot_digest)
    || !safeInteger(row.source_high_watermark) || !digest(row.manifest_digest)
    || !digest(row.terminal_source_receipt_binding_digest) || !digest(row.application_set_digest)
    || !digest(row.traffic_fence_receipt_digest) || !digest(row.checkpoint_digest)) fail();
  const core = {
    version: TOMBSTONE_REPLAY_CHECKPOINT_VERSION,
    restore_id: row.restore_id,
    restore_scope: row.restore_scope,
    restored_snapshot_digest: row.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: row.restore_completed_at_epoch_seconds,
    source_snapshot_digest: row.source_snapshot_digest,
    source_high_watermark: row.source_high_watermark,
    manifest_digest: row.manifest_digest,
    terminal_source_receipt_binding_digest: row.terminal_source_receipt_binding_digest,
    application_set_digest: row.application_set_digest,
    traffic_fence_receipt_digest: row.traffic_fence_receipt_digest,
  };
  if (sha256(core) !== row.checkpoint_digest) fail();
  return Object.freeze({ ...core, checkpoint_digest: row.checkpoint_digest }) as TombstoneReplayCheckpoint;
};

const parseCandidate = (value: unknown): PersistedRestoreCheckpointCandidate | null => {
  if (value === null) return null;
  const row = exactRecord(value, [
    "version", "checkpoint", "restored_generation_digest", "source_feed_generation_digest",
    "partition_topology_digest", "candidate_digest", "record_count",
    "recorded_at_epoch_micros", "persistence_receipt_digest",
  ]);
  if (row.version !== RESTORE_CHECKPOINT_CANDIDATE_VERSION || !safeInteger(row.record_count)
    || !digest(row.restored_generation_digest) || !digest(row.source_feed_generation_digest)
    || !digest(row.partition_topology_digest) || !digest(row.candidate_digest)
    || typeof row.recorded_at_epoch_micros !== "string" || !MICROS.test(row.recorded_at_epoch_micros)
    || !digest(row.persistence_receipt_digest)) fail();
  const checkpoint = parseCheckpoint(row.checkpoint);
  const candidateCore = {
    version: "postgres-restore-replay-checkpoint-candidate-v1",
    restored_generation_digest: row.restored_generation_digest,
    restore_id: checkpoint.restore_id,
    restore_scope: checkpoint.restore_scope,
    restored_snapshot_digest: checkpoint.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: checkpoint.restore_completed_at_epoch_seconds,
    source_snapshot_digest: checkpoint.source_snapshot_digest,
    source_feed_generation_digest: row.source_feed_generation_digest,
    partition_topology_digest: row.partition_topology_digest,
    source_high_watermark: checkpoint.source_high_watermark,
    manifest_digest: checkpoint.manifest_digest,
    record_count: row.record_count,
    terminal_source_receipt_binding_digest: checkpoint.terminal_source_receipt_binding_digest,
    application_set_digest: checkpoint.application_set_digest,
    terminal_feed_fence_receipt_digest: checkpoint.traffic_fence_receipt_digest,
    checkpoint_digest: checkpoint.checkpoint_digest,
  };
  if (sha256(candidateCore) !== row.candidate_digest) fail();
  const receiptCore = {
    version: "postgres-restore-replay-checkpoint-candidate-receipt-v1",
    restored_generation_digest: row.restored_generation_digest,
    restore_id: checkpoint.restore_id,
    candidate_digest: row.candidate_digest,
    recorded_at_epoch_micros: row.recorded_at_epoch_micros,
  };
  if (sha256(receiptCore) !== row.persistence_receipt_digest) fail();
  return Object.freeze({
    version: RESTORE_CHECKPOINT_CANDIDATE_VERSION,
    checkpoint,
    restored_generation_digest: row.restored_generation_digest,
    source_feed_generation_digest: row.source_feed_generation_digest,
    partition_topology_digest: row.partition_topology_digest,
    candidate_digest: row.candidate_digest,
    record_count: row.record_count,
    recorded_at_epoch_micros: row.recorded_at_epoch_micros,
    persistence_receipt_digest: row.persistence_receipt_digest,
  }) as PersistedRestoreCheckpointCandidate;
};

const parseAttestation = (value: unknown): RestoreGenerationAttestation => {
  const state = plainDiscriminant(value, "state");
  const row = exactRecord(value, state === "current" ? [
    "version", "state", "restore_id", "restore_scope", "restored_generation_digest",
    "restored_snapshot_digest", "target_identity_digest", "attestation_receipt_digest",
  ] : ["version", "state"]);
  if (row.version !== RESTORE_GENERATION_ATTESTATION_VERSION) fail();
  if (row.state === "unavailable") return Object.freeze({
    version: RESTORE_GENERATION_ATTESTATION_VERSION, state: "unavailable",
  });
  if (row.state !== "current" || !coordinate(row.restore_id) || !scope(row.restore_scope)
    || !digest(row.restored_generation_digest) || !digest(row.restored_snapshot_digest)
    || !digest(row.target_identity_digest) || !digest(row.attestation_receipt_digest)) fail();
  return Object.freeze({
    version: RESTORE_GENERATION_ATTESTATION_VERSION,
    state: "current", restore_id: row.restore_id, restore_scope: row.restore_scope,
    restored_generation_digest: row.restored_generation_digest,
    restored_snapshot_digest: row.restored_snapshot_digest,
    target_identity_digest: row.target_identity_digest,
    attestation_receipt_digest: row.attestation_receipt_digest,
  }) as RestoreGenerationAttestation;
};

const parseCoverage = (value: unknown): TerminalFeedAppliedCoverage | null => {
  if (value === null) return null;
  const row = exactRecord(value, [
    "version", "state", "restore_id", "restore_scope", "restored_generation_digest",
    "restored_snapshot_digest", "source_snapshot_digest", "source_feed_generation_digest",
    "partition_topology_digest", "source_current_high_watermark",
    "gap_free_through_high_watermark", "applied_through_high_watermark",
    "checkpoint_digest", "coverage_receipt_digest",
  ]);
  if (row.version !== TERMINAL_FEED_APPLIED_COVERAGE_VERSION
    || (row.state !== "complete" && row.state !== "incomplete") || !coordinate(row.restore_id)
    || !scope(row.restore_scope) || !digest(row.restored_generation_digest)
    || !digest(row.restored_snapshot_digest) || !digest(row.source_snapshot_digest)
    || !digest(row.source_feed_generation_digest) || !digest(row.partition_topology_digest)
    || !safeInteger(row.source_current_high_watermark)
    || !safeInteger(row.gap_free_through_high_watermark)
    || !safeInteger(row.applied_through_high_watermark) || !digest(row.checkpoint_digest)
    || !digest(row.coverage_receipt_digest)) fail();
  return Object.freeze({
    version: TERMINAL_FEED_APPLIED_COVERAGE_VERSION,
    state: row.state,
    restore_id: row.restore_id,
    restore_scope: row.restore_scope,
    restored_generation_digest: row.restored_generation_digest,
    restored_snapshot_digest: row.restored_snapshot_digest,
    source_snapshot_digest: row.source_snapshot_digest,
    source_feed_generation_digest: row.source_feed_generation_digest,
    partition_topology_digest: row.partition_topology_digest,
    source_current_high_watermark: row.source_current_high_watermark,
    gap_free_through_high_watermark: row.gap_free_through_high_watermark,
    applied_through_high_watermark: row.applied_through_high_watermark,
    checkpoint_digest: row.checkpoint_digest,
    coverage_receipt_digest: row.coverage_receipt_digest,
  }) as TerminalFeedAppliedCoverage;
};

const parseControl = (value: unknown): AccountControlProjection | null => {
  if (value === null) return null;
  const row = exactRecord(value, [
    "account_id", "control_revision", "account_generation", "account_epoch",
    "lifecycle_state", "deletion_epoch", "activation", "conflict",
  ]);
  if (!isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || !(["legacy", "migrating", "new", "rolled_back_stranded"] as const)
      .includes(row.account_generation as never)
    || !(row.account_epoch === null || safeInteger(row.account_epoch))
    || !(["active", "deletion_pending", "deleted"] as const)
      .includes(row.lifecycle_state as never)
    || !(row.deletion_epoch === null || safeInteger(row.deletion_epoch))
    || ((row.lifecycle_state === "active") !== (row.deletion_epoch === null))) fail();
  let activation: AccountControlProjection["activation"] = null;
  if (row.activation !== null) {
    const nested = exactRecord(row.activation, ["activated_epoch", "at_control_revision"]);
    if (!safeInteger(nested.activated_epoch) || !safeInteger(nested.at_control_revision)) fail();
    activation = Object.freeze({
      activated_epoch: nested.activated_epoch,
      at_control_revision: nested.at_control_revision,
    }) as AccountControlProjection["activation"];
  }
  let conflict: AccountControlProjection["conflict"] = null;
  if (row.conflict !== null) {
    const nested = exactRecord(row.conflict, ["at_control_revision", "detail"]);
    if (!safeInteger(nested.at_control_revision) || typeof nested.detail !== "string"
      || !(["malformed_observation", "account_id_mismatch", "stale_observation",
        "conflicting_observation", "unordered_generation_transition", "unordered_epoch",
        "withdrawn_epoch", "unordered_lifecycle", "mutated_deletion_epoch",
        "projection_conflicted"] as const).includes(nested.detail as never)) fail();
    conflict = Object.freeze({
      at_control_revision: nested.at_control_revision,
      detail: nested.detail,
    }) as AccountControlProjection["conflict"];
  }
  return Object.freeze({
    account_id: row.account_id,
    control_revision: row.control_revision,
    account_generation: row.account_generation,
    account_epoch: row.account_epoch,
    lifecycle_state: row.lifecycle_state,
    deletion_epoch: row.deletion_epoch,
    activation,
    conflict,
  }) as AccountControlProjection;
};

const parseFenceObservation = (
  value: unknown,
  accountId: string | null,
): RetainedTerminalFenceObservation => {
  const state = plainDiscriminant(value, "state");
  const stateRow = exactRecord(value, state === "current"
    ? ["version", "state", "latest_fence", "observation_receipt_digest"]
    : ["version", "state"]);
  if (stateRow.version !== RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION) fail();
  if (stateRow.state === "unavailable") return Object.freeze({
    version: RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION,
    state: "unavailable",
  });
  if (stateRow.state !== "current" || !digest(stateRow.observation_receipt_digest)) fail();
  let latestFence: RetainedTerminalFence | null = null;
  if (stateRow.latest_fence !== null) {
    const row = exactRecord(stateRow.latest_fence, [
      "version", "account_id", "deletion_epoch", "control_revision",
      "terminal_record_digest", "source_restore_id", "restored_snapshot_digest",
      "fence_receipt_digest",
    ]);
    if (row.version !== RETAINED_TERMINAL_FENCE_VERSION || !isWellFormedAccountId(row.account_id)
      || accountId === null || row.account_id !== accountId || !safeInteger(row.deletion_epoch)
      || !safeInteger(row.control_revision) || !digest(row.terminal_record_digest)
      || !coordinate(row.source_restore_id) || !digest(row.restored_snapshot_digest)
      || !digest(row.fence_receipt_digest)) fail();
    latestFence = Object.freeze({
      version: RETAINED_TERMINAL_FENCE_VERSION,
      account_id: row.account_id,
      deletion_epoch: row.deletion_epoch,
      control_revision: row.control_revision,
      terminal_record_digest: row.terminal_record_digest,
      source_restore_id: row.source_restore_id,
      restored_snapshot_digest: row.restored_snapshot_digest,
      fence_receipt_digest: row.fence_receipt_digest,
    }) as RetainedTerminalFence;
  }
  return Object.freeze({
    version: RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION,
    state: "current",
    latest_fence: latestFence,
    observation_receipt_digest: stateRow.observation_receipt_digest,
  }) as RetainedTerminalFenceObservation;
};

/**
 * Evaluates one detached lifecycle snapshot. Consistency is evidence
 * only: it authenticates nobody, grants nothing, and cannot open traffic.
 */
export const evaluateRestorePretrafficReadiness = (
  value: unknown,
): RestorePretrafficReadiness => {
  const input = exactRecord(value, [
    "restore_generation", "generation_attestation", "checkpoint_candidate", "terminal_feed_coverage",
    "control_projection", "retained_fence_observation",
  ]);
  const restore = parseRestore(input.restore_generation);
  const attestation = parseAttestation(input.generation_attestation);
  const candidate = parseCandidate(input.checkpoint_candidate);
  const coverage = parseCoverage(input.terminal_feed_coverage);
  const control = parseControl(input.control_projection);
  const fenceObservation = parseFenceObservation(
    input.retained_fence_observation,
    control?.account_id ?? null,
  );

  const blockers: RestorePretrafficBlocker[] = [];
  const checkpoint = candidate?.checkpoint ?? null;
  if (candidate === null) blockers.push("checkpoint_missing");
  else if (checkpoint!.restore_id !== restore.restore_id
    || checkpoint!.restore_scope !== restore.restore_scope
    || checkpoint!.restored_snapshot_digest !== restore.restored_snapshot_digest
    || checkpoint!.restore_completed_at_epoch_seconds !== restore.restore_completed_at_epoch_seconds
    || candidate.restored_generation_digest !== restore.restored_generation_digest) {
    blockers.push("checkpoint_coordinate_mismatch");
  }
  if (attestation.state === "unavailable") blockers.push("generation_attestation_unavailable");
  else if (attestation.restore_id !== restore.restore_id
    || attestation.restore_scope !== restore.restore_scope
    || attestation.restored_generation_digest !== restore.restored_generation_digest
    || attestation.restored_snapshot_digest !== restore.restored_snapshot_digest
    || attestation.target_identity_digest !== restore.target_identity_digest) {
    blockers.push("generation_attestation_mismatch");
  }
  if (coverage === null) blockers.push("terminal_feed_coverage_missing");
  else if (coverage.state !== "complete"
    || coverage.gap_free_through_high_watermark !== coverage.source_current_high_watermark
    || coverage.applied_through_high_watermark !== coverage.source_current_high_watermark) {
    blockers.push("terminal_feed_coverage_incomplete");
  } else if (checkpoint === null || candidate === null || coverage.restore_id !== restore.restore_id
    || coverage.restore_scope !== restore.restore_scope
    || coverage.restored_generation_digest !== restore.restored_generation_digest
    || coverage.restored_snapshot_digest !== restore.restored_snapshot_digest
    || coverage.source_snapshot_digest !== checkpoint.source_snapshot_digest
    || coverage.source_feed_generation_digest !== candidate.source_feed_generation_digest
    || coverage.partition_topology_digest !== candidate.partition_topology_digest
    || coverage.source_current_high_watermark !== checkpoint.source_high_watermark
    || coverage.checkpoint_digest !== checkpoint.checkpoint_digest) {
    blockers.push("terminal_feed_coverage_mismatch");
  }
  const controlDecision = evaluateAccountControlAdmission(control);
  if (!controlDecision.admitted) blockers.push(controlDecision.reason);
  if (fenceObservation.state === "unavailable") blockers.push("retained_fence_unavailable");
  else if (fenceObservation.latest_fence !== null) blockers.push("retained_terminal_fence_present");

  const evidence = {
    version: RESTORE_PRETRAFFIC_READINESS_VERSION,
    restore,
    checkpoint: candidate,
    generation_attestation: attestation,
    coverage,
    control_binding_digest: sha256(control),
    fence_observation_binding_digest: sha256(fenceObservation),
    blockers,
  };
  const readinessEvidenceDigest = sha256(evidence);
  if (blockers.length > 0) return Object.freeze({
    version: RESTORE_PRETRAFFIC_READINESS_VERSION,
    kind: "blocked" as const,
    blockers: Object.freeze(blockers),
    readiness_evidence_digest: readinessEvidenceDigest,
  });
  return Object.freeze({
    version: RESTORE_PRETRAFFIC_READINESS_VERSION,
    kind: "consistent_checkpoint_evidence" as const,
    blockers: Object.freeze([]) as readonly [],
    readiness_evidence_digest: readinessEvidenceDigest,
  });
};
