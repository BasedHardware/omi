import { expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  ATTACHMENT_STAGING_TTL_MS,
  MAIN_CHAT_ATTACHMENT_SCOPE,
} from "../../apps/service/chat/attachment-policy";
import { withAuthorizedChatAttachments } from "./chat-attachment-repository";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const hash = (character: string): string => character.repeat(64);
const account = "account:alice";

const authorityRow = (capability = "chat.write"): AuthorityStateRow => ({
  account_id: account,
  principal_id: "principal:chat",
  application_id: "app:chat",
  credential_id: "credential:chat",
  credential_generation: 1,
  capability,
  grant_id: "grant:chat-write",
  grant_version: 1,
  account_epoch: 2,
  control_conflict_reason: null,
  control_conflict_at_revision: null,
  destination_activation_epoch: 2,
  destination_activation_revision: 3,
  lifecycle_state: "active",
  deletion_epoch: null,
  account_generation: "new",
  credential_lifecycle: "active",
  grant_lifecycle: "active",
  grant_enabled: true,
  authentication_strength: "service-workload",
  credential_expires_at_epoch_seconds: 10_000,
  control_revision: 3,
  control_content_hash: hash("1"),
  credential_content_hash: hash("2"),
  grant_content_hash: hash("3"),
  db_now_epoch_seconds: 100,
});

const context = (capability = "chat.write") => {
  const row = authorityRow(capability);
  return createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: row.principal_id,
    account_id: account,
    application_id: row.application_id,
    credential_id: row.credential_id,
    credential_generation: row.credential_generation,
    capability,
    grant_id: row.grant_id,
    grant_version: row.grant_version,
    account_epoch: 2,
    destination_activation_revision: 3,
    lifecycle_state: "active",
    deletion_epoch: null,
    authentication_strength: row.authentication_strength,
    issued_at_epoch_seconds: 50,
    expires_at_epoch_seconds: 500,
    authorization_state_digest: authorizationStateDigest(row),
  }, 100);
};

const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00]);

test("chat.read never checks out attachment storage", async () => {
  const pool: PostgresTransactionPool = {
    async withTransaction() {
      throw Error("must not reach pool");
    },
  };
  await expect(withAuthorizedChatAttachments(
    pool,
    context("chat.read"),
    new AbortController().signal,
    () => null,
  )).rejects.toMatchObject({ code: "capability_denied" });
});

test("foreign account staging is refused before insert", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      throw new Error("must not mutate");
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  await expect(withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.stage({
      id: "att-1",
      contentReference: "ref-1",
      accountId: "account:bob",
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      displayName: "note.png",
      mimeType: "image/png",
      content: png,
      stagedAt: 1_000,
      stageExpiresAt: 1_000 + ATTACHMENT_STAGING_TTL_MS,
    }),
  )).rejects.toMatchObject({ code: "authorization_state_denied" });
});

test("stage, scan, bind, expire, and remove stay on one authorized connection", async () => {
  const rows = new Map<string, Record<string, unknown>>();
  const statements: string[] = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute(statement) {
      statements.push(statement.name);
      if (statement.name === "chat.attachment_stage") {
        const id = String(statement.values[1]);
        if (rows.has(id)) return { rowCount: 0 };
        rows.set(id, {
          account_id: account,
          id,
          content_reference: statement.values[2],
          attachment_scope: statement.values[3],
          display_name: statement.values[4],
          mime_type: statement.values[5],
          size_bytes: statement.values[6],
          attachment_state: "staged",
          scanner_id: "dev-noop-scanner",
          scanning_started_at: null,
          staged_at: statement.values[8],
          stage_expires_at: statement.values[9],
          bound_message_id: null,
          bound_at: null,
          content_expires_at: null,
          content_bytes: statement.values[10],
        });
        return { rowCount: 1 };
      }
      if (statement.name === "chat.attachment_scan"
        || statement.name === "chat.attachment_retry_scan") {
        const row = rows.get(String(statement.values[3]));
        if (row === undefined || row.attachment_state === "bound") return { rowCount: 0 };
        row.attachment_state = statement.values[0];
        row.scanning_started_at = statement.values[1];
        return { rowCount: 1 };
      }
      if (statement.name === "chat.attachment_bind") {
        const row = rows.get(String(statement.values[4]));
        if (row === undefined || row.attachment_state !== "clean") return { rowCount: 0 };
        row.attachment_state = "bound";
        row.bound_message_id = statement.values[0];
        row.bound_at = statement.values[1];
        row.content_expires_at = statement.values[2];
        return { rowCount: 1 };
      }
      if (statement.name === "chat.attachment_expire_content") {
        for (const row of rows.values()) {
          if (row.bound_message_id === statement.values[1]
            && typeof row.content_expires_at === "number"
            && row.content_expires_at <= Number(statement.values[2])) {
            row.content_reference = null;
            row.content_bytes = null;
          }
        }
        return { rowCount: 1 };
      }
      return { rowCount: 0 };
    },
    async query(statement) {
      statements.push(statement.name);
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.attachment_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.attachment_read") {
        const stored = rows.get(String(statement.values[1]));
        return (stored === undefined ? [] : [stored]) as never;
      }
      if (statement.name === "chat.attachment_remove_unbound") {
        const id = String(statement.values[0]);
        const stored = rows.get(id);
        if (stored === undefined || stored.attachment_state === "bound") {
          return [{ removed: false }] as never;
        }
        rows.delete(id);
        return [{ removed: true }] as never;
      }
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  const clock = { now: () => 1_500 };
  const staged = await withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.stage({
      id: "att-1",
      contentReference: "ref-1",
      accountId: account,
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      displayName: "note.png",
      mimeType: "image/png",
      content: png,
      stagedAt: 1_000,
      stageExpiresAt: 1_000 + ATTACHMENT_STAGING_TTL_MS,
    }),
  );
  expect(staged.state).toBe("staged");
  const scanned = await withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    async (storage) => {
      await storage.advanceScan("att-1", clock);
      return storage.advanceScan("att-1", clock);
    },
  );
  expect(scanned?.state).toBe("clean");
  expect(await withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.retryScan("att-1", clock),
  )).toBeNull();
  const bound = await withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.bindToMessage({
      accountId: account,
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      attachmentIds: ["att-1"],
      messageId: "msg-1",
      nowEpochMilliseconds: 2_000,
      contentExpiresAt: 2_000,
    }),
  );
  expect(bound.kind).toBe("ready");
  const expired = await withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.projectMessageAttachments({
      accountId: account,
      messageId: "msg-1",
      nowEpochMilliseconds: 2_001,
      attachments: [{
        id: "att-1",
        displayName: "note.png",
        mediaType: "image/png",
        sizeBytes: png.byteLength,
        contentReference: "ref-1",
      }],
    }),
  );
  expect(expired[0]?.contentReference).toBeNull();
  expect(await withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.removeUnbound("att-1", account),
  )).toBe(false);
  expect(statements).not.toContain("chat.read_history");
});

