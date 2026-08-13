import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  RESTORE_CHECKPOINT_CANDIDATE_VERSION,
  type PersistedRestoreCheckpointCandidate,
} from "../../core/control/restore-pretraffic-readiness";
import type { PostgresTransactionPool } from "./connection";

export const POSTGRES_RESTORE_CHECKPOINT_CANDIDATE_VERSION =
  "postgres-restore-replay-checkpoint-candidate-v1" as const;

export interface PostgresRestoreReplayCheckpointCandidate {
  readonly version: typeof POSTGRES_RESTORE_CHECKPOINT_CANDIDATE_VERSION;
  readonly restored_generation_digest: string;
  readonly restore_id: string;
  readonly restore_scope: "postgresql";
  readonly restored_snapshot_digest: string;
  readonly restore_completed_at_epoch_seconds: number;
  readonly source_snapshot_digest: string;
  readonly source_feed_generation_digest: string;
  readonly partition_topology_digest: string;
  readonly source_high_watermark: number;
  readonly manifest_digest: string;
  readonly record_count: number;
  readonly terminal_source_receipt_binding_digest: string;
  readonly application_set_digest: string;
  readonly terminal_feed_fence_receipt_digest: string;
  readonly checkpoint_digest: string;
}

export interface PostgresRestoreReplayCheckpointCandidateReceipt {
  readonly version: "postgres-restore-replay-checkpoint-candidate-receipt-v1";
  readonly result: "recorded" | "replayed";
  readonly restored_generation_digest: string;
  readonly restore_id: string;
  readonly candidate_digest: string;
  readonly recorded_at_epoch_micros: string;
  readonly persistence_receipt_digest: string;
}

export type PostgresRestoreReplayCheckpointLoadOutcome =
  | Readonly<{ kind: "missing" }>
  | Readonly<{ kind: "loaded"; candidate: PersistedRestoreCheckpointCandidate }>;

export interface PostgresRestoreReplayCheckpointRepository {
  record(
    candidate: PostgresRestoreReplayCheckpointCandidate,
  ): Promise<PostgresRestoreReplayCheckpointCandidateReceipt>;
  load(
    restoredGenerationDigest: string,
    restoreId: string,
  ): Promise<PostgresRestoreReplayCheckpointLoadOutcome>;
}

export class PostgresRestoreReplayCheckpointRepositoryError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "candidate_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresRestoreReplayCheckpointRepositoryError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const COORDINATE = /^[\x21-\x7e]+$/;
const MICROS = /^(?:0|[1-9][0-9]*)$/;
const MAX_COORDINATE_LENGTH = 256;
const MAX_RECORDS = 10_000;

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new PostgresRestoreReplayCheckpointRepositoryError("invalid_input");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string") || ownKeys.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    throw new PostgresRestoreReplayCheckpointRepositoryError("invalid_input");
  }
  const detached: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || !descriptor.enumerable) {
      throw new PostgresRestoreReplayCheckpointRepositoryError("invalid_input");
    }
    detached[key] = descriptor.value;
  }
  return detached;
};

const coordinate = (value: unknown): value is string => typeof value === "string"
  && value.length > 0 && value.length <= MAX_COORDINATE_LENGTH && COORDINATE.test(value);
const safeInteger = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;
const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);

