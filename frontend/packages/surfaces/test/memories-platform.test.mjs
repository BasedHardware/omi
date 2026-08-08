import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  citationSummary,
  completenessNotice,
  dataSourceBadge,
  emptyPresentation,
  filterLoadedPropositions,
  lineageRows,
  paginationAffordance,
} from "../src/production/proposition-presentation.ts";
import {
  PROPOSITION_FIXTURE_STATES,
  fixturePropositionStore,
} from "../src/production/proposition-fixtures.ts";
import { EN_MESSAGES } from "@omi-core/i18n";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

const UNKNOWN = { kind: "unknown" };
const known = (status, reasons = [], extras = {}) => ({
  kind: "known",
  status,
  reasons,
  complete: status === "complete",
  queryGap: extras.queryGap ?? false,
  hasMore: extras.hasMore ?? false,
});
const item = (id, text, extras = {}) => ({ id, text, ...extras });

// ---------------------------------------------------------------------------
// Completeness honesty. `complete` is the exceptional claim (core hard rule 12).
// ---------------------------------------------------------------------------

test("an unknown recall state makes no completeness claim at all", () => {
  const notice = completenessNotice(UNKNOWN);
  assert.equal(notice.kind, "unstated");
  assert.equal(notice.titleKey, null);
  assert.deepEqual(notice.reasonKeys, []);
  // red-proof: mapping kind:"unknown" onto the complete notice, or defaulting titleKey to
  // "memoriesPlatform.completeness.complete", makes this fail. Cursor and status metadata
  // are optional on this wire, so their absence must render as silence, never as a
  // completeness assertion the server never made.
});

test("a recall state carrying limitation reasons never renders as complete, even when it says it is", () => {
  const notice = completenessNotice(known("complete", ["projection_stale"]));
  assert.equal(notice.kind, "degraded");
  assert.equal(notice.titleKey, "memoriesPlatform.completeness.degraded");
  assert.deepEqual(notice.reasonKeys, ["memoriesPlatform.reason.projectionStale"]);
  assert.equal(notice.tone, "warning");
  // red-proof: using `recall.status` verbatim instead of deriving from the reasons returns
  // "complete" and fails. A projection that told us it is stale must not be presented as
  // an authoritative full answer.
});

test("reason precedence matches the ratified derivation: degraded outranks incomplete outranks partial", () => {
  const kindFor = (reasons) => completenessNotice(known("partial", reasons)).kind;
  assert.equal(kindFor(["time_bound", "accepted_work_pending", "projection_bypassed"]), "degraded");
  assert.equal(kindFor(["time_bound", "accepted_work_pending"]), "incomplete");
  assert.equal(kindFor(["time_bound"]), "partial");
  // red-proof: testing accepted_work_pending before the degraded set makes the first case
  // return "incomplete" and fail, which would present an unavailable projection as merely
  // lagging.
});

test("a limitation reason this build has never heard of still prevents a complete claim", () => {
  const notice = completenessNotice(known("complete", ["quota_bound_2027"]));
  assert.notEqual(notice.kind, "complete");
  assert.equal(notice.kind, "partial");
  assert.deepEqual(notice.reasonKeys, []);
  assert.equal(notice.unrecognizedReasonCount, 1);
  // red-proof: filtering the reasons down to the recognised ones BEFORE deriving the
  // status makes this return "complete" and fail. A client that has not been taught a new
  // limitation must get quieter, not more confident — and it must never fabricate copy for
  // a reason string it cannot describe.
});

test("recognised and unrecognised reasons coexist without either being lost", () => {
  const notice = completenessNotice(known("degraded", ["projection_stale", "quota_bound_2027"]));
  assert.deepEqual(notice.reasonKeys, ["memoriesPlatform.reason.projectionStale"]);
  assert.equal(notice.unrecognizedReasonCount, 1);
  // red-proof: dropping the unrecognised count silently hides from the user that the
  // server reported more limitations than the screen can name.
});

// ---------------------------------------------------------------------------
// Absence. Three different answers that must never collapse into one another.
// ---------------------------------------------------------------------------

