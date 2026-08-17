import { beforeAll, describe, expect, mock, test } from "bun:test";
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
const accountStub = {
  history: async (limit: number) => {
    accountCalls.push(`history:${limit}`);
    return { messages: [], page: { olderCursor: null, hasOlder: false } };
  },
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
