import { expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import type { ChatMessageRecord } from "../../apps/service/stores/chat-messages-store";
import type { ChatAdmissionReservation } from "./chat-write-repository";
import {
  authorizationStateDigest,
  type AuthorityStateRow,
} from "./transaction";
import type {
  PostgresTransactionPool,
  CheckedOutPostgresConnection,
} from "./connection";
import { withAuthorizedChatWrite } from "./chat-write-repository";

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

const human = (overrides: Partial<ChatMessageRecord> = {}): ChatMessageRecord => ({
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
  attachments: [],
  ...overrides,
});

const reservation = (
  overrides: Partial<ChatAdmissionReservation> = {},
): ChatAdmissionReservation => ({
  catalogRevision: "catalog-2",
  subscriptionRevision: "sub-1",
  usagePeriodUtc: "2026-09",
  billingUnit: "chat_message",
  ...overrides,
});

const messageSql = (message: ChatMessageRecord, generationId: string | null) => ({
  id: message.id,
  text: message.text,
  sender: message.sender,
  message_type: message.type,
  created_at: message.createdAt,
  updated_at: message.updatedAt,
  chat_session_id: message.chatSessionId,
  app_id: message.appId,
  journal_revision: message.journalRevision,
  payload_hash: message.payloadHash,
  message_source: message.messageSource,
  rating: message.rating,
  reported: message.reported,
  server_revision: message.revision,
  attachments_json: message.attachments ?? [],
  generation_id: generationId,
});

test("chat.write remains private until final clock and cancellation checks pass", async () => {
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
          : statement.name === "chat.write_final_clock"
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
    const pending = withAuthorizedChatWrite(
      pool,
      context(),
      controller.signal,
      async () => {
        began();
        await wait;
        return "ok";
      },
    );
    await started;
    expect(committed).toBe(false);
    if (mode === "aborted") controller.abort();
    released();
    if (mode === "success") await expect(pending).resolves.toBe("ok");
    else if (mode === "expired") await expect(pending).rejects.toMatchObject({ code: "expired_context" });
    else await expect(pending).rejects.toThrow();
    expect(committed).toBe(mode === "success");
  }
});

test("chat.read never checks out a chat.write connection", async () => {
  const pool: PostgresTransactionPool = {
    async withTransaction() {
      throw Error("must not reach pool");
    },
  };
  await expect(withAuthorizedChatWrite(
    pool,
    context("chat.read"),
    new AbortController().signal,
    () => null,
  )).rejects.toMatchObject({ code: "capability_denied" });
  await expect(withAuthorizedChatWrite(
    pool,
    context("memories.write"),
    new AbortController().signal,
    () => null,
  )).rejects.toMatchObject({ code: "capability_denied" });
});

test("a foreign account id is refused before any chat mutation", async () => {
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
  await expect(withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit({
      accountId: "account:bob",
      message: human(),
      generationId: "generation-foreign",
      acceptedEventId: "event-foreign",
      admittedAt: 200,
      attachmentIds: [],
    }, reservation()),
  )).rejects.toMatchObject({ code: "authorization_state_denied" });
});

test("admission creates, replays, and conflicts in one transaction without a second reservation row", async () => {
  const messages = new Map<string, ReturnType<typeof messageSql>>();
  const events: Record<string, unknown>[] = [];
  const reservations: string[] = [];
  const statements: string[] = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute(statement) {
      statements.push(statement.name);
      if (statement.name === "chat.write_insert_message") {
        const id = String(statement.values[1]);
        if (messages.has(id)) return { rowCount: 0 };
        messages.set(id, messageSql(human({
          id,
          text: String(statement.values[2]),
          payloadHash: String(statement.values[10]),
        }), String(statement.values[16])));
        return { rowCount: 1 };
      }
      if (statement.name === "chat.write_insert_reservation") {
        reservations.push(String(statement.values[1]));
        return { rowCount: 1 };
      }
      if (statement.name === "chat.write_insert_event") {
        events.push({
          event_id: statement.values[3],
          generation_id: statement.values[1],
          sequence: statement.values[2],
          created_at: statement.values[4],
          frame_json: JSON.parse(String(statement.values[5])),
        });
        return { rowCount: 1 };
      }
      return { rowCount: 0 };
    },
    async query(statement) {
      statements.push(statement.name);
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.write_read_message") {
        const stored = messages.get(String(statement.values[1]));
        return (stored === undefined ? [] : [stored]) as never;
      }
      if (statement.name === "chat.write_list_events") return events as never;
      if (statement.name === "chat.write_read_event") return [] as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  const input = {
    accountId: account,
    message: human(),
    generationId: "generation-1",
    acceptedEventId: "event-1",
    admittedAt: 200,
    attachmentIds: [] as const,
  };

  const created = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit(input, reservation()),
  );
  expect(created.kind).toBe("created");
  expect(reservations).toEqual(["client-1"]);
  expect(events.map((event) => (event.frame_json as { kind: string }).kind)).toEqual(["accepted"]);

  const replay = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit(input, reservation()),
  );
  expect(replay.kind).toBe("replay");
  expect(reservations).toEqual(["client-1"]);

  const conflict = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit({
      ...input,
      message: human({ text: "mutated", payloadHash: "sha256:two" }),
    }, reservation()),
  );
  expect(conflict.kind).toBe("conflict");
  expect(statements).not.toContain("chat.read_history");
});