const normalize = (value: unknown): PostgresRestoreReplayCheckpointCandidate => {
  const row = exactRecord(value, [
    "version", "restored_generation_digest", "restore_id", "restore_scope",
    "restored_snapshot_digest", "restore_completed_at_epoch_seconds",
    "source_snapshot_digest", "source_feed_generation_digest", "partition_topology_digest",
    "source_high_watermark", "manifest_digest", "record_count",
    "terminal_source_receipt_binding_digest", "application_set_digest",
    "terminal_feed_fence_receipt_digest", "checkpoint_digest",
  ]);
  if (row.version !== POSTGRES_RESTORE_CHECKPOINT_CANDIDATE_VERSION
    || !digest(row.restored_generation_digest) || !coordinate(row.restore_id)
    || row.restore_scope !== "postgresql" || !digest(row.restored_snapshot_digest)
    || !safeInteger(row.restore_completed_at_epoch_seconds)
    || !digest(row.source_snapshot_digest) || !digest(row.source_feed_generation_digest)
    || !digest(row.partition_topology_digest) || !safeInteger(row.source_high_watermark)
    || !digest(row.manifest_digest) || !safeInteger(row.record_count, MAX_RECORDS)
    || !digest(row.terminal_source_receipt_binding_digest)
    || !digest(row.application_set_digest) || !digest(row.terminal_feed_fence_receipt_digest)
    || !digest(row.checkpoint_digest)) {
    throw new PostgresRestoreReplayCheckpointRepositoryError("invalid_input");
  }
  return Object.freeze({
    version: POSTGRES_RESTORE_CHECKPOINT_CANDIDATE_VERSION,
    restored_generation_digest: row.restored_generation_digest,
    restore_id: row.restore_id,
    restore_scope: "postgresql",
    restored_snapshot_digest: row.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: row.restore_completed_at_epoch_seconds,
    source_snapshot_digest: row.source_snapshot_digest,
    source_feed_generation_digest: row.source_feed_generation_digest,
    partition_topology_digest: row.partition_topology_digest,
    source_high_watermark: row.source_high_watermark,
    manifest_digest: row.manifest_digest,
    record_count: row.record_count,
    terminal_source_receipt_binding_digest: row.terminal_source_receipt_binding_digest,
    application_set_digest: row.application_set_digest,
    terminal_feed_fence_receipt_digest: row.terminal_feed_fence_receipt_digest,
    checkpoint_digest: row.checkpoint_digest,
  });
};

const coreCheckpointDigest = (candidate: PostgresRestoreReplayCheckpointCandidate): string =>
  sha256({
    version: "tombstone-replay-checkpoint-v1",
    restore_id: candidate.restore_id,
    restore_scope: candidate.restore_scope,
    restored_snapshot_digest: candidate.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: candidate.restore_completed_at_epoch_seconds,
    source_snapshot_digest: candidate.source_snapshot_digest,
    source_high_watermark: candidate.source_high_watermark,
    manifest_digest: candidate.manifest_digest,
    terminal_source_receipt_binding_digest: candidate.terminal_source_receipt_binding_digest,
    application_set_digest: candidate.application_set_digest,
    traffic_fence_receipt_digest: candidate.terminal_feed_fence_receipt_digest,
  });

const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object" || isProxy(error)) return null;
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor && "value" in descriptor && typeof descriptor.value === "string"
    ? descriptor.value : null;
};

const mapFailure = (error: unknown): PostgresRestoreReplayCheckpointRepositoryError => {
  if (error instanceof PostgresRestoreReplayCheckpointRepositoryError) return error;
  if (providerCode(error) === "23505") {
    return new PostgresRestoreReplayCheckpointRepositoryError("candidate_conflict");
  }
  if (providerCode(error) === "40001") {
    return new PostgresRestoreReplayCheckpointRepositoryError("retryable_serialization");
  }
  return new PostgresRestoreReplayCheckpointRepositoryError("persistence_failed");
};

interface CandidateRow extends Record<string, unknown> {
  result: unknown;
  recorded_at_epoch_micros: unknown;
}

const persistenceReceiptDigest = (
  restoredGenerationDigest: string,
  restoreId: string,
  candidateDigest: string,
  recordedAtEpochMicros: string,
): string => sha256({
  version: "postgres-restore-replay-checkpoint-candidate-receipt-v1",
  restored_generation_digest: restoredGenerationDigest,
  restore_id: restoreId,
  candidate_digest: candidateDigest,
  recorded_at_epoch_micros: recordedAtEpochMicros,
});

