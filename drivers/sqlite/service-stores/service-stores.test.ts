// domain-pending(DIV-DOMCORE-013)
// domain-pending(UNK-DOMCORE-002)
import { mkdirSync } from "node:fs";
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { createLocalService } from "../../../apps/service/app-facing";
import type { AccountControlObservation } from "../../../core/control/account-control";
import {
  SqliteAccountControlProjectionStore,
  SqliteConversationsStore,
  SqliteFolderDeletionUnitOfWork,
  SqliteFoldersStore,
  SqliteStragglerTable,
  SqliteTasksStore,
  SqliteWriteIdRegistry,
  SqliteWriteUnitOfWork,
  createSqliteLocalServiceStores,
} from "./index";

const scratch = `/tmp/i5-${process.pid}`;
mkdirSync(scratch, { recursive: true });
let databaseNumber = 0;
const databasePath = (label: string): string =>
  `${scratch}/${String(++databaseNumber).padStart(3, "0")}-${label}.sqlite`;
const open = (path: string): Database => new Database(path, { create: true });

const observation = (
  accountId: string,
  overrides: Partial<AccountControlObservation> = {},
): AccountControlObservation => ({
  account_id: accountId,
  control_revision: 1,
  account_generation: "legacy",
  account_epoch: null,
  lifecycle_state: "active",
  deletion_epoch: null,
  ...overrides,
});

