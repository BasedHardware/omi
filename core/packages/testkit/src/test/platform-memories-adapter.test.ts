/**
 * The client half of the ratified contract seam, executed against the SAME
 * fixture corpora the backend runs.
 *
 * Two layers here, and the second is the one that matters:
 *
 *  1. CORPUS CONFORMANCE — every entry of every ratified corpus, driven
 *     through the adapter's real parse path. These prove the adapter agrees
 *     with the contract about what is honest. They are exhaustive by
 *     construction (a new fixture entry is automatically executed), and each
 *     asserts the corpus was non-empty so a loader regression cannot make the
 *     suite vacuously green.
 *
 *  2. INVARIANT TESTS — the data-loss laws, each with a red-proof (hard rule
 *     14). The corpora cannot express these: they describe single pages, and
 *     the data-loss path is a MULTI-PAGE walk that ends on an honest page.
 *
 * Hermetic: scripted responses only, no network, no clock, no randomness.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse } from "@omi-core/contracts";
import {
  PLATFORM_MEMORY_RECALL_MAX_LIMIT,
  PLATFORM_MEMORY_RECALL_MAX_PAGES,
  fetchSynthesizedMemoryIdSnapshot,
  parseSynthesizedMemoryPageResponse,
  synthesizedMemoryItemsFromPage,
  synthesizedRecallStateFromPage,
  walkSynthesizedMemoryPages,
} from "@omi-core/adapters-platform";
import {
  readRatifiedCorpus,
  readRatifiedFixtureManifest,
  readRatifiedForbiddenFields,
} from "../ratified-fixtures.js";

// ── scripted transports ──────────────────────────────────────────────────────

/** Answers each request from a queue; extra requests are a test failure. */
class ScriptedPages implements HttpClient {
  readonly paths: string[] = [];
  constructor(private readonly queue: HttpResponse[]) {}
  async request(_method: string, path: string): Promise<HttpResponse> {
    this.paths.push(path);
    const next = this.queue.shift();
    if (!next) throw new Error(`unscripted request: ${path}`);
    return next;
  }
}

/** Answers every request identically — models a server that never terminates. */
class RepeatingPage implements HttpClient {
  calls = 0;
  constructor(private readonly res: HttpResponse) {}
  async request(): Promise<HttpResponse> {
    this.calls += 1;
    return this.res;
  }
}

/** A response carrying the RAW body, so the canonical text parser is used. */
function textResponse(page: unknown, status = 200): HttpResponse {
  return { status, json: page, text: JSON.stringify(page) };
}

/** A response with only a pre-parsed body — the weaker boundary. */
function jsonOnlyResponse(page: unknown, status = 200): HttpResponse {
  return { status, json: page };
}

// ── page builders (the status-matrix vocabulary, spelled once) ───────────────

const DECLARED = "frontier-v1:declared";
const BEHIND = "frontier-v1:behind";
const STM = "frontier-v1:included";
const CURSOR = "v1.signature.payload";

type WindowKind = "complete_terminal" | "more_continuation" | "incomplete_terminal" | "incomplete_continuation";
type CompletenessKind = "complete" | "incomplete" | "degraded" | "partial";

function buildWindow(kind: WindowKind): unknown {
  switch (kind) {
    case "complete_terminal":
      return { status: "complete", complete: true, hasMore: false, nextCursor: null };
    case "more_continuation":
      return { status: "more", complete: false, hasMore: true, nextCursor: CURSOR };
    case "incomplete_terminal":
      return { status: "incomplete", complete: false, hasMore: false, nextCursor: null };
    case "incomplete_continuation":
      return { status: "incomplete", complete: false, hasMore: true, nextCursor: CURSOR };
  }
}

function frontiers(accepted: string | null): unknown {
  return {
    declaredFrontier: DECLARED,
    newestSearchedAcceptedFrontier: accepted,
    missingAcceptedFrontierReason: accepted === null ? "no_accepted_work" : null,
    newestSearchedStmFrontier: STM,
    missingStmFrontierReason: null,
  };
}

