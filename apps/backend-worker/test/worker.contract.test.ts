import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";
import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";
import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";

import { isChatCreate } from "../src/wire";

let handler: typeof import("../src/index")["default"];

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({
    DurableObject: class {},
  }));
  handler = (await import("../src/index")).default;
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
const accountStub = {
  configure: async () => undefined,
  history: async (limit: number) => {
    accountCalls.push(`history:${limit}`);
    return { messages: [], page: { olderCursor: null, hasOlder: false } };
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
      message: {
        id: input["id"],
        text: input["text"],
        sender: "human",
        createdAt: input["at"],
        generationOutcome: null,
      },
      generation: { id: `generation-${String(input["id"])}` },
    };
    admissions.set(String(input["id"]), admission);
    return { ...admission, created: true };
  },
  complete: async () => undefined,
  fail: async () => undefined,
};

const env = {
  ENVIRONMENT: "test",
  API_TOKEN: "test-token",
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
    });
    expect(health.headers.get("cache-control")).toBe("no-store");
    expect(accountCalls).toEqual([]);
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
      "/v1/chat-messages?olderCursor=cursor",
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
    });
    expect(accountCalls).toHaveLength(2);
    expect(accountCalls[0]).toMatch(/^account:token:[a-f0-9]{64}$/);
    expect(accountCalls[1]).toBe("history:100");
  });

  test("unknown routes use the stable backend error envelope", async () => {
    const response = await fetchWorker("/unknown");

    expect(response.status).toBe(404);
    expect((await response.json()) as unknown).toEqual({
      error: { code: "not_found", retryable: false, action: "edit_request" },
    });
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

  test.each([
    [null],
    [[]],
    [{ ...valid, op: "update" }],
    [{ ...valid, opId: "" }],
    [{ ...valid, at: -1 }],
    [{ ...valid, text: "" }],
    [{ ...valid, sender: "ai" }],
    [{ ...valid, journalRevision: 0.5 }],
    [{ ...valid, appId: "legacy-app" }],
    [{ ...valid, attachmentIds: [""] }],
  ])("rejects malformed create envelopes", (value: unknown) => {
    expect(isChatCreate(value)).toBe(false);
  });
});
