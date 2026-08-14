import assert from "node:assert/strict";
import test from "node:test";

import { tasksEmptyKind } from "../src/production/tasks-presentation.ts";

test("tasks empty kinds distinguish true-empty from filter-miss", () => {
  assert.equal(
    tasksEmptyKind({ phase: "ready", rowCount: 0, visibleCount: 0, filtering: false }),
    "empty-projection",
  );
  assert.equal(
    tasksEmptyKind({ phase: "ready", rowCount: 3, visibleCount: 0, filtering: true }),
    "filtered-out",
  );
  assert.equal(
    tasksEmptyKind({ phase: "ready", rowCount: 3, visibleCount: 0, filtering: false }),
    null,
  );
  assert.equal(
    tasksEmptyKind({ phase: "ready", rowCount: 3, visibleCount: 2, filtering: true }),
    null,
  );
  assert.equal(
    tasksEmptyKind({ phase: "initial-loading", rowCount: 0, visibleCount: 0, filtering: false }),
    null,
  );
  assert.equal(
    tasksEmptyKind({ phase: "unavailable", rowCount: 0, visibleCount: 0, filtering: false }),
    null,
  );
  // red-proof: returning filtered-out whenever visibleCount is 0 collapses a
  // day-bucket empty (no query) into a filter miss.
});
