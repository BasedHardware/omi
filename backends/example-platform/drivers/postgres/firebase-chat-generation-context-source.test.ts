import { describe, expect, test } from "bun:test";

import { createPostgresFirebaseChatGenerationContextSource } from
  "./firebase-chat-generation-context-source";

const PAGE = JSON.stringify({
  contractVersion: "1.0.0",
  items: [{
    id: "retrieval-node-v1:chat",
    text: "The owner likely prefers tea.",
    citations: ["citation-v1:chat"],
    provenance: {
      synthesisVersion: "chat-test-v1",
      inputDigest: "a".repeat(64),
      outputDigest: "b".repeat(64),
    },
  }],
  window: { status: "incomplete", complete: false, hasMore: false, nextCursor: null },
  completeness: {
    version: "recall-completeness-v1",
    status: "degraded",
    reasons: ["projection_bypassed"],
    frontiers: {
      declaredFrontier: "frontier-v1:chat",
      newestSearchedAcceptedFrontier: null,
      missingAcceptedFrontierReason: "projection_bypassed",
      newestSearchedStmFrontier: null,
      missingStmFrontierReason: "projection_bypassed",
    },
  },
  absence: null,
});

const input = () => ({
  accountId: "account:alice",
  bearerToken: "header.payload.signature",
  admitted: { message: {}, generationId: "generation:chat" },
}) as never;

describe("PostgreSQL Firebase Chat memory context source", () => {
  test("binds the expected account and preserves the exact canonical page", async () => {
    const calls: unknown[][] = [];
    const source = createPostgresFirebaseChatGenerationContextSource({
      memory: Object.freeze({
        readForAccount: async (...args: unknown[]) => {
          calls.push(args);
          return Object.freeze({ kind: "loaded" as const, canonical_json: PAGE });
        },
      }),
      now_epoch_seconds: () => 1_800_000_000,
    });
    await expect(source.load(input())).resolves.toEqual({
      version: "chat-generation-memory-context-v1",
      state: "loaded",
      canonical_page_json: PAGE,
    });
    expect(calls).toEqual([[
      "header.payload.signature",
      1_800_000_000,
      "account:alice",
      { limit: 25, cursor: null },
    ]]);
    expect(JSON.stringify(await source.load(input()))).not.toContain("header.payload.signature");
  });

  test("collapses denied, malformed, throwing, and noncanonical reads", async () => {
    for (const readForAccount of [
      async () => Object.freeze({ kind: "denied" as const, outcome: "authorization" as const }),
      async () => Object.freeze({ kind: "loaded" as const, canonical_json: "{}" }),
      async () => Object.freeze({ kind: "loaded" as const, canonical_json: PAGE, extra: true }),
      async () => { throw new Error("raw provider account secret"); },
    ]) {
      const source = createPostgresFirebaseChatGenerationContextSource({
        memory: Object.freeze({ readForAccount }),
        now_epoch_seconds: () => 1_800_000_000,
      });
      const outcome = await source.load(input());
      expect(outcome).toEqual({
        version: "chat-generation-memory-context-v1",
        state: "unavailable",
      });
      expect(JSON.stringify(outcome)).not.toMatch(/provider|secret|account:alice/i);
    }
  });

  test("rejects hostile options and never invokes hostile input accessors", async () => {
    expect(() => createPostgresFirebaseChatGenerationContextSource(new Proxy({}, {}) as never))
      .toThrow("invalid PostgreSQL Firebase Chat memory context options");
    let reads = 0;
    const source = createPostgresFirebaseChatGenerationContextSource({
      memory: Object.freeze({
        readForAccount: async () => { reads += 1; return { kind: "loaded", canonical_json: PAGE }; },
      }),
      now_epoch_seconds: () => 1_800_000_000,
    });
    let getterCalls = 0;
    const hostile = Object.defineProperty({
      accountId: "account:alice",
      admitted: {},
    }, "bearerToken", {
      enumerable: true,
      get() { getterCalls += 1; return "header.payload.signature"; },
    });
    await expect(source.load(hostile as never)).resolves.toEqual({
      version: "chat-generation-memory-context-v1",
      state: "unavailable",
    });
    expect(getterCalls).toBe(0);
    expect(reads).toBe(0);
  });
});
