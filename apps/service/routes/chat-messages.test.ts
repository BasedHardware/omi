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
  createLocalDevService,
  type LocalServiceStores,
} from "../app-facing";
import type { ChatGenerationSupervisor } from "../chat/generation-supervisor";
import { createInMemoryChatAdmission } from "../stores/chat-admission";
import { createInMemoryChatGenerationEventsStore } from "../stores/chat-generation-events-store";
import {
  createInMemoryChatMessagesStore,
  type ChatMessageRecord,
} from "../stores/chat-messages-store";
import type { InMemorySettingsProjectionStore } from "../control/settings-projection";
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

const post = (local: ReturnType<typeof createLocalDevService>, body: unknown): Promise<Response> =>
  Promise.resolve(local.app.request("/v1/chat-messages", {
    method: "POST",
    headers: { ...AUTHORIZATION(local.devToken), "content-type": "application/json" },
    body: JSON.stringify(body),
  }));

const inertSupervisor = (): ChatGenerationSupervisor => Object.freeze({
  onAdmitted: (): void => {},
  cancel: (): void => {},
  recoverInterrupted: (): void => {},
});

const admissionBody = async (response: Response): Promise<{
  readonly message: ChatMessageRecord;
  readonly generation: { readonly id: string };
}> => await response.json() as {
  readonly message: ChatMessageRecord;
  readonly generation: { readonly id: string };
};

const bootInMemory = (
  stores: LocalServiceStores = createInMemoryLocalServiceStores(),
  chatSupervisor?: ChatGenerationSupervisor,
) => {
  const db = new Database(":memory:");
  const local = createLocalDevService({
    db,
    stores,
    ownerAccountId: ACCOUNT,
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel: "chat-route-proof",
    chatSupervisor: chatSupervisor ?? inertSupervisor(),
  });
  return { db, local, stores };
};

