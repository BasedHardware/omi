import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { listEmptyKind } from "../src/production/list-empty-presentation.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("list empty kinds distinguish true-empty from filter-miss", () => {
  assert.equal(listEmptyKind({ phase: "ready", rowCount: 0, visibleCount: 0 }), "empty-projection");
  assert.equal(listEmptyKind({ phase: "ready", rowCount: 4, visibleCount: 0 }), "filtered-out");
  assert.equal(listEmptyKind({ phase: "ready", rowCount: 4, visibleCount: 2 }), null);
  assert.equal(listEmptyKind({ phase: "initial-loading", rowCount: 0, visibleCount: 0 }), null);
  assert.equal(listEmptyKind({ phase: "unavailable", rowCount: 0, visibleCount: 0 }), null);
  // red-proof: returning filtered-out for non-ready zero rows reintroduces the
  // conflation this helper exists to remove.
});

test("MemoriesProduction renders distinct data-empty-kind for each empty condition", async () => {
  const source = await read("src/production/MemoriesProduction.tsx");
  assert.match(source, /listEmptyKind\(/);
  assert.match(source, /data-empty-kind="empty-projection"/);
  assert.match(source, /data-empty-kind="filtered-out"/);
  const trueEmptyStart = source.indexOf('data-empty-kind="empty-projection"');
  assert.notEqual(trueEmptyStart, -1);
  const trueEmpty = source.slice(trueEmptyStart, source.indexOf(" : ", trueEmptyStart));
  assert.match(trueEmpty, /memories\.emptyTitle/);
  assert.match(trueEmpty, /memories\.emptyBody/);
  assert.doesNotMatch(trueEmpty, /common\.noResults/);
  const filterMissStart = source.indexOf('data-empty-kind="filtered-out"');
  assert.notEqual(filterMissStart, -1);
  const filterMiss = source.slice(filterMissStart, source.indexOf(" : ", filterMissStart));
  assert.match(filterMiss, /common\.noResults/);
  assert.doesNotMatch(filterMiss, /memories\.emptyTitle/);
  // red-proof: dropping either attribute, or pointing both at common.noResults,
  // fails the assertions above.
});

test("ConversationsProduction renders distinct data-empty-kind for each empty condition", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  assert.match(source, /listEmptyKind\(/);
  assert.match(source, /data-empty-kind="empty-projection"/);
  assert.match(source, /data-empty-kind="filtered-out"/);
  assert.match(source, /data-empty-kind="detail-not-found"/);
  const trueEmptyStart = source.indexOf('data-empty-kind="empty-projection"');
  assert.notEqual(trueEmptyStart, -1);
  const trueEmpty = source.slice(trueEmptyStart, source.indexOf(" : ", trueEmptyStart));
  assert.match(trueEmpty, /conversations\.emptyTitle/);
  assert.match(trueEmpty, /conversations\.emptyBody/);
  assert.doesNotMatch(trueEmpty, /common\.noResults/);
  const filterMissStart = source.indexOf('data-empty-kind="filtered-out"');
  assert.notEqual(filterMissStart, -1);
  const filterMiss = source.slice(filterMissStart, source.indexOf(" : ", filterMissStart));
  assert.match(filterMiss, /common\.noResults/);
  const detailMissStart = source.indexOf('data-empty-kind="detail-not-found"');
  assert.notEqual(detailMissStart, -1);
  const detailMiss = source.slice(detailMissStart, detailMissStart + 160);
  assert.match(detailMiss, /conversations\.detailNotFound/);
  // red-proof: collapsing detail-not-found into filtered-out, or dropping any
  // of the three attributes, fails the matching assertions above.
});
