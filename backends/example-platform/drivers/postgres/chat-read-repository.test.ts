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
import { withAuthorizedChatRead } from "./chat-read-repository";

const hash = (character: string): string => character.repeat(64);
const account = "account:alice";

const authorityRow = (): AuthorityStateRow => ({
  account_id: account,
  principal_id: "principal:chat",
  application_id: "app:chat",
  credential_id: "credential:chat",
  credential_generation: 1,
  capability: "chat.read",
  grant_id: "grant:chat",
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

const context = (capability = "chat.read") => {
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
    100,
  );
};

test("chat history remains private until final clock and cancellation checks pass", async () => {
  for (const mode of ["success", "expired", "aborted"]) {
    const controller = new AbortController();
    let committed = false;
    let released!: () => void;
    let began!: () => void;
    const wait = new Promise<void>((resolve) => {
      released = resolve;
    });
    const started = new Promise<void>((resolve) => {
      began = resolve;
    });
    const connection: CheckedOutPostgresConnection = {
      connectionIdentity: {},
      async execute() {
        return { rowCount: 0 };
      },
      async query(statement) {
        const rows = statement.name === "authority.lock_and_revalidate"
          ? [authorityRow()]
          : statement.name === "chat.read_snapshot"
            ? [{ sequence: 0 }]
            : statement.name === "chat.final_clock"
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
    const pending = withAuthorizedChatRead(
      pool,
      context(),
      controller.signal,
      async (storage) => {
        began();
        await wait;
        return storage.readSnapshotSequence();
      },
    );
    await started;
    expect(committed).toBe(false);
    if (mode === "aborted") controller.abort();
    released();
    if (mode === "success") await expect(pending).resolves.toBe(0);
    else if (mode === "expired") await expect(pending).rejects.toMatchObject({ code: "expired_context" });
    else await expect(pending).rejects.toThrow();
    expect(committed).toBe(mode === "success");
  }
});

test("an unrelated capability never checks out a chat connection", async () => {
  const pool: PostgresTransactionPool = {
    async withTransaction() {
      throw Error("must not reach pool");
    },
  };
  await expect(withAuthorizedChatRead(
    pool,
    context("memories.read"),
    new AbortController().signal,
    () => null,
  )).rejects.toMatchObject({ code: "capability_denied" });
});

test("unreadable stored chat history fails closed instead of inventing an empty page", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      const rows = statement.name === "authority.lock_and_revalidate"
        ? [authorityRow()]
        : statement.name === "chat.read_history"
          ? [{ page: { hasOlder: false, messages: "corrupt" } }]
          : statement.name === "chat.final_clock"
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
  await expect(withAuthorizedChatRead(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.listHistory({
      limit: 50,
      snapshotSequence: 0,
      olderThan: null,
    }),
  )).rejects.toMatchObject({ code: "persistence_failed" });
});

test("a string generation frame fails closed instead of completing an assistant row", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      const rows = statement.name === "authority.lock_and_revalidate"
        ? [authorityRow()]
        : statement.name === "chat.read_generation_events"
          ? [{ events: [{ id: "evt-done", generationId: "gen", sequence: 1, createdAt: 1, frame: "{\"kind\":\"done\"}" }] }]
          : statement.name === "chat.final_clock"
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
  await expect(withAuthorizedChatRead(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.listGenerationEvents("gen"),
  )).rejects.toMatchObject({ code: "persistence_failed" });
});

test("unreadable chat conversation sessions fail closed instead of inventing chat:chat-main", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      const rows = statement.name === "authority.lock_and_revalidate"
        ? [authorityRow()]
        : statement.name === "chat.read_conversation_sessions"
          ? [{ sessions: { id: "chat:chat-main" } }]
          : statement.name === "chat.final_clock"
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
  await expect(withAuthorizedChatRead(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.listConversationSessions(),
  )).rejects.toMatchObject({ code: "persistence_failed" });
});

test("granted empty chat conversation sessions stay an empty list", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      const rows = statement.name === "authority.lock_and_revalidate"
        ? [authorityRow()]
        : statement.name === "chat.read_conversation_sessions"
          ? [{ sessions: [] }]
          : statement.name === "chat.final_clock"
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
  await expect(withAuthorizedChatRead(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.listConversationSessions(),
  )).resolves.toEqual([]);
});

test("granted chat sessions with empty titles stay visible without inventing Chat", async () => {
  const session = {
    id: "chat:chat-main",
    title: "",
    overview: "",
    createdAt: 1000,
    updatedAt: 2000,
    startedAt: 1000,
    finishedAt: null,
    source: "chat",
    status: "in_progress",
    discarded: false,
    starred: false,
    visibility: "private",
    isLocked: false,
    folderId: null,
    revision: null,
  };
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      const rows = statement.name === "authority.lock_and_revalidate"
        ? [authorityRow()]
        : statement.name === "chat.read_conversation_sessions"
          ? [{ sessions: [session] }]
          : statement.name === "chat.final_clock"
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
  await expect(withAuthorizedChatRead(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.listConversationSessions(),
  )).resolves.toEqual([session]);
});

test("granted named chat sessions parse beside chat:chat-main", async () => {
  const session = (id: string) => ({
    id,
    title: "hello",
    overview: "answer",
    createdAt: 1000,
    updatedAt: 2000,
    startedAt: 1000,
    finishedAt: null,
    source: "chat",
    status: "in_progress",
    discarded: false,
    starred: false,
    visibility: "private",
    isLocked: false,
    folderId: null,
    revision: null,
  });
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      const rows = statement.name === "authority.lock_and_revalidate"
        ? [authorityRow()]
        : statement.name === "chat.read_conversation_sessions"
          ? [{ sessions: [session("chat:chat-main"), session("chat:session-alpha")] }]
          : statement.name === "chat.final_clock"
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
  await expect(withAuthorizedChatRead(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.listConversationSessions(),
  )).resolves.toEqual([session("chat:chat-main"), session("chat:session-alpha")]);
});
