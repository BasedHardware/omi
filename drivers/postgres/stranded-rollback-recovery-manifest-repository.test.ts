import { describe, expect, test } from "bun:test";

import type {
  CheckedOutPostgresConnection,
  PostgresQuery,
  PostgresTransactionPool,
} from "./connection";
import {
  STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
  STRANDED_ROLLBACK_RECOVERY_SURFACES,
  STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS,
  STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION,
  verifyStrandedRollbackRecovery,
} from "../../core/control/stranded-rollback-recovery";
import {
  PostgresStrandedRollbackRecoveryManifestError,
  createPostgresStrandedRollbackRecoveryManifestRepository,
} from "./stranded-rollback-recovery-manifest-repository";

const ACCOUNT = "acct-stranded-repository";
const digest = (value: string): string => value.repeat(64);
const rolledBackAt = 1_800_000_000;
const verified = () => verifyStrandedRollbackRecovery({
  control_projection: {
    account_id: ACCOUNT,
    control_revision: 9,
    account_generation: "rolled_back_stranded",
    account_epoch: 4,
    lifecycle_state: "active",
    deletion_epoch: null,
    activation: null,
    conflict: null,
  },
  rollback_coordinate: {
    version: "stranded-rollback-coordinate-v1",
    account_id: ACCOUNT,
    control_revision: 9,
    account_epoch: 4,
    database_generation_digest: digest("a"),
    cutover_frontier_digest: digest("b"),
    rollback_frontier_digest: digest("c"),
    cutover_at_epoch_seconds: rolledBackAt - 3_600,
    rolled_back_at_epoch_seconds: rolledBackAt,
    recovery_deadline_epoch_seconds: rolledBackAt + STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS,
  },
  source_receipts: STRANDED_ROLLBACK_RECOVERY_SURFACES.map((surface, index) => ({
    version: STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION,
    manifest_contract_version: STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
    scanner_contract_version: `scanner-${surface}-v1`,
    account_id: ACCOUNT,
    control_revision: 9,
    account_epoch: 4,
    database_generation_digest: digest("a"),
    surface,
    source_frontier_digest: String(index % 10).repeat(64),
    source_fence_state: "held" as const,
    source_fence_receipt_digest: digest("d"),
    record_count: index,
    record_set_digest: digest("e"),
  })),
  observed_at_epoch_seconds: rolledBackAt + 1,
}).verified_manifest!;

interface FakeRow extends Record<string, unknown> {
  classification?: string;
}

class FakeConnection implements CheckedOutPostgresConnection {
  readonly statements: string[] = [];
  stored: FakeRow | null = null;
  async query<Row extends Record<string, unknown>>(query: PostgresQuery): Promise<readonly Row[]> {
    this.statements.push(query.name);
    if (query.name.endsWith("set_role")) return [];
    if (query.name.endsWith("record")) {
      const values = query.values;
      this.stored = {
        classification: this.stored === null ? "stored" : "replayed",
        account_id: values[0],
        control_revision: values[1],
        account_epoch: values[2],
        database_generation_digest: values[3],
        cutover_frontier_digest: values[4],
        rollback_frontier_digest: values[5],
        cutover_at_epoch_seconds: values[6],
        rolled_back_at_epoch_seconds: values[7],
        recovery_deadline_epoch_seconds: values[8],
        surface_count: 11,
        total_record_count: 55,
        manifest_digest: values[9],
        persistence_receipt_digest: values[10],
      };
      return [this.stored as Row];
    }
    if (this.stored === null) return [];
    const { classification: ignored, ...loaded } = this.stored;
    void ignored;
    return [loaded as Row];
  }
}

class FakePool implements PostgresTransactionPool {
  readonly connection = new FakeConnection();
  readonly transactions: Array<{ isolationLevel: string; accessMode: string }> = [];
  async withTransaction<T>(options: { isolationLevel: "serializable"; accessMode: "read only" | "read write" }, callback: (connection: CheckedOutPostgresConnection) => Promise<T>): Promise<T> {
    this.transactions.push(options);
    return callback(this.connection);
  }
}

describe("PostgreSQL stranded rollback recovery manifest repository", () => {
  test("records, replays, and loads the exact verified manifest on one connection", async () => {
    const pool = new FakePool();
    const repository = createPostgresStrandedRollbackRecoveryManifestRepository(pool);
    const manifest = verified();
    const stored = await repository.record(manifest);
    const replayed = await repository.record(manifest);
    const loaded = await repository.load({
      version: "stranded-rollback-recovery-manifest-key-v1",
      account_id: ACCOUNT,
      control_revision: 9,
      account_epoch: 4,
      database_generation_digest: digest("a"),
      manifest_digest: manifest.manifest_digest,
    });
    expect(stored.kind).toBe("stored");
    expect(replayed.kind).toBe("replayed");
    expect(loaded).toEqual({ kind: "found", manifest: stored.manifest });
    expect(pool.connection.statements).toEqual([
      "stranded_rollback_recovery_manifest.set_role",
      "stranded_rollback_recovery_manifest.record",
      "stranded_rollback_recovery_manifest.set_role",
      "stranded_rollback_recovery_manifest.record",
      "stranded_rollback_recovery_manifest.set_role",
      "stranded_rollback_recovery_manifest.load",
    ]);
    expect(pool.transactions).toEqual([
      { isolationLevel: "serializable", accessMode: "read write" },
      { isolationLevel: "serializable", accessMode: "read write" },
      { isolationLevel: "serializable", accessMode: "read write" },
    ]);
  });

  test("rejects unverified plain manifests before opening PostgreSQL", async () => {
    const pool = new FakePool();
    const repository = createPostgresStrandedRollbackRecoveryManifestRepository(pool);
    await expect(repository.record(JSON.parse(JSON.stringify(verified())))).rejects
      .toMatchObject({ code: "invalid_input" });
    expect(pool.transactions).toHaveLength(0);
  });

  test("maps control denial and provider detail to closed errors", async () => {
    const pool: PostgresTransactionPool = {
      async withTransaction() {
        throw Object.assign(new Error("private SQL detail"), { code: "P0001" });
      },
    };
    await expect(createPostgresStrandedRollbackRecoveryManifestRepository(pool)
      .record(verified())).rejects.toEqual(
        new PostgresStrandedRollbackRecoveryManifestError("control_denied"),
      );
  });

  test("rejects hostile provider rows without invoking accessors", async () => {
    let getterCalls = 0;
    const hostile = Object.defineProperty({}, "classification", {
      enumerable: true,
      get() { getterCalls += 1; return "stored"; },
    });
    const pool: PostgresTransactionPool = {
      async withTransaction(_options, callback) {
        return callback({
          async query<Row extends Record<string, unknown>>(query: PostgresQuery) {
            return (query.name.endsWith("set_role") ? [] : [hostile]) as readonly Row[];
          },
        });
      },
    };
    await expect(createPostgresStrandedRollbackRecoveryManifestRepository(pool)
      .record(verified())).rejects.toMatchObject({ code: "persistence_failed" });
    expect(getterCalls).toBe(0);
  });
});
