import assert from "node:assert/strict";
import test from "node:test";

import { listEmptyKind } from "../src/production/list-empty-presentation.ts";

test("list empty kinds distinguish true-empty from filter-miss", () => {
  assert.equal(listEmptyKind({ phase: "ready", rowCount: 0, visibleCount: 0 }), "empty-projection");
  assert.equal(listEmptyKind({ phase: "ready", rowCount: 4, visibleCount: 0 }), "filtered-out");
  assert.equal(listEmptyKind({ phase: "ready", rowCount: 4, visibleCount: 2 }), null);
  assert.equal(listEmptyKind({ phase: "initial-loading", rowCount: 0, visibleCount: 0 }), null);
  assert.equal(listEmptyKind({ phase: "unavailable", rowCount: 0, visibleCount: 0 }), null);
  // red-proof: returning filtered-out for non-ready zero rows reintroduces the
  // conflation this helper exists to remove.
});
