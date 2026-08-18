import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";
import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";
import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";
import {
  parseChatGenerationEventStream,
  wireToChatAdmissionEnvelope,
  wireToChatHistoryEnvelope,
} from "@omi-core/adapters-platform";

import type { AccountBackend } from "../src/account";
import { CHAT_CAPABILITIES, isChatCreate } from "../src/wire";

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
  limitKey: "chat_messages",
  used: 0,
  limit: 1,
  limitReached: false,
  upgradeAvailable: true,
};
let entitlement = { ...initialEntitlement };
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
const accountStub = {
  configure: async () => undefined,
  history: async (limit: number) => {
    accountCalls.push(`history:${limit}`);
    return {
      messages: [],
      page: { olderCursor: null, hasOlder: false },
      capabilities: CHAT_CAPABILITIES,
    };
  },
  settings: async () => ({ identity, entitlement: { ...entitlement } }),
  admit: async (input: Record<string, unknown>) => {
    const payload = JSON.stringify(input);
    const prior = admissions.get(String(input["id"]));
    if (prior !== undefined) {
      if (prior.payload !== payload) return "conflict" as const;
      return { ...prior, created: false };
    }
    if (entitlement.limitReached || entitlement.used >= entitlement.limit)
      return "entitlement" as const;
    entitlement = {
      ...entitlement,
      used: entitlement.used + 1,
      limitReached: entitlement.used + 1 >= entitlement.limit,
    };
    const admission = {
      payload,
      message: canonicalMessage(input),
      generation: { id: `generation-${String(input["id"])}` },
    };
    admissions.set(String(input["id"]), admission);
    return { ...admission, created: true };
  },
  complete: async () => undefined,
  fail: async () => undefined,
  cancel: async () => cancellation,
  fetch: async () =>
    new Response(
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

beforeEach(() => {
  entitlement = { ...initialEntitlement };
  admissions.clear();
  cancellation = "accepted";
});

describe("worker request contract", () => {
  test("health and readiness do not require account storage", async () => {
    accountCalls.length = 0;

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
      accountCalls.length = 0;

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
    accountCalls.length = 0;

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
    accountCalls.length = 0;

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
    accountCalls.length = 0;

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

  test("retained projections expose canonical empty wire shapes", async () => {
    const conversations = await fetchWorker("/v1/conversations", {
      headers: authenticatedHeaders,
    });
    const memories = await fetchWorker("/v1/memories", {
      headers: authenticatedHeaders,
    });
    const tasks = await fetchWorker("/v1/tasks", {
      headers: authenticatedHeaders,
    });

    expect((await conversations.json()) as unknown).toEqual([]);
    const memoriesBody = await memories.text();
    const tasksBody = await tasks.text();
    expect(JSON.parse(memoriesBody) as unknown).toEqual({
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
    expect(parseSynthesizedPageJson(memoriesBody)).not.toBeNull();
    expect(parseTaskPageJson(tasksBody)).not.toBeNull();
  });

  test("chat history validates pagination before resolving the account", async () => {
    accountCalls.length = 0;

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

  test("chat history resolves the authenticated account and forwards a bounded limit", async () => {
    accountCalls.length = 0;

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
    expect(accountCalls).toHaveLength(2);
    expect(accountCalls[0]).toBe("account:test-account");
    expect(accountCalls[1]).toBe("history:100");
  });

  test("credential rotation preserves the configured account identity", async () => {
    accountCalls.length = 0;
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
    expect(accountCalls[0]).toBe("account:test-account");
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
    entitlement = { ...initialEntitlement, used: 1, limitReached: true };

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

  test("nonempty attachment sends fail until attachment staging exists", async () => {
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

  test("oversized send bodies fail before account storage", async () => {
    accountCalls.length = 0;
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
