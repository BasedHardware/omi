// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import type { ChatMessageRecord } from "../../../apps/service/stores/chat-messages-store";
import { createSqliteChatAdmission } from "./chat-admission";
import { createSqliteChatGenerationFinalization } from "./chat-generation-finalization";
import { SqliteChatGenerationEventsStore } from "./chat-generation-events-store";
import { SqliteChatMessagesStore } from "./chat-messages-store";
import { SqliteSettingsProjectionStore } from "./settings-projection";

const message = (overrides: Partial<ChatMessageRecord> = {}): ChatMessageRecord => ({
  id: "client-1",
  text: "hello",
  sender: "human",
  type: "text",
  createdAt: 100,
  updatedAt: 100,
  chatSessionId: null,
  appId: null,
  journalRevision: 1,
  payloadHash: "sha256:one",
  messageSource: "desktop_chat",
  rating: null,
  reported: false,
  revision: "revision-1",
  attachments: [{ displayName: "a.pdf", mediaType: "application/pdf", size: 42 }],
  ...overrides,
});

test("SQLite chat admission atomically records message, one quota use, and one accepted event", () => {
  const db = new Database(":memory:");
  const messages = new SqliteChatMessagesStore(db);
  const events = new SqliteChatGenerationEventsStore(db);
  const settings = new SqliteSettingsProjectionStore(db);
  const admission = createSqliteChatAdmission(db, messages, events, settings);
  settings.putEntitlement("account", {
    planLabel: "Metered",
    limitKey: "chat_messages",
    used: 0,
    limit: 2,
    limitReached: false,
    upgradeAvailable: true,
  });
  const input = {
    accountId: "account",
    message: message(),
    generationId: "generation-1",
    acceptedEventId: "event-1",
    admittedAt: 200,
  } as const;

  expect(admission.admit(input).kind).toBe("created");
  expect(admission.admit(input).kind).toBe("replay");
  expect(admission.admit({
    ...input,
    message: message({ text: "mutated", payloadHash: "sha256:two" }),
  }).kind).toBe("conflict");
  expect(settings.readEntitlement("account")?.used).toBe(1);
  expect(messages.readSnapshotSequence("account")).toBe(1);
  expect(messages.readMessage("account", "client-1")?.message.attachments).toEqual([
    { displayName: "a.pdf", mediaType: "application/pdf", size: 42 },
  ]);
  expect(events.listAfter("account", "generation-1", null)?.map((event) => event.frame.kind))
    .toEqual(["accepted"]);
  db.close();
});

