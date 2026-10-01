import { describe, expect, test } from "bun:test";

import {
  createInMemoryChatGenerationEventsStore,
  type ChatGenerationEventsStore,
} from "./chat-generation-events-store";

const append = (store: ChatGenerationEventsStore, kind: "accepted" | "snapshot" | "delta" | "done", eventId: string, createdAt: number, text = "") => store.append({
  accountId: "retention-account",
  generationId: "generation:retention",
  eventId,
  createdAt,
  frame: kind === "accepted"
    ? { kind, message: {
        id: "human:retention", text: "prompt", sender: "human", type: "text", createdAt: 0,
        updatedAt: 0, chatSessionId: null, appId: null, journalRevision: 1,
        payloadHash: `sha256:${"a".repeat(64)}`, messageSource: "chat", rating: null,
        reported: false, revision: "revision:human", attachments: Object.freeze([]),
      }, generation: { id: "generation:retention" } }
    : kind === "done"
      ? { kind, message: {
          id: "assistant:retention", text: "answer", sender: "ai", type: "text", createdAt: 3,
          updatedAt: 3, chatSessionId: null, appId: null, journalRevision: 1,
          payloadHash: `sha256:${"b".repeat(64)}`, messageSource: "chat_generation", rating: null,
          reported: false, revision: "revision:assistant", attachments: Object.freeze([]),
        } }
      : { kind, text },
});

describe("chat generation retention metadata", () => {
  test("compaction redacts expired detail while preserving terminal transcript and replay cursor", () => {
    const store = createInMemoryChatGenerationEventsStore();
    append(store, "accepted", "event:accepted", 0);
    append(store, "snapshot", "event:snapshot", 1, "secret prompt");
    append(store, "delta", "event:delta", 2, "secret answer");
    append(store, "done", "event:done", 3);
    const result = store.compact!("retention-account", "generation:retention", 20, { ttlMs: 10, maxDetailEvents: 0 });
    expect(result).not.toBeNull();
    expect(result?.metadata).toMatchObject({
      ttlMs: 10,
      expiresAt: 12,
      replayCursor: "event:done",
      redactedEventCount: 2,
      canonicalTranscriptRetained: true,
    });
    const events = store.listAfter("retention-account", "generation:retention", null)!;
    expect(events.map((event) => event.id)).toEqual(["event:accepted", "event:snapshot", "event:delta", "event:done"]);
    expect(events[1]?.frame).toEqual({ kind: "snapshot", text: "[redacted]" });
    expect(events[2]?.frame).toEqual({ kind: "delta", text: "[redacted]" });
    expect(events[3]?.frame.kind).toBe("done");
    expect(store.retentionMetadata!("retention-account", "generation:retention")).toEqual(result?.metadata);
    const replay = store.compact!("retention-account", "generation:retention", 30, { ttlMs: 10, maxDetailEvents: 0 });
    expect(replay?.redactedEventCount).toBe(0);
    expect(replay?.metadata.redactedEventCount).toBe(2);
  });

  test("retention policy rejects unbounded or negative values and unknown generations are inert", () => {
    const store = createInMemoryChatGenerationEventsStore();
    expect(store.compact!("retention-account", "missing", 0, { ttlMs: 10, maxDetailEvents: 1 })).toBeNull();
    expect(() => store.compact!("retention-account", "missing", 0, { ttlMs: 0, maxDetailEvents: 1 })).toThrow("invalid chat generation retention policy");
    expect(() => store.compact!("retention-account", "missing", 0, { ttlMs: 10, maxDetailEvents: -1 })).toThrow("invalid chat generation retention policy");
    append(store, "accepted", "event:active", 0);
    expect(store.compact!("retention-account", "generation:retention", 0, { ttlMs: 10, maxDetailEvents: 1 })).toBeNull();
    const overflowStore = createInMemoryChatGenerationEventsStore();
    append(overflowStore, "accepted", "event:overflow-accepted", Number.MAX_SAFE_INTEGER);
    append(overflowStore, "snapshot", "event:overflow-snapshot", Number.MAX_SAFE_INTEGER, "detail");
    append(overflowStore, "done", "event:overflow-done", Number.MAX_SAFE_INTEGER);
    expect(() => overflowStore.compact!("retention-account", "generation:retention", Number.MAX_SAFE_INTEGER, {
      ttlMs: 10, maxDetailEvents: 1,
    })).toThrow("retention expiry overflow");
  });
});
