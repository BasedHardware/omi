import { Database } from "bun:sqlite";

import { SqliteTasksStore } from "./tasks-store";

const [databasePath, baseRevision, value, startAtRaw] = process.argv.slice(2);
if (
  databasePath === undefined
  || baseRevision === undefined
  || value === undefined
  || startAtRaw === undefined
) {
  throw new TypeError(
    "usage: concurrent-task-child.ts <database-path> <base-revision> <value> <start-at-ms>",
  );
}

await Bun.sleep(Math.max(0, Number(startAtRaw) - Date.now()));
const db = new Database(databasePath, { create: true });
try {
  const store = new SqliteTasksStore(db);
  const outcome = store.apply("acct-concurrent", {
    op: "patch",
    record_id: "shared",
    patch: { value },
    base_revision: baseRevision,
  });
  process.stdout.write(JSON.stringify(outcome));
} finally {
  db.close();
}

