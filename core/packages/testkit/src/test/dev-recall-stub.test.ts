/**
 * The dev fixture server, driven through the REAL client adapter.
 *
 * A stub that emits pages its own contract rejects is worse than no stub: it
 * sends the shells chasing a client bug that does not exist. So the assertion
 * that matters is not "the stub returns JSON" — it is that every page the stub
 * can produce is accepted by `parseSynthesizedMemoryPageResponse` and yields
 * the recall state the scenario NAME promises.
 *
 * Hermetic: `buildDevRecallStubPage` is a pure function, so this drives the
 * page builder directly and never opens a socket. The loopback bind is proven
 * separately with lsof + a LAN curl that must fail (hard rule 13); a unit test
 * cannot prove a bind.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DEV_RECALL_STUB_MALFORMED_BODY,
  DEV_RECALL_STUB_PATH,
  DevRecallStubInvalidCursorError,
  buildDevRecallStubPage,
} from "@omi-core/dev-recall-stub";
import {
  parseSynthesizedMemoryPageResponse,
  synthesizedMemoryItemsFromPage,
  synthesizedRecallStateFromPage,
} from "@omi-core/adapters-platform";

function serve(page: unknown): ReturnType<typeof parseSynthesizedMemoryPageResponse> {
  // Exactly what the route writes: canonical JSON text plus the parsed body.
  const text = JSON.stringify(page);
  return parseSynthesizedMemoryPageResponse({ status: 200, json: JSON.parse(text), text });
}

test("the stub serves the route the client adapter asks for", () => {
  // red-proof: change DEV_RECALL_STUB_PATH to "/v1/recall" — the stub and the
  // client stop agreeing and every shell pointed at it 404s.
  // APPLIED 2026-08-08: observed '/v1/recall' !== '/v1/memories/recall'
  assert.equal(DEV_RECALL_STUB_PATH, "/v1/memories/recall");
});

test("every complete-scenario page is accepted by the real adapter and walks to a terminal", () => {
  // red-proof: in buildDevRecallStubPage, emit `hasMore: true` together with
  // `nextCursor: null` on the last page. The adapter rejects it as unreadable
  // (the ratified window law) and this test fails on the very first page.
  // APPLIED 2026-08-08: observed  'unreadable' !== 'page'
  let cursor: string | null = null;
  const seen: string[] = [];
  for (let i = 0; i < 10; i++) {
    const outcome = serve(buildDevRecallStubPage("complete", 2, cursor));
    assert.equal(outcome.kind, "page", `page ${i} must satisfy the ratified contract`);
    if (outcome.kind !== "page") return;
    seen.push(...synthesizedMemoryItemsFromPage(outcome.page).map((it) => it.id));
    const recall = synthesizedRecallStateFromPage(outcome.page);
    assert.equal(recall.kind, "known");
    if (recall.kind !== "known") return;
    assert.equal(recall.status, "complete", "the complete scenario declares complete recall");
    if (!outcome.page.window.hasMore) {
      assert.equal(outcome.page.window.status, "complete", "the walk ends on a complete terminal");
      // Content, not count: the walk must be duplicate-free, which is the
      // guarantee a keyset cursor exists to provide.
      assert.equal(new Set(seen).size, seen.length, `walk emitted duplicates: ${seen.join(",")}`);
      assert.ok(seen.length > 2, "the scenario is genuinely multi-page");
      return;
    }
    cursor = outcome.page.window.nextCursor;
  }
  assert.fail("the complete scenario never terminated within 10 pages");
});

test("degraded and query_gap scenarios are honest, not merely well-formed", () => {
  // red-proof: make the degraded scenario emit completeness.status "complete"
  // while keeping reasons ["projection_stale"]. The ratified validator rejects
  // it outright (status must be DERIVED from reasons), so `kind` flips to
  // "unreadable" — the contract will not let the stub lie even by accident.
  // APPLIED 2026-08-08: observed  'unreadable' !== 'page'
  const degraded = serve(buildDevRecallStubPage("degraded", 2, null));
  assert.equal(degraded.kind, "page");
  if (degraded.kind !== "page") return;
  const dState = synthesizedRecallStateFromPage(degraded.page);
  assert.equal(dState.kind === "known" && dState.status, "degraded");
  assert.equal(dState.kind === "known" && dState.complete, false);
  assert.deepEqual(dState.kind === "known" ? dState.reasons : null, ["projection_stale"]);

  const gap = serve(buildDevRecallStubPage("query_gap", 2, null));
  assert.equal(gap.kind, "page");
  if (gap.kind !== "page") return;
  const gState = synthesizedRecallStateFromPage(gap.page);
  assert.equal(gState.kind === "known" && gState.queryGap, true, "a query gap is a searched answer");
  assert.equal(gState.kind === "known" && gState.complete, true);
  assert.equal(synthesizedMemoryItemsFromPage(gap.page).length, 0);
});

test("the malformed scenario is genuinely rejected — the stub can prove UNKNOWN", () => {
  // The whole point of shipping a malformed scenario is that a shell can SEE
  // its own unknown-state rendering. If the adapter accepted this body the
  // scenario would be untestable, so assert the rejection rather than trust it.
  const outcome = parseSynthesizedMemoryPageResponse({
    status: 200,
    json: JSON.parse(DEV_RECALL_STUB_MALFORMED_BODY),
    text: DEV_RECALL_STUB_MALFORMED_BODY,
  });
  assert.equal(outcome.kind, "unreadable");
});

test("a cursor the stub never issued is an error, never a silent restart", () => {
  // red-proof: revert decodeCursor to `return 0` for an unrecognized cursor.
  // This test stops throwing — and worse, the walk in the first test above
  // would never terminate against a client that sent a stale cursor, because
  // every page would restart at offset 0 and hand back a fresh continuation.
  // A duplicate-forever loop wearing the costume of a healthy paginated read.
  // APPLIED 2026-08-08: observed  "Missing expected exception".
  for (const bad of ["nonsense", "dev-recall-stub.k.notanumber", "dev-recall-stub.x.2", "../../etc"]) {
    assert.throws(
      () => buildDevRecallStubPage("complete", 2, bad),
      DevRecallStubInvalidCursorError,
      `cursor ${bad} must be refused`,
    );
  }
  // The cursors it DOES issue keep working.
  const first = serve(buildDevRecallStubPage("complete", 2, null));
  assert.equal(first.kind, "page");
  if (first.kind !== "page") return;
  assert.ok(first.page.window.hasMore);
  assert.equal(serve(buildDevRecallStubPage("complete", 2, first.page.window.nextCursor)).kind, "page");
});

test("identical requests produce byte-identical pages", () => {
  // red-proof: seed any item text with Date.now() or Math.random(). The two
  // serializations diverge. Determinism is the entire value proposition of a
  // fixture server — a flaky fixture makes every downstream failure ambiguous.
  // APPLIED 2026-08-08: observed the two JSON strings differ.
  for (const scenario of ["complete", "degraded", "query_gap"] as const) {
    const a = JSON.stringify(buildDevRecallStubPage(scenario, 3, null));
    const b = JSON.stringify(buildDevRecallStubPage(scenario, 3, null));
    assert.equal(a, b, `${scenario} is not deterministic`);
  }
});
