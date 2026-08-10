import { mkdirSync } from "node:fs";
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import type { ConversationRecord } from "../../../apps/service/stores/conversations-store";
import type { FolderRecord } from "../../../apps/service/stores/folders-store";
import { createSqliteLocalServiceStores } from "./index";

const ACCOUNT = "acct-folders-sqlite";
const CREATED = "2026-08-03T12:00:00.000Z";
const UPDATED = "2026-08-07T12:00:00.000Z";
const scratch = `/tmp/folders-store-${process.pid}`;
mkdirSync(scratch, { recursive: true });
let number = 0;

const folder = (id: string, overrides: Partial<FolderRecord> = {}): FolderRecord => ({
  id,
  name: id,
  description: null,
  color: "#6B7280",
  icon: "folder",
  created_at: CREATED,
  updated_at: CREATED,
  order: 0,
  is_default: false,
  is_system: false,
  ...overrides,
});

const conversation = (id: string, folderId: string): ConversationRecord => ({
  id,
  structured: { title: id, overview: "SQLite folder reassignment proof" },
  created_at: CREATED,
  updated_at: CREATED,
  started_at: CREATED,
  finished_at: UPDATED,
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: folderId,
});

describe("SQLite folders store", () => {
  test("deleting a folder reassigns persisted conversation rows", () => {
    const path = `${scratch}/${++number}.sqlite`;
    const db = new Database(path, { create: true });
    const stores = createSqliteLocalServiceStores(db);
    stores.folders.upsert(ACCOUNT, folder("default", { is_default: true, is_system: true }));
    stores.folders.upsert(ACCOUNT, folder("work", { order: 1 }));
    expect(stores.conversations.upsert(ACCOUNT, conversation("c-1", "work")).stored).toBe(true);
    expect(stores.conversations.upsert(ACCOUNT, conversation("c-2", "work")).stored).toBe(true);

    expect(stores.folders.deleteFolder(ACCOUNT, "work", null))
      .toEqual({ deleted: true, moved_to_folder_id: "default" });
    expect(stores.conversations.listRecords(ACCOUNT).map((record) => ({
      id: record.id,
      folder_id: record.folder_id,
    }))).toEqual([
      { id: "c-1", folder_id: "default" },
      { id: "c-2", folder_id: "default" },
    ]);
    db.close();
  });
});
