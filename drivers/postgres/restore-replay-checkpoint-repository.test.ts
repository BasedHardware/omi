import { expect, test } from "bun:test";
import { createHash } from "node:crypto";

import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  POSTGRES_RESTORE_CHECKPOINT_CANDIDATE_VERSION,
  PostgresRestoreReplayCheckpointRepositoryError,
  createPostgresRestoreReplayCheckpointRepository,
  type PostgresRestoreReplayCheckpointCandidate,
} from "./restore-replay-checkpoint-repository";

const hash = (character: string): string => character.repeat(64);
const jsonDigest = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const candidate = (): PostgresRestoreReplayCheckpointCandidate => {
  const base = {
  version: POSTGRES_RESTORE_CHECKPOINT_CANDIDATE_VERSION,
  restored_generation_digest: hash("0"),
  restore_id: "restore-pg-2",
  restore_scope: "postgresql",
  restored_snapshot_digest: hash("1"),
  restore_completed_at_epoch_seconds: 100,
  source_snapshot_digest: hash("2"),
  source_feed_generation_digest: hash("8"),
  partition_topology_digest: hash("9"),
  source_high_watermark: 42,
  manifest_digest: hash("3"),
  record_count: 7,
  terminal_source_receipt_binding_digest: hash("4"),
  application_set_digest: hash("5"),
  terminal_feed_fence_receipt_digest: hash("6"),
  } as const;
  return {
    ...base,
    checkpoint_digest: jsonDigest({
      version: "tombstone-replay-checkpoint-v1",
      restore_id: base.restore_id,
      restore_scope: base.restore_scope,
      restored_snapshot_digest: base.restored_snapshot_digest,
      restore_completed_at_epoch_seconds: base.restore_completed_at_epoch_seconds,
      source_snapshot_digest: base.source_snapshot_digest,
      source_high_watermark: base.source_high_watermark,
      manifest_digest: base.manifest_digest,
      terminal_source_receipt_binding_digest: base.terminal_source_receipt_binding_digest,
      application_set_digest: base.application_set_digest,
      traffic_fence_receipt_digest: base.terminal_feed_fence_receipt_digest,
    }),
  };
};

const persistedRow = (input = candidate()): Record<string, unknown> => ({
  restore_id: input.restore_id,
  restored_generation_digest: input.restored_generation_digest,
  restore_scope: input.restore_scope,
  restored_snapshot_digest: input.restored_snapshot_digest,
  restore_completed_at_epoch_seconds: String(input.restore_completed_at_epoch_seconds),
  source_snapshot_digest: input.source_snapshot_digest,
  source_feed_generation_digest: input.source_feed_generation_digest,
  partition_topology_digest: input.partition_topology_digest,
  source_high_watermark: String(input.source_high_watermark),
  manifest_digest: input.manifest_digest,
  record_count: String(input.record_count),
  terminal_source_receipt_binding_digest: input.terminal_source_receipt_binding_digest,
  application_set_digest: input.application_set_digest,
  terminal_feed_fence_receipt_digest: input.terminal_feed_fence_receipt_digest,
  checkpoint_digest: input.checkpoint_digest,
  candidate_digest: jsonDigest(input),
  recorded_at_epoch_micros: "1800000000123456",
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "restore-checkpoint" });
  readonly statements: SqlStatement[] = [];
  result: "recorded" | "replayed" = "recorded";
  failureCode: string | null = null;
  loadRows: readonly Record<string, unknown>[] = [];

  async query<Row extends Record<string, unknown>>(
    statement: SqlStatement,
  ): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "restore_checkpoint.set_role") return [];
    if (statement.name === "restore_checkpoint.record_candidate") {
      if (this.failureCode !== null) {
        const error = Object.create(null) as { code: string };
        Object.defineProperty(error, "code", { value: this.failureCode });
        throw error;
      }
      return [{
        result: this.result,
        recorded_at_epoch_micros: "1800000000123456",
      } as unknown as Row];
    }
    if (statement.name === "restore_checkpoint.load_candidate") {
      return this.loadRows as readonly Row[];
    }
    throw new Error("unexpected statement");
  }

  async execute(): Promise<{ rowCount: number }> {
    throw new Error("checkpoint repository must use named functions");
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];
  transactions = 0;
  constructor(readonly connection: FakeConnection) {}
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.transactions += 1;
    this.options.push(options);
    return callback(this.connection);
  }
}

