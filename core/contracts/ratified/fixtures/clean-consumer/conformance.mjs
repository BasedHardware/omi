import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  hasHonestPageWindow,
  hasHonestRecallCompleteness,
  hasSafeSynthesizedPage,
} from "@omi-core/ratified-contracts/projections/synthesized";
import { hasSafeRecallTrace } from "@omi-core/ratified-contracts/recall/trace";

const fixtureRoot = new URL("./node_modules/@omi-core/ratified-contracts/fixtures/", import.meta.url);
for (const row of await fixture("page-conformance.json")) {
  assert.equal(hasSafeSynthesizedPage(row.page), row.safe, row.name);
}
for (const row of await fixture("read-page-windows.json")) {
  assert.equal(hasHonestPageWindow(row.window), row.honest, row.name);
}
for (const row of await fixture("recall-completeness.json")) {
  assert.equal(hasHonestRecallCompleteness(row.page), row.honest, row.name);
}
for (const row of await fixture("recall-trace.json")) {
  assert.equal(hasSafeRecallTrace(row.trace), row.safe, row.name);
}
for (const row of await fixture("status-matrix.json")) {
  assert.equal(hasSafeSynthesizedPage(statusMatrixPage(row)), row.safe, `${row.window}/${row.completeness}`);
}

async function fixture(name) {
  return JSON.parse(await readFile(new URL(name, fixtureRoot), "utf8"));
}

function statusMatrixPage(row) {
  const windows = {
    complete_terminal: { status: "complete", complete: true, hasMore: false, nextCursor: null },
    more_continuation: { status: "more", complete: false, hasMore: true, nextCursor: "cursor-v1:next" },
    incomplete_terminal: { status: "incomplete", complete: false, hasMore: false, nextCursor: null },
    incomplete_continuation: { status: "incomplete", complete: false, hasMore: true, nextCursor: "cursor-v1:next" },
  };
  const reasons = {
    complete: [],
    incomplete: ["accepted_work_pending"],
    degraded: ["projection_stale"],
    partial: ["source_bound"],
  };
  return {
    contractVersion: "1.0.0",
    items: row.empty ? [] : [{ id: "retrieval-node-v1:matrix", text: "Matrix result" }],
    window: windows[row.window],
    completeness: {
      version: "recall-completeness-v1",
      status: row.completeness,
      reasons: reasons[row.completeness],
      frontiers: {
        declaredFrontier: "frontier-v1:declared",
        newestIncludedStmFrontier: "frontier-v1:included",
        missingStmFrontierReason: null,
      },
    },
    absence: row.queryGap ? { kind: "query_gap" } : null,
  };
}
