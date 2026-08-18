import { createExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { runDurableObjectAlarm, runInDurableObject } from "cloudflare:test";
import { beforeEach, describe, expect, test } from "vitest";

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

const taskSchema =
  "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, description TEXT NOT NULL, completed INTEGER NOT NULL, completed_at INTEGER, due_at INTEGER, owner TEXT, source TEXT NOT NULL, provenance TEXT NOT NULL, sort_order REAL NOT NULL, indent_level INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, revision TEXT)";

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-client",
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
  await env.DB.exec(taskSchema);
  await env.DB.prepare("DELETE FROM chat_messages").run();
  await env.DB.prepare("DELETE FROM chat_admissions").run();
  await env.DB.prepare("DELETE FROM chat_generation_events").run();

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
      entitlement: { used: number; limit: number };
    };
    expect(beforeBody.entitlement.used).toBe(0);

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
