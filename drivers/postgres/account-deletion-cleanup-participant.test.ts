import { expect, test } from "bun:test";

import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { POSTGRES_DELETION_SURFACE_TABLES } from "./deletion-surface-registry";
import {
  createPostgresDeletionCleanupParticipant,
  PostgresDeletionCleanupError,
  type HeldPostgresDeletionCleanupSession,
} from "./account-deletion-cleanup-participant";

const coordinate = Object.freeze({
  account_id: "account:deleted",
  control_revision: 7,
  deletion_epoch: 3,
});
const operationRef = `opref1_${"a".repeat(64)}`;
const eligibilityDigest = "b".repeat(64);

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "cleanup" });
  readonly statements: SqlStatement[] = [];
  scanGate: Promise<void> | null = null;

  async query<Row extends Record<string, unknown>>(
    statement: SqlStatement,
  ): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "cleanup.set_role") return [];
    if (statement.name === "cleanup.lock_terminal") {
      return [{
        terminal_content_hash: "c".repeat(64),
        export_content_hash: "d".repeat(64),
        backend_pid: "42",
        database_now: new Date(0),
      } as unknown as Row];
    }
    if (statement.name === "cleanup.scan_surface") {
      if (this.scanGate !== null) {
        const gate = this.scanGate;
        this.scanGate = null;
        await gate;
      }
      const surface = statement.values[0] as keyof typeof POSTGRES_DELETION_SURFACE_TABLES;
      return POSTGRES_DELETION_SURFACE_TABLES[surface].map((table_name) => ({
        table_name,
        row_count: "0",
      } as unknown as Row));
    }
    if (statement.name === "cleanup.dispose_group") {
      const surfaces = JSON.parse(statement.values[0] as string) as readonly string[];
      return surfaces.map((surface) => ({
        surface,
        result: "already_absent",
        affected_count: "0",
        completed_at: new Date(0),
      } as unknown as Row));
    }
    throw new Error("unexpected statement");
  }

  async execute(): Promise<{ rowCount: number }> {
    throw new Error("cleanup participant must use named functions");
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];

  constructor(readonly connection: FakeConnection) {}

  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.options.push(options);
    return callback(this.connection);
  }
}

test("scans and disposes only the registered PostgreSQL cleanup group", async () => {
  const connection = new FakeConnection();
  const pool = new FakePool(connection);
  const participant = createPostgresDeletionCleanupParticipant(pool);
  let escaped: HeldPostgresDeletionCleanupSession | null = null;
  const result = await participant.withHeldDatabaseFence(
    coordinate,
    operationRef,
    eligibilityDigest,
    async (session) => {
      escaped = session;
      const scan = await session.scanOwned();
      expect(scan.map((receipt) => receipt.surface)).toEqual(
        Object.keys(POSTGRES_DELETION_SURFACE_TABLES) as Array<keyof typeof POSTGRES_DELETION_SURFACE_TABLES>,
      );
      expect(scan.every((receipt) => receipt.remaining_count === 0)).toBe(true);
      return session.dispose(["durable_work", "staged_results"]);
    },
  );

  expect(result.map((receipt) => receipt.surface))
    .toEqual(["durable_work", "staged_results"]);
  expect(pool.options).toEqual([{ isolationLevel: "serializable", accessMode: "read write" }]);
  expect(connection.statements.slice(0, 2).map((statement) => statement.name))
    .toEqual(["cleanup.set_role", "cleanup.lock_terminal"]);
  await expect(escaped!.scanOwned()).rejects
    .toEqual(new PostgresDeletionCleanupError("persistence_failed"));
});

test("drains an unawaited cleanup operation before allowing transaction completion", async () => {
  let release!: () => void;
  const connection = new FakeConnection();
  connection.scanGate = new Promise<void>((resolve) => { release = resolve; });
  const participant = createPostgresDeletionCleanupParticipant(new FakePool(connection));
  let settled = false;

  const completion = participant.withHeldDatabaseFence(
    coordinate,
    operationRef,
    eligibilityDigest,
    async (session) => {
      void session.scanOwned();
      return "callback-returned";
    },
  ).finally(() => { settled = true; });

  while (!connection.statements.some((statement) => statement.name === "cleanup.scan_surface")) {
    await Promise.resolve();
  }
  await Promise.resolve();
  expect(settled).toBe(false);
  release();
  await expect(completion).resolves.toBe("callback-returned");
  expect(settled).toBe(true);
});

test("fails closed when an ignored cleanup operation rejects", async () => {
  class RejectingConnection extends FakeConnection {
    override async query<Row extends Record<string, unknown>>(
      statement: SqlStatement,
    ): Promise<readonly Row[]> {
      if (statement.name === "cleanup.scan_surface") {
        throw new Error("private provider payload");
      }
      return super.query<Row>(statement);
    }
  }
  const participant = createPostgresDeletionCleanupParticipant(
    new FakePool(new RejectingConnection()),
  );
  await expect(participant.withHeldDatabaseFence(
    coordinate,
    operationRef,
    eligibilityDigest,
    async (session) => {
      void session.scanOwned();
      return "must-not-commit";
    },
  )).rejects.toEqual(new PostgresDeletionCleanupError("persistence_failed"));
});
