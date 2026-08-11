import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import { SqliteChatGenerationEventsStore } from "./chat-generation-events-store";

test("SQLite chat generation compaction persists redaction metadata", () => {
  const db = new Database(":memory:");
  const store = new SqliteChatGenerationEventsStore(db);
  const accountId = "retention-account";
  const generationId = "generation:retention";
  const payloadHash = `sha256:${"a".repeat(64)}`;
  const message = {
    id: "human:retention", text: "prompt", sender: "human" as const, type: "text" as const,
    createdAt: 0, updatedAt: 0, chatSessionId: null, appId: null, journalRevision: 1,
    payloadHash, messageSource: "chat", rating: null, reported: false,
    revision: "revision:human", attachments: [],
  };
  store.append({ accountId, generationId, eventId: "event:accepted", createdAt: 0,
    frame: { kind: "accepted", message, generation: { id: generationId } } });
  store.append({ accountId, generationId, eventId: "event:snapshot", createdAt: 1,
    frame: { kind: "snapshot", text: "secret" } });
  store.append({ accountId, generationId, eventId: "event:delta", createdAt: 2,
    frame: { kind: "delta", text: "secret answer" } });
  store.append({ accountId, generationId, eventId: "event:cancelled", createdAt: 3,
    frame: { kind: "cancelled", message: null } });
  const result = store.compact(accountId, generationId, 20, { ttlMs: 10, maxDetailEvents: 0 });
  expect(result?.metadata.redactedEventCount).toBe(2);
  expect(store.listAfter(accountId, generationId, null)?.map((event) => event.id)).toEqual([
    "event:accepted", "event:snapshot", "event:delta", "event:cancelled",
  ]);
  expect(store.listAfter(accountId, generationId, null)?.[1]?.frame).toEqual({ kind: "snapshot", text: "[redacted]" });
  expect(store.retentionMetadata(accountId, generationId)).toEqual(result?.metadata);
  db.close();
});
