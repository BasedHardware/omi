// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  createInMemoryLocalServiceStores,
  createLocalService,
  type LocalServiceStores,
} from "../app-facing";
import type { ChatGenerationSupervisor } from "../chat/generation-supervisor";
import { createInMemoryChatAdmission } from "../stores/chat-admission";
import { createInMemoryChatGenerationEventsStore } from "../stores/chat-generation-events-store";
import {
  createInMemoryChatMessagesStore,
  type ChatMessageRecord,
} from "../stores/chat-messages-store";
import {
  createSqliteLocalServiceStores,
  SqliteChatMessagesStore,
} from "../../../drivers/sqlite/service-stores";

const ACCOUNT = "chat-account";
const AUTHORIZATION = (token: string): HeadersInit => ({ authorization: `Bearer ${token}` });

const payload = (
  id: string,
  at: number,
  overrides: Readonly<Record<string, unknown>> = {},
): Readonly<Record<string, unknown>> => Object.freeze({
  op: "create",
  opId: `op-${id}`,
  id,
  at,
  text: `message ${id}`,
  sender: "human",
  journalRevision: 1,
  type: "text",
  appId: null,
  chatSessionId: null,
  messageSource: "desktop_chat",
  metadata: null,
  attachmentIds: [],
  ...overrides,
});

const post = (local: ReturnType<typeof createLocalService>, body: unknown): Promise<Response> =>
  Promise.resolve(local.app.request("/v1/chat-messages", {
    method: "POST",
    headers: { ...AUTHORIZATION(local.devToken), "content-type": "application/json" },
    body: JSON.stringify(body),
  }));

const bootInMemory = (
  stores: LocalServiceStores = createInMemoryLocalServiceStores(),
  chatSupervisor?: ChatGenerationSupervisor,
) => {
  const db = new Database(":memory:");
  const local = createLocalService({
    db,
    stores,
    ownerAccountId: ACCOUNT,
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel: "chat-route-proof",
    chatSupervisor,
  });
  return { db, local, stores };
};

