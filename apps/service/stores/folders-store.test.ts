import { describe, expect, test } from "bun:test";

import { createInMemoryConversationsStore, type ConversationRecord } from "./conversations-store";
import { createInMemoryFolderDeletionUnitOfWork } from "./folder-deletion-unit-of-work";
import { createInMemoryFoldersStore, type FolderRecord } from "./folders-store";

const ACCOUNT = "acct-folders";
const CREATED = "2026-08-03T12:00:00.000Z";
const UPDATED = "2026-08-07T12:00:00.000Z";

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
  structured: { title: id, overview: "folder reassignment proof" },
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

const stores = () => {
  const folders = createInMemoryFoldersStore();
  const conversations = createInMemoryConversationsStore({
    hasFolder: (accountId, folderId) => folders.hasFolder(accountId, folderId),
  });
  return {
    folders,
    conversations,
    folderDeletion: createInMemoryFolderDeletionUnitOfWork(folders, conversations),
  };
};

describe("in-memory folders store", () => {
  test("is the one folder-existence lookup used by conversations", () => {
    const { folders, conversations } = stores();
    expect(conversations.upsert(ACCOUNT, conversation("c-1", "missing")))
      .toEqual({ stored: false, reason: "folder_not_found" });
    folders.upsert(ACCOUNT, folder("work"));
    expect(conversations.upsert(ACCOUNT, conversation("c-1", "work")).stored).toBe(true);
  });

  test("creates in insertion order and patches only the provided values", () => {
    const { folders } = stores();
    folders.upsert(ACCOUNT, folder("default", { is_default: true, is_system: true }));
    const created = folders.createFolder(ACCOUNT, {
      id: "created",
      name: "Created",
      description: null,
      color: "#6B7280",
      icon: "folder",
      created_at: CREATED,
      updated_at: CREATED,
    });
    expect(created).toMatchObject({ created: true, record: { order: 1 } });
    expect(folders.patchFolder(ACCOUNT, "created", { name: null, order: "last" }, UPDATED))
      .toMatchObject({ updated: true, record: { name: null, order: "last", updated_at: UPDATED } });
  });

  test("delete validates system, self, and unknown targets before mutation", async () => {
    const { folders, folderDeletion } = stores();
    folders.upsert(ACCOUNT, folder("system", { is_system: true }));
    folders.upsert(ACCOUNT, folder("work"));
    expect(await folderDeletion.execute({
      accountId: ACCOUNT, folderId: "system", requestedTarget: null,
    }))
      .toEqual({ deleted: false, reason: "system_folder" });
    expect(await folderDeletion.execute({
      accountId: ACCOUNT, folderId: "work", requestedTarget: "work",
    }))
      .toEqual({ deleted: false, reason: "self_move" });
    expect(await folderDeletion.execute({
      accountId: ACCOUNT, folderId: "work", requestedTarget: "missing",
    }))
      .toEqual({ deleted: false, reason: "target_not_found" });
    expect(folders.hasFolder(ACCOUNT, "work")).toBe(true);
  });
});