test("query gap, unknown recall and an empty projection are three distinct empty states", () => {
  const gap = emptyPresentation(0, known("complete", [], { queryGap: true }));
  const unknown = emptyPresentation(0, UNKNOWN);
  const bare = emptyPresentation(0, known("complete", []));
  assert.equal(gap, "query-gap");
  assert.equal(unknown, "recall-unknown");
  assert.equal(bare, "empty-projection");
  assert.equal(new Set([gap, unknown, bare]).size, 3);
  // red-proof: returning one shared "empty" for every zero-item case collapses them and
  // fails. "We searched and there is nothing", "we do not know yet" and "there is nothing
  // here yet" are three different things to tell a person, and FE-CORE's published note
  // calls showing the same state for the first two the bug.
});

test("any loaded item at all means rows, regardless of a stale gap flag", () => {
  assert.equal(emptyPresentation(1, known("complete", [], { queryGap: true })), "rows");
  // red-proof: checking queryGap before the item count hides real rows behind an empty
  // state.
});

// ---------------------------------------------------------------------------
// Pagination. An end-of-list claim needs server evidence.
// ---------------------------------------------------------------------------

test("an unknown recall state offers no continuation and makes no end-of-list claim", () => {
  assert.deepEqual(paginationAffordance(UNKNOWN), { canLoadMore: false, terminal: false });
  // red-proof: defaulting `terminal` to true when recall is unknown makes this fail.
  // "You have reached the end" is a completeness claim; with no envelope we were told
  // nothing and must say nothing.
});

test("only a declared non-continuing window licenses the end-of-list line", () => {
  assert.deepEqual(paginationAffordance(known("complete", [])), { canLoadMore: false, terminal: true });
  assert.deepEqual(paginationAffordance(known("complete", [], { hasMore: true })), { canLoadMore: true, terminal: false });
  // red-proof: reporting both canLoadMore and terminal true for a continuing window puts
  // "load more" and "you have reached the end" on screen at the same time.
});

// ---------------------------------------------------------------------------
// Optional per-item metadata is absent-safe and never fabricated.
// ---------------------------------------------------------------------------

test("a proposition with no provenance produces no lineage rows and no placeholder digests", () => {
  assert.deepEqual(lineageRows(item("p1", "one")), []);
  // red-proof: emitting rows with empty-string or "unknown" values makes this fail, and
  // would put a digest-shaped blank in front of a reader as if it were verifiable.
});

test("lineage renders the server's digests whole and unmodified", () => {
  const digestIn = "3f1c8a2b7d4e6019bb52c7a8f0d31e94c6b7a2058e1f4d3c9a06b25e7f81c4d2";
  const digestOut = "a71e05c9d3b48f26107ec5a9b2d84f31068ca7e5b93d21f4780ac6e5d1b39274";
  const rows = lineageRows(item("p1", "one", {
    provenance: { synthesisVersion: "synth-2026.08.1", inputDigest: digestIn, outputDigest: digestOut },
  }));
  assert.deepEqual(rows, [
    { labelKey: "memoriesPlatform.synthesisVersion", value: "synth-2026.08.1" },
    { labelKey: "memoriesPlatform.inputDigest", value: digestIn },
    { labelKey: "memoriesPlatform.outputDigest", value: digestOut },
  ]);
  // red-proof: truncating a digest to a short prefix makes this fail. A shortened digest
  // cannot be checked against anything, so it is decoration wearing the costume of
  // evidence.
});

test("absent citations and zero citations are different answers", () => {
  assert.deepEqual(citationSummary(item("p1", "one")), { stated: false, count: 0 });
  assert.deepEqual(citationSummary(item("p2", "two", { citations: [] })), { stated: true, count: 0 });
  assert.deepEqual(citationSummary(item("p3", "three", { citations: ["c:1", "c:2"] })), { stated: true, count: 2 });
  // red-proof: normalising with `citations ?? []` makes the first case report stated:true
  // and fails — that would let "the server sent no citation field" render as "this
  // proposition is cited by nothing".
});

