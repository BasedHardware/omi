import { createExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { runDurableObjectAlarm, runInDurableObject } from "cloudflare:test";
import { beforeEach, describe, expect, test } from "vitest";

import {
  MAIN_CONVERSATION_ID,
  readConversations,
  paginateConversations,
} from "../src/conversations";
import { terminalEvent } from "../src/chat";
import handler from "../src/index";

const chatSchema = [
  "CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, text TEXT NOT NULL, sender TEXT NOT NULL, created_at INTEGER NOT NULL, generation_outcome TEXT, position INTEGER NOT NULL, payload TEXT)",
  "CREATE INDEX IF NOT EXISTS chat_messages_account_position ON chat_messages (account_id, position)",
  "CREATE TABLE IF NOT EXISTS chat_admissions (message_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, op_id TEXT NOT NULL, payload TEXT NOT NULL, generation_id TEXT NOT NULL)",
  "CREATE INDEX IF NOT EXISTS chat_admissions_account ON chat_admissions (account_id)",
  "CREATE INDEX IF NOT EXISTS chat_admissions_generation ON chat_admissions (generation_id)",
  "CREATE TABLE IF NOT EXISTS chat_generation_events (generation_id TEXT NOT NULL, account_id TEXT NOT NULL, event_id TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (generation_id, event_id))",
  "CREATE INDEX IF NOT EXISTS chat_generation_events_account ON chat_generation_events (account_id)",
];

const attachmentSchema = [
  "CREATE TABLE IF NOT EXISTS chat_attachments (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, op_id TEXT NOT NULL, display_name TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, state TEXT NOT NULL CHECK (state IN ('staged', 'uploaded', 'ingesting', 'ingested', 'invalid', 'bound', 'expired')), r2_key TEXT NOT NULL, expires_at INTEGER NOT NULL, bound_message_id TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)",
  "CREATE INDEX IF NOT EXISTS chat_attachments_account ON chat_attachments (account_id)",
  "CREATE INDEX IF NOT EXISTS chat_attachments_account_state ON chat_attachments (account_id, state)",
  "CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_account_op ON chat_attachments (account_id, op_id)",
  "CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_r2_key ON chat_attachments (r2_key)",
];

const taskSchema =
  "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, description TEXT NOT NULL, completed INTEGER NOT NULL, completed_at INTEGER, due_at INTEGER, owner TEXT, source TEXT NOT NULL, provenance TEXT NOT NULL, sort_order REAL NOT NULL, indent_level INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, revision TEXT)";

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-account",
};

const chatCreate = (id: string, text = "hello") => ({
  op: "create" as const,
  opId: `op-${id}`,
  id,
  at: 1,
  text,
  sender: "human" as const,
  journalRevision: 0,
  appId: null,
  chatSessionId: null,
  attachmentIds: [],
});

const insertAttachment = async (input: {
  id: string;
  accountId: string;
  state: string;
  boundMessageId?: string | null;
  displayName?: string;
  mimeType?: string;
  sizeBytes?: number;
}) => {
  const now = Date.now();
  await env.DB.prepare(
    "INSERT INTO chat_attachments (id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
  )
    .bind(
      input.id,
      input.accountId,
      `op-${input.id}`,
      input.displayName ?? "report.pdf",
      input.mimeType ?? "application/pdf",
      input.sizeBytes ?? 1024,
      input.state,
      `attachments/${input.accountId}/${input.id}`,
      now + 86_400_000,
      input.boundMessageId ?? null,
      now,
      now
    )
    .run();
};

const fetchWorker = (path: string, init?: RequestInit) =>
  handler.fetch(
    new Request(`https://worker.test${path}`, init),
    {
      ...env,
      API_TOKEN: "test-token",
      AI: { run: async () => ({ response: "AI reply" }) },
    } as never,
    createExecutionContext()
  );

beforeEach(async () => {
  for (const statement of chatSchema) {
    await env.DB.exec(statement);
  }
  for (const statement of attachmentSchema) {
    await env.DB.exec(statement);
  }
  await env.DB.exec(taskSchema);
  await env.DB.prepare("DELETE FROM chat_messages").run();
  await env.DB.prepare("DELETE FROM chat_admissions").run();
  await env.DB.prepare("DELETE FROM chat_generation_events").run();
  await env.DB.prepare("DELETE FROM chat_attachments").run();

  const stub = env.ACCOUNTS.getByName("test-account");
  await runInDurableObject(stub, (instance) =>
    (
      instance as unknown as {
        ctx: { storage: { deleteAll: () => Promise<void> } };
      }
    ).ctx.storage.deleteAll()
  );
});