test("records the exact content-free checkpoint candidate through the restore role", async () => {
  const connection = new FakeConnection();
  const pool = new FakePool(connection);
  const repository = createPostgresRestoreReplayCheckpointRepository(pool);
  const input = candidate();
  const receipt = await repository.record(input);

  expect(receipt).toMatchObject({
    version: "postgres-restore-replay-checkpoint-candidate-receipt-v1",
    result: "recorded",
    restored_generation_digest: input.restored_generation_digest,
    restore_id: input.restore_id,
  });
  expect(receipt.candidate_digest).toMatch(/^[0-9a-f]{64}$/);
  expect(receipt.persistence_receipt_digest).toMatch(/^[0-9a-f]{64}$/);
  expect(Object.isFrozen(receipt)).toBe(true);
  expect(pool.options).toEqual([{ isolationLevel: "serializable", accessMode: "read write" }]);
  expect(connection.statements.map((statement) => statement.name)).toEqual([
    "restore_checkpoint.set_role", "restore_checkpoint.record_candidate",
  ]);
  expect(connection.statements[0]!.text).toBe("SET LOCAL ROLE omi_platform_restore");
  expect(connection.statements[1]!.values.slice(0, 14)).toEqual([
    input.restored_generation_digest, input.restore_id, input.restored_snapshot_digest,
    input.restore_completed_at_epoch_seconds, input.source_snapshot_digest,
    input.source_feed_generation_digest, input.partition_topology_digest,
    input.source_high_watermark, input.manifest_digest, input.record_count,
    input.terminal_source_receipt_binding_digest, input.application_set_digest,
    input.terminal_feed_fence_receipt_digest, input.checkpoint_digest,
  ]);
});

test("returns a replay classification for the same exact candidate", async () => {
  const connection = new FakeConnection();
  const repository = createPostgresRestoreReplayCheckpointRepository(new FakePool(connection));
  const first = await repository.record(candidate());
  connection.result = "replayed";
  const replay = await repository.record(candidate());
  expect(first.result).toBe("recorded");
  expect(replay.result).toBe("replayed");
  expect(replay.candidate_digest).toBe(first.candidate_digest);
  expect(replay.recorded_at_epoch_micros).toBe(first.recorded_at_epoch_micros);
  expect(replay.persistence_receipt_digest).toBe(first.persistence_receipt_digest);
});

test("detaches input before opening the PostgreSQL transaction", async () => {
  const connection = new FakeConnection();
  const input = { ...candidate() };
  const completion = createPostgresRestoreReplayCheckpointRepository(
    new FakePool(connection),
  ).record(input);
  input.restore_id = "restore-substituted";
  input.checkpoint_digest = hash("a");
  const receipt = await completion;
  expect(receipt.restore_id).toBe("restore-pg-2");
  expect(connection.statements[1]!.values[1]).toBe("restore-pg-2");
  expect(connection.statements[1]!.values[13]).not.toBe(hash("a"));
});

test("rejects hostile or malformed candidates before PostgreSQL", async () => {
  const pool = new FakePool(new FakeConnection());
  const repository = createPostgresRestoreReplayCheckpointRepository(pool);
  let getterCalled = false;
  const hostile = { ...candidate() } as Record<string, unknown>;
  Object.defineProperty(hostile, "restore_id", {
    enumerable: true,
    get() { getterCalled = true; return "restore-pg-2"; },
  });
  await expect(repository.record(hostile as never)).rejects
    .toEqual(new PostgresRestoreReplayCheckpointRepositoryError("invalid_input"));
  await expect(repository.record({ ...candidate(), record_count: 10_001 })).rejects
    .toEqual(new PostgresRestoreReplayCheckpointRepositoryError("invalid_input"));
  await expect(repository.record({ ...candidate(), restore_scope: "legacy" as never })).rejects
    .toEqual(new PostgresRestoreReplayCheckpointRepositoryError("invalid_input"));
  await expect(repository.record({ ...candidate(), checkpoint_digest: hash("f") })).rejects
    .toEqual(new PostgresRestoreReplayCheckpointRepositoryError("invalid_input"));
  expect(getterCalled).toBe(false);
  expect(pool.transactions).toBe(0);
});

