import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { tasksEmptyKind } from "../src/production/tasks-presentation.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

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

test("TasksProduction renders distinct data-empty-kind for each empty condition", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  assert.match(source, /tasksEmptyKind\(/);
  assert.match(source, /data-empty-kind="empty-projection"/);
  assert.match(source, /data-empty-kind="filtered-out"/);
  assert.match(source, /common\.noResults/);
  // True-empty keeps title+body; filter-miss must not reuse that claim.
  const trueEmpty = source.match(/data-empty-kind="empty-projection"[\s\S]{0,240}/)?.[0] ?? "";
  assert.match(trueEmpty, /tasks\.emptyTitle/);
  assert.match(trueEmpty, /tasks\.emptyBody/);
  assert.doesNotMatch(trueEmpty, /common\.noResults/);
  const filterMiss = source.match(/data-empty-kind="filtered-out"[\s\S]{0,200}/)?.[0] ?? "";
  assert.match(filterMiss, /common\.noResults/);
  assert.doesNotMatch(filterMiss, /tasks\.emptyTitle/);
  // red-proof: dropping either data-empty-kind attribute, or pointing both
  // branches at the same copy key, fails the matching assertions above.
});
