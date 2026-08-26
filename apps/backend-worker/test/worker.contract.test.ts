import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";
import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";
import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";
import {
  parseChatGenerationEventStream,
  wireToChatAdmissionEnvelope,
  wireToChatHistoryEnvelope,
} from "@omi-core/adapters-platform";

import type { AccountBackend } from "../src/account";
import {
  CONVERSATIONS_FRONTIER,
  CONVERSATIONS_READ_CONTRACT_VERSION,
  MAIN_CONVERSATION_ID,
} from "../src/conversations";
import { CHAT_CAPABILITIES, isChatCreate } from "../src/wire";
import { createD1Mock } from "./d1-mock";

let handler: typeof import("../src/index")["default"];
let accountBackend: typeof AccountBackend;

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({
    DurableObject: class {},
  }));
  const worker = await import("../src/index");
  handler = worker.default;
  accountBackend = worker.AccountBackend;
});

const accountCalls: string[] = [];
const identity = { displayName: "Test Account", email: "test@example.invalid" };
const initialEntitlement = {
  planLabel: "Metered",
  limitKey: "chat",
  used: 0,
  limit: 1,
  limitReached: false,
  upgradeAvailable: true,
};
const admissions = new Map<
  string,
  {
    payload: string;
    message: Record<string, unknown>;
    generation: { id: string };
  }
>();
const canonicalMessage = (
  input: Record<string, unknown>,
  sender: "human" | "ai" = "human"
) => ({
  id: input["id"],
  text: input["text"],
  sender,
  type: input["type"] ?? "text",
  createdAt: input["at"],
  updatedAt: input["at"],
  chatSessionId: input["chatSessionId"] ?? null,
  appId: input["appId"] ?? null,
  journalRevision: input["journalRevision"],
  payloadHash: "sha256:test",
  messageSource: input["messageSource"] ?? "desktop_chat",
  rating: null,
  reported: false,
  generationOutcome: sender === "human" ? null : "completed",
  revision: "1",
  attachments: [],
});
let cancellation: "accepted" | "terminal" | "not_found" = "accepted";
let d1Mock: D1Database;
const accountStub = {
  admit: async (
    _accountId: string,
    input: Record<string, unknown>,
    chatLimit: number
  ) => {
    const payload = JSON.stringify(input);
    const prior = admissions.get(String(input["id"]));
    if (prior !== undefined) {
      if (prior.payload !== payload) return "conflict" as const;
      return { ...prior, created: false };
    }
    if (admissions.size >= chatLimit) return "entitlement" as const;
    const attachmentRows: Array<{
      id: string;
      displayName: string;
      mediaType: string;
      sizeBytes: number;
      contentReference: string | null;
    }> = [];
    const requestedIds = Array.isArray(input["attachmentIds"])
      ? input["attachmentIds"]
      : [];
    for (const attachmentId of requestedIds) {
      const row = await d1Mock
        .prepare(
          "SELECT id, display_name, media_type, size_bytes FROM chat_attachments WHERE id = ? AND account_id = ?"
        )
        .bind(String(attachmentId), "test-account")
        .first<{
          id: string;
          display_name: string;
          media_type: string;
          size_bytes: number;
        }>();
      if (row === null) continue;
      attachmentRows.push({
        id: row.id,
        displayName: row.display_name,
        mediaType: row.media_type,
        sizeBytes: row.size_bytes,
        contentReference: row.id,
      });
    }
    const admission = {
      payload,
      message: { ...canonicalMessage(input), attachments: attachmentRows },
      generation: { id: `generation-${String(input["id"])}` },
    };
    admissions.set(String(input["id"]), admission);
    await d1Mock
      .prepare(
        "INSERT OR IGNORE INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        String(input["id"]),
        "test-account",
        String(input["opId"]),
        payload,
        admission.generation.id
      )
      .run();
    return { ...admission, created: true };
  },
  cancel: async (_accountId: string, _generationId: string) => cancellation,
  fetch: async (request: Request) =>
    new URL(request.url).searchParams.get("generationId") === "missing"
      ? new Response(null, { status: 404 })
      : new Response(
          'id: 1\nevent: snapshot\ndata: {"kind":"snapshot","text":""}\n\n'
        ),
};