const READ_ROW_KEYS = Object.freeze([
  "restore_id", "restored_generation_digest", "restore_scope",
  "restored_snapshot_digest", "restore_completed_at_epoch_seconds",
  "source_snapshot_digest", "source_feed_generation_digest", "partition_topology_digest",
  "source_high_watermark", "manifest_digest", "record_count",
  "terminal_source_receipt_binding_digest", "application_set_digest",
  "terminal_feed_fence_receipt_digest", "checkpoint_digest", "candidate_digest",
  "recorded_at_epoch_micros",
] as const);

const databaseInteger = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): number | null => {
  if (typeof value === "bigint") value = value.toString();
  if (typeof value === "string") {
    if (!/^(?:0|[1-9][0-9]*)$/.test(value)) return null;
    value = Number(value);
  }
  return safeInteger(value, maximum) ? value : null;
};

const loadedCandidate = (value: unknown): PersistedRestoreCheckpointCandidate => {
  const row = exactRecord(value, READ_ROW_KEYS);
  const restoreCompletedAt = databaseInteger(row.restore_completed_at_epoch_seconds);
  const sourceHighWatermark = databaseInteger(row.source_high_watermark);
  const recordCount = databaseInteger(row.record_count, MAX_RECORDS);
  if (!digest(row.restored_generation_digest) || !coordinate(row.restore_id)
    || row.restore_scope !== "postgresql" || !digest(row.restored_snapshot_digest)
    || restoreCompletedAt === null || !digest(row.source_snapshot_digest)
    || !digest(row.source_feed_generation_digest) || !digest(row.partition_topology_digest)
    || sourceHighWatermark === null || !digest(row.manifest_digest) || recordCount === null
    || !digest(row.terminal_source_receipt_binding_digest)
    || !digest(row.application_set_digest) || !digest(row.terminal_feed_fence_receipt_digest)
    || !digest(row.checkpoint_digest) || !digest(row.candidate_digest)
    || typeof row.recorded_at_epoch_micros !== "string"
    || !MICROS.test(row.recorded_at_epoch_micros)) {
    throw new PostgresRestoreReplayCheckpointRepositoryError("persistence_failed");
  }
  const flat: PostgresRestoreReplayCheckpointCandidate = Object.freeze({
    version: POSTGRES_RESTORE_CHECKPOINT_CANDIDATE_VERSION,
    restored_generation_digest: row.restored_generation_digest,
    restore_id: row.restore_id,
    restore_scope: "postgresql",
    restored_snapshot_digest: row.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: restoreCompletedAt,
    source_snapshot_digest: row.source_snapshot_digest,
    source_feed_generation_digest: row.source_feed_generation_digest,
    partition_topology_digest: row.partition_topology_digest,
    source_high_watermark: sourceHighWatermark,
    manifest_digest: row.manifest_digest,
    record_count: recordCount,
    terminal_source_receipt_binding_digest: row.terminal_source_receipt_binding_digest,
    application_set_digest: row.application_set_digest,
    terminal_feed_fence_receipt_digest: row.terminal_feed_fence_receipt_digest,
    checkpoint_digest: row.checkpoint_digest,
  });
  if (coreCheckpointDigest(flat) !== flat.checkpoint_digest || sha256(flat) !== row.candidate_digest) {
    throw new PostgresRestoreReplayCheckpointRepositoryError("persistence_failed");
  }
  const recordedAt = row.recorded_at_epoch_micros;
  return Object.freeze({
    version: RESTORE_CHECKPOINT_CANDIDATE_VERSION,
    checkpoint: Object.freeze({
      version: "tombstone-replay-checkpoint-v1" as const,
      restore_id: flat.restore_id,
      restore_scope: flat.restore_scope,
      restored_snapshot_digest: flat.restored_snapshot_digest,
      restore_completed_at_epoch_seconds: flat.restore_completed_at_epoch_seconds,
      source_snapshot_digest: flat.source_snapshot_digest,
      source_high_watermark: flat.source_high_watermark,
      manifest_digest: flat.manifest_digest,
      terminal_source_receipt_binding_digest: flat.terminal_source_receipt_binding_digest,
      application_set_digest: flat.application_set_digest,
      traffic_fence_receipt_digest: flat.terminal_feed_fence_receipt_digest,
      checkpoint_digest: flat.checkpoint_digest,
    }),
    restored_generation_digest: flat.restored_generation_digest,
    source_feed_generation_digest: flat.source_feed_generation_digest,
    partition_topology_digest: flat.partition_topology_digest,
    candidate_digest: row.candidate_digest,
    record_count: flat.record_count,
    recorded_at_epoch_micros: recordedAt,
    persistence_receipt_digest: persistenceReceiptDigest(
      flat.restored_generation_digest, flat.restore_id, row.candidate_digest, recordedAt,
    ),
  });
};

