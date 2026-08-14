/** One suite, every domain: the rule-12 laws executed against all fetchers. */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  fetchConversationIdSnapshot,
  fetchFolderIdSnapshot,
  fetchIdSnapshot,
  fetchMemoryIdSnapshot,
} from "@omi-core/adapters-legacy";
import { fetchSynthesizedMemoryIdSnapshot } from "@omi-core/adapters-platform";
import { checkSnapshotConformance, type SnapshotDescriptor } from "../snapshot-conformance.js";

/**
 * `completeEvidence` is the ONLY thing that licenses `complete: true`. Three of
 * five entries have it; the two legacy ones were re-verified against the legacy
 * source rather than assumed, and the platform one cites a contract the SERVER
 * is bound to rather than a handler we read. The other two are filtered and
 * must never claim completeness.
 *
 * Note what the two memories rows say side by side: the SAME domain is
 * complete-incapable on the legacy generation and complete-capable on the
 * platform generation. That is not an inconsistency, it is the entire value of
 * the rewrite, and rule 12 is what makes the difference legible instead of a
 * flag someone flipped.
 */
const DESCRIPTORS: SnapshotDescriptor[] = [
  {
    domain: "tasks",
    fetch: (http) => fetchIdSnapshot(http),
    okBody: (ids) => ({ ids }),
    // Verified: the handler returns action_items_db.get_action_item_ids(uid),
    // which is `coll.select([]).stream()` over the user's whole collection —
    // no .where(), no .limit()/.offset(), no Python post-filter.
    completeEvidence:
      "backend/database/action_items.py get_action_item_ids: coll.select([]).stream() over the entire collection, no where/limit/post-filter; exposed unpaginated at GET /v1/action-items/ids",
  },
  {
    domain: "memories",
    fetch: (http) => fetchMemoryIdSnapshot(http, 100),
    okBody: (ids) => ids.map((id) => ({ id })),
    pageSize: 100,
    // NO completeEvidence: the list endpoint hides user-rejected
    // (`user_review is not False`) and invalidated (`invalid_at`) rows, and
    // applies that filter in Python AFTER Firestore's .limit(), so not even a
    // short page proves the set was exhausted.
  },
  {
    // The FIRST domain in this repo that may legitimately claim completeness
    // from a list read — and it may only because the SERVER declares its
    // coverage rather than the client inferring it. Everything about this
    // descriptor is that distinction.
    domain: "memories-platform",
    fetch: (http) => fetchSynthesizedMemoryIdSnapshot(http),
    okBody: (ids) => ({
      contractVersion: "1.0.0",
      items: ids.map((id) => ({ id: `retrieval-node-v1:${id}`, text: `synthesized ${id}` })),
      window: { status: "complete", complete: true, hasMore: false, nextCursor: null },
      completeness: {
        version: "recall-completeness-v1",
        status: "complete",
        reasons: [],
        frontiers: {
          declaredFrontier: "frontier-v1:declared",
          newestSearchedAcceptedFrontier: "frontier-v1:declared",
          missingAcceptedFrontierReason: null,
          newestSearchedStmFrontier: "frontier-v1:included",
          missingStmFrontierReason: null,
        },
      },
      absence: null,
    }),
    // NO pageSize, deliberately, and this is the one judgment call in this
    // file. The full-page law encodes "a short page is not proof, so a full
    // page is definitely not proof" — a heuristic about page FULLNESS, which
    // is the only signal the legacy wire offers. The ratified contract does
    // not use that signal at all: completeness is a declared envelope
    // (`completeness.status` + frontiers + typed null reasons) that is
    // independent of how many items fit on a page. Declaring a pageSize here
    // would make the harness build a full page — which our okBody renders as
    // an honest terminal-complete page, because that is what the contract
    // says a terminal page looks like — and then fail it for claiming
    // completeness the server explicitly declared. That would be the harness
    // enforcing the legacy wire's limitation against a wire that fixed it.
    // The laws that DO apply (non-200 -> null, junk -> null, no-evidence ->
    // never complete, evidence -> not a dead license) all still run, and the
    // multi-page walk laws that replace the full-page law live in
    // platform-memories-adapter.test.ts with their own red-proofs.
    completeEvidence:
      "@omi-core/ratified-contracts 0.1.1 SynthesizedMemoryRead: the server DECLARES coverage in a versioned completeness envelope (recall-completeness-v1) carrying declaredFrontier vs newestSearchedAcceptedFrontier and typed null reasons; fetchSynthesizedMemoryIdSnapshot claims complete only when every page of a walk begun at the first page declared status:'complete' AND the walk terminated on the CompleteTerminalWindow variant within maxPages — see contracts/ratified/fixtures/recall-completeness.json and status-matrix.json, both executed in platform-memories-adapter.test.ts",
  },
  {
    domain: "conversations",
    fetch: (http) => fetchConversationIdSnapshot(http, 100),
    okBody: (ids) => ids.map((id) => ({ id })),
    pageSize: 100,
    // NO completeEvidence: defaults to statuses=processing,completed, so
    // in_progress/merging/failed are structurally invisible.
  },
  {
    domain: "folders",
    fetch: (http) => fetchFolderIdSnapshot(http),
    okBody: (ids) => ids.map((id) => ({ id })),
    // Verified: folders_db.get_folders is
    // `folders_ref.order_by('order').stream()` — no where/limit/post-filter —
    // and the router returns it whole. Caveat that does NOT affect
    // completeness: on an empty store the handler first calls
    // initialize_system_folders(uid), so an empty result may materialize
    // system folders as a side effect before ids are returned.
    completeEvidence:
      "backend/database/folders.py get_folders: folders_ref.order_by('order').stream() with no where/limit/post-filter, returned whole by GET /v1/folders (unpaginated)",
  },
];