const env = {
  ENVIRONMENT: "test",
  API_TOKEN: "test-token",
  STAGING_ACCOUNT_ID: "test-account",
  ACCOUNTS: {
    getByName: (name: string) => {
      accountCalls.push(`account:${name}`);
      return accountStub;
    },
  },
  AI_MODEL: "test-model",
  AI: { run: async () => ({ response: "test response" }) },
  STAGING_DISPLAY_NAME: identity.displayName,
  STAGING_EMAIL: identity.email,
  STAGING_PLAN_LABEL: initialEntitlement.planLabel,
  STAGING_CHAT_LIMIT: initialEntitlement.limit,
  OBSERVABILITY_SINK_MODE: "cloudflare_only",
  OPENROUTER_GATEWAY_ENABLED: "false",
  OPENROUTER_MODEL: "openai/gpt-5.6-luna",
  get DB() {
    return d1Mock;
  },
};

const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};

const fetchWorker = (path: string, init?: RequestInit) =>
  handler.fetch(
    new Request(`https://worker.test${path}`, init),
    env as never,
    executionContext as never
  );

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-client",
};

const chatCreate = (id: string) => ({
  op: "create",
  opId: `op-${id}`,
  id,
  at: 1,
  text: "hello",
  sender: "human",
  journalRevision: 0,
  appId: null,
  chatSessionId: null,
  attachmentIds: [],
});

const emptyConversationPage = () => ({
  contractVersion: CONVERSATIONS_READ_CONTRACT_VERSION,
  items: [],
  window: {
    status: "complete",
    complete: true,
    hasMore: false,
    nextCursor: null,
  },
  completeness: {
    version: "conversations-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: CONVERSATIONS_FRONTIER,
      newestAppliedFrontier: CONVERSATIONS_FRONTIER,
      missingAppliedFrontierReason: null,
    },
  },
  absence: { kind: "query_gap" },
});

