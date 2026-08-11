// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";

import { createLocalDevService } from "./app-facing";
import { createSqliteLocalServiceStores } from "../../drivers/sqlite/service-stores";

const OWNER = "sqlite-reset-owner";
const OTHER_OWNER = "sqlite-reset-other-owner";
const OTHER_TOKEN = "synthetic-other-token";
const NOW = "2026-08-07T12:00:00.000Z";

test("explicit QA reset restores every externally supplied SQLite store family", async () => {
  const db = new Database(":memory:");
  const stores = createSqliteLocalServiceStores(db);
  const service = createLocalDevService({
    db,
    stores,
    persistentQaStores: true,
    ownerAccountId: OWNER,
    memoryCount: 2,
    accountTimezone: "UTC",
    devSecretLabel: "sqlite-total-reset-proof",
    listenDefaultUnmetered: true,
    chatSupervisor: Object.freeze({
      onAdmitted: (): void => {},
      cancel: (): void => {},
      recoverInterrupted: (): void => {},
    }),
  });

  stores.folders.upsert(OWNER, {
    id: "extra-folder",
    name: "Extra",
    description: null,
    color: null,
    icon: null,
    created_at: NOW,
    updated_at: NOW,
    order: 9,
    is_default: false,
    is_system: false,
  });
  expect(stores.conversations.upsert(OWNER, {
    id: "extra-conversation",
    structured: { title: "Synthetic", overview: "Reset proof" },
    created_at: NOW,
    updated_at: NOW,
    started_at: NOW,
    finished_at: NOW,
    source: "omi",
    status: "completed",
    discarded: false,
    starred: false,
    visibility: "private",
    is_locked: false,
    folder_id: "extra-folder",
  }).stored).toBeTrue();
  const task = stores.tasks.apply(OWNER, {
    op: "create",
    record_id: "extra-task",
    content: { title: "synthetic" },
  });
  expect(task.applied).toBeTrue();
  stores.registry.record({
    accountId: OWNER,
    writeId: "a".repeat(64),
    fingerprintOf: { op: "synthetic" },
    accountEpoch: 7,
    outcome: { record_id: "extra-task", revision: task.revision },
  });
  stores.stragglers.preserve(OWNER, {
    envelope_json: "{}",
    write_id: "b".repeat(64),
    account_epoch: 6,
    retained_at_epoch_seconds: 1,
  });
  expect(stores.control.observe({
    account_id: OWNER,
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
  }).accepted).toBeTrue();
  stores.settings.putIdentity(OWNER, { displayName: "Changed", email: "changed@example.invalid" });
  expect(stores.settings.consumeTranscriptionSeconds(OWNER, 3)?.used).toBe(3);
  stores.listen.openOrResume({
    accountId: OWNER,
    id: "listen-reset-session",
    conversationId: "listen-reset-session",
    clientConversationId: null,
    at: NOW,
    source: "synthetic",
    codec: "pcm16",
    sampleRate: 16_000,
    channels: 1,
  });
  stores.chatAttachments.stage({
    id: "attachment-reset",
    contentReference: "content-reset",
    accountId: OWNER,
    scope: "main-chat",
    displayName: "synthetic.txt",
    mimeType: "text/plain",
    content: new TextEncoder().encode("synthetic"),
    stagedAt: 1,
    stageExpiresAt: 10_000,
  });

  const chat = await service.app.request("/v1/chat-messages", {
    method: "POST",
    headers: {
      authorization: `Bearer ${service.devToken}`,
      "content-type": "application/json",
      "x-omi-client-id": "run-reset-proof::macos",
    },
    body: JSON.stringify({
      op: "create",
      opId: "op-reset-chat",
      id: "reset-chat",
      at: 1_786_352_400_000,
      text: "synthetic",
      sender: "human",
      journalRevision: 1,
      type: "text",
      appId: null,
      chatSessionId: null,
      messageSource: "desktop_chat",
      metadata: null,
      attachmentIds: [],
    }),
  });
  expect(chat.status).toBe(201);
  expect(stores.currentSession.revoke(OTHER_TOKEN, () => ({ uid: OTHER_OWNER })).status)
    .toBe("revoked");
  stores.accountLifecycle.setLifecycle(OTHER_OWNER, "deleted");

  const reset = await service.app.request("/v1/qa/reset", {
    method: "POST",
    headers: { authorization: `Bearer ${service.devToken}` },
  });
  expect(reset.status).toBe(200);

  expect(stores.folders.listFolders(OWNER).map((folder) => folder.id))
    .toEqual(["default-folder-qa", "work-folder-qa"]);
  expect(stores.conversations.listRecords(OWNER).map((conversation) => conversation.id))
    .toEqual(["quiet-chat-qa"]);
  expect(stores.tasks.listRecords(OWNER)).toEqual([]);
  expect(stores.registry.size(OWNER)).toBe(0);
  expect(stores.stragglers.exportAccount(OWNER)).toEqual([]);
  expect(stores.control.read(OWNER)).toBeNull();
  expect(stores.settings.readSettings(OWNER)).toEqual({
    status: "available",
    snapshot: {
      identity: { displayName: OWNER, email: "" },
      entitlement: {
        planLabel: "Omi Plus",
        limitKey: "transcription_seconds",
        used: 0,
        limit: null,
        limitReached: false,
        upgradeAvailable: false,
      },
    },
  });
  expect(stores.currentSession.authenticate(OTHER_TOKEN, () => ({ uid: OTHER_OWNER })))
    .toEqual({ uid: OTHER_OWNER });
  expect(stores.accountLifecycle.readLifecycle(OWNER)).toBe("active");
  expect(stores.accountLifecycle.readLifecycle(OTHER_OWNER)).toBeNull();
  expect(stores.listen.readSession(OWNER, "listen-reset-session")).toBeNull();
  expect(stores.chatMessages.readMessage(OWNER, "reset-chat")).toBeNull();
  expect(stores.chatEvents.listUnterminated()).toEqual([]);
  expect((db.query("SELECT count(*) AS count FROM service_chat_attachments").get() as {
    readonly count: number;
  }).count).toBe(0);
  expect(service.evidence.snapshot("run-reset-proof").rows.every((evidenceRow) =>
    (evidenceRow.http?.successful ?? 0) === 0
    && (evidenceRow.chat?.acceptedAdmission ?? 0) === 0
    && (evidenceRow.listen?.protocolReady ?? 0) === 0
    && (evidenceRow.listen?.acceptedBinary ?? 0) === 0)).toBeTrue();

  db.close();
});
