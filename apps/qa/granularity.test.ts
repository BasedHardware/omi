// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-002)
import { afterAll, describe, expect, test } from "bun:test";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import {
  DEFAULT_READ_ITEM_GRANULARITY,
  READ_ITEM_GRANULARITIES,
  isReadItemGranularity,
  selectNodesForGranularity,
} from "../../core/retrieve/granularity";
import type { StructuralNode } from "../../core/retrieve/tree";
import { mcpCall, pageTextOf, rpcErrorOf } from "./mcp-client";
import { startQaServer, type QaServer } from "./server";

/**
 * Item granularity as an EXPLICIT parameter of the read.
 *
 * Provisional coordinator ruling `decisions/COORD-item-granularity.md`:
 * granularity is a named parameter, not an implicit default of the transport.
 * The assertion that carries the whole ruling is
 * **"identical granularity ⇒ identical items, whichever door you came through"**
 * — everything else here supports it.
 */

const servers: QaServer[] = [];

const server = async (options: Parameters<typeof startQaServer>[0] = {}): Promise<QaServer> => {
  const started = await startQaServer({ port: 0, ...options });
  servers.push(started);
  return started;
};

afterAll(async () => {
  await Promise.all(servers.map((instance) => instance.stop()));
});

const readPage = async (
  instance: QaServer,
  granularity?: "temporal_leaf" | "all_nodes",
) => {
  const result = await mcpCall({
    url: instance.url, token: instance.token, limit: 100, granularity,
  });
  const text = pageTextOf(result);
  expect(text).not.toBeNull();
  const parsed = parseSynthesizedPageJson(text!);
  expect(parsed).not.toBeNull();
  return { page: parsed!, text: text! };
};

const node = (overrides: Partial<StructuralNode>): StructuralNode => ({
  node_id: "n", view_kind: "temporal", anchor_key: "year:2026", parent_node_id: null,
  child_node_ids: [], order_key: "year:2026", policy_partition_label: "p",
  member_claim_revision_ids: ["c"], structural_revision: "r",
  dependency_manifest: { live_member_revisions: ["c"], child_render_hashes: [] },
  graph_generation: "g", ...overrides,
});

