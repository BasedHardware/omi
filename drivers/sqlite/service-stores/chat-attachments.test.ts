import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
} from "../../../apps/service/app-facing";
import {
  ATTACHMENT_CONTENT_RETENTION_MS,
  ATTACHMENT_STAGING_TTL_MS,
  MAIN_CHAT_ATTACHMENT_SCOPE,
} from "../../../apps/service/chat/attachment-policy";
import type { ChatGenerationSupervisor } from "../../../apps/service/chat/generation-supervisor";
import { createInMemoryChatAdmission } from "../../../apps/service/stores/chat-admission";
import type {
  ChatAttachmentsStore,
  InMemoryChatAttachmentsStore,
} from "../../../apps/service/stores/chat-attachments-store";
import type {
  ChatMessageRecord,
  InMemoryChatMessagesStore,
} from "../../../apps/service/stores/chat-messages-store";
import type { InMemoryChatGenerationEventsStore } from "../../../apps/service/stores/chat-generation-events-store";
import type { InMemorySettingsProjectionStore } from "../../../apps/service/control/settings-projection";
import { createSqliteChatAdmission } from "./chat-admission";
import { SqliteChatAttachmentsStore } from "./chat-attachments-store";
import { SqliteChatGenerationEventsStore } from "./chat-generation-events-store";
import { SqliteChatMessagesStore } from "./chat-messages-store";
import { createSqliteLocalServiceStores } from "./index";
import { SqliteSettingsProjectionStore } from "./settings-projection";

const ACCOUNT = "attachment-sqlite-owner";
const PDF = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37, 0x0a]);

const inertSupervisor = (): ChatGenerationSupervisor => Object.freeze({
  onAdmitted: (): void => {},
  cancel: (): void => {},
  recoverInterrupted: (): void => {},
});

const stage = (store: ChatAttachmentsStore, id = "attachment-1", now = 1_000) => store.stage({
  id,
  contentReference: `${id}-content-reference`,
  accountId: ACCOUNT,
  scope: MAIN_CHAT_ATTACHMENT_SCOPE,
  displayName: "proof.pdf",
  mimeType: "application/pdf",
  content: PDF,
  stagedAt: now,
  stageExpiresAt: now + ATTACHMENT_STAGING_TTL_MS,
});

const message = (store: ChatAttachmentsStore, id = "attachment-1"): ChatMessageRecord => {
  const resolved = store.resolveForAdmission({
    accountId: ACCOUNT,
    scope: MAIN_CHAT_ATTACHMENT_SCOPE,
    attachmentIds: [id],
    messageId: "message-1",
    nowEpochMilliseconds: 1_001,
  });
  if (resolved.kind !== "ready") throw new TypeError("attachment fixture did not resolve");
  return Object.freeze({
    id: "message-1",
    text: "atomic attachment proof",
    sender: "human",
    type: "text",
    createdAt: 1_001,
    updatedAt: 1_001,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: "sha256:attachment-atomic-proof",
    messageSource: "desktop_chat",
    rating: null,
    reported: false,
    revision: "revision-1",
    attachments: resolved.attachments,
  });
};

const metered = {
  planLabel: "Metered",
  limitKey: "chat_messages",
  used: 0,
  limit: 4,
  limitReached: false,
  upgradeAvailable: true,
} as const;

const throwAfter = <Target extends object>(target: Target, method: keyof Target): Target =>
  new Proxy(Object.create(target) as Target, {
    get(_wrapper, property) {
      const value = Reflect.get(target, property, target) as unknown;
      if (typeof value !== "function") return value;
      if (property === method) {
        return (...args: unknown[]) => {
          Reflect.apply(value, target, args);
          throw new Error(`injected ${String(method)} failure`);
        };
      }
      return (...args: unknown[]) => Reflect.apply(value, target, args);
    },
  });