const emptyRecallPage = () => ({
  contractVersion: "1.0.0",
  items: [],
  window: {
    status: "complete",
    complete: true,
    hasMore: false,
    nextCursor: null,
  },
  completeness: {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: "frontier-v1:declared",
      newestSearchedAcceptedFrontier: null,
      missingAcceptedFrontierReason: "no_accepted_work",
      newestSearchedStmFrontier: null,
      missingStmFrontierReason: "no_eligible_stm",
    },
  },
  absence: { kind: "query_gap" },
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
  await d1Mock
    .prepare(
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

const insertChatMessage = async (input: {
  id: string;
  accountId: string;
  text: string;
  createdAt: number;
  position: number;
  chatSessionId: string | null;
  sender?: "human" | "ai";
  generationOutcome?: "completed" | "cancelled" | null;
}) => {
  const sender = input.sender ?? "human";
  const generationOutcome =
    input.generationOutcome ?? (sender === "human" ? null : "completed");
  await d1Mock
    .prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    .bind(
      input.id,
      input.accountId,
      input.text,
      sender,
      input.createdAt,
      generationOutcome,
      input.position,
      JSON.stringify({
        id: input.id,
        text: input.text,
        sender,
        type: "text",
        createdAt: input.createdAt,
        updatedAt: input.createdAt,
        chatSessionId: input.chatSessionId,
        appId: null,
        journalRevision: 0,
        payloadHash: "sha256:test",
        messageSource:
          sender === "human" ? "desktop_chat" : "assistant_generation",
        rating: null,
        reported: false,
        generationOutcome,
        revision: String(input.position),
        attachments: [],
      })
    )
    .run();
};

beforeEach(() => {
  d1Mock = createD1Mock();
  admissions.clear();
  cancellation = "accepted";
  accountCalls.length = 0;
});

describe("worker request contract", () => {
  test("health and readiness do not require account storage", async () => {
    const health = await fetchWorker("/health");
    const ready = await fetchWorker("/ready");

    expect(health.status).toBe(200);
    expect((await health.json()) as unknown).toEqual({
      status: "ok",
      environment: "test",
    });
    expect(ready.status).toBe(200);
    expect((await ready.json()) as unknown).toEqual({
      status: "ready",
      environment: "test",
      observability_sink_mode: "cloudflare_only",
    });
    expect(health.headers.get("cache-control")).toBe("no-store");
    expect(accountCalls).toEqual([]);
  });

  test("request telemetry is correlation-safe and excludes query content", async () => {
    const messages: unknown[][] = [];
    const originalLog = console.log;
    console.log = (...args: unknown[]) => messages.push(args);
    try {
      const response = await fetchWorker("/health?private=must-not-appear");
      const requestId = response.headers.get("x-omi-request-id");

      expect(response.status).toBe(200);
      expect(requestId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
      );
      expect(messages).toHaveLength(1);
      const [eventPayload] = messages[0]!;
      expect(messages[0]).toHaveLength(1);
      const event = JSON.parse(String(eventPayload)) as Record<string, unknown>;
      expect(event).toMatchObject({
        event: "request_completed",
        request_id: requestId,
        method: "GET",
        route: "/health",
        status: 200,
      });
      expect(event).not.toHaveProperty("path");
      expect(JSON.stringify(event)).not.toContain("must-not-appear");
    } finally {
      console.log = originalLog;
    }
  });

  test("readiness fails closed when required configuration is absent", async () => {
    const response = await handler.fetch(
      new Request("https://worker.test/ready"),
      { ...env, API_TOKEN: "" } as never,
      executionContext as never
    );

    expect(response.status).toBe(503);
    expect((await response.json()) as unknown).toEqual({
      error: {
        code: "service_unavailable",
        retryable: true,
        action: "retry",
      },
    });
  });

  test("readiness fails closed when the observability sink mode is absent", async () => {
    const response = await handler.fetch(
      new Request("https://worker.test/ready"),
      { ...env, OBSERVABILITY_SINK_MODE: "" } as never,
      executionContext as never
    );

    expect(response.status).toBe(503);
  });

  test("configuration failures log a route template rather than user input", async () => {
    const messages: unknown[][] = [];
    const originalError = console.error;
    console.error = (...args: unknown[]) => messages.push(args);
    try {
      const response = await handler.fetch(
        new Request("https://worker.test/v1/settings?private=must-not-appear", {
          headers: authenticatedHeaders,
        }),
        { ...env, API_TOKEN: "" } as never,
        executionContext as never
      );

      expect(response.status).toBe(401);
      const [eventPayload] = messages[0]!;
      const event = JSON.parse(String(eventPayload)) as Record<string, unknown>;
      expect(event).toMatchObject({
        event: "configuration_not_ready",
        route: "/v1/*",
      });
      expect(event).not.toHaveProperty("path");
      expect(JSON.stringify(event)).not.toContain("must-not-appear");
    } finally {
      console.error = originalError;
    }
  });

  // `/ready` reporting 503 is a signal, not an enforcement point: Cloudflare
  // routes request traffic regardless of what it returns, so the protected
  // surface needs its own coverage under the same unprovisioned configuration.
  //
  // These cases send `authorization: Bearer ` — a bearer prefix with an EMPTY
  // credential. It encodes to the same empty byte sequence an absent secret
  // encodes to, so the constant-time comparison alone reports a match and
  // authenticates an anonymous caller.
  //
  // The header must bypass `Headers`: bun strips optional whitespace, turning
  // "Bearer " into "Bearer", which fails the prefix check and never reaches the
  // comparison — a normalizing Headers cannot express this input at all.
  // workerd delivers the trailing space verbatim; issuing this exact request
  // over a raw socket against `wrangler dev` returned 200 and a full settings
  // body before this guard existed. The view below reproduces that production
  // input faithfully; it does not weaken the assertion.
  const onTheWireRequest = (
    path: string,
    headers: Record<string, string>
  ): Request => {
    const request = new Request(`https://worker.test${path}`);
    Object.defineProperty(request, "headers", {
      value: new Map(
        Object.entries(headers).map(([name, value]) => [
          name.toLowerCase(),
          value,
        ])
      ),
    });
    return request;
  };

  const anonymousHeaders = {
    authorization: "Bearer ",
    "x-omi-client-id": "test-client",
  };

  test.each([
    ["absent", undefined],
    ["empty", ""],
  ])(
    "an %s API_TOKEN secret refuses an empty bearer credential",
    async (_label, secret) => {
      const response = await handler.fetch(
        onTheWireRequest("/v1/settings", anonymousHeaders),
        { ...env, API_TOKEN: secret } as never,
        executionContext as never
      );

      expect(response.status).toBe(401);
      expect((await response.json()) as unknown).toEqual({
        error: {
          code: "unauthorized",
          retryable: false,
          action: "reauthenticate",
        },
      });
      // The account must never be resolved: refusal precedes storage access.
      expect(accountCalls).toEqual([]);
    }
  );

  test("an unprovisioned API_TOKEN secret refuses every protected route", async () => {
    const paths = [
      "/v1/settings",
      "/v1/chat-messages",
      "/v1/conversations",
      "/v1/memories",
      "/v1/tasks",
    ];
    const statuses = await Promise.all(
      paths.map(
        async (path) =>
          (
            await handler.fetch(
              onTheWireRequest(path, anonymousHeaders),
              { ...env, API_TOKEN: undefined } as never,
              executionContext as never
            )
          ).status
      )
    );

    expect(statuses).toEqual(paths.map(() => 401));
    expect(accountCalls).toEqual([]);
  });

  test("a provisioned API_TOKEN secret still admits its own credential", async () => {
    // The guard must fail closed on absent configuration without also breaking
    // the configured path it protects.
    const response = await fetchWorker("/v1/conversations", {
      headers: authenticatedHeaders,
    });

    expect(response.status).toBe(200);
    expect((await response.json()) as unknown).toEqual(emptyConversationPage());
  });

  test("a provisioned secret still refuses the empty bearer credential", async () => {
    const response = await handler.fetch(
      onTheWireRequest("/v1/settings", anonymousHeaders),
      env as never,
      executionContext as never
    );

    expect(response.status).toBe(401);
  });

  test("protected routes reject absent credentials before account access", async () => {
    const response = await fetchWorker("/v1/chat-messages");

    expect(response.status).toBe(401);
    expect((await response.json()) as unknown).toEqual({
      error: {
        code: "unauthorized",
        retryable: false,
        action: "reauthenticate",
      },
    });
    expect(accountCalls).toEqual([]);
  });

  test("protected routes reject invalid credentials and missing client identity", async () => {
    const invalidToken = await fetchWorker("/v1/conversations", {
      headers: { ...authenticatedHeaders, authorization: "Bearer wrong-token" },
    });
    const missingClient = await fetchWorker("/v1/conversations", {
      headers: { authorization: authenticatedHeaders.authorization },
    });

    expect(invalidToken.status).toBe(401);
    expect(missingClient.status).toBe(400);
    expect((await missingClient.json()) as unknown).toEqual({
      error: { code: "bad_request", retryable: false, action: "edit_request" },
    });
    expect(accountCalls).toEqual([]);
  });

  test("wired chat conversations and unwired memories stay honest empty successes", async () => {
    const conversations = await fetchWorker("/v1/conversations", {
      headers: authenticatedHeaders,
    });
    const memories = await fetchWorker("/v1/memories", {
      headers: authenticatedHeaders,
    });
    const tasks = await fetchWorker("/v1/tasks", {
      headers: authenticatedHeaders,
    });

    expect(conversations.status).toBe(200);
    expect(memories.status).toBe(200);
    expect((await conversations.json()) as unknown).toEqual(
      emptyConversationPage()
    );
    const memoriesBody = await memories.text();
    expect(JSON.parse(memoriesBody) as unknown).toEqual(emptyRecallPage());
    expect(parseSynthesizedPageJson(memoriesBody)).not.toBeNull();
    const tasksBody = await tasks.text();
    expect(JSON.parse(tasksBody) as unknown).toEqual({
      contractVersion: "1.0.0",
      items: [],
      window: {
        status: "complete",
        complete: true,
        hasMore: false,
        nextCursor: null,
      },
      completeness: {
        version: "tasks-completeness-v1",
        status: "complete",
        reasons: [],
        frontiers: {
          declaredFrontier: "frontier-v1:tasks-declared",
          newestAppliedFrontier: "frontier-v1:tasks-declared",
          missingAppliedFrontierReason: null,
        },
      },
      absence: { kind: "query_gap" },
    });
    expect(parseTaskPageJson(tasksBody)).not.toBeNull();
  });

  test("conversations project grouped D1 chat sessions, not a 503", async () => {
    await insertChatMessage({
      id: "main-one",
      accountId: "test-account",
      text: "hello from main",
      createdAt: 1_000,
      position: 1,
      chatSessionId: null,
    });
    await insertChatMessage({
      id: "main-two",
      accountId: "test-account",
      text: "follow up",
      createdAt: 2_000,
      position: 2,
      chatSessionId: null,
    });
    await insertChatMessage({
      id: "session-one",
      accountId: "test-account",
      text: "other session",
      createdAt: 3_000,
      position: 3,
      chatSessionId: "session-alpha",
    });
    await insertChatMessage({
      id: "foreign",
      accountId: "other-account",
      text: "must not leak",
      createdAt: 4_000,
      position: 1,
      chatSessionId: "session-foreign",
    });

    const envelope = await fetchWorker("/v1/conversations?limit=50", {
      headers: authenticatedHeaders,
    });
    expect(envelope.status).toBe(200);
    const page = (await envelope.json()) as {
      items: Array<{ id: string; title: string; overview: string }>;
      window: {
        status: string;
        complete: boolean;
        hasMore: boolean;
        nextCursor: string | null;
      };
      absence: { kind: string } | null;
    };
    expect(page.items.map((item) => item.id)).toEqual([
      "session-alpha",
      MAIN_CONVERSATION_ID,
    ]);
    expect(page.items[0]).toMatchObject({
      id: "session-alpha",
      title: "other session",
      overview: "other session",
      source: "chat",
      status: "in_progress",
      discarded: false,
      starred: false,
      visibility: "private",
      isLocked: false,
      folderId: null,
      revision: null,
    });
    expect(page.items[1]).toMatchObject({
      id: MAIN_CONVERSATION_ID,
      title: "hello from main",
      overview: "follow up",
      createdAt: 1_000,
      updatedAt: 2_000,
    });
    expect(page.window).toEqual({
      status: "complete",
      complete: true,
      hasMore: false,
      nextCursor: null,
    });
    expect(page.absence).toBeNull();

    const legacy = await fetchWorker("/v1/conversations?limit=50&offset=0", {
      headers: authenticatedHeaders,
    });
    expect(legacy.status).toBe(200);
    const records = (await legacy.json()) as Array<{
      id: string;
      structured: { title: string; overview: string };
      created_at: string;
      is_locked: boolean;
      folder_id: string | null;
    }>;
    expect(records).toHaveLength(2);
    expect(records[0]).toMatchObject({
      id: "session-alpha",
      structured: { title: "other session", overview: "other session" },
      is_locked: false,
      folder_id: null,
    });
    expect(records[1]?.id).toBe(MAIN_CONVERSATION_ID);
    expect(Number.isFinite(Date.parse(records[0]!.created_at))).toBe(true);
  });

  test("conversation pagination and query validation match neighboring list routes", async () => {
    await insertChatMessage({
      id: "page-a",
      accountId: "test-account",
      text: "first session",
      createdAt: 10,
      position: 1,
      chatSessionId: "session-a",
    });
    await insertChatMessage({
      id: "page-b",
      accountId: "test-account",
      text: "second session",
      createdAt: 20,
      position: 2,
      chatSessionId: "session-b",
    });

    const first = await fetchWorker("/v1/conversations?limit=1", {
      headers: authenticatedHeaders,
    });
    expect(first.status).toBe(200);
    const firstPage = (await first.json()) as {
      items: Array<{ id: string }>;
      window: { status: string; hasMore: boolean; nextCursor: string | null };
    };
    expect(firstPage.items.map((item) => item.id)).toEqual(["session-b"]);
    expect(firstPage.window.hasMore).toBe(true);
    expect(firstPage.window.nextCursor).toBe("session-b");

    const second = await fetchWorker(
      `/v1/conversations?limit=1&cursor=${encodeURIComponent("session-b")}`,
      { headers: authenticatedHeaders }
    );
    expect(second.status).toBe(200);
    const secondPage = (await second.json()) as {
      items: Array<{ id: string }>;
      window: {
        status: string;
        complete: boolean;
        hasMore: boolean;
        nextCursor: string | null;
      };
    };
    expect(secondPage.items.map((item) => item.id)).toEqual(["session-a"]);
    expect(secondPage.window).toEqual({
      status: "complete",
      complete: true,
      hasMore: false,
      nextCursor: null,
    });

    const offsetPage = await fetchWorker("/v1/conversations?limit=1&offset=1", {
      headers: authenticatedHeaders,
    });
    expect(offsetPage.status).toBe(200);
    expect((await offsetPage.json()) as Array<{ id: string }>).toEqual([
      expect.objectContaining({ id: "session-a" }),
    ]);

    const invalidLimit = await fetchWorker("/v1/conversations?limit=0", {
      headers: authenticatedHeaders,
    });
    const invalidCursor = await fetchWorker("/v1/conversations?cursor=", {
      headers: authenticatedHeaders,
    });
    const unknownCursor = await fetchWorker(
      "/v1/conversations?cursor=missing-session",
      { headers: authenticatedHeaders }
    );
    const extra = await fetchWorker("/v1/conversations?limit=1&extra=1", {
      headers: authenticatedHeaders,
    });
    expect(invalidLimit.status).toBe(400);
    expect(invalidCursor.status).toBe(400);
    expect(unknownCursor.status).toBe(400);
    expect(extra.status).toBe(400);
  });

  test("memories stay an honest empty recall page because no store exists", async () => {
    const response = await fetchWorker("/v1/memories?limit=50", {
      headers: authenticatedHeaders,
    });
    expect(response.status).toBe(200);
    const body = await response.text();
    expect(parseSynthesizedPageJson(body)).not.toBeNull();
    expect(JSON.parse(body) as unknown).toEqual(emptyRecallPage());

    const emptyCursor = await fetchWorker("/v1/memories?cursor=", {
      headers: authenticatedHeaders,
    });
    const extra = await fetchWorker("/v1/memories?limit=1&extra=1", {
      headers: authenticatedHeaders,
    });
    expect(emptyCursor.status).toBe(400);
    expect(extra.status).toBe(400);
  });

  test("chat history validates pagination before resolving the account", async () => {
    const invalidLimit = await fetchWorker("/v1/chat-messages?limit=0", {
      headers: authenticatedHeaders,
    });
    const unsupportedCursor = await fetchWorker(
      "/v1/chat-messages?olderCursor=",
      {
        headers: authenticatedHeaders,
      }
    );

    expect(invalidLimit.status).toBe(400);
    expect(unsupportedCursor.status).toBe(400);
    expect(accountCalls).toEqual([]);
  });

  test("chat history reads persisted messages from D1 without resolving the DO", async () => {
    const response = await fetchWorker("/v1/chat-messages?limit=100", {
      headers: authenticatedHeaders,
    });

    expect(response.status).toBe(200);
    expect((await response.json()) as unknown).toEqual({
      messages: [],
      page: { olderCursor: null, hasOlder: false },
      capabilities: CHAT_CAPABILITIES,
    });
    expect(
      wireToChatHistoryEnvelope({
        messages: [],
        page: { olderCursor: null, hasOlder: false },
        capabilities: CHAT_CAPABILITIES,
      })
    ).not.toBeNull();
    expect(accountCalls).toEqual([]);
  });

  test("credential rotation preserves the configured account identity", async () => {
    const response = await handler.fetch(
      new Request("https://worker.test/v1/chat-messages?limit=10", {
        headers: {
          authorization: "Bearer rotated-token",
          "x-omi-client-id": "test-client",
        },
      }),
      { ...env, API_TOKEN: "rotated-token" } as never,
      executionContext as never
    );

    expect(response.status).toBe(200);
  });

  test("unknown routes use the stable backend error envelope", async () => {
    const response = await fetchWorker("/unknown");

    expect(response.status).toBe(404);
    expect((await response.json()) as unknown).toEqual({
      error: { code: "not_found", retryable: false, action: "edit_request" },
    });
  });

  test("chat history rejects repeated and unknown query parameters", async () => {
    const repeated = await fetchWorker("/v1/chat-messages?limit=1&limit=2", {
      headers: authenticatedHeaders,
    });
    const unknown = await fetchWorker("/v1/chat-messages?extra=1", {
      headers: authenticatedHeaders,
    });

    expect(repeated.status).toBe(400);
    expect(unknown.status).toBe(400);
  });

  test("pagination cursor survives a strict atob implementation (WHATWG/V8)", async () => {
    for (let i = 1; i <= 3; i += 1) {
      await d1Mock
        .prepare(
          "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
        )
        .bind(
          `cursor-msg-${i}`,
          "test-account",
          `message ${i}`,
          i,
          i,
          JSON.stringify({
            id: `cursor-msg-${i}`,
            text: `message ${i}`,
            sender: "human",
            type: "text",
            createdAt: i,
            updatedAt: i,
            chatSessionId: null,
            appId: null,
            journalRevision: 0,
            payloadHash: "sha256:test",
            messageSource: "desktop_chat",
            rating: null,
            reported: false,
            generationOutcome: null,
            revision: String(i),
            attachments: [],
          })
        )
        .run();
    }

    const firstPage = await fetchWorker("/v1/chat-messages?limit=2", {
      headers: authenticatedHeaders,
    });
    expect(firstPage.status).toBe(200);
    const firstBody = (await firstPage.json()) as {
      messages: Array<{ id: string }>;
      page: { olderCursor: string | null; hasOlder: boolean };
    };
    expect(firstBody.page.hasOlder).toBe(true);
    expect(firstBody.page.olderCursor).not.toBeNull();
    const cursor = firstBody.page.olderCursor!;

    const originalAtob = globalThis.atob;
    globalThis.atob = ((input: string) => {
      if (input.length % 4 !== 0)
        throw new Error(
          `InvalidCharacterError: base64 length ${input.length} is not a multiple of 4`
        );
      return originalAtob(input);
    }) as typeof atob;

    try {
      const secondPage = await fetchWorker(
        `/v1/chat-messages?limit=2&olderCursor=${encodeURIComponent(cursor)}`,
        { headers: authenticatedHeaders }
      );
      expect(secondPage.status).toBe(200);
      const secondBody = (await secondPage.json()) as {
        messages: Array<{ id: string }>;
        page: { olderCursor: string | null; hasOlder: boolean };
      };
      expect(secondBody.messages).toHaveLength(1);
      expect(secondBody.page.hasOlder).toBe(false);
    } finally {
      globalThis.atob = originalAtob;
    }
  });

  test("cancellation distinguishes accepted from already terminal", async () => {
    const accepted = await fetchWorker("/v1/chat-generations/generation-id", {
      method: "DELETE",
      headers: authenticatedHeaders,
    });
    cancellation = "terminal";
    const terminal = await fetchWorker("/v1/chat-generations/generation-id", {
      method: "DELETE",
      headers: authenticatedHeaders,
    });

    expect(accepted.status).toBe(202);
    expect((await accepted.json()) as unknown).toEqual({
      cancellation: { state: "accepted" },
    });
    expect(terminal.status).toBe(204);
    expect(await terminal.text()).toBe("");
  });
});

describe("settings entitlement admission contract", () => {
  test("Settings renders the same entitlement consumed by chat admission", async () => {
    const before = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });
    const admitted = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("shared-projection")),
    });
    const after = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });

    expect(before.status).toBe(200);
    expect((await before.json()) as unknown).toEqual({
      identity,
      entitlement: initialEntitlement,
    });
    expect(admitted.status).toBe(201);
    expect((await after.json()) as unknown).toEqual({
      identity,
      entitlement: { ...initialEntitlement, used: 1, limitReached: true },
    });
  });

  test("an identical replay consumes quota exactly once", async () => {
    const request = chatCreate("replay-once");
    const init = {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(request),
    };

    const first = await fetchWorker("/v1/chat-messages", init);
    const firstBody = await first.text();
    const replay = await fetchWorker("/v1/chat-messages", init);
    const settings = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });

    expect(first.status).toBe(201);
    expect(wireToChatAdmissionEnvelope(JSON.parse(firstBody))).not.toBeNull();
    expect(replay.status).toBe(200);
    expect(await replay.text()).toBe(firstBody);
    expect(await settings.json()).toMatchObject({
      entitlement: { used: 1, limit: 1, limitReached: true },
    });
  });

  test("concurrent distinct admissions share one atomic quota ceiling", async () => {
    const responses = await Promise.all(
      ["atomic-first", "atomic-second"].map((id) =>
        fetchWorker("/v1/chat-messages", {
          method: "POST",
          headers: {
            ...authenticatedHeaders,
            "content-type": "application/json",
          },
          body: JSON.stringify(chatCreate(id)),
        })
      )
    );
    const settings = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });

    expect(responses.map((response) => response.status).sort()).toEqual([
      201, 402,
    ]);
    expect(await settings.json()).toMatchObject({
      entitlement: { used: 1, limit: 1, limitReached: true },
    });
  });

  test("an exhausted entitlement returns the stable 402 refusal without consumption", async () => {
    await accountStub.admit("test-account", chatCreate("seed"), 1);

    const response = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("exhausted")),
    });
    const settings = await fetchWorker("/v1/settings", {
      headers: authenticatedHeaders,
    });

    expect(response.status).toBe(402);
    expect((await response.json()) as unknown).toEqual({
      error: { code: "entitlement", retryable: false, action: "upgrade" },
    });
    expect(await settings.json()).toMatchObject({
      entitlement: { used: 1, limit: 1, limitReached: true },
    });
  });

  test("unknown attachment ids stay rejected with the existing error shape", async () => {
    const response = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("attachment-rejected"),
        attachmentIds: ["attachment-id"],
      }),
    });

    expect(response.status).toBe(422);
    expect((await response.json()) as unknown).toEqual({
      error: {
        code: "attachment_rejected",
        retryable: false,
        action: "edit_request",
      },
    });
  });

  test("foreign-account and incomplete attachments are rejected", async () => {
    await insertAttachment({
      id: "att-foreign",
      accountId: "other-account",
      state: "ingested",
    });
    await insertAttachment({
      id: "att-staged",
      accountId: "test-account",
      state: "staged",
    });

    const foreign = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("attach-foreign"),
        attachmentIds: ["att-foreign"],
      }),
    });
    const incomplete = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("attach-incomplete"),
        attachmentIds: ["att-staged"],
      }),
    });

    expect(foreign.status).toBe(422);
    expect((await foreign.json()) as unknown).toEqual({
      error: {
        code: "attachment_rejected",
        retryable: false,
        action: "edit_request",
      },
    });
    expect(incomplete.status).toBe(422);
    expect((await incomplete.json()) as unknown).toEqual({
      error: {
        code: "attachment_rejected",
        retryable: false,
        action: "edit_request",
      },
    });
    expect(accountCalls).toEqual([]);
  });

  test("completed same-account attachments are admitted with real metadata", async () => {
    await insertAttachment({
      id: "att-ready",
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
        ...chatCreate("attach-ready"),
        attachmentIds: ["att-ready"],
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
    expect(body.message.id).toBe("attach-ready");
    expect(body.message.attachments).toEqual([
      {
        id: "att-ready",
        displayName: "notes.pdf",
        mediaType: "application/pdf",
        sizeBytes: 2048,
        contentReference: "att-ready",
      },
    ]);
    expect(wireToChatAdmissionEnvelope(body)).not.toBeNull();
  });

  test("zero attachments still admit as today", async () => {
    const response = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(chatCreate("attach-none")),
    });

    expect(response.status).toBe(201);
    const body = (await response.json()) as {
      message: { attachments: unknown[] };
    };
    expect(body.message.attachments).toEqual([]);
  });

  test("oversized send bodies fail before account storage", async () => {
    const response = await fetchWorker("/v1/chat-messages", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...chatCreate("oversized-body"),
        text: "x".repeat(70_000),
      }),
    });

    expect(response.status).toBe(413);
    expect(accountCalls).toEqual([]);
  });
});

