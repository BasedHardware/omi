import { expect, test } from "bun:test";

import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  createPostgresTombstoneRestoreTarget,
  PostgresTombstoneRestoreTargetError,
  type HeldPostgresTombstoneRestoreTarget,
} from "./tombstone-restore-target";

const restore = Object.freeze({
  restore_id: "restore-pg-1",
  restore_scope: "postgresql" as const,
  restored_snapshot_digest: "a".repeat(64),
  restore_completed_at_epoch_seconds: 1_800_000_000,
});
const terminal = Object.freeze({
  account_id: "account:deleted",
  control_revision: 12,
  deletion_epoch: 4,
  terminal_record_digest: "b".repeat(64),
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "restore" });
  readonly statements: SqlStatement[] = [];
  applyGate: Promise<void> | null = null;
  applyFailureCode: string | null = null;
  applyResult: "applied" | "already_absent" = "applied";

  async query<Row extends Record<string, unknown>>(
    statement: SqlStatement,
  ): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "restore_target.set_role") return [];
    if (statement.name === "restore_target.hold") {
      return [{ backend_pid: "42", database_now: new Date(0) } as unknown as Row];
    }
    if (statement.name === "restore_target.apply_terminal_fence") {
      if (this.applyGate !== null) {
        const gate = this.applyGate;
        this.applyGate = null;
        await gate;
      }
      if (this.applyFailureCode !== null) {
        const error = Object.create(null) as { code: string };
        Object.defineProperty(error, "code", { value: this.applyFailureCode });
        throw error;
      }
      return [{
        result: this.applyResult,
        applied_at_epoch_micros: "1800000000123456",
      } as unknown as Row];
    }
    throw new Error("unexpected statement");
  }

  async execute(): Promise<{ rowCount: number }> {
    throw new Error("restore target must use named functions");
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

test("installs one exact PostgreSQL terminal fence through the dedicated role", async () => {
  const connection = new FakeConnection();
  const pool = new FakePool(connection);
  const target = createPostgresTombstoneRestoreTarget(pool);
  let escaped: HeldPostgresTombstoneRestoreTarget | null = null;
  const outcome = await target.withHeldTarget(restore, async (session) => {
    escaped = session;
    return session.apply(terminal);
  });

  expect(outcome).toMatchObject({
    version: "terminal-application-outcome-v1",
    restore_id: restore.restore_id,
    restore_scope: restore.restore_scope,
    restored_snapshot_digest: restore.restored_snapshot_digest,
    ...terminal,
    result: "applied",
    error_code: null,
  });
  expect(outcome.target_receipt_digest).toMatch(/^[0-9a-f]{64}$/);
  expect(Object.isFrozen(outcome)).toBe(true);
  expect(pool.options).toEqual([{ isolationLevel: "serializable", accessMode: "read write" }]);
  expect(connection.statements.map((statement) => statement.name)).toEqual([
    "restore_target.set_role", "restore_target.hold", "restore_target.apply_terminal_fence",
  ]);
  expect(connection.statements[0]!.text).toBe("SET LOCAL ROLE omi_platform_restore");
  expect(connection.statements[1]!.values).toEqual([
    restore.restore_id, "postgresql", restore.restored_snapshot_digest,
    restore.restore_completed_at_epoch_seconds,
  ]);
  await expect(escaped!.apply(terminal)).rejects
    .toEqual(new PostgresTombstoneRestoreTargetError("persistence_failed"));
});

test("implements the coordinator's per-record target application seam", async () => {
  const target = createPostgresTombstoneRestoreTarget(new FakePool(new FakeConnection()));
  await expect(target.applyTerminalRecord({ restore, terminal_record: terminal }))
    .resolves.toMatchObject({
      restore_id: restore.restore_id,
      account_id: terminal.account_id,
      result: "applied",
    });
});

test("detaches nested coordinator request coordinates before the first await", async () => {
  const connection = new FakeConnection();
  const target = createPostgresTombstoneRestoreTarget(new FakePool(connection));
  const mutableRestore = { ...restore };
  const mutableTerminal = { ...terminal };
  const completion = target.applyTerminalRecord({
    restore: mutableRestore,
    terminal_record: mutableTerminal,
  });
  mutableRestore.restore_id = "restore-substituted";
  mutableTerminal.account_id = "account:substituted";
  const outcome = await completion;
  expect(outcome.restore_id).toBe(restore.restore_id);
  expect(outcome.account_id).toBe(terminal.account_id);
  expect(connection.statements.find((statement) => statement.name === "restore_target.hold")?.values[0])
    .toBe(restore.restore_id);
  expect(connection.statements.find((statement) =>
    statement.name === "restore_target.apply_terminal_fence")?.values[0]).toBe(terminal.account_id);
});

test("maps a dominating higher target fence to stable already-absent replay", async () => {
  const connection = new FakeConnection();
  connection.applyResult = "already_absent";
  const target = createPostgresTombstoneRestoreTarget(new FakePool(connection));
  const first = await target.applyTerminalRecord({ restore, terminal_record: terminal });
  const replay = await target.applyTerminalRecord({ restore, terminal_record: terminal });
  expect(first.result).toBe("already_absent");
  expect(replay).toEqual(first);
  expect(first.target_receipt_digest).toMatch(/^[0-9a-f]{64}$/);
  expect(connection.statements.filter((statement) =>
    statement.name === "restore_target.apply_terminal_fence")).toHaveLength(2);
});

test("drains started target operations before transaction completion", async () => {
  let release!: () => void;
  const connection = new FakeConnection();
  connection.applyGate = new Promise<void>((resolve) => { release = resolve; });
  const target = createPostgresTombstoneRestoreTarget(new FakePool(connection));
  let settled = false;
  const completion = target.withHeldTarget(restore, async (session) => {
    void session.apply(terminal);
    return "callback-returned";
  }).finally(() => { settled = true; });

  while (!connection.statements.some((statement) =>
    statement.name === "restore_target.apply_terminal_fence")) await Promise.resolve();
  await Promise.resolve();
  expect(settled).toBe(false);
  release();
  await expect(completion).resolves.toBe("callback-returned");
  expect(settled).toBe(true);
});

test("fails the transaction when an ignored target operation rejects", async () => {
  const connection = new FakeConnection();
  connection.applyFailureCode = "23505";
  const target = createPostgresTombstoneRestoreTarget(new FakePool(connection));
  await expect(target.withHeldTarget(restore, async (session) => {
    void session.apply(terminal);
    return "must-not-commit";
  })).rejects.toEqual(new PostgresTombstoneRestoreTargetError("target_conflict"));
});

test("rejects non-PostgreSQL and hostile coordinates before opening a transaction", async () => {
  const pool = new FakePool(new FakeConnection());
  const target = createPostgresTombstoneRestoreTarget(pool);
  await expect(target.withHeldTarget(
    { ...restore, restore_scope: "legacy" },
    async () => undefined,
  )).rejects.toEqual(new PostgresTombstoneRestoreTargetError("invalid_input"));

  let getterCalled = false;
  const hostile = { ...restore } as Record<string, unknown>;
  Object.defineProperty(hostile, "restore_id", {
    enumerable: true,
    get() { getterCalled = true; return restore.restore_id; },
  });
  await expect(target.withHeldTarget(
    hostile as unknown as typeof restore,
    async () => undefined,
  )).rejects.toEqual(new PostgresTombstoneRestoreTargetError("invalid_input"));
  expect(getterCalled).toBe(false);
  expect(pool.transactions).toBe(0);
});

test("maps serialization and target conflicts to closed codes", async () => {
  for (const [provider, expected] of [
    ["40001", "retryable_serialization"],
    ["23505", "target_conflict"],
  ] as const) {
    const connection = new FakeConnection();
    connection.applyFailureCode = provider;
    const target = createPostgresTombstoneRestoreTarget(new FakePool(connection));
    await expect(target.withHeldTarget(restore, async (session) => session.apply(terminal)))
      .rejects.toEqual(new PostgresTombstoneRestoreTargetError(expected));
  }
});