test("missing reservation metadata refuses instead of treating null as unlimited", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      throw new Error("must not write without a reservation");
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.write_read_message") return [] as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  await expect(withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit({
      accountId: account,
      message: human(),
      generationId: "generation-unmetered",
      acceptedEventId: "event-unmetered",
      admittedAt: 200,
      attachmentIds: [],
    }, null),
  )).resolves.toEqual({ kind: "entitlement" });
});

test("injected synthetic reservation metadata is recorded once and replayed without a second row", async () => {
  const messages = new Map<string, ReturnType<typeof messageSql>>();
  const events: Record<string, unknown>[] = [];
  const reservations: string[] = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute(statement) {
      if (statement.name === "chat.write_insert_message") {
        messages.set(String(statement.values[1]), messageSql(human(), String(statement.values[16])));
        return { rowCount: 1 };
      }
      if (statement.name === "chat.write_insert_reservation") {
        reservations.push(String(statement.values[1]));
        return { rowCount: 1 };
      }
      if (statement.name === "chat.write_insert_event") {
        events.push({ frame_json: { kind: "accepted" } });
        return { rowCount: 1 };
      }
      return { rowCount: 0 };
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.write_read_message") {
        const stored = messages.get(String(statement.values[1]));
        return (stored === undefined ? [] : [stored]) as never;
      }
      if (statement.name === "chat.write_list_events") return events as never;
      if (statement.name === "chat.write_read_event") return [] as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  const created = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit({
      accountId: account,
      message: human(),
      generationId: "generation-reserved",
      acceptedEventId: "event-reserved",
      admittedAt: 200,
      attachmentIds: [],
    }, reservation()),
  );
  expect(created.kind).toBe("created");
  expect(reservations).toEqual(["client-1"]);
  const replay = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit({
      accountId: account,
      message: human(),
      generationId: "generation-reserved",
      acceptedEventId: "event-reserved",
      admittedAt: 200,
      attachmentIds: [],
    }, reservation()),
  );
  expect(replay.kind).toBe("replay");
  expect(reservations).toEqual(["client-1"]);
});

test("non-empty attachments fail closed because production attachment storage is unmounted", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      throw new Error("must not write attachments");
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_final_clock") return [{ now: 100 }] as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  await expect(withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit({
      accountId: account,
      message: human({ attachments: [{
        id: "att-1",
        displayName: "note.txt",
        mediaType: "text/plain",
        sizeBytes: 4,
        contentReference: "ref-1",
      }] }),
      generationId: "generation-att",
      acceptedEventId: "event-att",
      admittedAt: 200,
      attachmentIds: ["att-1"],
    }, reservation()),
  )).resolves.toEqual({ kind: "attachment_not_found" });
});

test("review: failed accepted event rolls back message and reservation metadata", async () => {
  let stored: ReturnType<typeof messageSql> | null = null;
  const reservations: string[] = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute(statement) {
      if (statement.name === "chat.write_insert_message") {
        stored = messageSql(human(), "generation-rollback");
        return { rowCount: 1 };
      }
      if (statement.name === "chat.write_insert_reservation") {
        reservations.push(String(statement.values[1]));
        return { rowCount: 1 };
      }
      if (statement.name === "chat.write_insert_event") throw Error("accepted event failed");
      return { rowCount: 0 };
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_read_message") return (stored === null ? [] : [stored]) as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      try { return await operation(connection); }
      catch (error) {
        stored = null;
        reservations.length = 0;
        throw error;
      }
    },
  };
  await expect(withAuthorizedChatWrite(
    pool, context(), new AbortController().signal,
    storage => storage.admit({
      accountId: account, message: human(), generationId: "generation-rollback",
      acceptedEventId: "event-rollback", admittedAt: 200, attachmentIds: [],
    }, reservation()),
  )).rejects.toMatchObject({ code: "persistence_failed" });
  expect(stored).toBeNull();
  expect(reservations).toEqual([]);
});