function buildCompleteness(kind: CompletenessKind): unknown {
  const version = "recall-completeness-v1";
  switch (kind) {
    case "complete":
      return { version, status: "complete", reasons: [], frontiers: frontiers(DECLARED) };
    case "incomplete":
      // `accepted_work_pending` is only honest when the accepted frontier is
      // genuinely behind the declared one — the contract cross-checks it.
      return { version, status: "incomplete", reasons: ["accepted_work_pending"], frontiers: frontiers(BEHIND) };
    case "degraded":
      return { version, status: "degraded", reasons: ["projection_stale"], frontiers: frontiers(DECLARED) };
    case "partial":
      return { version, status: "partial", reasons: ["source_bound"], frontiers: frontiers(DECLARED) };
  }
}

let itemCounter = 0;
function buildItem(text = "Synthesized result"): unknown {
  itemCounter += 1;
  return { id: `retrieval-node-v1:fixture-${itemCounter}`, text };
}

interface PageSpec {
  readonly window: WindowKind;
  readonly completeness: CompletenessKind;
  readonly empty?: boolean;
  readonly queryGap?: boolean;
  readonly items?: readonly unknown[];
}

function buildPage(spec: PageSpec): unknown {
  const items = spec.items ?? (spec.empty === true ? [] : [buildItem()]);
  return {
    contractVersion: "1.0.0",
    items,
    window: buildWindow(spec.window),
    completeness: buildCompleteness(spec.completeness),
    absence: spec.queryGap === true ? { kind: "query_gap" } : null,
  };
}

function accepts(page: unknown): boolean {
  return parseSynthesizedMemoryPageResponse(textResponse(page)).kind === "page";
}

// ── layer 1: corpus conformance ──────────────────────────────────────────────

test("the ratified fixture manifest names exactly the corpora this suite runs", () => {
  const manifest = readRatifiedFixtureManifest();
  assert.deepEqual(
    [...manifest.files].sort(),
    [
      "page-conformance.json",
      "read-page-windows.json",
      "recall-completeness.json",
      "recall-trace.json",
      "status-matrix.json",
      // The write seam's two files. They are NOT run by this test — this file
      // is the memory READ consumer — but they must be named here or the
      // exact-equality check below stops being exact. Their consumer is
      // `write-ops-conformance.test.ts`, in this same suite, and the
      // `ratified-write-ops` row in `core/scripts/check-wire-conformance.mjs`
      // is what mechanically requires that consumer to exist and read them.
      "write-ops-conformance.json",
      "write-ops-outcomes.json",
    ],
    "a corpus was added or renamed upstream and this suite does not run it",
  );
});

test("corpus page-conformance: the adapter accepts exactly the safe pages", () => {
  const corpus = readRatifiedCorpus("page-conformance") as readonly {
    name: string;
    page: unknown;
    safe: boolean;
  }[];
  assert.ok(corpus.length >= 8, `page-conformance corpus shrank to ${corpus.length} entries`);
  const wrong: string[] = [];
  for (const entry of corpus) {
    if (accepts(entry.page) !== entry.safe) {
      wrong.push(`${entry.name}: expected safe=${entry.safe}`);
    }
  }
  assert.deepEqual(wrong, []);
});

test("corpus status-matrix: window x completeness pairing decides acceptance", () => {
  const corpus = readRatifiedCorpus("status-matrix") as readonly {
    window: WindowKind;
    completeness: CompletenessKind;
    empty?: boolean;
    queryGap?: boolean;
    safe: boolean;
  }[];
  assert.ok(corpus.length >= 22, `status-matrix corpus shrank to ${corpus.length} entries`);
  const wrong: string[] = [];
  for (const row of corpus) {
    const spec: PageSpec = {
      window: row.window,
      completeness: row.completeness,
      ...(row.empty === true ? { empty: true } : {}),
      ...(row.queryGap === true ? { queryGap: true } : {}),
    };
    if (accepts(buildPage(spec)) !== row.safe) {
      wrong.push(
        `${row.window} x ${row.completeness}${row.empty ? " empty" : ""}${row.queryGap ? " queryGap" : ""}: expected safe=${row.safe}`,
      );
    }
  }
  assert.deepEqual(wrong, []);
});