test("expired staging cannot bind and production composition stays unmounted", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.attachment_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.attachment_read") {
        return [{
          account_id: account,
          id: "att-expired",
          content_reference: "ref-expired",
          attachment_scope: MAIN_CHAT_ATTACHMENT_SCOPE,
          display_name: "old.png",
          mime_type: "image/png",
          size_bytes: 8,
          attachment_state: "clean",
          scanner_id: "dev-noop-scanner",
          scanning_started_at: 10,
          staged_at: 10,
          stage_expires_at: 20,
          bound_message_id: null,
          bound_at: null,
          content_expires_at: null,
          content_bytes: png,
        }] as never;
      }
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  await expect(withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.bindToMessage({
      accountId: account,
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      attachmentIds: ["att-expired"],
      messageId: "msg-1",
      nowEpochMilliseconds: 21,
      contentExpiresAt: 21 + 1_000,
    }),
  )).resolves.toEqual({ kind: "not_found" });

  const app = await Bun.file(new URL("./firebase-authorized-memory-service-app.ts", import.meta.url)).text();
  const production = await Bun.file(new URL("../../apps/service/bin/production-server.ts", import.meta.url)).text();
  const memoryApp = await Bun.file(new URL("../../apps/service/memory-service-app.ts", import.meta.url)).text();
  for (const source of [app, production, memoryApp]) {
    expect(source).not.toContain("chat-attachment-repository");
    expect(source).not.toContain("chat-attachments");
    expect(source).not.toContain("withAuthorizedChatAttachments");
    expect(source).not.toContain("loadForGeneration");
  }
  const repository = await Bun.file(new URL("./chat-attachment-repository.ts", import.meta.url)).text();
  expect(repository).not.toContain("loadForGeneration");
  expect(repository).toContain("dev-noop-scanner");
});

test("retryScan restarts failed terminals and ignores clean or bound rows", async () => {
  const rows = new Map<string, Record<string, unknown>>([
    ["att-timeout", {
      account_id: account,
      id: "att-timeout",
      content_reference: "ref-timeout",
      attachment_scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      display_name: "old.png",
      mime_type: "image/png",
      size_bytes: 8,
      attachment_state: "timed_out",
      scanner_id: "dev-noop-scanner",
      scanning_started_at: 10,
      staged_at: 10,
      stage_expires_at: 10 + ATTACHMENT_STAGING_TTL_MS,
      bound_message_id: null,
      bound_at: null,
      content_expires_at: null,
      content_bytes: png,
    }],
  ]);
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute(statement) {
      if (statement.name === "chat.attachment_scan"
        || statement.name === "chat.attachment_retry_scan") {
        const row = rows.get(String(statement.values[3]));
        if (row === undefined || row.attachment_state === "bound") return { rowCount: 0 };
        row.attachment_state = statement.values[0];
        row.scanning_started_at = statement.values[1];
        return { rowCount: 1 };
      }
      return { rowCount: 0 };
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.attachment_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.attachment_read") {
        const stored = rows.get(String(statement.values[1]));
        return (stored === undefined ? [] : [stored]) as never;
      }
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  const retried = await withAuthorizedChatAttachments(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.retryScan("att-timeout", { now: () => 1_500 }),
  );
  expect(retried?.state).toBe("clean");
});
