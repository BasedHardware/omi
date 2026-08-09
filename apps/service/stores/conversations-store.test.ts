import { describe, expect, test } from "bun:test";

import {
  createInMemoryConversationsStore,
  type ConversationRecord,
} from "./conversations-store";

const ACCOUNT = "acct-conversations";
const FIRST_TIME = "2026-08-03T12:00:00.000Z";
const UPDATED_TIME = "2026-08-07T12:00:00.000Z";

const conversation = (overrides: Partial<ConversationRecord> = {}): ConversationRecord => ({
  id: "quiet-chat-qa",
  structured: { title: "QA bridge check", overview: "A deterministic conversation." },
  created_at: FIRST_TIME,
  updated_at: FIRST_TIME,
  started_at: FIRST_TIME,
  finished_at: UPDATED_TIME,
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: null,
  ...overrides,
});

describe("in-memory conversations store", () => {
  test("holds the decided record vocabulary and isolates accounts", () => {
    const store = createInMemoryConversationsStore();
    const saved = store.upsert(ACCOUNT, conversation());

    expect(saved.stored).toBe(true);
    expect(store.listRecords(ACCOUNT)).toEqual([conversation()]);
    expect(store.listRecords("another-account")).toEqual([]);
    expect(Object.isFrozen(store.listRecords(ACCOUNT))).toBe(true);
    expect(Object.isFrozen(store.readRecord(ACCOUNT, "quiet-chat-qa")?.structured)).toBe(true);
  });

  test("named mutations update the timestamp and bump one account revision", () => {
    const store = createInMemoryConversationsStore();
    store.upsert(ACCOUNT, conversation());

    expect(store.updateTitle(ACCOUNT, "quiet-chat-qa", "Changed", UPDATED_TIME))
      .toMatchObject({ updated: true, state_revision: 1 });
    expect(store.updateStarred(ACCOUNT, "quiet-chat-qa", true, UPDATED_TIME))
      .toMatchObject({ updated: true, state_revision: 2 });
    expect(store.updateVisibility(ACCOUNT, "quiet-chat-qa", "shared", UPDATED_TIME))
      .toMatchObject({ updated: true, state_revision: 3 });
    expect(store.readRecord(ACCOUNT, "quiet-chat-qa")).toMatchObject({
      structured: { title: "Changed" },
      starred: true,
      visibility: "shared",
      updated_at: UPDATED_TIME,
    });
    expect(store.readStateRevision(ACCOUNT)).toBe(3);
  });

  test("folder integrity is checked before either row or revision changes", () => {
    const store = createInMemoryConversationsStore({
      hasFolder: (accountId, folderId) => accountId === ACCOUNT && folderId === "work-folder-qa",
    });
    store.upsert(ACCOUNT, conversation());
    const before = store.readRecord(ACCOUNT, "quiet-chat-qa");

    expect(store.updateFolder(ACCOUNT, "quiet-chat-qa", "missing", UPDATED_TIME))
      .toEqual({ updated: false, reason: "folder_not_found" });
    expect(store.readRecord(ACCOUNT, "quiet-chat-qa")).toEqual(before);
    expect(store.readStateRevision(ACCOUNT)).toBe(0);

    expect(store.updateFolder(ACCOUNT, "quiet-chat-qa", "work-folder-qa", UPDATED_TIME))
      .toMatchObject({ updated: true, state_revision: 1 });
    expect(store.updateFolder(ACCOUNT, "quiet-chat-qa", null, UPDATED_TIME))
      .toMatchObject({ updated: true, state_revision: 2 });
    expect(store.readRecord(ACCOUNT, "quiet-chat-qa")?.folder_id).toBeNull();
  });

  test("delete bumps revision only when a row existed", () => {
    const store = createInMemoryConversationsStore();
    store.upsert(ACCOUNT, conversation());

    expect(store.deleteRecord(ACCOUNT, "quiet-chat-qa"))
      .toEqual({ deleted: true, state_revision: 1 });
    expect(store.deleteRecord(ACCOUNT, "quiet-chat-qa"))
      .toEqual({ deleted: false, reason: "not_found" });
    expect(store.readStateRevision(ACCOUNT)).toBe(1);
  });
});