describe("attachment admission atomicity", () => {
  for (const failure of ["binding", "message", "quota", "dispatch"] as const) {
    test(`in-memory ${failure} failure rolls attachment, message, quota, and dispatch back`, () => {
      const stores = createInMemoryLocalServiceStores();
      stores.settings.putEntitlement(ACCOUNT, metered);
      stage(stores.chatAttachments);
      const admission = createInMemoryChatAdmission(
        (failure === "message"
          ? throwAfter(stores.chatMessages, "admitHuman")
          : stores.chatMessages) as InMemoryChatMessagesStore,
        (failure === "dispatch"
          ? throwAfter(stores.chatEvents, "append")
          : stores.chatEvents) as InMemoryChatGenerationEventsStore,
        (failure === "quota"
          ? throwAfter(stores.settings, "putEntitlement")
          : stores.settings) as InMemorySettingsProjectionStore,
        (failure === "binding"
          ? throwAfter(stores.chatAttachments, "bindToMessage")
          : stores.chatAttachments) as InMemoryChatAttachmentsStore,
      );

      expect(() => admission.admit({
        accountId: ACCOUNT,
        message: message(stores.chatAttachments),
        generationId: "generation-1",
        acceptedEventId: "accepted-1",
        admittedAt: 1_001,
        attachmentIds: ["attachment-1"],
      })).toThrow(`injected ${failure === "binding" ? "bindToMessage"
        : failure === "message" ? "admitHuman"
        : failure === "quota" ? "putEntitlement" : "append"} failure`);
      expect(stores.chatAttachments.snapshotAccount(ACCOUNT).rows?.[0]?.state).toBe("staged");
      expect(stores.chatMessages.readMessage(ACCOUNT, "message-1")).toBeNull();
      expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(0);
      expect(stores.chatEvents.listUnterminated()).toEqual([]);
    });

    test(`SQLite ${failure} failure rolls attachment, message, quota, and dispatch back`, () => {
      const db = new Database(":memory:");
      const attachments = new SqliteChatAttachmentsStore(db);
      const messages = new SqliteChatMessagesStore(db);
      const events = new SqliteChatGenerationEventsStore(db);
      const settings = new SqliteSettingsProjectionStore(db);
      settings.putEntitlement(ACCOUNT, metered);
      stage(attachments);
      const admission = createSqliteChatAdmission(
        db,
        failure === "message" ? throwAfter(messages, "admitHuman") : messages,
        failure === "dispatch" ? throwAfter(events, "append") : events,
        failure === "quota" ? throwAfter(settings, "putEntitlement") : settings,
        failure === "binding" ? throwAfter(attachments, "bindToMessage") : attachments,
      );

      expect(() => admission.admit({
        accountId: ACCOUNT,
        message: message(attachments),
        generationId: "generation-1",
        acceptedEventId: "accepted-1",
        admittedAt: 1_001,
        attachmentIds: ["attachment-1"],
      })).toThrow();
      expect((db.query(`
        SELECT attachment_state AS state FROM service_chat_attachments WHERE id = ?
      `).get("attachment-1") as { state: string }).state).toBe("staged");
      expect(messages.readMessage(ACCOUNT, "message-1")).toBeNull();
      expect(settings.readEntitlement(ACCOUNT)?.used).toBe(0);
      expect(events.listUnterminated()).toEqual([]);
      db.close();
    });
  }
});