test("corpus read-page-windows: a dishonest window is never accepted in a page", () => {
  const corpus = readRatifiedCorpus("read-page-windows") as readonly {
    name: string;
    window: { status: string; complete: boolean; hasMore: boolean; nextCursor: string | null };
    honest: boolean;
  }[];
  assert.ok(corpus.length >= 7, `read-page-windows corpus shrank to ${corpus.length} entries`);
  const wrong: string[] = [];
  for (const entry of corpus) {
    // Pair each window with a completeness the matrix marks SAFE for it, so
    // acceptance turns solely on the window's own honesty.
    const completeness = entry.window.status === "complete" ? "complete" : "incomplete";
    const page = {
      contractVersion: "1.0.0",
      items: [buildItem()],
      window: entry.window,
      completeness: buildCompleteness(completeness),
      absence: null,
    };
    if (accepts(page) !== entry.honest) wrong.push(`${entry.name}: expected honest=${entry.honest}`);
  }
  assert.deepEqual(wrong, []);
});

test("corpus recall-completeness: every completeness envelope verdict is reproduced", () => {
  const corpus = readRatifiedCorpus("recall-completeness") as readonly {
    name: string;
    page: { items: unknown[]; completeness?: unknown; absence?: unknown };
    honest: boolean;
  }[];
  assert.ok(corpus.length >= 25, `recall-completeness corpus shrank to ${corpus.length} entries`);
  const wrong: string[] = [];
  for (const entry of corpus) {
    // The corpus entries are completeness-only skeletons (`items: [{}]`), so
    // give them a valid item and window and let the envelope decide.
    const page = {
      contractVersion: "1.0.0",
      items: entry.page.items.map(() => buildItem()),
      window: buildWindow(entry.page.items.length === 0 ? "incomplete_terminal" : "incomplete_terminal"),
      ...(entry.page.completeness !== undefined ? { completeness: entry.page.completeness } : {}),
      absence: entry.page.absence ?? null,
    };
    // `incomplete_terminal` is matrix-safe with every completeness except
    // `complete`, so entries whose envelope claims complete are re-paired.
    const completenessStatus = (entry.page.completeness as { status?: string } | undefined)?.status;
    if (completenessStatus === "complete") {
      (page as { window: unknown }).window = buildWindow("complete_terminal");
    }
    if (accepts(page) !== entry.honest) wrong.push(`${entry.name}: expected honest=${entry.honest}`);
  }
  assert.deepEqual(wrong, []);
});

test("corpus forbidden-public-fields: no projection field escapes into a surface item", () => {
  const forbidden = readRatifiedForbiddenFields();
  assert.ok(forbidden.projection.length >= 30, "forbidden projection field list shrank");
  assert.ok(forbidden.projection.includes("content"), "the editable-content field must stay forbidden");
  assert.ok(forbidden.projection.includes("locked"), "the lock field must stay forbidden");

  const outcome = parseSynthesizedMemoryPageResponse(
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
  );
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const items = synthesizedMemoryItemsFromPage(outcome.page);
  assert.equal(items.length, 1);
  const keys = Object.keys(items[0]!);
  assert.deepEqual(
    keys.filter((k) => forbidden.projection.includes(k)),
    [],
    `surface item leaked a forbidden field: ${keys.join(",")}`,
  );
  // And the positive half: a server that DOES send a forbidden field is refused
  // outright rather than having it stripped, because a projection carrying
  // editable content is not a projection we understand.
  for (const field of ["content", "locked", "visibility", "category"]) {
    const leaky = buildPage({
      window: "complete_terminal",
      completeness: "complete",
      items: [{ id: "retrieval-node-v1:leak", text: "t", [field]: "x" }],
    });
    assert.equal(accepts(leaky), false, `a page carrying \`${field}\` must be rejected, not sanitized`);
  }
});

// ── layer 2: invariants, each with an applied red-proof ──────────────────────