test("candidate digest binds fresh feed generation and partition topology", async () => {
  const firstConnection = new FakeConnection();
  const first = await createPostgresRestoreReplayCheckpointRepository(
    new FakePool(firstConnection),
  ).record(candidate());
  const changed = candidate();
  const changedFeed = { ...changed, source_feed_generation_digest: hash("a") };
  const second = await createPostgresRestoreReplayCheckpointRepository(
    new FakePool(new FakeConnection()),
  ).record(changedFeed);
  const changedTopology = { ...changed, partition_topology_digest: hash("b") };
  const third = await createPostgresRestoreReplayCheckpointRepository(
    new FakePool(new FakeConnection()),
  ).record(changedTopology);
  expect(second.candidate_digest).not.toBe(first.candidate_digest);
  expect(third.candidate_digest).not.toBe(first.candidate_digest);
});

test("loads one verified persisted candidate with the stable persistence receipt", async () => {
  const connection = new FakeConnection();
  connection.loadRows = [persistedRow()];
  const pool = new FakePool(connection);
  const repository = createPostgresRestoreReplayCheckpointRepository(pool);
  const recorded = await repository.record(candidate());
  const loaded = await repository.load(hash("0"), "restore-pg-2");
  expect(loaded.kind).toBe("loaded");
  if (loaded.kind !== "loaded") throw new Error("expected loaded candidate");
  expect(loaded.candidate).toMatchObject({
    version: "restore-checkpoint-candidate-v1",
    restored_generation_digest: hash("0"),
    source_feed_generation_digest: hash("8"),
    partition_topology_digest: hash("9"),
    record_count: 7,
    recorded_at_epoch_micros: "1800000000123456",
  });
  expect(loaded.candidate.checkpoint.checkpoint_digest).toBe(candidate().checkpoint_digest);
  expect(loaded.candidate.candidate_digest).toBe(recorded.candidate_digest);
  expect(loaded.candidate.persistence_receipt_digest).toBe(recorded.persistence_receipt_digest);
  expect(Object.isFrozen(loaded.candidate)).toBe(true);
  expect(Object.isFrozen(loaded.candidate.checkpoint)).toBe(true);
  expect(pool.options.at(-1)).toEqual({ isolationLevel: "serializable", accessMode: "read only" });
});

test("returns distinct missing and rejects corrupted persisted candidates", async () => {
  const connection = new FakeConnection();
  const pool = new FakePool(connection);
  const repository = createPostgresRestoreReplayCheckpointRepository(pool);
  await expect(repository.load(hash("0"), "restore-missing"))
    .resolves.toEqual({ kind: "missing" });

  connection.loadRows = [{ ...persistedRow(), candidate_digest: hash("f") }];
  await expect(repository.load(hash("0"), "restore-pg-2")).rejects
    .toEqual(new PostgresRestoreReplayCheckpointRepositoryError("persistence_failed"));
  await expect(repository.load("bad", "restore-pg-2")).rejects
    .toEqual(new PostgresRestoreReplayCheckpointRepositoryError("invalid_input"));
});

test("maps candidate conflicts and serialization failures to closed codes", async () => {
  for (const [providerCode, expected] of [
    ["23505", "candidate_conflict"],
    ["40001", "retryable_serialization"],
  ] as const) {
    const connection = new FakeConnection();
    connection.failureCode = providerCode;
    const repository = createPostgresRestoreReplayCheckpointRepository(
      new FakePool(connection),
    );
    await expect(repository.record(candidate())).rejects
      .toEqual(new PostgresRestoreReplayCheckpointRepositoryError(expected));
  }
});