test("postgres bigint strings decode before detachChatMessage", async () => {
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      return { rowCount: 0 };
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_final_clock") return [{ now: "100" }] as never;
      if (statement.name === "chat.write_read_message") {
        return [{
          ...messageSql(human(), "generation-bigint"),
          created_at: "100",
          updated_at: "100",
          journal_revision: "1",
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
  const replayed = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.admit({
      accountId: account,
      message: human(),
      generationId: "generation-bigint",
      acceptedEventId: "event-bigint",
      admittedAt: 200,
      attachmentIds: [],
    }, reservation()),
  );
  expect(replayed.kind).toBe("replay");
  if (replayed.kind !== "replay") throw new Error("expected replay");
  expect(replayed.stored.message.createdAt).toBe(100);
  expect(replayed.stored.message.journalRevision).toBe(1);
});

test("finalization persists assistant and terminal together and later complete is settlement", async () => {
  const messages = new Map<string, ReturnType<typeof messageSql>>();
  const events: Record<string, unknown>[] = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute(statement) {
      if (statement.name === "chat.write_insert_message") {
        const stored = messageSql({
          ...human({
            id: String(statement.values[1]),
            sender: "ai",
            text: String(statement.values[2]),
            payloadHash: String(statement.values[10]),
          }),
        }, String(statement.values[16]));
        messages.set(stored.id, stored);
        return { rowCount: 1 };
      }
      if (statement.name === "chat.write_insert_event") {
        events.push({
          event_id: statement.values[3],
          generation_id: statement.values[1],
          sequence: statement.values[2],
          created_at: statement.values[4],
          frame_json: JSON.parse(String(statement.values[5])),
        });
        return { rowCount: 1 };
      }
      return { rowCount: 0 };
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.write_read_message") {
        const stored = messages.get(String(statement.values[1]));
        return (stored === undefined ? [] : [stored]) as never;
      }
      if (statement.name === "chat.write_list_events") return events as never;
      if (statement.name === "chat.write_read_event") return [] as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  const assistant = human({
    id: "assistant-1",
    sender: "ai",
    text: "answer",
    payloadHash: "sha256:assistant",
  });
  const first = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.finalize({
      accountId: account,
      generationId: "generation-1",
      eventId: "event-done",
      createdAt: 300,
      frame: { kind: "done", message: assistant },
    }),
  );
  expect(first.frame.kind).toBe("done");
  expect(messages.get("assistant-1")?.payload_hash).toBe("sha256:assistant");
  const settled = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.finalize({
      accountId: account,
      generationId: "generation-1",
      eventId: "event-done-retry",
      createdAt: 400,
      frame: { kind: "done", message: assistant },
    }),
  );
  expect(settled.id).toBe("event-done");
  expect(events).toHaveLength(1);
});

test("a stored cancelled terminal wins over a later complete and does not insert an assistant", async () => {
  const messages = new Map<string, ReturnType<typeof messageSql>>();
  const events: Record<string, unknown>[] = [{
    event_id: "event-cancelled",
    generation_id: "generation-cancel",
    sequence: 2,
    created_at: 250,
    frame_json: { kind: "cancelled", message: null },
  }];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute() {
      throw new Error("must not write after a stored terminal");
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_final_clock") return [{ now: 100 }] as never;
      if (statement.name === "chat.write_list_events") return events as never;
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      return operation(connection);
    },
  };
  const settled = await withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.finalize({
      accountId: account,
      generationId: "generation-cancel",
      eventId: "event-done",
      createdAt: 400,
      frame: {
        kind: "done",
        message: human({
          id: "assistant-late",
          sender: "ai",
          payloadHash: "sha256:late",
        }),
      },
    }),
  );
  expect(settled.frame).toEqual({ kind: "cancelled", message: null });
  expect(messages.size).toBe(0);
});

test("a crash after the assistant insert rolls the whole write transaction back", async () => {
  let committed = false;
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    async execute(statement) {
      if (statement.name === "chat.write_insert_message") return { rowCount: 1 };
      if (statement.name === "chat.write_insert_event") {
        throw new Error("injected terminal abort");
      }
      return { rowCount: 0 };
    },
    async query(statement) {
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow()] as never;
      if (statement.name === "chat.write_read_message") {
        return [messageSql(human({
          id: "assistant-crash",
          sender: "ai",
          payloadHash: "sha256:crash",
        }), "generation-crash")] as never;
      }
      if (statement.name === "chat.write_list_events" || statement.name === "chat.write_read_event") {
        return [] as never;
      }
      return [] as never;
    },
  };
  const pool: PostgresTransactionPool = {
    async withTransaction(_options, operation) {
      try {
        const result = await operation(connection);
        committed = true;
        return result;
      } catch (error) {
        committed = false;
        throw error;
      }
    },
  };
  await expect(withAuthorizedChatWrite(
    pool,
    context(),
    new AbortController().signal,
    (storage) => storage.finalize({
      accountId: account,
      generationId: "generation-crash",
      eventId: "event-crash",
      createdAt: 300,
      frame: {
        kind: "done",
        message: human({
          id: "assistant-crash",
          sender: "ai",
          payloadHash: "sha256:crash",
        }),
      },
    }),
  )).rejects.toMatchObject({ code: "persistence_failed" });
  expect(committed).toBe(false);
});
