// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-002)
import { describe, expect, test } from "bun:test";

import {
  DEFAULT_READ_ITEM_GRANULARITY,
  READ_ITEM_GRANULARITIES,
  isReadItemGranularity,
  selectNodesForGranularity,
  selectTreeNodesForGranularity,
} from "./granularity";
import type { StructuralNode, StructuralTree } from "./tree";

const node = (overrides: Partial<StructuralNode> = {}): StructuralNode => ({
  node_id: "n",
  view_kind: "temporal",
  anchor_key: "year:2026",
  parent_node_id: null,
  child_node_ids: [],
  order_key: "year:2026",
  policy_partition_label: "p",
  member_claim_revision_ids: ["c"],
  structural_revision: "r",
  dependency_manifest: { live_member_revisions: ["c"], child_render_hashes: [] },
  graph_generation: "g",
  ...overrides,
});

describe("granularity unit selection", () => {
  test("DEFAULT_READ_ITEM_GRANULARITY is temporal_leaf", () => {
    // red-proof: change DEFAULT_READ_ITEM_GRANULARITY to "all_nodes" in granularity.ts
    expect(DEFAULT_READ_ITEM_GRANULARITY).toBe("temporal_leaf");
  });

  test("READ_ITEM_GRANULARITIES enumerates exactly the two named values", () => {
    // red-proof: drop "all_nodes" from READ_ITEM_GRANULARITIES (or add a third value)
    expect(READ_ITEM_GRANULARITIES).toEqual(["temporal_leaf", "all_nodes"]);
  });

  test("isReadItemGranularity accepts only the two named string values", () => {
    // red-proof: make isReadItemGranularity always return true (or accept "daily")
    for (const value of READ_ITEM_GRANULARITIES) expect(isReadItemGranularity(value)).toBe(true);
    for (const value of ["", "leaf", "ALL_NODES", "daily", null, undefined, 1, {}]) {
      expect(isReadItemGranularity(value)).toBe(false);
    }
  });

  test("selectTreeNodesForGranularity delegates to selectNodesForGranularity on tree.nodes", () => {
    // red-proof: change selectTreeNodesForGranularity to return tree.nodes unfiltered
    // (ignore granularity) or to select from an empty array instead of tree.nodes
    const nodes = [
      node({ node_id: "year", anchor_key: "year:2026", child_node_ids: ["day"] }),
      node({ node_id: "day", anchor_key: "year:2026/month:08/day:07", child_node_ids: [] }),
      node({ node_id: "entity", view_kind: "entity", anchor_key: "entity:x", child_node_ids: [] }),
    ];
    const tree: StructuralTree = { input_generation: "g1", nodes };

    for (const granularity of READ_ITEM_GRANULARITIES) {
      expect(selectTreeNodesForGranularity(tree, granularity)).toEqual(
        selectNodesForGranularity(nodes, granularity),
      );
    }
  });

  test("selectNodesForGranularity returns a frozen array for both granularities", () => {
    // red-proof: remove Object.freeze from both return paths in selectNodesForGranularity
    const nodes = [
      node({ node_id: "year", child_node_ids: ["day"] }),
      node({ node_id: "day", child_node_ids: [] }),
    ];

    for (const granularity of READ_ITEM_GRANULARITIES) {
      const result = selectNodesForGranularity(nodes, granularity);
      expect(Object.isFrozen(result)).toBe(true);
      expect(() => {
        (result as StructuralNode[]).push(node({ node_id: "mutated" }));
      }).toThrow();
    }
  });

  test("selectNodesForGranularity never mutates its input array", () => {
    // red-proof: mutate `nodes` in place before returning (e.g. nodes.filter in place via
    // splice, or push into the input) inside selectNodesForGranularity
    const nodes = [
      node({ node_id: "year", child_node_ids: ["day"] }),
      node({ node_id: "day", child_node_ids: [] }),
      node({ node_id: "source", view_kind: "source", anchor_key: "capture:x", child_node_ids: [] }),
    ];
    const beforeIds = nodes.map((item) => item.node_id);
    const beforeLength = nodes.length;

    selectNodesForGranularity(nodes, "temporal_leaf");
    selectNodesForGranularity(nodes, "all_nodes");

    expect(nodes).toHaveLength(beforeLength);
    expect(nodes.map((item) => item.node_id)).toEqual(beforeIds);
  });

  test("an empty node list returns an empty frozen array for both granularities", () => {
    // red-proof: return null/undefined, or throw, when nodes.length === 0
    for (const granularity of READ_ITEM_GRANULARITIES) {
      const result = selectNodesForGranularity([], granularity);
      expect(result).toEqual([]);
      expect(result).toHaveLength(0);
      expect(Object.isFrozen(result)).toBe(true);
    }
  });

  test("mixed view_kinds: all_nodes keeps every node; temporal_leaf keeps only temporal leaves", () => {
    // red-proof: change isTemporalLeaf to only check child_node_ids.length === 0
    // (drop view_kind === "temporal"), so entity/source empty-children nodes leak into
    // temporal_leaf; or filter view_kind on the all_nodes path so entity/source disappear
    const temporalRollup = node({
      node_id: "rollup",
      view_kind: "temporal",
      anchor_key: "year:2026",
      child_node_ids: ["leaf"],
    });
    const temporalLeaf = node({
      node_id: "leaf",
      view_kind: "temporal",
      anchor_key: "year:2026/month:08/day:07",
      child_node_ids: [],
    });
    const entity = node({
      node_id: "entity",
      view_kind: "entity",
      anchor_key: "entity:x",
      child_node_ids: [],
    });
    const source = node({
      node_id: "source",
      view_kind: "source",
      anchor_key: "capture:x",
      child_node_ids: [],
    });
    const nodes = [temporalRollup, temporalLeaf, entity, source];

    expect(selectNodesForGranularity(nodes, "all_nodes").map((item) => item.node_id))
      .toEqual(["rollup", "leaf", "entity", "source"]);
    expect(selectNodesForGranularity(nodes, "temporal_leaf").map((item) => item.node_id))
      .toEqual(["leaf"]);
  });
});