describe("ratified /v1/chat-messages route", () => {
  test("POST admission is finite JSON with the canonical human message and generation id", async () => {
    const { db, local } = bootInMemory();
    const admitted = await post(local, payload("json-admission", 1_786_352_400_000));

    expect(admitted.status).toBe(201);
    expect(admitted.headers.get("content-type")).toContain("application/json");
    expect(await admitted.json()).toEqual({
      message: expect.objectContaining({
        id: "json-admission",
        text: "message json-admission",
        sender: "human",
      }),
      generation: { id: expect.any(String) },
    });
    db.close();
  });

  test("in-memory admission rolls message, quota, and event back when quota persistence crashes", async () => {
    const base = createInMemoryLocalServiceStores();
    base.settings.putEntitlement(ACCOUNT, {
      planLabel: "Metered",
      limitKey: "chat_messages",
      used: 0,
      limit: 3,
      limitReached: false,
      upgradeAvailable: true,
    });
    let quotaWrites = 0;
    const crashingSettings: InMemorySettingsProjectionStore = Object.freeze({
      putIdentity: base.settings.putIdentity,
      putEntitlement(): void {
        quotaWrites += 1;
        throw new Error("injected quota crash");
      },
      readEntitlement: base.settings.readEntitlement,
      consumeTranscriptionSeconds: base.settings.consumeTranscriptionSeconds,
      readSettings: base.settings.readSettings,
      snapshotAccount: base.settings.snapshotAccount,
      restoreAccount: base.settings.restoreAccount,
      reset: base.settings.reset,
    });
    const stores: LocalServiceStores = Object.freeze({
      ...base,
      settings: crashingSettings,
      chatAdmission: createInMemoryChatAdmission(
        base.chatMessages,
        base.chatEvents,
        crashingSettings,
        base.chatAttachments,
      ),
    });
    const { db, local } = bootInMemory(stores);

    const admitted = await post(local, payload("atomic-crash", 1_000));

    expect(admitted.status).toBe(503);
    expect(quotaWrites).toBe(1);
    expect(base.chatMessages.readMessage(ACCOUNT, "atomic-crash")).toBeNull();
    expect(base.settings.readEntitlement(ACCOUNT)?.used).toBe(0);
    expect(base.chatEvents.listUnterminated()).toEqual([]);
    db.close();
  });

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
    const supervisorGenerations = new Set<string>();
    const { db, local } = bootInMemory(stores, {
      onAdmitted: (input) => {
        supervisorAdmissions += 1;
        supervisorGenerations.add(input.acceptedEvent.generationId);
      },
      cancel: (): void => {},
      recoverInterrupted: (): void => {},
    });
    const request = payload("client-01", 1_786_352_400_000);

    const first = await post(local, request);
    const replay = await post(local, request);
    const mutated = await post(local, { ...request, text: "mutated payload" });

    expect(first.status).toBe(201);
    expect(replay.status).toBe(200);
    expect(await admissionBody(replay)).toEqual(await admissionBody(first));
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
    expect(supervisorAdmissions).toBe(2);
    expect(supervisorGenerations.size).toBe(1);
    db.close();
  });

  test("SQLite keyset chain is duplicate-free and gap-free across an explicit concurrent insert", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-chat-keyset-"));
    const path = join(directory, "service.sqlite");
    const primary = new Database(path);
    const secondary = new Database(path);
    try {
      const stores = createSqliteLocalServiceStores(primary);
      const local = createLocalDevService({
        db: primary,
        stores,
        ownerAccountId: ACCOUNT,
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: "chat-sqlite-keyset-proof",
        chatSupervisor: inertSupervisor(),
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

  test("history cursor minted before an account epoch advance is refused", async () => {
    const stores = createInMemoryLocalServiceStores();
    const { db, local } = bootInMemory(stores);
    for (const [id, at] of [["epoch-1", 1_000], ["epoch-2", 2_000], ["epoch-3", 3_000]] as const) {
      const admitted = await post(local, payload(id, at));
      expect(admitted.status).toBe(201);
      await admitted.body?.cancel();
    }
    expect(stores.control.observe({
      account_id: ACCOUNT,
      control_revision: 1,
      account_generation: "legacy",
      account_epoch: null,
      lifecycle_state: "active",
      deletion_epoch: null,
    }).accepted).toBe(true);
    expect(stores.control.observe({
      account_id: ACCOUNT,
      control_revision: 2,
      account_generation: "migrating",
      account_epoch: null,
      lifecycle_state: "active",
      deletion_epoch: null,
    }).accepted).toBe(true);
    expect(stores.control.observe({
      account_id: ACCOUNT,
      control_revision: 3,
      account_generation: "new",
      account_epoch: 7,
      lifecycle_state: "active",
      deletion_epoch: null,
    }).accepted).toBe(true);
    expect(stores.control.activate(ACCOUNT, { epoch: 7, at_control_revision: 3 }).activated)
      .toBe(true);

    const first = await local.app.request("/v1/chat-messages?limit=1", {
      headers: AUTHORIZATION(local.devToken),
    });
    expect(first.status).toBe(200);
    const firstPage = await first.json() as {
      page: { olderCursor: string; hasOlder: boolean };
    };
    expect(firstPage.page.hasOlder).toBe(true);
    const cursorUrl =
      `/v1/chat-messages?limit=1&olderCursor=${encodeURIComponent(firstPage.page.olderCursor)}`;
    expect((await local.app.request(cursorUrl, {
      headers: AUTHORIZATION(local.devToken),
    })).status).toBe(200);

    expect(stores.control.observe({
      account_id: ACCOUNT,
      control_revision: 4,
      account_generation: "new",
      account_epoch: 8,
      lifecycle_state: "active",
      deletion_epoch: null,
    }).accepted).toBe(true);
    expect(stores.control.activate(ACCOUNT, { epoch: 8, at_control_revision: 4 }).activated)
      .toBe(true);
    const stale = await local.app.request(cursorUrl, {
      headers: AUTHORIZATION(local.devToken),
    });

    expect(stale.status).toBe(400);
    expect(await stale.json()).toEqual({
      error: { code: "bad_request", retryable: false, action: "refresh_history" },
    });
    db.close();
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
      chatAdmission: createInMemoryChatAdmission(
        messages,
        events,
        base.settings,
        base.chatAttachments,
      ),
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

  test("SQLite migrates closed vocabulary and serves future sender/type spellings intact", async () => {
    const db = new Database(":memory:");
    db.exec(`
      CREATE TABLE service_chat_messages (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        id TEXT NOT NULL,
        text TEXT NOT NULL,
        sender TEXT NOT NULL CHECK (sender IN ('human', 'ai', 'unknown')),
        message_type TEXT NOT NULL CHECK (message_type IN ('text', 'day_summary', 'unknown')),
        created_at INTEGER NOT NULL CHECK (created_at >= 0),
        updated_at INTEGER NOT NULL CHECK (updated_at >= 0),
        chat_session_id TEXT,
        app_id TEXT,
        journal_revision INTEGER NOT NULL CHECK (journal_revision >= 0),
        payload_hash TEXT NOT NULL,
        message_source TEXT NOT NULL,
        rating REAL,
        reported INTEGER NOT NULL CHECK (reported IN (0, 1)),
        server_revision TEXT,
        attachments_json TEXT,
        generation_id TEXT,
        UNIQUE (account_id, id)
      );
      CREATE INDEX service_chat_messages_history
        ON service_chat_messages (
          account_id, app_id, chat_session_id, created_at DESC, id DESC, sequence
        );
    `);
    const stores = createSqliteLocalServiceStores(db);
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "chat-sqlite-future-vocabulary-proof",
      chatSupervisor: inertSupervisor(),
    });
    db.exec("PRAGMA ignore_check_constraints = ON;");
    db.query(`
      INSERT INTO service_chat_messages (
        account_id, id, text, sender, message_type, created_at, updated_at,
        chat_session_id, app_id, journal_revision, payload_hash, message_source,
        rating, reported, server_revision, attachments_json, generation_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      ACCOUNT, "future-sqlite", "future vocabulary", "future_model", "future_kind", 10, 10,
      null, null, 1, "sha256:future", "restore", null, 0, "revision-future", null, null,
    );
    db.exec("PRAGMA ignore_check_constraints = OFF;");

    const history = await local.app.request("/v1/chat-messages", {
      headers: AUTHORIZATION(local.devToken),
    });

    expect(history.status).toBe(200);
    const body = await history.json() as { messages: ChatMessageRecord[] };
    expect(body.messages[0]).toMatchObject({
      id: "future-sqlite",
      sender: "future_model",
      type: "future_kind",
    });
    const schema = db.query(`
      SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'service_chat_messages'
    `).get() as { readonly sql: string };
    expect(schema.sql).not.toContain("sender IN");
    expect(schema.sql).not.toContain("message_type IN");
    expect(stores.chatMessages.writeCanonical(ACCOUNT, {
      ...body.messages[0]!,
      id: "future-write",
      payloadHash: "sha256:future-write",
    }, null).kind).toBe("invalid_vocabulary");
    expect((await post(local, payload("future-sender-write", 20, {
      sender: "future_model",
    }))).status).toBe(422);
    expect((await post(local, payload("future-type-write", 30, {
      type: "future_kind",
    }))).status).toBe(422);
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

  test("caller-authored attachment metadata is rejected and capabilities advertise enforced policy", async () => {
    const { db, local } = bootInMemory();
    const attachments = [{
      displayName: "meeting-notes.pdf",
      mediaType: "application/pdf",
      size: 12_345,
    }];
    const admitted = await post(local, payload("with-metadata", 500, { attachments }));
    expect(admitted.status).toBe(422);

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
    expect(body.messages).toEqual([]);
    expect(body.capabilities).toEqual({
      maxAttachmentsPerMessage: 4,
      maxAttachmentBytes: 50 * 1024 * 1024,
      allowedAttachmentMimeTypes: [
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf", "text/plain", "text/markdown",
      ],
    });
    db.close();
  });

  test("an unknown attachment id is not-found before message, event, or quota writes", async () => {
    const stores = createInMemoryLocalServiceStores();
    stores.settings.putEntitlement(ACCOUNT, {
      planLabel: "Metered",
      limitKey: "chat_messages",
      used: 0,
      limit: 3,
      limitReached: false,
      upgradeAvailable: true,
    });
    const { db, local } = bootInMemory(stores);

    const rejected = await post(local, payload("opaque-attachment", 600, {
      attachmentIds: ["opaque-attachment"],
    }));

    expect(rejected.status).toBe(404);
    expect(await rejected.json()).toEqual({
      error: { code: "not_found", retryable: false, action: "edit_request" },
    });
    expect(stores.chatMessages.readSnapshotSequence(ACCOUNT)).toBe(0);
    expect(stores.chatEvents.listUnterminated()).toEqual([]);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(0);

    const empty = await post(local, payload("empty-attachments", 700));
    const absentBody = { ...payload("absent-attachments", 800) };
    delete (absentBody as { attachmentIds?: unknown }).attachmentIds;
    const absent = await post(local, absentBody);
    expect([empty.status, absent.status]).toEqual([201, 201]);
    expect(stores.chatMessages.readSnapshotSequence(ACCOUNT)).toBe(2);
    expect(stores.settings.readEntitlement(ACCOUNT)?.used).toBe(2);
    await empty.body?.cancel();
    await absent.body?.cancel();
    db.close();
  });
});