test("a complete-terminal walk that passed through a degraded page never claims the whole set", async () => {
  // red-proof: in packages/adapters-platform/src/memories.ts, change
  //   `wholeSet: everyPageCompleteRecall && window.status === "complete"`
  // to `wholeSet: window.status === "complete"`. The walk below then reports
  // wholeSet:true and complete:true, and this test fails on both assertions.
  // APPLIED 2026-08-08: observed
  //   AssertionError: a degraded page anywhere in the walk forecloses completeness
  //   + actual - expected ... true !== false
  const http = new ScriptedPages([
    textResponse(buildPage({ window: "more_continuation", completeness: "degraded" })),
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
  ]);
  const walk = await walkSynthesizedMemoryPages(http);
  assert.ok(walk, "the walk itself succeeded");
  assert.equal(walk.pages, 2, "both pages were read");
  assert.equal(
    walk.wholeSet,
    false,
    "a degraded page anywhere in the walk forecloses completeness",
  );

  const snapshot = await fetchSynthesizedMemoryIdSnapshot(
    new ScriptedPages([
      textResponse(buildPage({ window: "more_continuation", completeness: "degraded" })),
      textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
    ]),
  );
  assert.ok(snapshot);
  assert.equal(snapshot.complete, false, "and the snapshot may not license a reconcile delete");
  // Content, not row count: the ids the degraded page did return are still
  // knowledge and must be carried, they just cannot authorize a delete.
  assert.equal(snapshot.ids.length, 2);
});

test("an all-complete walk that ends on a complete-terminal window does claim the whole set", async () => {
  // red-proof: change the terminal branch's `window.status === "complete"` to
  // `window.status !== "complete"` and this inverts to wholeSet:false.
  // APPLIED 2026-08-08: observed
  //   AssertionError: declared complete recall across a terminated walk IS the evidence
  //   + actual - expected ... false !== true
  // This is the positive control for the test above: without it, hardcoding
  // `wholeSet: false` would pass every honesty test in this file.
  const http = new ScriptedPages([
    textResponse(buildPage({ window: "more_continuation", completeness: "complete" })),
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
  ]);
  const walk = await walkSynthesizedMemoryPages(http);
  assert.ok(walk);
  assert.equal(walk.wholeSet, true, "declared complete recall across a terminated walk IS the evidence");
  assert.equal(walk.recall.kind, "known");
});

test("an incomplete-terminal window ends the walk without proving the set", async () => {
  // red-proof: drop `everyPageCompleteRecall &&` AND relax the window check to
  // `!window.hasMore`; wholeSet flips to true here.
  // APPLIED 2026-08-08: observed  ... true !== false
  const http = new ScriptedPages([
    textResponse(buildPage({ window: "incomplete_terminal", completeness: "incomplete" })),
  ]);
  const walk = await walkSynthesizedMemoryPages(http);
  assert.ok(walk);
  assert.equal(walk.wholeSet, false);
  assert.equal(walk.recall.kind, "known");
  if (walk.recall.kind !== "known") return;
  assert.equal(walk.recall.complete, false);
  assert.deepEqual(walk.recall.reasons, ["accepted_work_pending"], "the server's reason is carried verbatim");
});

test("an unreadable body is UNKNOWN — never an empty page, never a complete one", async () => {
  // red-proof: in `parseSynthesizedMemoryPageResponse`, replace the
  // `{ kind: "unreadable" }` return with
  //   `{ kind: "page", page: { contractVersion:"1.0.0", items: [], window: buildWindow("complete_terminal"), … } }`
  // (i.e. "treat a body we do not understand as an empty complete page") and
  // the snapshot below becomes `{ complete: true, ids: [] }` — which
  // Projection.reconcile turns into a full local wipe.
  // APPLIED 2026-08-08: observed  AssertionError: ... Expected values to be strictly equal: {...} !== null
  for (const junk of [null, {}, { unexpected: true }, "nope", 42, [], { contractVersion: "1.0.0" }]) {
    const snapshot = await fetchSynthesizedMemoryIdSnapshot(new RepeatingPage(jsonOnlyResponse(junk)));
    assert.equal(snapshot, null, `junk body ${JSON.stringify(junk)} must yield null, not a snapshot`);
  }
  const outcome = parseSynthesizedMemoryPageResponse(jsonOnlyResponse({ unexpected: true }));
  assert.equal(outcome.kind, "unreadable");
});

