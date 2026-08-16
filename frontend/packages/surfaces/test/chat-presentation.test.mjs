import assert from "node:assert/strict";
import test from "node:test";

import { chatBodyKind } from "../src/production/chat-presentation.ts";

test("chat body kind never claims empty or beginning-of-thread while refresh is unfinished", () => {
  assert.equal(chatBodyKind("ready", 0), "empty-projection");
  assert.equal(chatBodyKind("ready", 2), "thread");
  assert.equal(chatBodyKind("initial-loading", 0), "loading");
  assert.equal(chatBodyKind("initial-loading", 2), "thread");
  assert.equal(chatBodyKind("refreshing", 0), "loading");
  assert.equal(chatBodyKind("refreshing", 1), "thread");
  assert.equal(chatBodyKind("unavailable", 0), "unavailable");
  assert.equal(chatBodyKind("unavailable", 1), "thread");
  assert.equal(chatBodyKind("saved-but-refresh-failed", 0), "unavailable");
  assert.equal(chatBodyKind("saved-but-refresh-failed", 3), "thread");
  // red-proof: prefer phase === "initial-loading" over messageCount so a
  // local projection is replaced by the loading empty primitive.
});