describe("ratified /v1/chat-messages route", () => {
  test("idempotent replay stores once, consumes quota once, and payload mutation conflicts", async () => {
    const stores = createInMemoryLocalServiceStores();
    stores.settings.putEntitlement(ACCOUNT, {
      planLabel: "Metered",
      limitKey: "chat_messages",
      used: 0,
      limit: 3,
      limitReached: false,
      upgradeAvailable: true,
    });
    let supervisorAdmissions = 0;
    const { db, local } = bootInMemory(stores, {
      onAdmitted: () => { supervisorAdmissions += 1; },
    });
    const request = payload("client-01", 1_786_352_400_000);

    const first = await post(local, request);
    const replay = await post(local, request);
    const mutated = await post(local, { ...request, text: "mutated payload" });

    expect(first.status).toBe(201);
    expect(replay.status).toBe(200);
    expect(await replay.json()).toEqual(await first.json());
    expect(mutated.status).toBe(409);
    expect(await mutated.json()).toEqual({
      error: {
        code: "client_message_id_conflict",
        retryable: false,
        action: "edit_request",
      },
    });
    expect(stores.chatMessages.readSnapshotSequence(ACCOUNT)).toBe(1);
    const admitted = stores.chatMessages.readMessage(ACCOUNT, "client-01")!;
    expect(stores.chatEvents.listAfter(ACCOUNT, admitted.generationId!, null)).toHaveLength(1);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(1);
    expect(supervisorAdmissions).toBe(1);
    db.close();
  });

  test("SQLite keyset chain is duplicate-free and gap-free across an explicit concurrent insert", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-chat-keyset-"));
    const path = join(directory, "service.sqlite");
    const primary = new Database(path);
    const secondary = new Database(path);
    try {
      const stores = createSqliteLocalServiceStores(primary);
      const local = createLocalService({
        db: primary,
        stores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "chat-sqlite-keyset-proof",
      });
      for (const [id, at] of [["m1", 1_000], ["m2", 2_000], ["m3", 3_000], ["m4", 4_000]] as const) {
        expect((await post(local, payload(id, at))).status).toBe(201);
      }

      const first = await local.app.request("/v1/chat-messages?limit=2", {
        headers: AUTHORIZATION(local.devToken),
      });
      expect(first.status).toBe(200);
      const firstPage = await first.json() as {
        messages: ChatMessageRecord[];
        page: { olderCursor: string; hasOlder: boolean };
      };
      expect(firstPage.messages.map((message) => message.id)).toEqual(["m3", "m4"]);

      // The other WAL connection writes a backdated row after page 1 and before page 2.
      // Its ordering key lands between the two pages, but its insertion sequence is above
      // page 1's signed snapshot ceiling.
      const concurrent = new SqliteChatMessagesStore(secondary);
      expect(concurrent.writeCanonical(ACCOUNT, {
        id: "m-between",
        text: "concurrent",
        sender: "human",
        type: "text",
        createdAt: 2_500,
        updatedAt: 2_500,
        chatSessionId: null,
        appId: null,
        journalRevision: 1,
        payloadHash: "sha256:concurrent",
        messageSource: "desktop_chat",
        rating: null,
        reported: false,
        revision: "revision-concurrent",
      }, "generation-concurrent").kind).toBe("created");

      const secondUrl =
        `/v1/chat-messages?limit=2&olderCursor=${encodeURIComponent(firstPage.page.olderCursor)}`;
      const second = await local.app.request(
        secondUrl,
        { headers: AUTHORIZATION(local.devToken) },
      );
      expect(second.status).toBe(200);
      const secondPage = await second.json() as {
        messages: ChatMessageRecord[];
        page: { olderCursor: null; hasOlder: boolean };
      };
      expect(secondPage.messages.map((message) => message.id)).toEqual(["m1", "m2"]);
      expect(secondPage.page).toEqual({ olderCursor: null, hasOlder: false });
      const replayedSecond = await local.app.request(secondUrl, {
        headers: AUTHORIZATION(local.devToken),
      });
      expect(await replayedSecond.json()).toEqual(secondPage);
      const walked = [...firstPage.messages, ...secondPage.messages].map((message) => message.id);
      expect(new Set(walked).size).toBe(4);
      expect([...walked].sort()).toEqual(["m1", "m2", "m3", "m4"]);

      const refreshed = await local.app.request("/v1/chat-messages?limit=100", {
        headers: AUTHORIZATION(local.devToken),
      });
      const refreshedPage = await refreshed.json() as { messages: ChatMessageRecord[] };
      expect(refreshedPage.messages.map((message) => message.id)).toEqual([
        "m1", "m2", "m-between", "m3", "m4",
      ]);
    } finally {
      secondary.close();
      primary.close();
      rmSync(directory, { recursive: true, force: true });
    }
  });

  test("unknown sender/type are refused on write and retained on tolerant history read", async () => {
    const base = createInMemoryLocalServiceStores();
    const messages = createInMemoryChatMessagesStore([{
      accountId: ACCOUNT,
      stored: {
        generationId: null,
        message: {
          id: "future-vocabulary",
          text: "retained without false attribution",
          sender: "unknown",
          type: "unknown",
          createdAt: 10,
          updatedAt: 10,
          chatSessionId: null,
          appId: null,
          journalRevision: 1,
          payloadHash: "sha256:restored",
          messageSource: "restored",
          rating: null,
          reported: false,
          revision: "restored-revision",
        },
      },
    }]);
    const events = createInMemoryChatGenerationEventsStore();
    const stores: LocalServiceStores = {
      ...base,
      chatMessages: messages,
      chatEvents: events,
      chatAdmission: createInMemoryChatAdmission(messages, events, base.settings),
    };
    const { db, local } = bootInMemory(stores);

    expect((await post(local, payload("bad-sender", 20, { sender: "unknown" }))).status).toBe(422);
    expect((await post(local, payload("bad-type", 30, { type: "unknown" }))).status).toBe(422);
    const history = await local.app.request("/v1/chat-messages", {
      headers: AUTHORIZATION(local.devToken),
    });
    expect(history.status).toBe(200);
    const body = await history.json() as { messages: ChatMessageRecord[] };
    expect(body.messages).toHaveLength(1);
    expect(body.messages[0]).toMatchObject({
      id: "future-vocabulary",
      sender: "unknown",
      type: "unknown",
    });
    db.close();
  });

  test("the shared Settings entitlement projection moves chat admission", async () => {
    const stores = createInMemoryLocalServiceStores();
    stores.settings.putEntitlement(ACCOUNT, {
      planLabel: "One send",
      limitKey: "chat_messages",
      used: 0,
      limit: 1,
      limitReached: false,
      upgradeAvailable: true,
    });
    const { db, local } = bootInMemory(stores);

    expect((await post(local, payload("quota-1", 100))).status).toBe(201);
    const exhausted = await post(local, payload("quota-2", 200));
    expect(exhausted.status).toBe(402);
    expect(await exhausted.json()).toEqual({
      error: { code: "entitlement", retryable: false, action: "upgrade" },
    });
    expect(stores.chatMessages.readMessage(ACCOUNT, "quota-2")).toBeNull();

    const sameProjection = stores.settings.readEntitlement(ACCOUNT)!;
    stores.settings.putEntitlement(ACCOUNT, {
      ...sameProjection,
      limit: 2,
      limitReached: false,
    });
    expect((await post(local, payload("quota-2", 200))).status).toBe(201);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(2);
    db.close();
  });

  test("attachment metadata round-trips while advertised attachment support stays off", async () => {
    const { db, local } = bootInMemory();
    const attachments = [{
      displayName: "meeting-notes.pdf",
      mediaType: "application/pdf",
      size: 12_345,
    }];
    const admitted = await post(local, payload("with-metadata", 500, { attachments }));
    expect(admitted.status).toBe(201);
    expect((await admitted.json() as { message: ChatMessageRecord }).message.attachments)
      .toEqual(attachments);

    const history = await local.app.request("/v1/chat-messages", {
      headers: AUTHORIZATION(local.devToken),
    });
    expect(history.status).toBe(200);
    const body = await history.json() as {
      messages: ChatMessageRecord[];
      capabilities: {
        maxAttachmentsPerMessage: number;
        maxAttachmentBytes: number;
        allowedAttachmentMimeTypes: string[];
      };
    };
    expect(body.messages[0]?.attachments).toEqual(attachments);
    expect(body.capabilities).toEqual({
      maxAttachmentsPerMessage: 0,
      maxAttachmentBytes: 0,
      allowedAttachmentMimeTypes: [],
    });
    db.close();
  });
});
