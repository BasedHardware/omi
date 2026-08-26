import { createExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { runDurableObjectAlarm, runInDurableObject } from "cloudflare:test";
import { beforeEach, describe, expect, test } from "vitest";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import { MAIN_CONVERSATION_ID } from "../src/conversations";
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

  test("memories remain an empty recall page because D1 has no memories store", async () => {
    const response = await fetchWorker("/v1/memories", {
      headers: authenticatedHeaders,
    });
    expect(response.status).toBe(200);
    const body = await response.text();
    const page = parseSynthesizedPageJson(body);
    expect(page).not.toBeNull();
    expect(page?.items).toEqual([]);
    expect(page?.completeness.status).toBe("complete");
    expect(page?.absence).toEqual({ kind: "query_gap" });
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
