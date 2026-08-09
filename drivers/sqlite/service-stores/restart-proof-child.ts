import { Database } from "bun:sqlite";

import { createLocalService } from "../../../apps/service/app-facing";
import { createSqliteLocalServiceStores } from "./index";

const OWNER = "acct-i5-restart-proof";
const EPOCH = 7;
const WRITE_ID = "15".repeat(32);
const RECORD_ID = "task-i5-persistent";
const DESCRIPTION = "I5 restart proof task";

const open = (path: string): Database =>
  path === ":memory:" ? new Database(":memory:") : new Database(path, { create: true });

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
      provenance: ["i5:restart-proof"],
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

const main = async (): Promise<void> => {
  const phase = process.argv[2];
  const databasePath = process.argv[3];
  if ((phase !== "write" && phase !== "read-and-replay") || databasePath === undefined) {
    throw new TypeError("usage: restart-proof-child.ts <write|read-and-replay> <database-path>");
  }

  const db = open(databasePath);
  try {
    const service = createLocalService({
      db,
      ownerAccountId: OWNER,
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "i5-restart-proof",
      stores: createSqliteLocalServiceStores(db),
    });

    if (phase === "write") {
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
      const activation = await request(service, "/v1/qa/control/activate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ epoch: EPOCH, at_control_revision: 3 }),
      });
      const written = await request(service, "/v1/tasks/ops", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: envelope,
      });
      process.stdout.write(JSON.stringify({ activation, written }));
      return;
    }

    const read = await request(service, "/v1/tasks?limit=10");
    const replay = await request(service, "/v1/tasks/ops", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: envelope,
    });
    process.stdout.write(JSON.stringify({ read, replay, description: DESCRIPTION }));
  } finally {
    db.close();
  }
};

await main();