describe("ratified generation wire", () => {
  test("worker event encoding is accepted by the frontend parser", () => {
    const encode = (
      accountBackend.prototype as unknown as {
        encode(event: { id: string; kind: "snapshot"; text: string }): string;
      }
    ).encode;
    const transcript = encode.call(accountBackend.prototype, {
      id: "event-1",
      kind: "snapshot",
      text: "hello",
    });

    expect(parseChatGenerationEventStream(transcript)).toEqual([
      { kind: "snapshot", text: "hello" },
    ]);
    expect(transcript).toContain("event: snapshot\n");
    expect(transcript).not.toContain('"id":"event-1"');
  });

  test("generation endpoint emits a parser-compatible leading snapshot", async () => {
    const response = await fetchWorker(
      "/v1/chat-generations/generation-id/events",
      { headers: authenticatedHeaders }
    );

    expect(response.status).toBe(200);
    expect(parseChatGenerationEventStream(await response.text())).toEqual([
      { kind: "snapshot", text: "" },
    ]);
  });

  test("generation endpoint returns the fixed typed refusal before SSE begins", async () => {
    const response = await fetchWorker("/v1/chat-generations/missing/events", {
      headers: authenticatedHeaders,
    });

    expect(response.status).toBe(404);
    expect((await response.json()) as unknown).toEqual({
      error: {
        code: "not_found",
        retryable: false,
        action: "refresh_history",
      },
    });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  test("resume replays strictly after the cursor and heals terminal reconnects", () => {
    const selectReplay = (
      accountBackend.prototype as unknown as {
        selectReplay(
          events: Array<
            | { id: string; kind: "snapshot"; text: string }
            | { id: string; kind: "done"; message: Record<string, unknown> }
          >,
          lastEventId: string | null
        ): unknown;
      }
    ).selectReplay;
    const done = {
      id: "event-2",
      kind: "done" as const,
      message: canonicalMessage({
        id: "assistant-id",
        text: "complete",
        type: "text",
        at: 2,
        journalRevision: 0,
      }),
    };
    const events = [
      { id: "event-1", kind: "snapshot" as const, text: "" },
      done,
    ];

    expect(
      selectReplay.call(accountBackend.prototype, events, "event-1")
    ).toEqual([done]);
    expect(
      selectReplay.call(accountBackend.prototype, events, "event-2")
    ).toEqual([done]);
    expect(
      selectReplay.call(accountBackend.prototype, events.slice(0, 1), "expired")
    ).toBe("expired");
  });
});

describe("chat create wire validator", () => {
  const valid = {
    op: "create",
    opId: "op-1",
    id: "message-1",
    at: 1,
    text: "hello",
    sender: "human",
    journalRevision: 0,
    appId: null,
    chatSessionId: null,
    attachmentIds: ["attachment-1"],
  } as const;

  test("accepts the canonical create envelope", () => {
    expect(isChatCreate(valid)).toBe(true);
  });

  test("accepts bounded canonical scope identifiers", () => {
    expect(
      isChatCreate({
        ...valid,
        appId: "legacy-app",
        chatSessionId: "session-1",
      })
    ).toBe(true);
  });

  test.each([
    [null],
    [[]],
    [{ ...valid, op: "update" }],
    [{ ...valid, opId: "" }],
    [{ ...valid, at: -1 }],
    [{ ...valid, text: "" }],
    [{ ...valid, sender: "ai" }],
    [{ ...valid, journalRevision: 0.5 }],
    [{ ...valid, appId: "" }],
    [{ ...valid, chatSessionId: "s".repeat(129) }],
    [{ ...valid, attachmentIds: [""] }],
  ])("rejects malformed create envelopes", (value: unknown) => {
    expect(isChatCreate(value)).toBe(false);
  });
});