describe("D1-authoritative chat persistence", () => {
  test("admission writes message, admission, and snapshot event to D1", async () => {
    const response = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-message-one")),
    });

    expect(response.status).toBe(201);
    const body = (await response.json()) as {
      message: { id: string };
      generation: { id: string };
    };
    expect(body.message.id).toBe("d1-message-one");
    expect(body.generation.id).toMatch(/^[-a-z0-9]+$/);

    const messageRow = await env.DB.prepare(
      "SELECT id, account_id, text, sender FROM chat_messages WHERE id = ?"
    )
      .bind("d1-message-one")
      .first<{
        id: string;
        account_id: string;
        text: string;
        sender: string;
      }>();
    expect(messageRow).not.toBeNull();
    expect(messageRow!.account_id).toBe("test-account");
    expect(messageRow!.text).toBe("hello");
    expect(messageRow!.sender).toBe("human");

    const admissionRow = await env.DB.prepare(
      "SELECT message_id, account_id, generation_id FROM chat_admissions WHERE message_id = ?"
    )
      .bind("d1-message-one")
      .first<{
        message_id: string;
        account_id: string;
        generation_id: string;
      }>();
    expect(admissionRow).not.toBeNull();
    expect(admissionRow!.account_id).toBe("test-account");
    expect(admissionRow!.generation_id).toBe(body.generation.id);

    const eventRow = await env.DB.prepare(
      "SELECT generation_id, account_id, event_id, payload FROM chat_generation_events WHERE generation_id = ?"
    )
      .bind(body.generation.id)
      .first<{
        generation_id: string;
        account_id: string;
        event_id: string;
        payload: string;
      }>();
    expect(eventRow).not.toBeNull();
    expect(eventRow!.account_id).toBe("test-account");
    expect(eventRow!.event_id).toBe("1");
    const eventPayload = JSON.parse(eventRow!.payload) as { kind: string };
    expect(eventPayload.kind).toBe("snapshot");
  });

  test("history reads persisted messages from D1", async () => {
    await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-history-one", "first message")),
    });

    const response = await fetchWorker("/v1/chat-messages?limit=50", {
      headers: authenticatedHeaders,
    });

    expect(response.status).toBe(200);
    const body = (await response.json()) as {
      messages: Array<{ id: string; text: string; sender: string }>;
    };
    expect(body.messages).toHaveLength(1);
    expect(body.messages[0]!.id).toBe("d1-history-one");
    expect(body.messages[0]!.text).toBe("first message");
    expect(body.messages[0]!.sender).toBe("human");
  });

  test("history GET stays on the main session unless chatSessionId is requested", async () => {
    await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-main-session", "main prompt")),
    });
    await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("d1-named-session", "named prompt"),
        chatSessionId: "session-alpha",
      }),
    });

    const main = await fetchWorker("/v1/chat-messages?limit=50", {
      headers: authenticatedHeaders,
    });
    expect(main.status).toBe(200);
    expect(
      ((await main.json()) as { messages: Array<{ id: string }> }).messages.map(
        (message) => message.id
      )
    ).toEqual(["d1-main-session"]);

    const named = await fetchWorker(
      "/v1/chat-messages?limit=50&chatSessionId=session-alpha",
      { headers: authenticatedHeaders }
    );
    expect(named.status).toBe(200);
    expect(
      (
        (await named.json()) as { messages: Array<{ id: string }> }
      ).messages.map((message) => message.id)
    ).toEqual(["d1-named-session"]);
  });

  test("idempotent replay returns the same message without duplicating D1 rows", async () => {
    const init = {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-replay-one")),
    } as const;

    const first = await fetchWorker("/v1/chat-messages", init);
    const firstBody = await first.text();
    expect(first.status).toBe(201);

    const replay = await fetchWorker("/v1/chat-messages", init);
    expect(replay.status).toBe(200);
    expect(await replay.text()).toBe(firstBody);

    const messageCount = await env.DB.prepare(
      "SELECT COUNT(*) as count FROM chat_messages WHERE id = ?"
    )
      .bind("d1-replay-one")
      .first<{ count: number }>();
    expect(messageCount!.count).toBe(1);

    const admissionCount = await env.DB.prepare(
      "SELECT COUNT(*) as count FROM chat_admissions WHERE message_id = ?"
    )
      .bind("d1-replay-one")
      .first<{ count: number }>();
    expect(admissionCount!.count).toBe(1);
  });

  test("account isolation excludes foreign-account messages from history", async () => {
    await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-own-message", "own message")),
    });

    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)"
    )
      .bind(
        "d1-foreign-message",
        "other-account",
        "foreign message",
        "human",
        2,
        2,
        JSON.stringify({
          id: "d1-foreign-message",
          text: "foreign message",
          sender: "human",
          type: "text",
          createdAt: 2,
          updatedAt: 2,
          chatSessionId: null,
          appId: null,
          journalRevision: 0,
          payloadHash: "sha256:foreign",
          messageSource: "desktop_chat",
          rating: null,
          reported: false,
          generationOutcome: null,
          revision: "2",
          attachments: [],
        })
      )
      .run();

    const response = await fetchWorker("/v1/chat-messages?limit=50", {
      headers: authenticatedHeaders,
    });

    expect(response.status).toBe(200);
    const body = (await response.json()) as {
      messages: Array<{ id: string }>;
    };
    expect(body.messages).toHaveLength(1);
    expect(body.messages[0]!.id).toBe("d1-own-message");
  });

  test("settings entitlement derives used count from D1 admissions", async () => {
    const before = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });
    expect(before.status).toBe(200);
    const beforeBody = (await before.json()) as {
      entitlement: {
        planLabel: string;
        used: number;
        limit: number;
        upgradeAvailable: boolean;
      };
    };
    expect(beforeBody.entitlement.used).toBe(0);
    expect(beforeBody.entitlement.limit).toBe(env.STAGING_CHAT_LIMIT);
    expect(beforeBody.entitlement.planLabel).toBe("");
    expect(beforeBody.entitlement.planLabel).not.toBe(env.STAGING_PLAN_LABEL);
    expect(beforeBody.entitlement.upgradeAvailable).toBe(false);

    await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-settings-one")),
    });

    const after = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });
    const afterBody = (await after.json()) as {
      entitlement: { used: number; limit: number };
    };
    expect(afterBody.entitlement.used).toBe(1);
    expect(afterBody.entitlement.limit).toBe(env.STAGING_CHAT_LIMIT);
  });

  test("alarm completes generation and writes AI message with done event to D1", async () => {
    const admissionResponse = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-alarm-one", "run generation")),
    });
    const admissionBody = (await admissionResponse.json()) as {
      generation: { id: string };
    };
    const generationId = admissionBody.generation.id;

    const stub = env.ACCOUNTS.getByName("test-account");
    await runInDurableObject(stub, (instance) => {
      Object.defineProperty(instance, "env", {
        configurable: true,
        value: {
          ...(instance as unknown as { env: Record<string, unknown> }).env,
          AI: { run: async () => ({ response: "AI completed reply" }) },
        },
      });
    });
    await runDurableObjectAlarm(stub);

    const aiMessage = await env.DB.prepare(
      "SELECT id, account_id, text, sender, generation_outcome FROM chat_messages WHERE sender = 'ai' AND account_id = ?"
    )
      .bind("test-account")
      .first<{
        id: string;
        account_id: string;
        text: string;
        sender: string;
        generation_outcome: string;
      }>();
    expect(aiMessage).not.toBeNull();
    expect(aiMessage!.text).toBe("AI completed reply");
    expect(aiMessage!.generation_outcome).toBe("completed");

    const doneEvent = await env.DB.prepare(
      "SELECT event_id, payload FROM chat_generation_events WHERE generation_id = ? AND event_id = '2'"
    )
      .bind(generationId)
      .first<{ event_id: string; payload: string }>();
    expect(doneEvent).not.toBeNull();
    const eventPayload = JSON.parse(doneEvent!.payload) as { kind: string };
    expect(eventPayload.kind).toBe("done");
  });

  test("cancellation writes a terminal cancelled event to D1", async () => {
    const admissionResponse = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-cancel-one")),
    });
    const admissionBody = (await admissionResponse.json()) as {
      generation: { id: string };
    };
    const generationId = admissionBody.generation.id;

    const response = await fetchWorker(`/v1/chat-generations/${generationId}`, {
      method: "DELETE",
      headers: authenticatedHeaders,
    });

    expect(response.status).toBe(202);
    const cancelledEvent = await env.DB.prepare(
      "SELECT event_id, payload FROM chat_generation_events WHERE generation_id = ? AND event_id = '2'"
    )
      .bind(generationId)
      .first<{ event_id: string; payload: string }>();
    expect(cancelledEvent).not.toBeNull();
    const eventPayload = JSON.parse(cancelledEvent!.payload) as {
      kind: string;
    };
    expect(eventPayload.kind).toBe("cancelled");
  });
});

