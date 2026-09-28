import { Database } from "bun:sqlite";

import type { FolderRecord } from "../../../apps/service/stores/folders-store";
import { createSqliteLocalServiceStores } from "./index";

const ACCOUNT = "acct-folder-restart";
const FOLDER_ID = "folder-persistent";
const databasePath = process.argv[3];
const phase = process.argv[2];

if ((phase !== "write" && phase !== "read") || databasePath === undefined) {
  throw new TypeError("usage: folders-restart-proof-child.ts <write|read> <database-path>");
}

const db = new Database(databasePath, databasePath === ":memory:" ? undefined : { create: true });
try {
  const stores = createSqliteLocalServiceStores(db);
  if (phase === "write") {
    const record: FolderRecord = {
      id: FOLDER_ID,
      name: "Persistent folder",
      description: "Separate-process persistence proof.",
      color: "#007AFF",
      icon: "briefcase",
      created_at: "2026-08-03T12:00:00.000Z",
      updated_at: "2026-08-07T12:00:00.000Z",
      order: 0,
      is_default: false,
      is_system: false,
    };
    stores.folders.upsert(ACCOUNT, record);
    process.stdout.write(JSON.stringify({ id: record.id, name: record.name }));
  } else {
    const found = stores.folders.readFolder(ACCOUNT, FOLDER_ID);
    process.stdout.write(JSON.stringify({ found: found !== null, record: found }));
  }
} finally {
  db.close();
}
