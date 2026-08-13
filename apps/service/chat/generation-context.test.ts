import { describe, expect, test } from "bun:test";

import {
  loadedChatGenerationMemoryContext,
  snapshotChatGenerationMemoryContext,
  unavailableChatGenerationMemoryContext,
} from "./generation-context";

const PAGE = JSON.stringify({
  contractVersion: "1.0.0",
  items: [],
  window: { status: "incomplete", complete: false, hasMore: false, nextCursor: null },
  completeness: {
    version: "recall-completeness-v1",
    status: "partial",
    reasons: ["policy_bound"],
    frontiers: {
      declaredFrontier: "frontier-v1:chat-context",
      newestSearchedAcceptedFrontier: null,
      missingAcceptedFrontierReason: "policy_bound",
      newestSearchedStmFrontier: null,
      missingStmFrontierReason: "policy_bound",
    },
  },
  absence: { kind: "query_gap" },
});

describe("Chat generation memory context", () => {
  test("retains canonical completeness bytes and snapshots loaded context", () => {
    const loaded = loadedChatGenerationMemoryContext(PAGE);
    expect(snapshotChatGenerationMemoryContext(loaded)).toEqual(loaded);
    expect((snapshotChatGenerationMemoryContext(loaded) as { canonical_page_json: string })
      .canonical_page_json).toBe(PAGE);
  });

  test("unavailable is not an empty or complete memory claim", () => {
    expect(unavailableChatGenerationMemoryContext()).toEqual({
      version: "chat-generation-memory-context-v1",
      state: "unavailable",
    });
    expect(snapshotChatGenerationMemoryContext(unavailableChatGenerationMemoryContext()))
      .toBe(unavailableChatGenerationMemoryContext());
  });

  test("rejects noncanonical pages, extras, accessors, and proxies without invoking getters", () => {
    expect(() => loadedChatGenerationMemoryContext("{}"))
      .toThrow("invalid canonical Chat memory context");
    expect(snapshotChatGenerationMemoryContext({
      version: "chat-generation-memory-context-v1",
      state: "unavailable",
      extra: true,
    })).toBeNull();
    let getters = 0;
    const accessor = Object.defineProperty({
      version: "chat-generation-memory-context-v1",
      state: "loaded",
    }, "canonical_page_json", {
      enumerable: true,
      get() { getters += 1; return PAGE; },
    });
    expect(snapshotChatGenerationMemoryContext(accessor)).toBeNull();
    expect(getters).toBe(0);
    expect(snapshotChatGenerationMemoryContext(new Proxy({}, {}))).toBeNull();
  });
});