describe("D1 chat projects an honest conversation list", () => {
  test("admitted chat becomes a conversation page, not projection_unavailable", async () => {
    const created = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-conversation-one", "project me")),
    });
    expect(created.status).toBe(201);

    const envelope = await fetchWorker("/v1/conversations", {
      headers: authenticatedHeaders,
    });
    expect(envelope.status).toBe(200);
    const page = (await envelope.json()) as {
      items: Array<{
        id: string;
        title: string;
        overview: string;
        source: string;
      }>;
      completeness: { version: string; status: string };
      absence: { kind: string } | null;
    };
    expect(page.completeness).toEqual({
      version: "conversations-completeness-v1",
      status: "complete",
      reasons: [],
      frontiers: {
        declaredFrontier: "frontier-v1:conversations-declared",
        newestAppliedFrontier: "frontier-v1:conversations-declared",
        missingAppliedFrontierReason: null,
      },
    });
    expect(page.absence).toBeNull();
    expect(page.items).toHaveLength(1);
    expect(page.items[0]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "project me",
      overview: "project me",
      source: "chat",
    });

    const legacy = await fetchWorker("/v1/conversations?limit=50&offset=0", {
      headers: authenticatedHeaders,
    });
    expect(legacy.status).toBe(200);
    const records = (await legacy.json()) as Array<{
      id: string;
      structured: { title: string };
    }>;
    expect(records).toEqual([
      expect.objectContaining({
        id: MAIN_CONVERSATION_ID,
        structured: expect.objectContaining({ title: "project me" }),
      }),
    ]);
  });

  test("space-padded and space-only stored chat-main group onto chat:chat-main", async () => {
    const bodies = [
      { ...chatCreate("d1-exact-main", "stored as chat-main"), at: 1 },
      {
        ...chatCreate("d1-padded-main", "stored as space-padded chat-main"),
        at: 2,
        chatSessionId: " chat-main ",
      },
      {
        ...chatCreate("d1-space-main", "stored as space-only chatSessionId"),
        at: 3,
        chatSessionId: "  ",
      },
      {
        ...chatCreate("d1-named", "named session stays named"),
        at: 5,
        chatSessionId: "session-alpha",
      },
      {
        ...chatCreate("d1-padded-named", "padded named stays named"),
        at: 4,
        chatSessionId: " session-alpha ",
      },
    ];
    for (const body of bodies) {
      const created = await fetchWorker("/v1/chat-messages", {
        method: "POST",
        headers: {
          ...authenticatedHeaders,
          "content-type": "application/json",
        },
        body: JSON.stringify(body),
      });
      expect(created.status).toBe(201);
    }

    const listed = await fetchWorker("/v1/conversations?limit=50", {
      headers: authenticatedHeaders,
    });
    expect(listed.status).toBe(200);
    expect(
      ((await listed.json()) as { items: Array<{ id: string }> }).items.map(
        (item) => item.id
      )
    ).toEqual([
      "chat:session-alpha",
      "chat: session-alpha ",
      MAIN_CONVERSATION_ID,
    ]);

    const mainHistory = await fetchWorker("/v1/chat-messages?limit=50", {
      headers: authenticatedHeaders,
    });
    expect(mainHistory.status).toBe(200);
    expect(
      (
        (await mainHistory.json()) as { messages: Array<{ id: string }> }
      ).messages.map((message) => message.id)
    ).toEqual(["d1-exact-main", "d1-padded-main", "d1-space-main"]);

    const paddedQuery = await fetchWorker(
      "/v1/chat-messages?limit=50&chatSessionId=%20chat-main%20",
      { headers: authenticatedHeaders }
    );
    expect(paddedQuery.status).toBe(200);
    expect(
      (
        (await paddedQuery.json()) as { messages: Array<{ id: string }> }
      ).messages.map((message) => message.id)
    ).toEqual([]);
  });

  test("conversation metadata stays bounded and preserves projection semantics", async () => {
    const accountId = "bounded-conversation-metadata";
    const title = `\uFEFF\t${"😀".repeat(130)}${" ".repeat(1000)}tail\u00a0`;
    const overview = `\n${"x".repeat(237)}${" ".repeat(1000)}tail\u3000`;
    const insert = (
      id: string,
      text: string,
      sender: string,
      position: number,
      createdAt: number,
      payload: string | null,
      account = accountId
    ) =>
      env.DB.prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      ).bind(
        id,
        account,
        text,
        sender,
        createdAt,
        sender === "ai" ? "completed" : null,
        position,
        payload
      );
    const payload = JSON.stringify({
      chatSessionId: "large",
      ignored: "p".repeat(30000),
    });
    await env.DB.batch([
      insert("bounded-first", "Initial assistant", "ai", 1, 900, payload),
      insert("bounded-title", title, "human", 2, 800, payload),
      ...Array.from({ length: 75 }, (_, index) =>
        insert(
          `bounded-middle-${index}`,
          "m".repeat(20000),
          "human",
          index + 3,
          1000 + index,
          payload
        )
      ),
      insert("bounded-last", overview, "ai", 100, 500, payload),
      insert("bounded-malformed", "\t\n", "human", 101, 400, "{broken"),
      insert("bounded-null", "ignored", "ai", 102, 410, "null"),
      insert("bounded-array", "ignored", "human", 103, 420, "[]"),
      insert(
        "bounded-empty",
        "ignored",
        "human",
        104,
        430,
        '{"chatSessionId":""}'
      ),
      insert(
        "bounded-type",
        "\u00a0Fallback overview\uFEFF",
        "human",
        105,
        440,
        '{"chatSessionId":{"nested":"wrong"}}'
      ),
      insert(
        "bounded-private",
        "must remain private",
        "human",
        106,
        9999,
        payload,
        "another-account"
      ),
    ]);
    let returnedRows: unknown[] = [];
    const database = new Proxy(env.DB, {
      get(target, property) {
        if (property !== "prepare") return Reflect.get(target, property);
        return (sql: string) => {
          const statement = target.prepare(sql);
          if (!sql.includes("chat_messages")) return statement;
          return {
            bind: (...values: unknown[]) => ({
              all: async () => {
                const result = await statement.bind(...values).all();
                returnedRows = result.results;
                return result;
              },
            }),
          };
        };
      },
    });
    const rows = await readConversations(database, accountId);
    expect(returnedRows).toHaveLength(2);
    expect(JSON.stringify(returnedRows).length).toBeLessThan(9000);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      id: "chat:large",
      title: `${"😀".repeat(130)}${" ".repeat(107)}...`,
      overview: `${overview.trim().slice(0, 237)}...`,
      createdAt: 900,
      updatedAt: 500,
      startedAt: 900,
      finishedAt: null,
      status: "in_progress",
    });
    expect(rows[1]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "ignored",
      overview: "Fallback overview",
      createdAt: 400,
      updatedAt: 440,
      finishedAt: null,
      status: "in_progress",
    });
  });

  test("empty chat titles stay visible without inventing a Chat title", async () => {
    const accountId = "empty-chat-title";
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind("empty-chat-title-1", accountId, " \t\n", 1, 1, "{broken")
      .run();
    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "",
      overview: "",
      source: "chat",
      status: "in_progress",
    });
  });

  test("NEXT LINE-only chat titles stay visible without inventing a Chat title", async () => {
    const accountId = "nel-chat-title";
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind("nel-chat-title-1", accountId, "\u0085", 1, 1, "{broken")
      .run();
    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "",
      overview: "",
      source: "chat",
      status: "in_progress",
    });
  });

  test("chat titles omit leading and trailing NEXT LINE", async () => {
    const accountId = "nel-padded-chat-title";
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind(
        "nel-padded-chat-title-1",
        accountId,
        "\u0085Visible title\u0085",
        1,
        1,
        "{broken"
      )
      .run();
    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "Visible title",
      overview: "Visible title",
      source: "chat",
      status: "in_progress",
    });
  });

  test("chat titles skip a NEXT LINE-only first human turn", async () => {
    const accountId = "nel-then-visible-chat-title";
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind("nel-then-visible-1", accountId, "\u0085", 1, 1, "{broken")
      .run();
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind("nel-then-visible-2", accountId, "Visible later", 2, 2, "{broken")
      .run();
    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "Visible later",
      overview: "Visible later",
      source: "chat",
      status: "in_progress",
    });
  });

  test("chat titles do not invent an assistant title after a NEXT LINE-only human turn", async () => {
    const accountId = "nel-then-ai-chat-title";
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind("nel-then-ai-1", accountId, "\u0085", 1, 1, "{broken")
      .run();
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'ai', ?, 'completed', ?, ?)"
    )
      .bind("nel-then-ai-2", accountId, "Assistant words", 2, 2, "{broken")
      .run();
    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "",
      overview: "Assistant words",
      source: "chat",
      status: "in_progress",
    });
  });

  test("chat titles bound Unicode characters matching production left()", async () => {
    const accountId = "emoji-char-bound-chat-title";
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind(
        "emoji-char-bound-fitting",
        accountId,
        "😀".repeat(121),
        1,
        1,
        JSON.stringify({ chatSessionId: "fitting" })
      )
      .run();
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind(
        "emoji-char-bound-oversized",
        accountId,
        "😀".repeat(241),
        2,
        2,
        JSON.stringify({ chatSessionId: "oversized" })
      )
      .run();
    const rows = await readConversations(env.DB, accountId);
    expect(rows.find((row) => row.id === "chat:fitting")).toMatchObject({
      title: "😀".repeat(121),
      overview: "😀".repeat(121),
    });
    expect(rows.find((row) => row.id === "chat:oversized")).toMatchObject({
      title: `${"😀".repeat(237)}...`,
      overview: `${"😀".repeat(237)}...`,
    });
  });

  test("chat overviews skip a NEXT LINE-only last turn", async () => {
    const accountId = "nel-last-chat-overview";
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind("nel-last-overview-1", accountId, "Title speech", 100, 1, "{broken")
      .run();
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'ai', ?, 'completed', ?, ?)"
    )
      .bind("nel-last-overview-2", accountId, "Later speech", 150, 2, "{broken")
      .run();
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
    )
      .bind("nel-last-overview-3", accountId, "\u0085", 200, 3, "{broken")
      .run();
    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "Title speech",
      overview: "Later speech",
      createdAt: 100,
      updatedAt: 200,
      source: "chat",
      status: "in_progress",
    });
  });

  test("conversation projection preserves embedded NUL and duplicate JSON key semantics", async () => {
    const accountId = "nul-conversations";
    const fixtures = [
      {
        session: "\0",
        text: "start\0end",
        payload: JSON.stringify({ chatSessionId: "\0" }),
      },
      {
        session: "a\0b",
        text: `${"x".repeat(235)}\0${"😀".repeat(200)}`,
        payload: JSON.stringify({ chatSessionId: "a\0b" }),
      },
      {
        session: "last",
        text: "\uFEFF Last wins \uFEFF",
        payload: '{"chatSessionId":"first","chatSessionId":"last"}',
      },
      {
        session: "chat-main",
        text: "Non-string last value",
        payload: '{"chatSessionId":"wrong","chatSessionId":null}',
      },
    ];
    await env.DB.batch(
      fixtures.map((fixture, index) =>
        env.DB.prepare(
          "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
        ).bind(
          `nul-conversation-${index}`,
          accountId,
          fixture.text,
          index,
          index,
          fixture.payload
        )
      )
    );
    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(fixtures.length);
    for (const fixture of fixtures) {
      const text = fixture.text.trim();
      const characters = Array.from(text);
      const display =
        characters.length > 240
          ? `${characters.slice(0, 237).join("")}...`
          : text;
      expect(
        rows.find((row) => row.id === `chat:${fixture.session}`)
      ).toMatchObject({ title: display, overview: display });
    }
  });

  test("conversation IDs preserve JSON UTF-16 escapes through D1", async () => {
    const accountId = "surrogate-conversations";
    const fixtures = [
      { session: "\ud800", payload: '{"chatSessionId":"\\ud800"}' },
      { session: "\udfff", payload: '{"chatSessionId":"\\uDFFF"}' },
      {
        session: "a\ud800b\udfffc",
        payload: JSON.stringify({ chatSessionId: "a\ud800b\udfffc" }),
      },
      { session: "😀", payload: '{"chatSessionId":"\\ud83d\\ude00"}' },
      {
        session: "literal😀",
        payload: JSON.stringify({ chatSessionId: "literal😀" }),
      },
      {
        session: "\ud800\ud800\uFEFF",
        payload: JSON.stringify({ chatSessionId: "\ud800\ud800\uFEFF" }),
      },
    ];
    await env.DB.batch(
      fixtures.map((fixture, index) =>
        env.DB.prepare(
          "INSERT INTO chat_messages (id, account_id, text, sender, created_at, position, payload) VALUES (?, ?, 'surrogate', 'human', ?, ?, ?)"
        ).bind(
          `surrogate-id-${index}`,
          accountId,
          index,
          index,
          fixture.payload
        )
      )
    );
    const rows = await readConversations(env.DB, accountId);
    const units = (text: string) =>
      Array.from({ length: text.length }, (_, index) => text.charCodeAt(index));
    expect(rows.map((row) => units(row.id))).toEqual(
      [...fixtures].reverse().map((fixture) => units(`chat:${fixture.session}`))
    );
  });

  test("chat session namespaces cannot collide with recordings or nested prefixes", async () => {
    const accountId = "conversation-namespace-test";
    const recordingId = crypto.randomUUID();
    const sessionIds = [
      `recording:${recordingId}`,
      `chat:recording:${recordingId}`,
      "chat-main",
      "chat:chat-main",
    ];
    for (const [index, sessionId] of sessionIds.entries()) {
      await env.DB.prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, position, payload) VALUES (?, ?, ?, 'human', 1, ?, ?)"
      )
        .bind(
          `namespace-chat-${index}`,
          accountId,
          `Chat ${index}`,
          index + 1,
          JSON.stringify({ chatSessionId: sessionId })
        )
        .run();
    }
    await env.DB.prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, position, payload) VALUES (?, 'foreign-account', 'foreign', 'human', 1, 1, ?)"
    )
      .bind(
        "namespace-foreign",
        JSON.stringify({ chatSessionId: `recording:${recordingId}` })
      )
      .run();
    await env.DB.prepare(
      "INSERT INTO device_sessions (id, account_id, device_id, codec, state, r2_prefix, started_at, ended_at, created_at, updated_at) VALUES (?, ?, 'test-device', 21, 'complete', ?, 1, 1, 1, 1)"
    )
      .bind(recordingId, accountId, `namespace/${recordingId}`)
      .run();
    await env.DB.prepare(
      "INSERT INTO device_transcriptions (session_id, account_id, state, available_at, text, updated_at) VALUES (?, ?, 'completed', 1, 'Recorded words', 1)"
    )
      .bind(recordingId, accountId)
      .run();

    const rows = await readConversations(env.DB, accountId);
    expect(rows).toHaveLength(sessionIds.length + 1);
    expect(new Set(rows.map((row) => row.id)).size).toBe(rows.length);
    expect(rows.find((row) => row.source === "omi")?.id).toBe(
      `recording:${recordingId}`
    );
    expect(
      rows
        .filter((row) => row.source === "chat")
        .map((row) => row.id)
        .sort()
    ).toEqual(sessionIds.map((sessionId) => `chat:${sessionId}`).sort());
    expect(rows.find((row) => row.id === MAIN_CONVERSATION_ID)?.source).toBe(
      "chat"
    );
    expect(await readConversations(env.DB, accountId)).toEqual(rows);

    const walked: string[] = [];
    let cursor: string | undefined;
    for (let index = 0; index < rows.length; index++) {
      const page = paginateConversations(
        await readConversations(env.DB, accountId),
        1,
        cursor
      );
      if (page === "invalid_cursor") throw new Error("Stable cursor rejected");
      expect(page.items).toHaveLength(1);
      const id = page.items[0]!.id;
      expect(walked).not.toContain(id);
      walked.push(id);
      if (index < rows.length - 1) {
        expect(page.window.hasMore).toBe(true);
        expect(page.window.nextCursor).toBe(id);
        cursor = page.window.nextCursor ?? undefined;
      } else {
        expect(page.window.hasMore).toBe(false);
        expect(page.window.nextCursor).toBeNull();
      }
    }
    expect(walked).toEqual(rows.map((row) => row.id));
  });

  test("memories remain non-retryably unavailable because D1 has no memories store", async () => {
    const response = await fetchWorker("/v1/memories", {
      headers: authenticatedHeaders,
    });
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      error: {
        code: "projection_unavailable",
        retryable: false,
        action: "none",
      },
    });
  });
});

