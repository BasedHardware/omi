/**
 * The platform memory adapter against a HOSTILE server.
 *
 * The dev stub is well-behaved by construction; BE-SURFACE's real binding is
 * not, and neither is anything that ships later. Every case below is a thing a
 * real server does — truncate a body, forget an envelope, reissue a cursor,
 * repeat a row — and each one has a DEFINED outcome asserted here.
 *
 * The governing rule is hard rule 12, in its strongest form: a response we do
 * not fully understand yields `null`, never an empty snapshot and never a
 * `complete` one, because `Projection.reconcile` turns
 * `{ complete: true, ids: [] }` into a full local wipe. Every "must be null"
 * assertion in this file is guarding a user-data-loss path, not a type error.
 *
 * Hermetic: scripted responses only.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse } from "@omi-core/contracts";
import {
  PLATFORM_MEMORY_RECALL_MAX_WALK_ITEMS,
  fetchSynthesizedMemoryIdSnapshot,
  parseSynthesizedMemoryPageResponse,
  walkSynthesizedMemoryPages,
} from "@omi-core/adapters-platform";

const DECLARED = "frontier-v1:declared";
const STM = "frontier-v1:included";

function completeness(): unknown {
  return {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: DECLARED,
      newestSearchedAcceptedFrontier: DECLARED,
      missingAcceptedFrontierReason: null,
      newestSearchedStmFrontier: STM,
      missingStmFrontierReason: null,
    },
  };
}

function page(ids: readonly string[], nextCursor: string | null): Record<string, unknown> {
  return {
    contractVersion: "1.0.0",
    items: ids.map((id) => ({ id, text: `synthesized ${id}` })),
    window:
      nextCursor === null
        ? { status: "complete", complete: true, hasMore: false, nextCursor: null }
        : { status: "more", complete: false, hasMore: true, nextCursor },
    completeness: completeness(),
    absence: null,
  };
}

function ok(body: unknown): HttpResponse {
  const text = JSON.stringify(body);
  return { status: 200, json: JSON.parse(text), text };
}

class Scripted implements HttpClient {
  calls = 0;
  constructor(private readonly queue: readonly HttpResponse[]) {}
  async request(): Promise<HttpResponse> {
    const next = this.queue[Math.min(this.calls, this.queue.length - 1)]!;
    this.calls += 1;
    return next;
  }
}

/** Models our own fixed bug's cousin: any cursor restarts at page one. */
class CursorAmnesiaServer implements HttpClient {
  calls = 0;
  constructor(private readonly terminateAfter: number) {}
  async request(_m: string, path: string): Promise<HttpResponse> {
    this.calls += 1;
    // Always serves the FIRST page's ids, regardless of the cursor it is given.
    const last = this.calls >= this.terminateAfter;
    void path;
    return ok(page(["mem-1", "mem-2"], last ? null : `cursor-${this.calls}`));
  }
}

// ── malformed bodies ─────────────────────────────────────────────────────────

test("truncated or garbage JSON is unreadable, and a snapshot is null", async () => {
  // red-proof: in parseSynthesizedMemoryPageResponse, return
  // `{ kind: "page", page: res.json as … }` when parseSynthesizedPageJson gives
  // null. Every assertion below flips, and the snapshot becomes a complete
  // empty set — a full local wipe through Projection.reconcile.
  // APPLIED 2026-08-08: observed 'page' !== 'unreadable'
  const honest = JSON.stringify(page(["mem-1"], null));
  const bodies = [
    honest.slice(0, honest.length - 1), // truncated mid-object
    honest.slice(0, 12), // truncated early
    "", // empty
    "not json at all",
    "{", // unbalanced
    "[]", // valid JSON, wrong shape
    "null",
    `${honest}${honest}`, // two documents concatenated
  ];
  for (const text of bodies) {
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
    const outcome = parseSynthesizedMemoryPageResponse({ status: 200, json: parsed, text });
    assert.equal(outcome.kind, "unreadable", `body ${JSON.stringify(text.slice(0, 20))} must be unreadable`);
    const snapshot = await fetchSynthesizedMemoryIdSnapshot(
      new Scripted([{ status: 200, json: parsed, text }]),
    );
    assert.equal(snapshot, null, "an unreadable body must never become a snapshot");
  }
});