export const createPostgresRestoreReplayCheckpointRepository = (
  pool: PostgresTransactionPool,
): PostgresRestoreReplayCheckpointRepository => Object.freeze({
  async record(candidateValue: PostgresRestoreReplayCheckpointCandidate): Promise<PostgresRestoreReplayCheckpointCandidateReceipt> {
    const candidate = normalize(candidateValue);
    if (coreCheckpointDigest(candidate) !== candidate.checkpoint_digest) {
      throw new PostgresRestoreReplayCheckpointRepositoryError("invalid_input");
    }
    const candidateDigest = sha256(candidate);
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await connection.query({
            name: "restore_checkpoint.set_role",
            text: "SET LOCAL ROLE omi_platform_restore",
            values: [],
          });
          const rows = await connection.query<CandidateRow>({
            name: "restore_checkpoint.record_candidate",
            text: "SELECT * FROM omi_memory.record_postgres_restore_replay_checkpoint_candidate($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
            values: [
              candidate.restored_generation_digest, candidate.restore_id,
              candidate.restored_snapshot_digest, candidate.restore_completed_at_epoch_seconds,
              candidate.source_snapshot_digest, candidate.source_feed_generation_digest,
              candidate.partition_topology_digest, candidate.source_high_watermark,
              candidate.manifest_digest, candidate.record_count,
              candidate.terminal_source_receipt_binding_digest,
              candidate.application_set_digest, candidate.terminal_feed_fence_receipt_digest,
              candidate.checkpoint_digest, candidateDigest,
            ],
          });
          const row = rows[0];
          if (rows.length !== 1 || row === undefined
            || (row.result !== "recorded" && row.result !== "replayed")
            || typeof row.recorded_at_epoch_micros !== "string"
            || !MICROS.test(row.recorded_at_epoch_micros)) {
            throw new PostgresRestoreReplayCheckpointRepositoryError("persistence_failed");
          }
          return Object.freeze({
            version: "postgres-restore-replay-checkpoint-candidate-receipt-v1" as const,
            result: row.result,
            restored_generation_digest: candidate.restored_generation_digest,
            restore_id: candidate.restore_id,
            candidate_digest: candidateDigest,
            recorded_at_epoch_micros: row.recorded_at_epoch_micros,
            persistence_receipt_digest: persistenceReceiptDigest(
              candidate.restored_generation_digest, candidate.restore_id,
              candidateDigest, row.recorded_at_epoch_micros,
            ),
          });
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },
  async load(restoredGenerationDigest: string, restoreId: string) {
    if (!digest(restoredGenerationDigest) || !coordinate(restoreId)) {
      throw new PostgresRestoreReplayCheckpointRepositoryError("invalid_input");
    }
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read only" },
        async (connection) => {
          await connection.query({
            name: "restore_checkpoint.set_role",
            text: "SET LOCAL ROLE omi_platform_restore",
            values: [],
          });
          const rows = await connection.query<Record<string, unknown>>({
            name: "restore_checkpoint.load_candidate",
            text: "SELECT * FROM omi_memory.read_postgres_restore_replay_checkpoint_candidate($1, $2)",
            values: [restoredGenerationDigest, restoreId],
          });
          if (rows.length === 0) return Object.freeze({ kind: "missing" as const });
          if (rows.length !== 1) {
            throw new PostgresRestoreReplayCheckpointRepositoryError("persistence_failed");
          }
          return Object.freeze({ kind: "loaded" as const, candidate: loadedCandidate(rows[0]) });
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },
});