describe("D1 chat attachment admit bind", () => {
  test("zero attachments still admit", async () => {
    const response = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("d1-attach-none")),
    });
    expect(response.status).toBe(201);
    const body = (await response.json()) as {
      message: { attachments: unknown[] };
    };
    expect(body.message.attachments).toEqual([]);
  });

  test("chat create with attachments without object storage is nested non-retryable", async () => {
    await insertAttachment({
      id: "d1-att-no-r2",
      accountId: "test-account",
      state: "ingested",
    });
    const response = await handler.fetch(
      new Request("https://worker.test/v1/chat-messages", {
        method: "POST",
        headers: {
          ...authenticatedHeaders,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          ...chatCreate("d1-attach-no-r2"),
          attachmentIds: ["d1-att-no-r2"],
        }),
      }),
      {
        ...env,
        API_TOKEN: "test-token",
        AI: { run: async () => ({ response: "AI reply" }) },
        ATTACHMENTS: undefined,
      } as never,
      createExecutionContext()
    );

    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBeNull();
    expect((await response.json()) as unknown).toEqual({
      error: {
        code: "service_unavailable",
        retryable: false,
        action: "none",
      },
    });
  });

  test("foreign and incomplete attachments stay rejected", async () => {
    await insertAttachment({
      id: "d1-att-foreign",
      accountId: "other-account",
      state: "ingested",
    });
    await insertAttachment({
      id: "d1-att-staged",
      accountId: "test-account",
      state: "staged",
    });

    const foreign = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("d1-attach-foreign"),
        attachmentIds: ["d1-att-foreign"],
      }),
    });
    const incomplete = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("d1-attach-staged"),
        attachmentIds: ["d1-att-staged"],
      }),
    });

    expect(foreign.status).toBe(422);
    expect((await foreign.json()) as { error: { code: string } }).toEqual({
      error: {
        code: "attachment_rejected",
        retryable: false,
        action: "edit_request",
      },
    });
    expect(incomplete.status).toBe(422);
    expect((await incomplete.json()) as { error: { code: string } }).toEqual({
      error: {
        code: "attachment_rejected",
        retryable: false,
        action: "edit_request",
      },
    });
  });

  test("completed same-account attachments bind onto the admitted message", async () => {
    await insertAttachment({
      id: "d1-att-ready",
      accountId: "test-account",
      state: "ingested",
      displayName: "notes.pdf",
      mimeType: "application/pdf",
      sizeBytes: 2048,
    });

    const response = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("d1-attach-ready"),
        attachmentIds: ["d1-att-ready"],
      }),
    });
    expect(response.status).toBe(201);
    const body = (await response.json()) as {
      message: {
        id: string;
        attachments: Array<{
          id: string;
          displayName: string;
          mediaType: string;
          sizeBytes: number;
          contentReference: string | null;
        }>;
      };
    };
    expect(body.message.id).toBe("d1-attach-ready");
    expect(body.message.attachments).toEqual([
      {
        id: "d1-att-ready",
        displayName: "notes.pdf",
        mediaType: "application/pdf",
        sizeBytes: 2048,
        contentReference: "d1-att-ready",
      },
    ]);

    const row = await env.DB.prepare(
      "SELECT state, bound_message_id, account_id FROM chat_attachments WHERE id = ?"
    )
      .bind("d1-att-ready")
      .first<{
        state: string;
        bound_message_id: string | null;
        account_id: string;
      }>();
    expect(row).toEqual({
      state: "bound",
      bound_message_id: "d1-attach-ready",
      account_id: "test-account",
    });

    const stored = await env.DB.prepare(
      "SELECT payload FROM chat_messages WHERE id = ?"
    )
      .bind("d1-attach-ready")
      .first<{ payload: string }>();
    const payload = JSON.parse(stored!.payload) as {
      attachments: Array<{ id: string }>;
    };
    expect(payload.attachments).toEqual([
      expect.objectContaining({ id: "d1-att-ready", displayName: "notes.pdf" }),
    ]);
  });
});