describe("the SQLite service-store adapters", () => {
  test("conversations persist typed fields, mutations, ordering, and revision after reopen", () => {
    const path = databasePath("conversations");
    const firstDb = open(path);
    const first = new SqliteConversationsStore(firstDb);
    const row = {
      id: "conversation-a",
      structured: { title: "first", overview: "overview" },
      created_at: "2026-08-03T12:00:00.000Z",
      updated_at: "2026-08-03T12:00:00.000Z",
      started_at: "2026-08-03T12:00:00.000Z",
      finished_at: "2026-08-03T12:05:00.000Z",
      source: "omi",
      status: "completed",
      discarded: false,
      starred: false,
      visibility: "private" as const,
      is_locked: false,
      folder_id: null,
    };
    expect(first.upsert("acct-a", row).stored).toBe(true);
    const beforeMissingFolder = first.readRecord("acct-a", "conversation-a");
    expect(first.updateFolder(
      "acct-a", "conversation-a", "missing-folder", "2026-08-07T12:00:00.000Z",
    )).toEqual({ updated: false, reason: "folder_not_found" });
    expect(first.readRecord("acct-a", "conversation-a")).toEqual(beforeMissingFolder);
    expect(first.readStateRevision("acct-a")).toBe(0);
    expect(first.updateStarred(
      "acct-a", "conversation-a", true, "2026-08-07T12:00:00.000Z",
    )).toMatchObject({ updated: true, state_revision: 1 });
    firstDb.close();

    const secondDb = open(path);
    const second = new SqliteConversationsStore(secondDb);
    expect(second.readRecord("acct-a", "conversation-a")).toMatchObject({
      structured: { title: "first", overview: "overview" },
      starred: true,
      updated_at: "2026-08-07T12:00:00.000Z",
    });
    expect(second.readStateRevision("acct-a")).toBe(1);
    secondDb.close();
  });

  test("tasks preserve revision chains, tombstones, content, and order after reopen", () => {
    const path = databasePath("tasks");
    const firstDb = open(path);
    const first = new SqliteTasksStore(firstDb);
    const created = first.apply("acct-a", {
      op: "create", record_id: "a", content: { title: "first", nested: { v: 1 } },
    });
    first.apply("acct-a", { op: "create", record_id: "b", content: { title: "second" } });
    expect(created.applied).toBe(true);
    if (!created.applied || created.revision === null) return;
    first.apply("acct-a", { op: "delete", record_id: "a", base_revision: created.revision });
    firstDb.close();

    const secondDb = open(path);
    const second = new SqliteTasksStore(secondDb);
    const recreated = second.apply("acct-a", {
      op: "create", record_id: "a", content: { title: "first", nested: { v: 1 } },
    });
    expect(recreated.applied).toBe(true);
    if (!recreated.applied) return;
    expect(recreated.revision).not.toBe(created.revision);
    expect(second.listRecords("acct-a").map((row) => row.record_id)).toEqual(["a", "b"]);
    expect(second.readRecord("acct-a", "a")?.content).toEqual({ title: "first", nested: { v: 1 } });
    secondDb.close();
  });

  test("write-id replay and reuse survive reopen, including null outcomes", () => {
    const path = databasePath("registry");
    const content = { domain: "tasks", account_epoch: 7, op: { a: 1, b: 2 } };
    const firstDb = open(path);
    const first = new SqliteWriteIdRegistry(firstDb);
    first.record({
      accountId: "acct-a",
      writeId: "a".repeat(64),
      fingerprintOf: content,
      accountEpoch: 7,
      outcome: { record_id: "task-a", revision: null },
    });
    firstDb.close();

    const secondDb = open(path);
    const second = new SqliteWriteIdRegistry(secondDb);
    expect(second.lookup("acct-a", "a".repeat(64), {
      op: { b: 2, a: 1 }, account_epoch: 7, domain: "tasks",
    })).toEqual({ kind: "replay", outcome: { record_id: "task-a", revision: null } });
    expect(second.lookup("acct-a", "a".repeat(64), { ...content, account_epoch: 8 }))
      .toEqual({ kind: "reuse" });
    secondDb.close();
  });

  test("straggler bytes, insertion order, lifecycle deletion, and retention survive reopen", () => {
    const path = databasePath("stragglers");
    const firstDb = open(path);
    const first = new SqliteStragglerTable(firstDb);
    first.preserve("acct-a", {
      envelope_json: "{\"exact\":1}", write_id: "first", account_epoch: 1,
      retained_at_epoch_seconds: 100,
    });
    first.preserve("acct-a", {
      envelope_json: "{\"exact\":2}", write_id: "second", account_epoch: 2,
      retained_at_epoch_seconds: 200,
    });
    firstDb.close();

    const secondDb = open(path);
    const second = new SqliteStragglerTable(secondDb);
    expect(second.exportAccount("acct-a").map((row) => row.envelope_json))
      .toEqual(["{\"exact\":1}", "{\"exact\":2}"]);
    expect(second.deleteAccount("acct-a")).toBe(2);
    expect(second.exportAccount("acct-a")).toEqual([]);
    secondDb.close();
  });

  test("control activation and poisoned refusals survive reopen", () => {
    const path = databasePath("control");
    const account = "acct-control";
    const firstDb = open(path);
    const first = new SqliteAccountControlProjectionStore(firstDb);
    first.observe(observation(account));
    first.observe(observation(account, { control_revision: 2, account_generation: "migrating" }));
    first.observe(observation(account, {
      control_revision: 3, account_generation: "new", account_epoch: 7,
    }));
    expect(first.activate(account, { epoch: 7, at_control_revision: 3 }).activated).toBe(true);
    const conflict = first.observe(observation(account, {
      control_revision: 3, account_generation: "new", account_epoch: 8,
    }));
    expect(conflict.accepted).toBe(false);
    firstDb.close();

    const secondDb = open(path);
    const second = new SqliteAccountControlProjectionStore(secondDb);
    expect(second.read(account)).toMatchObject({
      account_epoch: 7,
      activation: { activated_epoch: 7, at_control_revision: 3 },
      conflict: { detail: "conflicting_observation" },
    });
    expect(second.activate(account, { epoch: 7, at_control_revision: 3 }))
      .toEqual({ activated: false, reason: "projection_conflicted" });
    secondDb.close();
  });

  test("createLocalService uses an injected bundle and retains the in-memory default", () => {
    const sqliteDb = open(databasePath("injection"));
    const stores = createSqliteLocalServiceStores(sqliteDb);
    const injected = createLocalService({
      db: sqliteDb,
      ownerAccountId: "acct-injected",
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "injection-test",
      stores,
    });
    expect(injected.writePath.conversations).toBe(stores.conversations);
    expect(injected.writePath.tasks).toBe(stores.tasks);
    expect(stores.conversations).toBeInstanceOf(SqliteConversationsStore);
    expect(injected.writePath.folders).toBe(stores.folders);
    expect(stores.folders).toBeInstanceOf(SqliteFoldersStore);
    expect(injected.writePath.folderDeletion).toBe(stores.folderDeletion);
    expect(stores.folderDeletion).toBeInstanceOf(SqliteFolderDeletionUnitOfWork);
    expect(injected.writePath.registry).toBe(stores.registry);
    expect(injected.writePath.unitOfWork).toBe(stores.unitOfWork);
    expect(stores.unitOfWork).toBeInstanceOf(SqliteWriteUnitOfWork);
    expect(injected.writePath.stragglers).toBe(stores.stragglers);
    expect(injected.writePath.control).toBe(stores.control);
    sqliteDb.close();

    const memoryDb = new Database(":memory:");
    const defaulted = createLocalService({
      db: memoryDb,
      ownerAccountId: "acct-default",
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "default-test",
    });
    expect(defaulted.writePath.tasks.constructor).toBe(Object);
    memoryDb.close();
  });

  test("two connections serialize conditional writes instead of losing one", async () => {
    const path = databasePath("concurrent-tasks");
    const seedDb = open(path);
    const seeded = new SqliteTasksStore(seedDb).apply("acct-concurrent", {
      op: "create", record_id: "shared", content: { value: "seed" },
    });
    expect(seeded.applied).toBe(true);
    if (!seeded.applied || seeded.revision === null) return;
    seedDb.close();

    const child = new URL("./concurrent-task-child.ts", import.meta.url).pathname;
    const startAt = String(Date.now() + 150);
    const spawn = (value: string) => Bun.spawn({
      cmd: [process.execPath, "run", child, path, seeded.revision!, value, startAt],
      stdout: "pipe",
      stderr: "pipe",
    });
    const left = spawn("left");
    const right = spawn("right");
    const [leftExit, rightExit] = await Promise.all([left.exited, right.exited]);
    expect([leftExit, rightExit]).toEqual([0, 0]);
    const outcomes = await Promise.all([
      new Response(left.stdout).json(),
      new Response(right.stdout).json(),
    ]) as Array<{ readonly applied: boolean; readonly reason?: string }>;
    expect(outcomes.filter((outcome) => outcome.applied)).toHaveLength(1);
    expect(outcomes.filter((outcome) => outcome.reason === "conflict")).toHaveLength(1);

    const checkDb = open(path);
    const stored = new SqliteTasksStore(checkDb).readRecord("acct-concurrent", "shared");
    expect(["left", "right"]).toContain((stored?.content as { value?: string }).value);
    checkDb.close();
  });
});

