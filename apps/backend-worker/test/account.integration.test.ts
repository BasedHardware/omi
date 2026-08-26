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

const attachmentSchema = [
  "CREATE TABLE IF NOT EXISTS chat_attachments (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, op_id TEXT NOT NULL, display_name TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, state TEXT NOT NULL CHECK (state IN ('staged', 'uploaded', 'ingesting', 'ingested', 'invalid', 'bound', 'expired')), r2_key TEXT NOT NULL, expires_at INTEGER NOT NULL, bound_message_id TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)",
  "CREATE INDEX IF NOT EXISTS chat_attachments_account ON chat_attachments (account_id)",
];

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-account",
};

const create = (id: string) => ({
  op: "create" as const,
  opId: `op-${id}`,
  id,
  at: 1,
  text: "hello",
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
      AI: { run: async () => ({ response: "test response" }) },
    } as never,
    createExecutionContext()
  );

beforeEach(async () => {
  for (const statement of chatSchema) {
    await env.DB.exec(statement);
  }
  await env.DB.exec(taskSchema);
  for (const statement of attachmentSchema) {
    await env.DB.exec(statement);
  }
  await env.DB.prepare("DELETE FROM chat_messages").run();
  await env.DB.prepare("DELETE FROM chat_admissions").run();
  await env.DB.prepare("DELETE FROM chat_generation_events").run();
  await env.DB.prepare("DELETE FROM chat_attachments").run();
});

describe("AccountBackend D1-backed coordination", () => {
  test("settings reflects env config and D1 admission count without resetting usage", async () => {
    const before = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });
    expect((await before.json()) as unknown).toMatchObject({
      identity: {
        displayName: "Test Account",
        email: "test@example.invalid",
      },
      entitlement: { used: 0, limit: 10, limitReached: false },
    });

    const admitted = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(create("first")),
    });
    expect(admitted.status).toBe(201);

    const after = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });
    expect((await after.json()) as unknown).toMatchObject({
      identity: {
        displayName: "Test Account",
        email: "test@example.invalid",
      },
      entitlement: { used: 1, limit: 10, limitReached: false },
    });
  });

  test("admission persists canonical state to D1 and schedules recoverable generation work", async () => {
    const admission = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(create("message")),
    });
    expect(admission.status).toBe(201);
    const admissionBody = (await admission.json()) as {
      message: { id: string };
    };
    expect(admissionBody.message.id).toBe("message");

    const history = await fetchWorker("/v1/chat-messages?limit=50", {
      headers: authenticatedHeaders,
    });
    const historyBody = (await history.json()) as {
      messages: Array<{ id: string }>;
    };
    expect(historyBody.messages).toHaveLength(1);
    expect(historyBody.messages[0]!.id).toBe("message");

    const stub = env.ACCOUNTS.getByName("test-account");
    expect(
      await runInDurableObject(stub, (_instance, state) =>
        state.storage.getAlarm()
      )
    ).not.toBeNull();

    const replay = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(create("message")),
    });
    expect(replay.status).toBe(200);

    const settings = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });
    expect((await settings.json()) as unknown).toMatchObject({
      entitlement: { used: 1 },
    });
  });

  test("provider failure terminates its generation and advances queued work", async () => {
    const first = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(create("first")),
    });
    const second = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(create("second")),
    });
    expect(first.status).toBe(201);
    expect(second.status).toBe(201);

    const firstBody = (await first.json()) as { generation: { id: string } };
    const secondBody = (await second.json()) as { generation: { id: string } };

    const stub = env.ACCOUNTS.getByName("test-account");
    await runInDurableObject(stub, (instance) => {
      Object.defineProperty(instance, "env", {
        configurable: true,
        value: {
          ...(instance as unknown as { env: Record<string, unknown> }).env,
          AI: {
            run: async () => {
              throw new Error("provider unavailable");
            },
          },
        },
      });
    });
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    const failed = await stub.fetch(
      `https://account.internal/events?generationId=${firstBody.generation.id}`
    );
    expect(await failed.text()).toContain("event: failed");
    expect(
      await runInDurableObject(stub, (_instance, state) =>
        state.storage.getAlarm()
      )
    ).not.toBeNull();

    await runInDurableObject(stub, (instance) => {
      Object.defineProperty(instance, "env", {
        configurable: true,
        value: {
          ...(instance as unknown as { env: Record<string, unknown> }).env,
          AI: { run: async () => ({ response: "second completed" }) },
        },
      });
    });
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    const completed = await stub.fetch(
      `https://account.internal/events?generationId=${secondBody.generation.id}`
    );
    expect(await completed.text()).toContain("event: done");

    const history = await fetchWorker("/v1/chat-messages?limit=50", {
      headers: authenticatedHeaders,
    });
    const historyBody = (await history.json()) as {
      messages: Array<{ text: string }>;
    };
    expect(historyBody.messages.map((message) => message.text)).toEqual([
      "hello",
      "hello",
      "second completed",
    ]);
  });
});
