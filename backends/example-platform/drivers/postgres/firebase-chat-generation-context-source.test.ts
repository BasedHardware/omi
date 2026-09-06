import { describe, expect, test } from "bun:test";
import { normalizeChatGenerationContext, type ChatGenerationContextSourceInput } from "../../apps/service/chat/generation-context";

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

const input = (): ChatGenerationContextSourceInput & { generationId: string; nowEpochMilliseconds: number } => ({
  accountId: "account:alice",
  generationId: "generation:chat",
  nowEpochMilliseconds: 1_800_000_000_000,
  history: [],
  bearerToken: "header.payload.signature",
  admitted: { message: {
    id: "human:chat", text: "What do I prefer?", sender: "human", type: "text",
    createdAt: 1_800_000_000_000, updatedAt: 1_800_000_000_000,
    chatSessionId: null, appId: null, journalRevision: 1,
    payloadHash: `sha256:${"c".repeat(64)}`, messageSource: "chat", rating: null,
    reported: false, revision: "revision:chat", attachments: [],
  }, generationId: "generation:chat" },
});

describe("PostgreSQL Firebase Chat memory context source", () => {
  test("binds the expected account and produces a trusted current supervisor context packet", async () => {
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
    const request = input();
    const packet = normalizeChatGenerationContext(await source.load(request), request);
    expect(packet.items).toHaveLength(1);
    expect(packet.items[0]).toMatchObject({ ownerAccountId: request.accountId, redactedPreview: "The owner likely prefers tea.", policyDecision: "degraded" });
    expect(() => normalizeChatGenerationContext(packet, { ...request, accountId: "account:bob" })).toThrow("owner or generation mismatch");
    expect(calls).toEqual([[
      "header.payload.signature",
      1_800_000_000,
      "account:alice",
      { limit: 25, cursor: null },
    ]]);
    expect(JSON.stringify(await source.load(input()))).not.toContain("header.payload.signature");
  });

  test("collapses denied, malformed, and throwing read outcomes without claiming absence", async () => {
    for (const readForAccount of [
      async () => Object.freeze({ kind: "denied" as const, outcome: "authorization" as const }),
      async () => Object.freeze({ kind: "loaded" as const, canonical_json: PAGE, extra: true }),
      async () => { throw new Error("raw provider account secret"); },
    ]) {
      const source = createPostgresFirebaseChatGenerationContextSource({
        memory: Object.freeze({ readForAccount }),
        now_epoch_seconds: () => 1_800_000_000,
      });
      const outcome = await source.load(input());
      expect(normalizeChatGenerationContext(outcome, input()).items).toEqual([]);
      expect(JSON.stringify(outcome)).not.toMatch(/provider|secret|absence/i);
    }
  });

  test("rejects a noncanonical page through the current packet builder", async () => {
    const source = createPostgresFirebaseChatGenerationContextSource({
      memory: { readForAccount: async () => ({ kind: "loaded", canonical_json: "{}" }) },
      now_epoch_seconds: () => 1_800_000_000,
    });
    await expect(source.load(input())).rejects.toThrow("invalid canonical page");
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
    await expect(source.load(hostile as never)).resolves.toEqual([]);
    expect(getterCalls).toBe(0);
    expect(reads).toBe(0);
  });
});