test("optional metadata that is present but malformed rejects the page, never strips it", async () => {
  // HONEST LABEL: this is a CHARACTERIZATION test of the ratified contract, not
  // a red-proof of our own logic. The rejection is performed by the ratified
  // validator, which this branch may not modify, so there is no mutation inside
  // our code that makes only this test fail — the cases below all reject at
  // BOTH parse boundaries. Its value is real but different: it pins which
  // malformed-metadata shapes the contract refuses, so a future ratified-package
  // upgrade that quietly loosened any of them would land red here instead of
  // silently letting half-understood lineage onto a surface.
  //
  // red-proof (of the wiring, which is the part we own): make
  // parseSynthesizedMemoryPageResponse return `{ kind: "page", … }`
  // unconditionally. APPLIED 2026-08-08: observed 'page' !== 'unreadable'.
  const bad: readonly unknown[] = [
    { id: "m1", text: "t", citations: "not-an-array" },
    { id: "m1", text: "t", citations: [""] }, // empty ref
    { id: "m1", text: "t", citations: ["dup", "dup"] }, // duplicate refs
    { id: "m1", text: "t", citations: [42] },
    { id: "m1", text: "t", provenance: {} }, // missing required keys
    { id: "m1", text: "t", provenance: { synthesisVersion: "v1", inputDigest: "short", outputDigest: "b".repeat(64) } },
    { id: "m1", text: "t", provenance: { synthesisVersion: "", inputDigest: "a".repeat(64), outputDigest: "b".repeat(64) } },
    { id: "m1", text: "t", provenance: { synthesisVersion: "v1", inputDigest: "A".repeat(64), outputDigest: "b".repeat(64) } }, // uppercase hex
    { id: "m1", text: "   " }, // whitespace-only text
    { id: "", text: "t" }, // empty id
    { id: "m1", text: "t", extra: "unexpected" }, // unknown key
  ];
  for (const item of bad) {
    const p = page([], null);
    p["items"] = [item];
    p["absence"] = null;
    const text = JSON.stringify(p);
    const outcome = parseSynthesizedMemoryPageResponse({ status: 200, json: JSON.parse(text), text });
    assert.equal(outcome.kind, "unreadable", `item ${JSON.stringify(item)} must reject the page`);
  }
});

test("an envelope present on page one and missing on page two fails the whole walk", async () => {
  // red-proof: relax the exact-key check so a page without `completeness` is
  // accepted. The walk then terminates on page two and reports wholeSet from
  // page one's envelope alone — completeness inherited from a page that is not
  // the page being described.
  // APPLIED 2026-08-08: observed  {...} !== null
  const second = page(["mem-3"], null);
  delete second["completeness"];
  const http = new Scripted([ok(page(["mem-1", "mem-2"], "cursor-1")), ok(second)]);
  assert.equal(await walkSynthesizedMemoryPages(http), null);
  assert.equal(await fetchSynthesizedMemoryIdSnapshot(new Scripted([ok(page(["mem-1"], "c1")), ok(second)])), null);
});

test("a 200 whose body is a DIFFERENT well-formed shape is still unreadable", async () => {
  // The dangerous near-miss: a proxy or an error handler returning a valid JSON
  // object that is simply not this contract. It must not be coerced.
  for (const body of [
    { error: "unauthorized" },
    { data: { items: [] } },
    { contractVersion: "2.0.0", items: [], window: null, completeness: null, absence: null },
    { ...page(["mem-1"], null), extraTopLevelKey: 1 },
  ]) {
    const text = JSON.stringify(body);
    assert.equal(
      parseSynthesizedMemoryPageResponse({ status: 200, json: JSON.parse(text), text }).kind,
      "unreadable",
      `${text.slice(0, 40)} must be unreadable`,
    );
  }
});

// ── pagination hostility ─────────────────────────────────────────────────────

test("a cursor the server no longer recognises is an error, and the walk yields null", async () => {
  // BE-SURFACE answers a tampered cursor with 400 (their status file). A 4xx
  // mid-walk must abort the walk, not truncate it into a "set".
  // red-proof: change the walk's `if (outcome.kind !== "page") return null` to
  // `break` — the walk then returns page one's ids as though complete.
  // APPLIED 2026-08-08: observed  {...} !== null
  for (const status of [400, 401, 403, 404, 410, 500, 503]) {
    const http = new Scripted([ok(page(["mem-1"], "stale-cursor")), { status, json: null }]);
    assert.equal(await walkSynthesizedMemoryPages(http), null, `mid-walk ${status} must abort`);
  }
});

test("a server that ignores the cursor and replays page one is refused, not looped", async () => {
  // THE HOSTILE CASE THAT MATTERS. This is the exact cousin of the bug found
  // and fixed in our own dev stub, where an unrecognized cursor decoded to
  // offset 0. Against such a server a keyset walk re-reads page one forever;
  // if it ever lands on a complete-terminal page, a naive client claims the
  // whole set from a duplicate-riddled prefix and reconciles against it.
  //
  // red-proof: remove the `if (seenIds.has(item.id)) return null` guard from
  // walkSynthesizedMemoryPages. The walk below then returns wholeSet:true with
  // ids ["mem-1","mem-2","mem-1","mem-2",...] — a complete snapshot asserting a
  // set that repeats, which reconcile would happily act on.
  // APPLIED 2026-08-08: observed  AssertionError: a repeated id breaks the
  // keyset guarantee, so the walk knows nothing ... {...} !== null
  const terminating = new CursorAmnesiaServer(3);
  assert.equal(
    await walkSynthesizedMemoryPages(terminating),
    null,
    "a repeated id breaks the keyset guarantee, so the walk knows nothing",
  );
  assert.ok(terminating.calls >= 2, "it did keep reading until the repeat was visible");

  // And the never-terminating variant is bounded rather than hanging.
  const forever = new CursorAmnesiaServer(Number.MAX_SAFE_INTEGER);
  assert.equal(await fetchSynthesizedMemoryIdSnapshot(forever, { maxPages: 50 }), null);
  assert.ok(forever.calls <= 50, `bounded: ${forever.calls} calls`);
});

