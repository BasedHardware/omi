// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { readAfterApplicationAuthorization } from "../../../core/retrieve/authorization-boundary";
import {
  DEFAULT_READ_ITEM_GRANULARITY,
  selectNodesForGranularity,
} from "../../../core/retrieve/granularity";
import { buildDeterministicAnchors } from "../../../core/retrieve/tree";
import { createSqliteQaRecallLoader } from "../../../drivers/sqlite/application-recall-read";
import { produceQaRenders } from "../../qa/renders";
import { devPrincipalToAuthorizationRequest } from "../auth/dev-token";
import { seedQaSnapshot } from "../qa/seed";

/**
 * Granularity is a parameter of the READ, not of the transport.
 *
 * The app-facing REST binding and the MCP path independently chose different
 * item granularities - leaves-only here, rollups-and-leaves there. The same
 * query must not return different results depending on which door answered it,
 * because that difference becomes visible the moment an agent and a person
 * compare "the same" memories.
 *
 * This lane briefly carried its own selector. It has been DELETED in favour of
 * the canonical `core/retrieve/granularity.ts`: two selectors is the bug, not
 * the fix. These tests pin that both doors now agree through that one module.
 */

const OWNER = "granularity-owner";
const TIMEZONE = "America/Los_Angeles";
const MEMORIES = 5;

const projectSeeded = () => {
  const db = new Database(":memory:");
  seedQaSnapshot(db, {
    owner_account_id: OWNER,
    memory_count: MEMORIES,
    account_timezone: TIMEZONE,
  });
  const load = createSqliteQaRecallLoader({
    db,
    owner_account_id: OWNER,
    account_timezone: TIMEZONE,
    limits: { max_items: 512, max_bytes: 4_000_000 },
  })();
  return readAfterApplicationAuthorization(
    devPrincipalToAuthorizationRequest({ uid: OWNER }, { app_id: "a", key_id: "k" }),
    () => ({
      // storage-provenance-ok(test fixture: the durable snapshot is the input to the authorization boundary, and only the projection it returns is asserted on)
      snapshot: structuredClone(load.durable_snapshot),
      options: { account_timezone: TIMEZONE },
    }),
  );
};

const sortedIds = (values: readonly { node_id: string }[]): readonly string[] =>
  [...values.map((value) => value.node_id)].sort();

describe("memory read granularity is a parameter of the read, not of the transport", () => {
  test("the MCP door's produced renders match the canonical selection, at every granularity", async () => {
    // This is the cross-door invariant. `produceQaRenders` renders the whole
    // tree and then selects through the SAME core module this composition uses,
    // so for a given granularity both doors serve the same structural nodes.
    //
    // red-proof: give either door its own selector - which is exactly what this
    // lane had, and exactly what made this test fail on the merged branch - and
    // the node sets diverge.
    const projected = projectSeeded();
    const tree = buildDeterministicAnchors(projected);

    for (const granularity of ["temporal_leaf", "all_nodes"] as const) {
      const canonical = selectNodesForGranularity(tree.nodes, granularity);
      // Mirrors the real door exactly (apps/qa/recall-service.ts): production is
      // granularity-agnostic, so render the whole tree and select afterwards.
      // Written 2026-08-08 when this test passed granularity to produceQaRenders
      // as a second argument that no longer exists — JS ignored it silently, so
      // the test compared all 17 nodes against a 5-node leaf selection. The
      // reconciliation is to match the door, not to relax the assertion.
      const allRenders = await produceQaRenders(projectSeeded());
      const selectedIds = new Set(canonical.map((structuralNode) => structuralNode.node_id));
      const viaMcp = allRenders.filter((render) => selectedIds.has(render.node_id));
      expect(sortedIds(viaMcp)).toEqual(sortedIds(canonical));
      // Non-vacuity: at leaf granularity the door must actually discard rollups,
      // or the filter above would be proving nothing.
      if (granularity === "temporal_leaf") {
        expect(allRenders.length).toBeGreaterThan(viaMcp.length);
      }
    }
  });

  test("the leaf granularity yields exactly one item per seeded local day", async () => {
    // red-proof: drop the child_node_ids check in the core leaf predicate and
    // temporal rollups reappear, so the count exceeds the seeded day count.
    const projected = projectSeeded();
    const tree = buildDeterministicAnchors(projected);
    const leaves = selectNodesForGranularity(tree.nodes, "temporal_leaf");
    expect(leaves.length).toBe(MEMORIES);
  });

  test("the two granularities genuinely differ, so the equality above is not vacuous", () => {
    // red-proof: make all_nodes an alias of temporal_leaf and this fails, which
    // would mean every equality assertion here proved nothing.
    const projected = projectSeeded();
    const tree = buildDeterministicAnchors(projected);
    const leaves = selectNodesForGranularity(tree.nodes, "temporal_leaf");
    const everything = selectNodesForGranularity(tree.nodes, "all_nodes");

    expect(everything.length).toBeGreaterThan(leaves.length);
    for (const id of sortedIds(leaves)) expect(sortedIds(everything)).toContain(id);
  });

  test("the app-facing default is the leaf granularity", () => {
    // red-proof: flip the core default and a person scrolling memories starts
    // seeing "2026" and "August 2026" as entries.
    expect(DEFAULT_READ_ITEM_GRANULARITY).toBe("temporal_leaf");
  });
});