test("every domain's id-snapshot fetcher obeys the rule-12 honesty laws", async () => {
  const failures = await checkSnapshotConformance(DESCRIPTORS);
  assert.deepEqual(failures, [], failures.map((f) => `${f.domain}: ${f.law} (got ${f.got})`).join("\n"));
});

/**
 * The harness must reject a descriptor that claims completeness without real
 * evidence — the mechanism failure that let the memories data-loss bug ship
 * past a green suite. Proven here rather than assumed, since this suite is now
 * the only thing standing between a wrong `complete: true` and user data loss.
 */
test("a complete-capable descriptor with no substantive evidence is rejected", async () => {
  const bare: SnapshotDescriptor = {
    domain: "fixture-bare-claim",
    fetch: (http) => fetchFolderIdSnapshot(http),
    okBody: (ids) => ids.map((id) => ({ id })),
    completeEvidence: "unfiltered",
  };
  const failures = await checkSnapshotConformance([bare]);
  assert.equal(failures.length, 1, "a hand-wave must not license completeness");
  assert.match(failures[0]!.law, /completeEvidence must be a real locator or justification/);
});

test("a fetcher that claims completeness without declaring evidence is rejected", async () => {
  const undeclared: SnapshotDescriptor = {
    domain: "fixture-undeclared-complete",
    // folders legitimately returns complete:true, but this descriptor declares
    // no evidence — exactly the memories bug's shape.
    fetch: (http) => fetchFolderIdSnapshot(http),
    okBody: (ids) => ids.map((id) => ({ id })),
  };
  const failures = await checkSnapshotConformance([undeclared]);
  assert.equal(failures.length, 1);
  assert.match(failures[0]!.law, /no completeEvidence declared, so complete must NEVER be true/);
});

test("declared evidence that the fetcher never honors is rejected as a dead license", async () => {
  const dead: SnapshotDescriptor = {
    domain: "fixture-dead-license",
    // memories never claims completeness, so declaring evidence is a lie in
    // the other direction — the descriptor and the code disagree.
    fetch: (http) => fetchMemoryIdSnapshot(http, 100),
    okBody: (ids) => ids.map((id) => ({ id })),
    completeEvidence:
      "a plausible-looking but incorrect justification string of more than the minimum length",
  };
  const failures = await checkSnapshotConformance([dead]);
  assert.equal(failures.length, 1);
  assert.match(failures[0]!.law, /completeEvidence is declared but the fetcher never achieves complete:true/);
});