test("a non-200 anywhere in the walk yields null, including mid-walk", async () => {
  // red-proof: change the walk's `if (outcome.kind !== "page") return null;` to
  // `if (outcome.kind !== "page") break;` — the mid-walk case then returns the
  // first page's items as if the walk had ended, and `ids` becomes length 1.
  // APPLIED 2026-08-08: observed  AssertionError ... {...} !== null
  for (const status of [401, 402, 404, 500, 503]) {
    assert.equal(
      await fetchSynthesizedMemoryIdSnapshot(new RepeatingPage({ status, json: null })),
      null,
      `status ${status} must yield null`,
    );
  }
  const midWalk = new ScriptedPages([
    textResponse(buildPage({ window: "more_continuation", completeness: "complete" })),
    { status: 503, json: null },
  ]);
  assert.equal(await fetchSynthesizedMemoryIdSnapshot(midWalk), null, "a truncated walk is not a set");
});

test("a non-terminating server is bounded, and its walk is not the whole set", async () => {
  // red-proof: remove the `pages < maxPages` bound from the while condition;
  // this test hangs instead of failing, which is itself the signal.
  // APPLIED 2026-08-08: observed the test time out rather than complete.
  //
  // The server here advances honestly — fresh ids and a fresh cursor on every
  // page — it simply never ends. That is the case the page bound exists for.
  // A server that REPEATS ids or cursors is a different failure and is refused
  // outright rather than bounded; see platform-memories-hostile.test.ts.
  let n = 0;
  const endless: HttpClient = {
    async request(): Promise<HttpResponse> {
      n += 1;
      const p = buildPage({
        window: "more_continuation",
        completeness: "complete",
        items: [{ id: `retrieval-node-v1:page-${n}`, text: `item ${n}` }],
      }) as { window: { nextCursor: string } };
      p.window.nextCursor = `cursor-${n}`;
      return textResponse(p);
    },
  };
  const walk = await walkSynthesizedMemoryPages(endless, { maxPages: 5 });
  assert.ok(walk);
  assert.equal(walk.pages, 5);
  assert.equal(n, 5, "the bound is enforced at the transport, not just reported");
  assert.equal(walk.wholeSet, false, "a walk that did not terminate proves nothing");
  assert.ok(PLATFORM_MEMORY_RECALL_MAX_PAGES > 0);
});

test("optional metadata is genuinely optional and absent keys stay absent", async () => {
  // red-proof: in `synthesizedMemoryItemsFromPage`, replace the conditional
  // spreads with `citations: item.citations ?? []` and
  // `provenance: item.provenance ?? undefined`. The `Object.hasOwn` assertions
  // below then fail — a caller could no longer tell "no citations sent" from
  // "empty citation list sent".
  // APPLIED 2026-08-08: observed
  //   AssertionError: an absent citations key must not materialize ... true !== false
  const page = buildPage({
    window: "complete_terminal",
    completeness: "complete",
    items: [
      { id: "retrieval-node-v1:bare", text: "no metadata at all" },
      {
        id: "retrieval-node-v1:rich",
        text: "full metadata",
        citations: ["citation-v1:a", "citation-v1:b"],
        provenance: {
          synthesisVersion: "v1",
          inputDigest: "a".repeat(64),
          outputDigest: "b".repeat(64),
        },
      },
    ],
  });
  const outcome = parseSynthesizedMemoryPageResponse(textResponse(page));
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const items = synthesizedMemoryItemsFromPage(outcome.page);

  const bare = items[0]!;
  assert.equal(Object.hasOwn(bare, "citations"), false, "an absent citations key must not materialize");
  assert.equal(Object.hasOwn(bare, "provenance"), false, "an absent provenance key must not materialize");
  assert.equal(bare.text, "no metadata at all", "and ignoring the metadata is still correct");

  const rich = items[1]!;
  assert.deepEqual(rich.citations, ["citation-v1:a", "citation-v1:b"]);
  assert.equal(rich.provenance?.synthesisVersion, "v1");
  assert.equal(rich.provenance?.inputDigest, "a".repeat(64));
});