describe("item granularity is an explicit parameter", () => {
  test("THE INVARIANT — identical granularity yields identical items, whichever door", async () => {
    // This is the assertion the ruling exists to protect. Two independently
    // constructed servers over identical content, asked for the SAME
    // granularity, must return byte-identical pages. If a transport ever starts
    // deciding granularity for itself, this is what fails.
    //
    // red-proof: hard-code `granularity` to "all_nodes" inside
    // apps/qa/mcp-ports.ts readPage (i.e. let the transport decide instead of
    // forwarding what the caller asked) and the explicit-leaf comparison below
    // diverges from the default one.
    const doorA = await server({ claim_count: 5 });
    const doorB = await server({ claim_count: 5 });

    for (const granularity of READ_ITEM_GRANULARITIES) {
      const fromA = await readPage(doorA, granularity);
      const fromB = await readPage(doorB, granularity);
      expect(fromA.text).toBe(fromB.text);
    }

    // And a caller that does not ask gets the shared default, NOT a
    // transport-chosen value: omitting the parameter must equal naming the
    // default explicitly.
    const omitted = await readPage(doorA);
    const named = await readPage(doorA, DEFAULT_READ_ITEM_GRANULARITY);
    expect(omitted.text).toBe(named.text);
  });

  test("the two granularities genuinely differ, so the invariant is not vacuous", async () => {
    // Without this, the test above would pass even if granularity were ignored
    // entirely. It pins that the parameter actually does something.
    const instance = await server({ claim_count: 5 });
    const leaves = await readPage(instance, "temporal_leaf");
    const all = await readPage(instance, "all_nodes");

    expect(leaves.page.items).toHaveLength(5);
    expect(all.page.items).toHaveLength(12);
    expect(leaves.text).not.toBe(all.text);

    // Every leaf item is a single-claim proposition; the hierarchy adds rollups.
    for (const item of leaves.page.items) {
      expect(item.text).toContain("over 1 claim(s)");
    }
    expect(all.page.items.some((item) => item.text.includes("over 5 claim(s)"))).toBe(true);
  });

  test("the app-facing default is temporal leaves — rollups must be asked for", async () => {
    // red-proof: change DEFAULT_READ_ITEM_GRANULARITY to "all_nodes" and a
    // person scrolling their memories starts seeing "2026" and "August 2026"
    // as entries.
    expect(DEFAULT_READ_ITEM_GRANULARITY).toBe("temporal_leaf");
    const instance = await server({ claim_count: 5 });
    const defaulted = await readPage(instance);
    expect(defaulted.page.items).toHaveLength(5);
    for (const item of defaulted.page.items) {
      expect(item.text).toContain("over 1 claim(s)");
    }
  });

  test("a cursor is bound to its granularity and cannot be continued at another", async () => {
    // Otherwise page two of a leaves-only read could be continued as an
    // all-nodes read, returning items page one could never have contained.
    // red-proof: drop `granularity` from declared_generation_digest in
    // recall-service.ts and this cross-granularity continuation succeeds.
    const instance = await server({ claim_count: 6 });
    const firstLeaf = await mcpCall({
      url: instance.url, token: instance.token, limit: 2, granularity: "temporal_leaf",
    });
    const parsed = parseSynthesizedPageJson(pageTextOf(firstLeaf)!)!;
    expect(parsed.window.nextCursor).not.toBeNull();

    const crossed = await mcpCall({
      url: instance.url, token: instance.token, limit: 2,
      granularity: "all_nodes", cursor: parsed.window.nextCursor!,
    });
    expect(rpcErrorOf(crossed)).toEqual({ code: -32602, message: "Invalid cursor" });
  });

  test("an unknown granularity is rejected, never silently defaulted", async () => {
    // A silent fallback would mean a client typo produces a different result set
    // with no signal -- the quiet version of the divergence this ruling forbids.
    const instance = await server({ claim_count: 3 });
    const bogus = await mcpCall({
      url: instance.url, token: instance.token, limit: 2,
      headerOverrides: {},
      granularity: "daily" as never,
    });
    expect(rpcErrorOf(bogus)).toEqual({ code: -32602, message: "Invalid params" });
    expect(pageTextOf(bogus)).toBeNull();
  });

  test("the tool advertises granularity so a caller can discover it", async () => {
    const instance = await server({ claim_count: 2 });
    const listed = await mcpCall({ url: instance.url, token: instance.token, method: "tools/list" });
    const body = JSON.stringify(listed.body);
    expect(body).toContain("granularity");
    expect(body).toContain("temporal_leaf");
    expect(body).toContain("all_nodes");
  });

  test("selectNodesForGranularity uses child linkage, not anchor-key depth", () => {
    // A depth heuristic counting "/" in year/month/day would misclassify if the
    // hierarchy ever gained or lost a level. Structural fact beats string shape.
    const year = node({ node_id: "y", anchor_key: "year:2026", child_node_ids: ["m"] });
    const month = node({ node_id: "m", anchor_key: "year:2026/month:08", child_node_ids: ["d"] });
    const day = node({ node_id: "d", anchor_key: "year:2026/month:08/day:07", child_node_ids: [] });
    const source = node({ node_id: "s", view_kind: "source", anchor_key: "capture:x", child_node_ids: [] });
    const nodes = [year, month, day, source];

    expect(selectNodesForGranularity(nodes, "temporal_leaf").map((item) => item.node_id))
      .toEqual(["d"]);
    expect(selectNodesForGranularity(nodes, "all_nodes").map((item) => item.node_id))
      .toEqual(["y", "m", "d", "s"]);

    // Selection never reorders: ordering authority lives in the recall kernel.
    const reversed = [...nodes].reverse();
    expect(selectNodesForGranularity(reversed, "all_nodes").map((item) => item.node_id))
      .toEqual(["s", "d", "m", "y"]);
  });

  test("isReadItemGranularity accepts exactly the two named values", () => {
    expect(READ_ITEM_GRANULARITIES).toEqual(["temporal_leaf", "all_nodes"]);
    for (const value of READ_ITEM_GRANULARITIES) expect(isReadItemGranularity(value)).toBe(true);
    for (const value of ["", "leaf", "ALL_NODES", null, undefined, 1, {}]) {
      expect(isReadItemGranularity(value)).toBe(false);
    }
  });
});
