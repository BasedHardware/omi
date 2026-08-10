import { writeFileSync } from "node:fs";
import { Database } from "bun:sqlite";

import type { ConversationRecord } from "../../../apps/service/stores/conversations-store";
import type { FolderRecord } from "../../../apps/service/stores/folders-store";
import type { LocalServiceStores } from "../../../apps/service/app-facing";
import {
  createSqliteLocalServiceStores,
  SqliteFolderDeletionUnitOfWork,
} from "./index";

const ACCOUNT = "acct-folder-atomicity";
const SOURCE = "folder-source";
const TARGET = "folder-target";
const phase = process.argv[2];
const databasePath = process.argv[3];
const markerPath = process.argv[4];
if ((phase !== "crash" && phase !== "restart") || databasePath === undefined || markerPath === undefined) {
  throw new TypeError("usage: folders-delete-crash-proof-child.ts <crash|restart> <database-path> <marker-path>");
}

const folder = (id: string, overrides: Partial<FolderRecord> = {}): FolderRecord => ({
  id,
  name: id,
  description: null,
  color: "#6B7280",
  icon: "folder",
  created_at: "2026-08-03T12:00:00.000Z",
  updated_at: "2026-08-07T12:00:00.000Z",
  order: id === TARGET ? 0 : 1,
  is_default: id === TARGET,
  is_system: id === TARGET,
  ...overrides,
});

const conversation: ConversationRecord = {
  id: "conversation-in-source",
  structured: { title: "Atomic folder move", overview: "Kill between writes." },
  created_at: "2026-08-03T12:00:00.000Z",
  updated_at: "2026-08-07T12:00:00.000Z",
  started_at: "2026-08-03T12:00:00.000Z",
  finished_at: "2026-08-07T12:00:00.000Z",
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: SOURCE,
};

const db = new Database(databasePath, { create: true });
try {
  let stores: LocalServiceStores;
  if (phase === "crash") {
    const regular = createSqliteLocalServiceStores(db);
    const folderDeletion = new SqliteFolderDeletionUnitOfWork(db, {
      afterConversationReassignment() {
        writeFileSync(markerPath, "conversation-reassigned-folder-not-deleted\n", "utf8");
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0);
      },
    });
    stores = Object.freeze({ ...regular, folderDeletion });
    stores.folders.upsert(ACCOUNT, folder(TARGET));
    stores.folders.upsert(ACCOUNT, folder(SOURCE));
    const saved = stores.conversations.upsert(ACCOUNT, conversation);
    if (!saved.stored) throw new Error("conversation seed refused");
    await stores.folderDeletion.execute({
      accountId: ACCOUNT,
      folderId: SOURCE,
      requestedTarget: TARGET,
    });
    throw new Error("delete unexpectedly escaped crash barrier");
  }

  stores = createSqliteLocalServiceStores(db);
  const sourceExists = stores.folders.hasFolder(ACCOUNT, SOURCE);
  const targetExists = stores.folders.hasFolder(ACCOUNT, TARGET);
  const storedConversation = stores.conversations.readRecord(ACCOUNT, conversation.id);
  process.stdout.write(JSON.stringify({
    sourceExists,
    targetExists,
    conversationFolderId: storedConversation?.folder_id ?? null,
    folderRows: stores.folders.listFolders(ACCOUNT).length,
    conversationRows: stores.conversations.listRecords(ACCOUNT).length,
  }));
} finally {
  db.close();
}