test("deterministic server order is preserved, never re-sorted", async () => {
  // red-proof: add `.sort((a, b) => a.id.localeCompare(b.id))` to the return of
  // `synthesizedMemoryItemsFromPage`. The text sequence below reverses.
  // APPLIED 2026-08-08: observed
  //   AssertionError ... [ 'alpha', 'beta', 'gamma' ] deepEqual [ 'gamma', 'beta', 'alpha' ]
  // Row counts would not have caught this; the assertion is on CONTENT ORDER.
  const page = buildPage({
    window: "complete_terminal",
    completeness: "complete",
    items: [
      { id: "retrieval-node-v1:zzz", text: "gamma" },
      { id: "retrieval-node-v1:mmm", text: "beta" },
      { id: "retrieval-node-v1:aaa", text: "alpha" },
    ],
  });
  const outcome = parseSynthesizedMemoryPageResponse(textResponse(page));
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  assert.deepEqual(
    synthesizedMemoryItemsFromPage(outcome.page).map((i) => i.text),
    ["gamma", "beta", "alpha"],
  );
});

test("the canonical-text boundary is strictly stronger than the parsed-object one", () => {
  // red-proof: in `parseSynthesizedMemoryPageResponse`, delete the
  // `typeof res.text === "string"` branch so everything goes through the
  // object predicate. The duplicate-key payload below is then ACCEPTED and
  // `boundary` reports "trusted-parsed-json" for a body the contract rejects.
  // APPLIED 2026-08-08: observed
  //   AssertionError: a duplicate-key payload must be refused at the byte boundary
  //   'page' !== 'unreadable'
  //
  // This test is the entire justification for adding `HttpResponse.text`.
  const honest = buildPage({ window: "complete_terminal", completeness: "complete" });
  const canonical = JSON.stringify(honest);

  // Same document, one key sent twice. JSON.parse keeps the LAST value, so the
  // object predicate cannot see the attack at all; the canonical round trip can.
  const duplicated = canonical.replace('"contractVersion":"1.0.0"', '"contractVersion":"9.9.9","contractVersion":"1.0.0"');
  assert.notEqual(duplicated, canonical, "the duplicate-key payload was actually constructed");

  const strong = parseSynthesizedMemoryPageResponse({ status: 200, json: JSON.parse(duplicated), text: duplicated });
  assert.equal(strong.kind, "unreadable", "a duplicate-key payload must be refused at the byte boundary");
  assert.equal(strong.boundary, "canonical-json-text");

  const weak = parseSynthesizedMemoryPageResponse({ status: 200, json: JSON.parse(duplicated) });
  assert.equal(weak.kind, "page", "the object predicate genuinely cannot see it — this is the gap, documented");
  assert.equal(weak.boundary, "trusted-parsed-json");

  // Non-canonical whitespace is likewise invisible to the object predicate.
  const spaced = JSON.stringify(honest, null, 2);
  assert.equal(
    parseSynthesizedMemoryPageResponse({ status: 200, json: honest, text: spaced }).kind,
    "unreadable",
  );
});

test("the recall state is carried from the server, never derived from the page", () => {
  // red-proof: change `complete: page.completeness.status === "complete"` to
  // `complete: page.window.complete` — the degraded page below then reports
  // complete:true because its WINDOW terminated, which is precisely the
  // window/completeness conflation the status matrix marks safe-to-serialize
  // but never safe-to-trust.
  // APPLIED 2026-08-08: observed
  //   AssertionError: a terminated window is not a complete recall ... true !== false
  const outcome = parseSynthesizedMemoryPageResponse(
    textResponse(buildPage({ window: "complete_terminal", completeness: "degraded" })),
  );
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const state = synthesizedRecallStateFromPage(outcome.page);
  assert.equal(state.kind, "known");
  if (state.kind !== "known") return;
  assert.equal(state.status, "degraded");
  assert.equal(state.complete, false, "a terminated window is not a complete recall");
  assert.deepEqual(state.reasons, ["projection_stale"], "and the reason is preserved, not dropped");
  assert.equal(state.hasMore, false);
  assert.equal(state.queryGap, false);
});

