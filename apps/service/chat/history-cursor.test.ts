import { expect, test } from "bun:test";

import {
  createChatHistoryCursorCodec,
  ExpiredChatHistoryCursorError,
  InvalidChatHistoryCursorError,
} from "./history-cursor";

const codec = createChatHistoryCursorCodec({
  activeId: "active",
  keys: [{ id: "active", secret: new Uint8Array(32).fill(7) }],
});

test("chat history cursor is signed and binds account, scope, direction, snapshot, and boundary", () => {
  const cursor = codec.issue({
    accountId: "account-a",
    snapshotSequence: 9,
    olderThan: { createdAt: 123, id: "message-3" },
    issuedAtEpochSeconds: 1_000,
    ttlSeconds: 60,
  });
  expect(codec.verify(cursor, { accountId: "account-a", nowEpochSeconds: 1_010 })).toEqual({
    snapshotSequence: 9,
    olderThan: { createdAt: 123, id: "message-3" },
    issuedAtEpochSeconds: 1_000,
  });
  expect(() => codec.verify(cursor, { accountId: "account-b", nowEpochSeconds: 1_010 }))
    .toThrow(InvalidChatHistoryCursorError);
  const tail = cursor.at(-1) === "A" ? "B" : "A";
  expect(() => codec.verify(`${cursor.slice(0, -1)}${tail}`, {
    accountId: "account-a",
    nowEpochSeconds: 1_010,
  })).toThrow(InvalidChatHistoryCursorError);
  expect(() => codec.verify(cursor, { accountId: "account-a", nowEpochSeconds: 1_060 }))
    .toThrow(ExpiredChatHistoryCursorError);
});