// ---------------------------------------------------------------------------
// Fixture versus live must be unmistakable.
// ---------------------------------------------------------------------------

test("a fixture render and a live render carry different copy, tone and detail", () => {
  const fixture = dataSourceBadge({ kind: "fixture", fixture: "degraded" });
  const live = dataSourceBadge({ kind: "live", origin: "http://127.0.0.1:4811" });
  assert.equal(fixture.labelKey, "dataSource.fixture");
  assert.equal(fixture.detail, "degraded");
  assert.equal(fixture.tone, "fixture");
  assert.equal(live.labelKey, "dataSource.live");
  assert.equal(live.detail, "http://127.0.0.1:4811");
  assert.equal(live.tone, "live");
  assert.notEqual(fixture.labelKey, live.labelKey);
  assert.match(EN_MESSAGES["dataSource.fixture"], /not from your account/);
  // red-proof: making both branches return the same labelKey, or softening the fixture
  // copy so it no longer says the data is not the user's, removes the only on-screen
  // signal telling a reviewer whether they are looking at a review corpus or real data.
});

test("the data-source badge is never hidden at desktop width the way the QA label is", async () => {
  const styles = await read("src/production/styles.css");
  const platform = await read("src/production/memories-platform.css");
  assert.match(styles, /html\[data-platform="desktop"\] \.qa-label \{ display: none; \}/);
  assert.ok(
    !/\.data-source-badge[^{]*\{[^}]*display:\s*none/.test(platform),
    "the data-source badge must not be hidden at any width",
  );
  assert.match(platform, /html\[data-platform="desktop"\] \.data-source-badge/);
  // red-proof: styling the badge as `.qa-label` (which styles.css hides on desktop, as the
  // first assertion pins) would make every desktop review capture of a fixture look
  // exactly like a live one. That confusion is the specific failure this guards.
});

// ---------------------------------------------------------------------------
// Contract drift guard against the ratified source of record.
// ---------------------------------------------------------------------------

test("every ratified limitation reason has surface copy and is recognised by the notice", async () => {
  const ratified = await read("../../contracts/ratified/src/projections/synthesized.ts");
  const presentation = await read("src/production/proposition-presentation.ts");

  const reasons = [...new Set(
    [...ratified.matchAll(/"(accepted_work_pending|projection_stale|projection_unavailable|projection_bypassed|source_bound|time_bound|policy_bound)"/g)]
      .map((match) => match[1]),
  )];
  assert.equal(reasons.length, 7, "the ratified reason vocabulary changed size");

  for (const reason of reasons) {
    assert.ok(
      presentation.includes(`"${reason}"`),
      `proposition-presentation.ts does not classify the ratified reason ${reason}`,
    );
    const notice = completenessNotice(known("complete", [reason]));
    assert.equal(
      notice.unrecognizedReasonCount,
      0,
      `ratified reason ${reason} is not recognised by completenessNotice`,
    );
    assert.equal(notice.reasonKeys.length, 1, `ratified reason ${reason} produced no copy key`);
    assert.ok(
      Object.hasOwn(EN_MESSAGES, notice.reasonKeys[0]),
      `catalog has no copy for ${notice.reasonKeys[0]} (ratified reason ${reason})`,
    );
  }

  for (const status of ["complete", "incomplete", "degraded", "partial"]) {
    assert.ok(
      Object.hasOwn(EN_MESSAGES, `memoriesPlatform.completeness.${status}`),
      `no catalog copy for completeness status ${status}`,
    );
  }
  // red-proof: adding an eighth reason to the ratified contract without teaching this
  // surface makes this fail. The surface restates the ratified vocabulary rather than
  // importing it (the package is vendored under a content hash), so this test is the thing
  // that stops the restatement rotting silently.
});

// ---------------------------------------------------------------------------
// Fixtures cover the states the surface has to be honest about.
// ---------------------------------------------------------------------------

test("the recall-unknown fixture serves rows with no envelope", async () => {
  const store = fixturePropositionStore("recall-unknown");
  const items = await store.list();
  assert.ok(items.length > 0, "the unknown-recall fixture must still carry items");
  assert.equal(store.recall().kind, "unknown");
  assert.equal(completenessNotice(store.recall()).kind, "unstated");
  assert.equal(paginationAffordance(store.recall()).terminal, false);
  assert.equal(emptyPresentation(items.length, store.recall()), "rows");
  // red-proof: giving this fixture a known recall envelope deletes the only coverage of
  // the optional-metadata path, which is the path David's frontend contract says must
  // work.
});

test("continuation accumulates in server order and then stops offering itself", async () => {
  const store = fixturePropositionStore("paged");
  const before = await store.list();
  assert.equal(store.hasMore(), true);

  await store.loadMore();
  const after = await store.list();
  assert.deepEqual(
    after.map((row) => row.id),
    [...before.map((row) => row.id), "prop:0006", "prop:0007"],
  );
  assert.equal(store.hasMore(), false);
  assert.equal(paginationAffordance(store.recall()).terminal, true);

  await store.loadMore();
  assert.deepEqual((await store.list()).map((row) => row.id), after.map((row) => row.id));
  // red-proof: an unconditional append in loadMore duplicates prop:0006/prop:0007 on the
  // second call and fails; sorting the accumulated list breaks the order assertion. Server
  // order is the product, and a replayed continuation must be idempotent.
});

test("every declared fixture state constructs a store the presentation layer can render", async () => {
  const seen = new Set();
  for (const state of PROPOSITION_FIXTURE_STATES) {
    const store = fixturePropositionStore(state);
    const items = await store.list();
    const recall = store.recall();
    assert.ok(Array.isArray(items), `fixture ${state} produced no items array`);
    assert.ok(
      ["initial-loading", "ready", "unavailable"].includes(store.status().refresh.phase),
      `fixture ${state} produced an unexpected refresh phase`,
    );
    assert.equal(store.status().queue.pendingCount, 0, `fixture ${state} invented a write queue`);
    seen.add(`${completenessNotice(recall).kind}/${emptyPresentation(items.length, recall)}`);
  }
  // The corpus must actually exercise distinct presentations, not eleven copies of one.
  assert.ok(seen.size >= 6, `fixture corpus only reaches ${seen.size} distinct presentations`);
  // red-proof: adding a state to PROPOSITION_FIXTURE_STATES without a case in the factory
  // makes it fall through to the default corpus, which does not raise the distinct-
  // presentation count and fails this. A row-count assertion here would have passed.
});

// ---------------------------------------------------------------------------
// Supplementary source checks: the read model must not grow write affordances.
// ---------------------------------------------------------------------------

test("filtering matches proposition text over loaded rows only", () => {
  const rows = [item("p1", "Morning review"), item("p2", "Native shells"), item("p3", "morning light")];
  assert.deepEqual(filterLoadedPropositions(rows, "morning", "en").map((row) => row.id), ["p1", "p3"]);
  assert.equal(filterLoadedPropositions(rows, "   ", "en"), rows);
  assert.match(EN_MESSAGES["memoriesPlatform.filterSavedPlaceholder"], /^Filter/);
  // red-proof: a case-sensitive comparison drops p1; relabelling the control as a search
  // would claim a backend search this function does not perform.
});

test("the platform Memories surface exposes no write affordance and no legacy memory field", async () => {
  const source = await read("src/production/MemoriesPlatformProduction.tsx");
  for (const forbidden of ["store.create", "store.patch", "store.delete", "memories.visibility", "memory.visibility", "makePublic", "makePrivate", "deleteConfirm", "<textarea"]) {
    assert.ok(!source.includes(forbidden), `platform Memories must not reference ${forbidden}`);
  }
  assert.ok(source.includes('data-generation="platform"'), "the generation must be inspectable in the DOM");
  assert.ok(source.includes("data-data-source={badge.tone}"), "the data source must be inspectable in the DOM");
  // red-proof: reintroducing the legacy editable card here passes every other test in this
  // file while breaking board ruling PR-2 — the platform wire has no editable memory
  // fields and no internal record ids to edit them by.
});