describe("SQLite attachment retention and restart", () => {
  test("two concurrent message ids race for one staged id and exactly one binds/charges/dispatches", async () => {
    const db = new Database(":memory:");
    const stores = createSqliteLocalServiceStores(db);
    stores.settings.putEntitlement(ACCOUNT, metered);
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "sqlite-attachment-binding-race",
      chatSupervisor: inertSupervisor(),
      nowEpochMilliseconds: () => 5_000,
      attachmentId: () => "race-id",
      attachmentContentReference: () => "race-reference",
    });
    const body = new FormData();
    body.append("file", new File([PDF], "race.pdf", { type: "application/pdf" }));
    expect((await local.app.request("/v1/chat-attachments", {
      method: "POST",
      headers: { authorization: `Bearer ${local.devToken}` },
      body,
    })).status).toBe(201);
    const race = (id: string) => local.app.request("/v1/chat-messages", {
      method: "POST",
      headers: {
        authorization: `Bearer ${local.devToken}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        op: "create", opId: `op-${id}`, id, at: 5_000, text: id, sender: "human",
        journalRevision: 1, type: "text", appId: null, chatSessionId: null,
        messageSource: "desktop_chat", metadata: null, attachmentIds: ["race-id"],
      }),
    });
    const responses = await Promise.all([race("race-left"), race("race-right")]);
    expect(responses.map((response) => response.status).sort()).toEqual([201, 404]);
    expect(stores.chatMessages.readSnapshotSequence(ACCOUNT)).toBe(1);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(1);
    expect(stores.chatEvents.listUnterminated()).toHaveLength(1);
    expect((db.query(`
      SELECT attachment_state, bound_message_id FROM service_chat_attachments WHERE id = ?
    `).get("race-id") as { attachment_state: string; bound_message_id: string })).toMatchObject({
      attachment_state: "bound",
      bound_message_id: expect.stringMatching(/^race-(?:left|right)$/),
    });
    db.close();
  });

  test("QA reset removes attachment ids, metadata, ownership and content with Chat state", async () => {
    const db = new Database(":memory:");
    const stores = createSqliteLocalServiceStores(db);
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "sqlite-attachment-reset",
      chatSupervisor: inertSupervisor(),
      nowEpochMilliseconds: () => 5_000,
      attachmentId: () => "reset-id",
      attachmentContentReference: () => "reset-reference",
    });
    const body = new FormData();
    body.append("file", new File([PDF], "reset.pdf", { type: "application/pdf" }));
    expect((await local.app.request("/v1/chat-attachments", {
      method: "POST",
      headers: { authorization: `Bearer ${local.devToken}` },
      body,
    })).status).toBe(201);
    expect((db.query("SELECT COUNT(*) AS count FROM service_chat_attachments").get() as {
      count: number;
    }).count).toBe(1);

    const reset = await local.app.request("/v1/qa/reset", {
      method: "POST",
      headers: { authorization: `Bearer ${local.devToken}` },
    });
    expect(reset.status).toBe(200);
    expect((db.query("SELECT COUNT(*) AS count FROM service_chat_attachments").get() as {
      count: number;
    }).count).toBe(0);
    db.close();
  });

  test("30-day boundary clears bytes/reference transactionally and preserves durable metadata after reopen", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-chat-attachment-retention-"));
    const path = join(directory, "service.sqlite");
    const now = { value: 50_000 };
    const uploadAndSend = async (local: ReturnType<typeof createLocalDevService>): Promise<void> => {
      const body = new FormData();
      body.append("file", new File([PDF], "retained.pdf", { type: "application/pdf" }));
      const upload = await local.app.request("/v1/chat-attachments", {
        method: "POST",
        headers: { authorization: `Bearer ${local.devToken}` },
        body,
      });
      expect(upload.status).toBe(201);
      const send = await local.app.request("/v1/chat-messages", {
        method: "POST",
        headers: {
          authorization: `Bearer ${local.devToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          op: "create", opId: "op-retained", id: "retained-message", at: now.value,
          text: "retain this", sender: "human", journalRevision: 1, type: "text",
          appId: null, chatSessionId: null, messageSource: "desktop_chat", metadata: null,
          attachmentIds: ["retained-id"],
        }),
      });
      expect(send.status).toBe(201);
    };
    const history = async (local: ReturnType<typeof createLocalDevService>) => {
      const response = await local.app.request("/v1/chat-messages", {
        headers: { authorization: `Bearer ${local.devToken}` },
      });
      expect(response.status).toBe(200);
      return (await response.json()).messages[0].attachments[0] as Record<string, unknown>;
    };

    try {
      const firstDb = new Database(path, { create: true });
      const firstStores = createSqliteLocalServiceStores(firstDb);
      const first = createLocalDevService({
        db: firstDb,
        stores: firstStores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "sqlite-attachment-retention",
        chatSupervisor: inertSupervisor(),
        nowEpochMilliseconds: () => now.value,
        attachmentId: () => "retained-id",
        attachmentContentReference: () => "retained-reference",
      });
      await uploadAndSend(first);
      now.value = 50_000 + ATTACHMENT_CONTENT_RETENTION_MS - 1;
      expect((await history(first)).contentReference).toBe("retained-reference");
      expect(firstStores.chatAttachments.loadForGeneration({
        accountId: ACCOUNT,
        messageId: "retained-message",
        attachments: firstStores.chatMessages.readMessage(ACCOUNT, "retained-message")!
          .message.attachments ?? [],
        nowEpochMilliseconds: now.value,
      })[0]?.content).toEqual(PDF);
      firstDb.close();

      now.value += 1;
      const secondDb = new Database(path, { create: true });
      const secondStores = createSqliteLocalServiceStores(secondDb);
      const second = createLocalDevService({
        db: secondDb,
        stores: secondStores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "sqlite-attachment-retention",
        chatSupervisor: inertSupervisor(),
        nowEpochMilliseconds: () => now.value,
        attachmentId: () => "unused-id",
        attachmentContentReference: () => "unused-reference",
      });
      expect(await history(second)).toEqual({
        id: "retained-id",
        displayName: "retained.pdf",
        mediaType: "application/pdf",
        sizeBytes: PDF.byteLength,
        contentReference: null,
      });
      expect(secondStores.chatAttachments.loadForGeneration({
        accountId: ACCOUNT,
        messageId: "retained-message",
        attachments: secondStores.chatMessages.readMessage(ACCOUNT, "retained-message")!
          .message.attachments ?? [],
        nowEpochMilliseconds: now.value,
      })[0]?.content).toBeNull();
      expect(secondDb.query(`
        SELECT content_reference, content_bytes FROM service_chat_attachments WHERE id = ?
      `).get("retained-id")).toEqual({ content_reference: null, content_bytes: null });
      secondDb.close();
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
