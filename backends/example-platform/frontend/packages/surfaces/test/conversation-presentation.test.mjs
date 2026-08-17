import assert from "node:assert/strict";
import test from "node:test";

import { conversationDetailKind } from "../src/production/conversation-presentation.ts";

test("conversation detail kind never claims not-found while refresh is unfinished", () => {
  assert.equal(conversationDetailKind({ phase: "ready", detailId: undefined, found: false }), "none");
  assert.equal(conversationDetailKind({ phase: "ready", detailId: "c1", found: true }), "detail");
  assert.equal(conversationDetailKind({ phase: "initial-loading", detailId: "c1", found: true }), "detail");
  assert.equal(conversationDetailKind({ phase: "refreshing", detailId: "c1", found: true }), "detail");
  assert.equal(conversationDetailKind({ phase: "initial-loading", detailId: "c1", found: false }), "loading");
  assert.equal(conversationDetailKind({ phase: "refreshing", detailId: "c1", found: false }), "loading");
  assert.equal(conversationDetailKind({ phase: "ready", detailId: "c1", found: false }), "not-found");
  assert.equal(conversationDetailKind({ phase: "unavailable", detailId: "c1", found: false }), "unavailable");
  assert.equal(conversationDetailKind({ phase: "saved-but-refresh-failed", detailId: "c1", found: false }), "unavailable");
  assert.equal(conversationDetailKind({ phase: "saved-but-refresh-failed", detailId: "c1", found: true }), "detail");
  // red-proof: treat missing detail during initial-loading as not-found so a
  // still-hydrating URL claims the conversation was removed.
});
