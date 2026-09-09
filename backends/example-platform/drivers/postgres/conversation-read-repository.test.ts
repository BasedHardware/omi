import { expect, test } from "bun:test";
import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  authorizationStateDigest,
  type AuthorityStateRow,
} from "./transaction";
import type {
  PostgresTransactionPool,
  CheckedOutPostgresConnection,
} from "./connection";
import { withAuthorizedConversationRead } from "./conversation-read-repository";
const hash = (character: string): string => character.repeat(64);
const account = "account:alice";

const authorityRow = (): AuthorityStateRow => ({
  account_id: account,
  principal_id: "principal:listen",
  application_id: "app:listen",
  credential_id: "credential:listen",
  credential_generation: 1,
  capability: "conversations.read",
  grant_id: "grant:listen",
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

const context = (capability = "conversations.read") => {
  const row = authorityRow();
  return createAuthorizedLedgerWriteContextIssuer().issue(
    {
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
    },
    100
  );
};

test("read responses remain private until final clock and cancellation checks pass", async () => {
  for (const mode of ["success", "expired", "aborted"]) {
    const controller = new AbortController();
    let committed = false;
    let released!: () => void;
    let began!: () => void;
    const wait = new Promise<void>((resolve) => (released = resolve));
    const started = new Promise<void>((resolve) => (began = resolve));
    const connection: CheckedOutPostgresConnection = {
      connectionIdentity: {},
      async execute() {
        return { rowCount: 0 };
      },
      async query(statement) {
        const rows =
          statement.name === "authority.lock_and_revalidate"
            ? [authorityRow()]
            : statement.name === "conversations.read_snapshot"
            ? [{ snapshot: { revision: 0, records: [] } }]
            : statement.name === "conversations.final_clock"
            ? [{ now: mode === "expired" ? 500 : 499 }]
            : [];
        return rows as never;
      },
    };
    const pool: PostgresTransactionPool = {
      async withTransaction(options, operation) {
        expect(options.signal).toBe(controller.signal);
        const result = await operation(connection);
        committed = true;
        return result;
      },
    };
    const pending = withAuthorizedConversationRead(
      pool,
      context(),
      controller.signal,
      async (snapshot) => {
        began();
        await wait;
        return snapshot;
      }
    );
    await started;
    expect(committed).toBe(false);
    if (mode === "aborted") controller.abort();
    released();
    if (mode === "success")
      await expect(pending).resolves.toEqual({ revision: 0, records: [] });
    else if (mode === "expired")
      await expect(pending).rejects.toMatchObject({ code: "expired_context" });
    else await expect(pending).rejects.toThrow();
    expect(committed).toBe(mode === "success");
  }
});
test("union cursor saves bind epoch milliseconds as bigint the same way listen capture already does", async () => {
  const saved: Array<{ text: string; values: readonly unknown[] }> = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      saved.push({ text: statement.text, values: statement.values });
      const rows =
        statement.name === "authority.lock_and_revalidate"
          ? [authorityRow()]
          : statement.name === "conversations.read_snapshot"
          ? [{ snapshot: { revision: 1, records: [] } }]
          : statement.name === "conversations.save_union_cursor"
          ? [{}]
          : statement.name === "conversations.final_clock"
          ? [{ now: 100 }]
          : [];
      return rows as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  await withAuthorizedConversationRead(
    pool,
    context(),
    new AbortController().signal,
    async (_snapshot, _now, storage) => {
      await storage.saveUnion(
        hash("a"),
        hash("b"),
        1,
        0,
        "2026-09-07T13:50:44.000Z",
        1_757_250_000_000,
        "recording:11111111-2222-4333-8444-555555555555",
        "listen",
        1000
      );
      return "ok";
    }
  );
  const unionSave = saved.find((statement) =>
    statement.text.includes("save_conversation_union_cursor")
  );
  expect(unionSave?.text).toContain("$5::timestamptz");
  expect(unionSave?.text).toContain("$6::bigint");
  expect(unionSave?.values[5]).toBe(1_757_250_000_000n);
});

test("union cursor saves pass a named chat last_id outside printable ASCII", async () => {
  const saved: Array<{ text: string; values: readonly unknown[] }> = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      saved.push({ text: statement.text, values: statement.values });
      const rows =
        statement.name === "authority.lock_and_revalidate"
          ? [authorityRow()]
          : statement.name === "conversations.read_snapshot"
          ? [{ snapshot: { revision: 1, records: [] } }]
          : statement.name === "conversations.save_union_cursor"
          ? [{}]
          : statement.name === "conversations.final_clock"
          ? [{ now: 100 }]
          : [];
      return rows as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  await withAuthorizedConversationRead(
    pool,
    context(),
    new AbortController().signal,
    async (_snapshot, _now, storage) => {
      await storage.saveUnion(
        hash("a"),
        hash("b"),
        1,
        0,
        "2026-09-07T13:50:44.000Z",
        1_757_250_000_000,
        "chat:你好",
        "chat",
        1000
      );
      return "ok";
    }
  );
  const unionSave = saved.find((statement) =>
    statement.text.includes("save_conversation_union_cursor")
  );
  expect(unionSave?.values[6]).toBe("chat:你好");
});

test("union cursor load accepts a named chat last_id outside printable ASCII", async () => {
  for (const lastId of ["chat:你好", "chat: session-alpha "]) {
    const connection: CheckedOutPostgresConnection = {
      connectionIdentity: {},
      async execute() {
        return { rowCount: 0 };
      },
      async query(statement) {
        const rows =
          statement.name === "authority.lock_and_revalidate"
            ? [authorityRow()]
            : statement.name === "conversations.read_snapshot"
            ? [{ snapshot: { revision: 1, records: [] } }]
            : statement.name === "conversations.read_union_page"
            ? [
                {
                  snapshot: {
                    revision: 1,
                    records: [],
                    after: { updatedAt: 1, id: lastId },
                  },
                },
              ]
            : statement.name === "conversations.final_clock"
            ? [{ now: 100 }]
            : [];
        return rows as never;
      },
    };
    const pool: PostgresTransactionPool = {
      async withTransaction(_options, operation) {
        return operation(connection);
      },
    };
    const loaded = await withAuthorizedConversationRead(
      pool,
      context(),
      new AbortController().signal,
      async (_snapshot, _now, storage) =>
        storage.loadUnion(2, hash("c"), hash("d"), 1, 0)
    );
    expect(loaded.after).toEqual({ updatedAt: 1, id: lastId });
  }
});

test("union cursor load still rejects an empty or oversized last_id", async () => {
  for (const lastId of ["", "x".repeat(257)]) {
    const connection: CheckedOutPostgresConnection = {
      connectionIdentity: {},
      async execute() {
        return { rowCount: 0 };
      },
      async query(statement) {
        const rows =
          statement.name === "authority.lock_and_revalidate"
            ? [authorityRow()]
            : statement.name === "conversations.read_snapshot"
            ? [{ snapshot: { revision: 1, records: [] } }]
            : statement.name === "conversations.read_union_page"
            ? [
                {
                  snapshot: {
                    revision: 1,
                    records: [],
                    after: { updatedAt: 1, id: lastId },
                  },
                },
              ]
            : statement.name === "conversations.final_clock"
            ? [{ now: 100 }]
            : [];
        return rows as never;
      },
    };
    const pool: PostgresTransactionPool = {
      async withTransaction(_options, operation) {
        return operation(connection);
      },
    };
    await expect(
      withAuthorizedConversationRead(
        pool,
        context(),
        new AbortController().signal,
        async (_snapshot, _now, storage) =>
          storage.loadUnion(2, hash("c"), hash("d"), 1, 0)
      )
    ).rejects.toMatchObject({ code: "persistence_failed" });
  }
});

test("an unrelated capability never checks out a conversation connection", async () => {
  const pool: PostgresTransactionPool = {
    async withTransaction() {
      throw Error("must not reach pool");
    },
  };
  await expect(
    withAuthorizedConversationRead(
      pool,
      context("memories.read"),
      new AbortController().signal,
      () => null
    )
  ).rejects.toMatchObject({ code: "capability_denied" });
});
