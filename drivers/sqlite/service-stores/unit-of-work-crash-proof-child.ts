// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)

import { writeFileSync } from "node:fs";
import { Database } from "bun:sqlite";

import { createLocalService } from "../../../apps/service/app-facing";
import { createSqliteLocalServiceStores, createSqliteWriteUnitOfWork } from "./index";

const OWNER = "acct-i7-crash-proof";
const EPOCH = 7;
const WRITE_ID = "17".repeat(32);
const RECORD_ID = "task-i7-atomic";
const DESCRIPTION = "I7 atomic write proof task";

const envelope = JSON.stringify({
  write_id: WRITE_ID,
  account_epoch: EPOCH,
  domain: "tasks",
  op: {
    op: "create",
    record_id: RECORD_ID,
    content: {
      description: DESCRIPTION,
      completed: false,
      completedAt: null,
      dueAt: null,
      owner: null,
      source: "assistant",
      provenance: ["i7:crash-proof"],
      sortOrder: 1,
      indentLevel: 0,
      createdAt: 1_786_000_000,
      updatedAt: 1_786_000_000,
    },
  },
});

const request = async (
  service: ReturnType<typeof createLocalService>,
  path: string,
  init: RequestInit = {},
): Promise<{ readonly status: number; readonly body: string }> => {
  const response = await service.app.request(path, {
    ...init,
    headers: {
      authorization: `Bearer ${service.devToken}`,
      ...(init.headers ?? {}),
    },
  });
  return { status: response.status, body: await response.text() };
};

const observe = (overrides: Record<string, unknown>) => ({
  control_revision: 1,
  account_generation: "legacy",
  account_epoch: null,
  lifecycle_state: "active",
  deletion_epoch: null,
  ...overrides,
});

const activate = async (service: ReturnType<typeof createLocalService>): Promise<void> => {
  for (const observation of [
    observe({}),
    observe({ control_revision: 2, account_generation: "migrating" }),
    observe({ control_revision: 3, account_generation: "new", account_epoch: EPOCH }),
  ]) {
    const result = await request(service, "/v1/qa/control/observe", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(observation),
    });
    if (result.status !== 200) throw new Error(`control observation failed: ${result.status}`);
  }
  const result = await request(service, "/v1/qa/control/activate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ epoch: EPOCH, at_control_revision: 3 }),
  });
  if (result.status !== 200) throw new Error(`control activation failed: ${result.status}`);
};

const postWrite = (service: ReturnType<typeof createLocalService>) => request(service, "/v1/tasks/ops", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: envelope,
});

const counts = (db: Database) => Object.freeze({
  taskRecords: (db.query("SELECT COUNT(*) AS count FROM service_task_records").get() as { count: number }).count,
  taskApplies: (db.query("SELECT COUNT(*) AS count FROM service_task_apply_sequence").get() as { count: number }).count,
  registryRows: (db.query("SELECT COUNT(*) AS count FROM service_write_id_registry").get() as { count: number }).count,
});

const main = async (): Promise<void> => {
  const phase = process.argv[2];
  const databasePath = process.argv[3];
  const markerPath = process.argv[4];
  if ((phase !== "crash" && phase !== "restart") || databasePath === undefined || markerPath === undefined) {
    throw new TypeError("usage: unit-of-work-crash-proof-child.ts <crash|restart> <database-path> <marker-path>");
  }

  const db = new Database(databasePath, { create: true });
  try {
    const stores = createSqliteLocalServiceStores(db);
    if (phase === "crash") {
      const unitOfWork = createSqliteWriteUnitOfWork(db, {
        beforeRegistryRecord(): never {
          // This call begins only after `tasks.apply` has returned. The parent
          // observes the marker, sends SIGKILL, and never lets record execute.
          writeFileSync(markerPath, "task-applied-registry-not-recorded\n", "utf8");
          Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0);
          throw new Error("unreachable");
        },
      });
      const crashStores = Object.freeze({
        ...stores,
        unitOfWork,
      });
      const service = createLocalService({
        db,
        ownerAccountId: OWNER,
        memoryCount: 1,
        accountTimezone: "UTC",
        devSecretLabel: "i7-crash-proof",
        stores: crashStores,
      });
      await activate(service);
      await postWrite(service);
      throw new Error("write unexpectedly escaped the crash barrier");
    }

    const beforeReplay = counts(db);
    const service = createLocalService({
      db,
      ownerAccountId: OWNER,
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "i7-crash-proof",
      stores,
    });
    const replay = await postWrite(service);
    const read = await request(service, "/v1/tasks?limit=10");
    const secondReplay = await postWrite(service);
    const afterReplay = counts(db);
    process.stdout.write(JSON.stringify({
      beforeReplay,
      replay,
      read,
      secondReplay,
      afterReplay,
      description: DESCRIPTION,
    }));
  } finally {
    db.close();
  }
};

await main();
