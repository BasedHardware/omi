import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";

import { createLocalDevService } from "./app-facing";
import { createEmptyChatGenerationContextSource } from "./chat/generation-context";

test("warmupChatGenerationContext loads context without admitting a chat message", async () => {
  // red-proof: skip the load call and loads stays 0; write a message inside
  // warmup and history grows.
  const inner = createEmptyChatGenerationContextSource();
  let loads = 0;
  const service = createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: "local-dev-user",
    memoryCount: 3,
    accountTimezone: "America/Los_Angeles",
    devSecretLabel: "omi-local-dev-token-not-a-secret-v1",
    generationContext: {
      async load(input) {
        loads += 1;
        return inner.load(input);
      },
    },
  });
  const snapshotSequence = service.writePath.chatMessages.readSnapshotSequence("local-dev-user");
  const before = service.writePath.chatMessages.listHistory("local-dev-user", {
    limit: 50,
    snapshotSequence,
    olderThan: null,
  });
  await service.warmupChatGenerationContext();
  const after = service.writePath.chatMessages.listHistory("local-dev-user", {
    limit: 50,
    snapshotSequence,
    olderThan: null,
  });
  expect(loads).toBe(1);
  expect(after.messages.map((message) => message.id)).toEqual(before.messages.map((message) => message.id));
});
