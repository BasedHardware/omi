import assert from "node:assert/strict";
import test from "node:test";

import { tasksBodyKind, tasksEmptyKind } from "../src/production/tasks-presentation.ts";

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

test("tasks body kind keeps saved rows on screen while refresh is still initial-loading", () => {
  assert.equal(
    tasksBodyKind({ phase: "initial-loading", rowCount: 3, visibleCount: 3, filtering: false }),
    "rows",
  );
  assert.equal(
    tasksBodyKind({ phase: "initial-loading", rowCount: 0, visibleCount: 0, filtering: false }),
    "loading",
  );
  assert.equal(
    tasksBodyKind({ phase: "ready", rowCount: 0, visibleCount: 0, filtering: false }),
    "empty-projection",
  );
  assert.equal(
    tasksBodyKind({ phase: "unavailable", rowCount: 0, visibleCount: 0, filtering: false }),
    "unavailable",
  );
  assert.equal(
    tasksBodyKind({ phase: "ready", rowCount: 3, visibleCount: 0, filtering: true }),
    "filtered-out",
  );
  assert.equal(
    tasksBodyKind({ phase: "refreshing", rowCount: 2, visibleCount: 2, filtering: false }),
    "rows",
  );
  assert.equal(
    tasksBodyKind({ phase: "refreshing", rowCount: 0, visibleCount: 0, filtering: false }),
    "loading",
  );
  assert.equal(
    tasksBodyKind({ phase: "saved-but-refresh-failed", rowCount: 0, visibleCount: 0, filtering: false }),
    "rows",
  );
  // red-proof: prefer phase === "initial-loading" over rowCount so a local
  // projection is replaced by the loading empty primitive. Zero-row
  // refreshing must not fall through to empty-projection either.
});