test("SQLite refuses unknown vocabulary on write but reads restored unknown rows", () => {
  const db = new Database(":memory:");
  const messages = new SqliteChatMessagesStore(db);
  expect(messages.writeCanonical("account", message({ sender: "unknown" }), null).kind)
    .toBe("invalid_vocabulary");
  expect(messages.writeCanonical("account", message({ type: "unknown" }), null).kind)
    .toBe("invalid_vocabulary");

  db.query(`
    INSERT INTO service_chat_messages (
      account_id, id, text, sender, message_type, created_at, updated_at,
      chat_session_id, app_id, journal_revision, payload_hash, message_source,
      rating, reported, server_revision, attachments_json, generation_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    "account", "restored", "future vocabulary", "unknown", "unknown", 1, 1,
    null, null, 1, "sha256:restored", "restore", null, 0, "revision-restored", null, null,
  );
  expect(messages.readMessage("account", "restored")?.message).toMatchObject({
    sender: "unknown",
    type: "unknown",
  });
  expect(messages.listHistory("account", {
    limit: 10,
    snapshotSequence: messages.readSnapshotSequence("account"),
    olderThan: null,
  }).messages.map((stored) => stored.id)).toEqual(["restored"]);
  db.close();
});

test("SQLite preserves monotonic journal revision and the cancelled-partial event shape", () => {
  const db = new Database(":memory:");
  const messages = new SqliteChatMessagesStore(db);
  const events = new SqliteChatGenerationEventsStore(db);
  expect(messages.admitHuman("account", message({ journalRevision: 3 }), "generation-1").kind)
    .toBe("created");
  expect(messages.admitHuman("account", message({ journalRevision: 2 }), "generation-1").kind)
    .toBe("replay");
  expect(messages.readMessage("account", "client-1")?.message.journalRevision).toBe(3);
  expect(messages.admitHuman("account", message({
    journalRevision: 4,
    updatedAt: 400,
    revision: "revision-4",
  }), "generation-1").kind).toBe("replay");
  const partial = message({ id: "assistant-partial", sender: "ai", text: "partial" });
  expect(events.append({
    accountId: "account",
    generationId: "generation-1",
    eventId: "event-cancelled",
    createdAt: 500,
    frame: { kind: "cancelled", message: partial },
  }).kind).toBe("appended");
  const event = events.listAfter("account", "generation-1", null)?.[0];
  expect(event?.frame).toEqual({ kind: "cancelled", message: partial });
  db.close();
});

test("SQLite terminal append is compare-and-set and replays the winning terminal", () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-chat-terminal-cas-"));
  const path = join(directory, "service.sqlite");
  const firstDb = new Database(path);
  const secondDb = new Database(path);
  try {
    const first = new SqliteChatGenerationEventsStore(firstDb);
    const second = new SqliteChatGenerationEventsStore(secondDb);
    expect(first.append({
      accountId: "account",
      generationId: "generation-cas",
      eventId: "accepted-cas",
      createdAt: 100,
      frame: {
        kind: "accepted",
        message: message(),
        generation: { id: "generation-cas" },
      },
    }).kind).toBe("appended");
    const winning = first.append({
      accountId: "account",
      generationId: "generation-cas",
      eventId: "done-cas",
      createdAt: 200,
      frame: { kind: "done", message: message({ id: "assistant-cas", sender: "ai" }) },
    });
    const losing = second.append({
      accountId: "account",
      generationId: "generation-cas",
      eventId: "cancelled-cas",
      createdAt: 201,
      frame: { kind: "cancelled", message: null },
    });

    expect(winning.kind).toBe("appended");
    expect(losing.kind).toBe("replay");
    expect(losing.kind === "replay" ? losing.event.frame.kind : null).toBe("done");
    expect(first.listAfter("account", "generation-cas", null)?.map((event) => event.frame.kind))
      .toEqual(["accepted", "done"]);
    expect(second.readLifecycle("account", "generation-cas")?.state).toBe("terminal");
  } finally {
    secondDb.close();
    firstDb.close();
    rmSync(directory, { recursive: true, force: true });
  }
});

test("SQLite rolls canonical assistant persistence back when terminal append crashes", () => {
  const db = new Database(":memory:");
  const messages = new SqliteChatMessagesStore(db);
  const events = new SqliteChatGenerationEventsStore(db);
  const settings = new SqliteSettingsProjectionStore(db);
  expect(createSqliteChatAdmission(db, messages, events, settings).admit({
    accountId: "account",
    message: message(),
    generationId: "generation-1",
    acceptedEventId: "event-accepted",
    admittedAt: 200,
  }).kind).toBe("created");
  const assistant = message({
    id: "assistant-1",
    sender: "ai",
    text: "canonical answer",
    payloadHash: "sha256:assistant",
  });
  const crashing = createSqliteChatGenerationFinalization(db, {
    beforeTerminalAppend: () => { throw new Error("injected terminal crash"); },
  });

  expect(() => crashing.finalize({
    accountId: "account",
    generationId: "generation-1",
    eventId: "event-done",
    createdAt: 300,
    frame: { kind: "done", message: assistant },
  })).toThrow("injected terminal crash");
  expect(messages.readMessage("account", "assistant-1")).toBeNull();
  expect(events.readLifecycle("account", "generation-1")?.state).toBe("active");
  expect(events.listAfter("account", "generation-1", null)?.map((event) => event.frame.kind))
    .toEqual(["accepted"]);

  expect(createSqliteChatGenerationFinalization(db).finalize({
    accountId: "account",
    generationId: "generation-1",
    eventId: "event-done",
    createdAt: 300,
    frame: { kind: "done", message: assistant },
  }).frame).toEqual({ kind: "done", message: assistant });
  expect(messages.readMessage("account", "assistant-1")?.message).toEqual(assistant);
  expect(events.readLifecycle("account", "generation-1")?.state).toBe("terminal");
  db.close();
});

test("SQLite rolls both finalization writes back when the transaction crashes after append", () => {
  const db = new Database(":memory:");
  const messages = new SqliteChatMessagesStore(db);
  const events = new SqliteChatGenerationEventsStore(db);
  const settings = new SqliteSettingsProjectionStore(db);
  expect(createSqliteChatAdmission(db, messages, events, settings).admit({
    accountId: "account",
    message: message(),
    generationId: "generation-after-append",
    acceptedEventId: "event-after-append-accepted",
    admittedAt: 200,
  }).kind).toBe("created");
  const assistant = message({
    id: "assistant-after-append",
    sender: "ai",
    text: "must roll back",
    payloadHash: "sha256:assistant-after-append",
  });
  const crashing = createSqliteChatGenerationFinalization(db, {
    afterTerminalAppend: () => { throw new Error("injected post-append crash"); },
  });

  expect(() => crashing.finalize({
    accountId: "account",
    generationId: "generation-after-append",
    eventId: "event-after-append-done",
    createdAt: 300,
    frame: { kind: "done", message: assistant },
  })).toThrow("injected post-append crash");
  expect(messages.readMessage("account", "assistant-after-append")).toBeNull();
  expect(events.readLifecycle("account", "generation-after-append")?.state).toBe("active");
  expect(events.listAfter("account", "generation-after-append", null)?.map(
    (event) => event.frame.kind,
  )).toEqual(["accepted"]);
  db.close();
});

test("SQLite chat message, quota, and event records survive adapter restart", () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-chat-restart-"));
  const path = join(directory, "service.sqlite");
  try {
    {
      const db = new Database(path);
      const messages = new SqliteChatMessagesStore(db);
      const events = new SqliteChatGenerationEventsStore(db);
      const settings = new SqliteSettingsProjectionStore(db);
      settings.putEntitlement("account", {
        planLabel: "Metered",
        limitKey: "chat_messages",
        used: 0,
        limit: 5,
        limitReached: false,
        upgradeAvailable: true,
      });
      expect(createSqliteChatAdmission(db, messages, events, settings).admit({
        accountId: "account",
        message: message(),
        generationId: "generation-1",
        acceptedEventId: "event-1",
        admittedAt: 200,
      }).kind).toBe("created");
      db.close();
    }
    {
      const db = new Database(path);
      const messages = new SqliteChatMessagesStore(db);
      const events = new SqliteChatGenerationEventsStore(db);
      const settings = new SqliteSettingsProjectionStore(db);
      expect(messages.readMessage("account", "client-1")?.message.attachments).toEqual([
        { displayName: "a.pdf", mediaType: "application/pdf", size: 42 },
      ]);
      expect(settings.readEntitlement("account")?.used).toBe(1);
      expect(events.listAfter("account", "generation-1", null)?.map((event) => event.id))
        .toEqual(["event-1"]);
      db.close();
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