describe("restart acceptance and red mutation", () => {
  const proof = new URL("./restart-proof.ts", import.meta.url).pathname;
  const run = (path: string) => Bun.spawnSync({
    cmd: [process.execPath, "run", proof, path],
    stdout: "pipe",
    stderr: "pipe",
  });

  test("write through the door, stop, restart, and read the task through the door", () => {
    const result = run(databasePath("restart-proof"));
    expect(result.exitCode, result.stderr.toString()).toBe(0);
    expect(result.stdout.toString()).toContain("read through door: 200 found=\"I5 restart proof task\"");
    expect(result.stdout.toString()).toContain("replay after restart: 200 idempotent=true");
  });

  test(":memory: mutation makes the same restart proof fail", () => {
    const result = run(":memory:");
    expect(result.exitCode).not.toBe(0);
    expect(result.stderr.toString()).toContain("restart persistence proof failed");
  });
});

describe("apply and write-id record are one durable unit of work", () => {
  const proof = new URL("./unit-of-work-crash-proof.ts", import.meta.url).pathname;

  test("a real SIGKILL between apply and record rolls both back before replay", () => {
    const root = `/tmp/i7-${process.pid}`;
    mkdirSync(root, { recursive: true });
    const nonce = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const result = Bun.spawnSync({
      cmd: [process.execPath, "run", proof, `${root}/${nonce}.sqlite`, `${root}/${nonce}.marker`],
      stdout: "pipe",
      stderr: "pipe",
    });
    expect(result.exitCode, result.stderr.toString()).toBe(0);
    expect(result.stdout.toString()).toBe([
      "child reached boundary: task applied, write_id not recorded",
      "kill child: SIGKILL",
      "restart child: complete",
      "after crash: task_records=0 task_applies=0 registry_rows=0",
      "replay same write_id: 200 idempotent=false",
      "after replay: task_records=1 task_applies=1 registry_rows=1",
      "second replay: 200 idempotent=true",
      "unit-of-work crash proof: PASS",
      "",
    ].join("\n"));
  });
});