describe("generation reads bound attachment bytes", () => {
  test("bound text/plain R2 bytes appear in the mocked AI prompt", async () => {
    const r2Key = "attachments/test-account/d1-att-text";
    await insertAttachment({
      id: "d1-att-text",
      accountId: "test-account",
      state: "ingested",
      displayName: "notes.txt",
      mimeType: "text/plain",
      sizeBytes: 18,
    });
    await env.ATTACHMENTS.put(r2Key, "plain file contents", {
      httpMetadata: { contentType: "text/plain" },
    });

    const admitted = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("d1-gen-text", "summarize the file"),
        attachmentIds: ["d1-att-text"],
      }),
    });
    expect(admitted.status).toBe(201);

    const captured: string[] = [];
    const stub = env.ACCOUNTS.getByName("test-account");
    await runInDurableObject(stub, (instance) => {
      Object.defineProperty(instance, "env", {
        configurable: true,
        value: {
          ...(instance as unknown as { env: Record<string, unknown> }).env,
          AI: {
            run: async (
              _model: string,
              input: { messages?: Array<{ role: string; content: string }> }
            ) => {
              const user = input.messages?.find(
                (message) => message.role === "user"
              );
              if (user !== undefined) captured.push(user.content);
              return { response: "ok" };
            },
          },
        },
      });
    });
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect(captured).toHaveLength(1);
    expect(captured[0]).toContain("summarize the file");
    expect(captured[0]).toContain("plain file contents");
  });

  test("missing bound text fails generation instead of dropping bytes or leaking foreign files", async () => {
    await insertAttachment({
      id: "d1-att-foreign-text",
      accountId: "other-account",
      state: "bound",
      boundMessageId: "d1-gen-iso",
      displayName: "secret.txt",
      mimeType: "text/plain",
      sizeBytes: 12,
    });
    await env.ATTACHMENTS.put(
      "attachments/other-account/d1-att-foreign-text",
      "foreign-secret-bytes",
      { httpMetadata: { contentType: "text/plain" } }
    );
    await insertAttachment({
      id: "d1-att-missing-text",
      accountId: "test-account",
      state: "ingested",
      displayName: "gone.txt",
      mimeType: "text/plain",
      sizeBytes: 4,
    });

    const admitted = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("d1-gen-iso", "hello without file"),
        attachmentIds: ["d1-att-missing-text"],
      }),
    });
    expect(admitted.status).toBe(201);
    const admittedBody = (await admitted.json()) as {
      generation: { id: string };
    };

    const captured: string[] = [];
    const stub = env.ACCOUNTS.getByName("test-account");
    await runInDurableObject(stub, (instance) => {
      Object.defineProperty(instance, "env", {
        configurable: true,
        value: {
          ...(instance as unknown as { env: Record<string, unknown> }).env,
          AI: {
            run: async (
              _model: string,
              input: { messages?: Array<{ role: string; content: string }> }
            ) => {
              const user = input.messages?.find(
                (message) => message.role === "user"
              );
              if (user !== undefined) captured.push(user.content);
              return { response: "ok" };
            },
          },
        },
      });
    });
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect(captured).toEqual([]);
    expect(captured.join("")).not.toContain("foreign-secret-bytes");
    expect(
      await terminalEvent(env.DB, "test-account", admittedBody.generation.id)
    ).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
  });
});