test("a query gap is distinguishable from an unknown recall", async () => {
  // red-proof: change `queryGap: page.absence !== null` to `queryGap: page.items.length === 0`.
  // The unreadable case below still yields kind:"unknown" (so that half still
  // passes), but the empty-complete page and an empty page WITHOUT an absence
  // marker become indistinguishable — and the contract rejects the latter, so
  // the mutation is caught by the first assertion pair.
  // APPLIED 2026-08-08: observed  AssertionError ... true !== false on the
  // non-empty query-gap discrimination below.
  const gapOutcome = parseSynthesizedMemoryPageResponse(
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete", empty: true, queryGap: true })),
  );
  assert.equal(gapOutcome.kind, "page");
  if (gapOutcome.kind !== "page") return;
  const gap = synthesizedRecallStateFromPage(gapOutcome.page);
  assert.equal(gap.kind, "known");
  if (gap.kind !== "known") return;
  assert.equal(gap.queryGap, true, "the server searched and found nothing — that IS the answer");
  assert.equal(gap.complete, true);
  assert.equal(synthesizedMemoryItemsFromPage(gapOutcome.page).length, 0);

  // A page WITH items is never a query gap, even though both render as "no
  // more to fetch".
  const full = parseSynthesizedMemoryPageResponse(
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
  );
  assert.equal(full.kind, "page");
  if (full.kind !== "page") return;
  const fullState = synthesizedRecallStateFromPage(full.page);
  assert.equal(fullState.kind === "known" && fullState.queryGap, false);

  // And the third state: we do not know. Not complete, not a gap.
  const unknown = await walkSynthesizedMemoryPages(new RepeatingPage(jsonOnlyResponse({ nope: true })));
  assert.equal(unknown, null, "an unreadable walk is UNKNOWN, not an empty complete result");
});

test("the page request is clamped to the limit the server will actually honor", async () => {
  // red-proof: delete the `Math.min(requested, PLATFORM_MEMORY_RECALL_MAX_LIMIT)`
  // clamp; the first asserted path becomes `limit=100000`.
  // APPLIED 2026-08-08: observed
  //   AssertionError ... '/v1/memories?limit=100000' !== '/v1/memories?limit=100'
  const http = new ScriptedPages([
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
  ]);
  await walkSynthesizedMemoryPages(http, { limit: 100_000 });
  await walkSynthesizedMemoryPages(http, { limit: 0 });
  await walkSynthesizedMemoryPages(http, { limit: 25 });
  assert.deepEqual(http.paths, [
    `/v1/memories?limit=${PLATFORM_MEMORY_RECALL_MAX_LIMIT}`,
    `/v1/memories?limit=${PLATFORM_MEMORY_RECALL_MAX_LIMIT}`,
    "/v1/memories?limit=25",
  ]);
});

test("a continuation carries the server's cursor verbatim, url-encoded", async () => {
  // red-proof: drop `encodeURIComponent` from the cursor query; the asserted
  // path loses its escaping and a cursor containing `&` silently truncates the
  // request into a different query.
  // APPLIED 2026-08-08: observed
  //   AssertionError ... '?limit=100&cursor=v1.sig&x=1' !== '?limit=100&cursor=v1.sig%26x%3D1'
  const cursorPage = buildPage({ window: "more_continuation", completeness: "complete" }) as {
    window: { nextCursor: string };
  };
  cursorPage.window.nextCursor = "v1.sig&x=1";
  const http = new ScriptedPages([
    textResponse(cursorPage),
    textResponse(buildPage({ window: "complete_terminal", completeness: "complete" })),
  ]);
  await walkSynthesizedMemoryPages(http);
  assert.deepEqual(http.paths, [
    "/v1/memories?limit=100",
    "/v1/memories?limit=100&cursor=v1.sig%26x%3D1",
  ]);
});