test("a server that reissues the same cursor is caught even without a duplicate id", async () => {
  // red-proof: remove the `seenCursors` cycle check from
  // walkSynthesizedMemoryPages. The walk below then spins all the way to
  // maxPages and returns a NON-NULL wholeSet:false walk, i.e. a cycling server
  // is reported as a legitimate truncated read rather than as a broken one.
  // APPLIED 2026-08-08: observed a non-null walk with pages === 8 and 8 calls.
  //
  // WHY THIS TEST LOOKS THE WAY IT DOES. My first version of it used an
  // item-less continuation page, and removing the guard did not turn it red —
  // the page was already rejected by the contract (an item-less page must carry
  // a query_gap absence, and an absence is only valid on a terminal page), so
  // the guard was never reached and the test was decorative. Found by applying
  // the mutation, not by reading it. The server below therefore emits FRESH ids
  // on every page, so the duplicate-id guard can never fire, and only the
  // repeated cursor reveals the cycle.
  let n = 0;
  const cycling: HttpClient = {
    async request(): Promise<HttpResponse> {
      n += 1;
      return ok(page([`mem-fresh-${n}`], "same-cursor"));
    },
  };
  assert.equal(
    await walkSynthesizedMemoryPages(cycling, { maxPages: 8 }),
    null,
    "a repeated cursor means the server is cycling us, which is not a truncated read",
  );
  assert.equal(n, 2, "it stops on the SECOND sight of the cursor, not at maxPages");
});

test("a continuation page with no items is rejected by the contract itself", async () => {
  // "Fewer items than the window implies", in its sharpest form: a page that
  // says there is more but hands over nothing. The ratified validator already
  // forbids it — an item-less page must carry a query_gap absence, and an
  // absence is only valid on a terminal page — so this is asserted rather than
  // re-implemented. Proving it here is what lets the walk trust the shape.
  const empty = page([], "cursor-1");
  const text = JSON.stringify(empty);
  assert.equal(parseSynthesizedMemoryPageResponse({ status: 200, json: JSON.parse(text), text }).kind, "unreadable");

  // The legal near-neighbour: a terminal page with no items AND a query gap.
  const gap = page([], null);
  gap["absence"] = { kind: "query_gap" };
  const gapText = JSON.stringify(gap);
  assert.equal(
    parseSynthesizedMemoryPageResponse({ status: 200, json: JSON.parse(gapText), text: gapText }).kind,
    "page",
    "a searched-and-empty terminal page is legitimate and must still work",
  );
});

test("a walk is bounded in total items, and exceeding the bound fails rather than truncates", async () => {
  // red-proof: replace `if (items.length + pageItems.length > maxItems) return null`
  // with a `break`. The walk then returns a TRUNCATED item list that terminated
  // normally — indistinguishable from a complete one, which is the worst
  // available outcome.
  // APPLIED 2026-08-08: observed  {...} !== null
  let n = 0;
  const flood: HttpClient = {
    async request(): Promise<HttpResponse> {
      const ids = Array.from({ length: 100 }, (_, i) => `mem-${n * 100 + i}`);
      n += 1;
      return ok(page(ids, `cursor-${n}`));
    },
  };
  assert.equal(await walkSynthesizedMemoryPages(flood, { maxItems: 250, maxPages: 100 }), null);
  assert.ok(n <= 4, `stopped as soon as the ceiling was crossed: ${n} pages`);
  assert.equal(PLATFORM_MEMORY_RECALL_MAX_WALK_ITEMS, 20_000);
});

test("an honest multi-page walk still succeeds — the guards are not blanket refusal", async () => {
  // The positive control. Every test above asserts a refusal; without this one,
  // hardcoding `return null` in walkSynthesizedMemoryPages would pass them all.
  const http = new Scripted([
    ok(page(["mem-1", "mem-2"], "cursor-1")),
    ok(page(["mem-3", "mem-4"], "cursor-2")),
    ok(page(["mem-5"], null)),
  ]);
  const walk = await walkSynthesizedMemoryPages(http);
  assert.ok(walk, "a well-behaved server must still walk cleanly");
  assert.equal(walk.pages, 3);
  assert.deepEqual(walk.items.map((i) => i.id), ["mem-1", "mem-2", "mem-3", "mem-4", "mem-5"]);
  assert.equal(walk.wholeSet, true);

  const snapshot = await fetchSynthesizedMemoryIdSnapshot(
    new Scripted([
      ok(page(["mem-1", "mem-2"], "cursor-1")),
      ok(page(["mem-3", "mem-4"], "cursor-2")),
      ok(page(["mem-5"], null)),
    ]),
  );
  assert.ok(snapshot);
  assert.equal(snapshot.complete, true);
  assert.deepEqual([...snapshot.ids], ["mem-1", "mem-2", "mem-3", "mem-4", "mem-5"]);
});
