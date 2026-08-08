// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { readAfterApplicationAuthorization } from "../../../core/retrieve/authorization-boundary";
import { renderStructuralTree } from "../../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../../core/retrieve/tree";
import { createSqliteQaRecallLoader } from "../../../drivers/sqlite/application-recall-read";
import { produceQaRenders } from "../../qa/renders";
import { devPrincipalToAuthorizationRequest } from "../auth/dev-token";
import { createQaDeterministicSynthesizer } from "./qa-synthesizer";
import {
  DEFAULT_APP_FACING_MEMORY_READ_GRANULARITY,
  selectRendersForGranularity,
} from "./granularity";
import { seedQaSnapshot } from "../qa/seed";

/**
 * Granularity is a parameter of the READ, not of the transport.
 *
 * The app-facing REST binding and the MCP path independently chose different
 * item granularities - leaves-only here, rollups-and-leaves there. That is the
 * divergence this module exists to remove: the same query must not return
 * different results depending on which door answered it, because the difference
 * becomes visible the moment an agent and a person compare "the same" memories.
 *
 * These tests pin the part of that invariant which is checkable today: for a
 * given granularity, BOTH doors select the SAME STRUCTURAL NODES. Full
 * item-for-item identity additionally requires the two doors to share a
 * synthesizer and codec scoping, which they do not yet - reported to the
 * coordinator rather than changed unilaterally across another agent's files.
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
      snapshot: structuredClone(load.durable_snapshot),
      options: { account_timezone: TIMEZONE },
    }),
  );
};

/** The REST door's render production. */
const restRenders = async (projected: ReturnType<typeof projectSeeded>) => {
  const tree = buildDeterministicAnchors(projected);
  const renders = await renderStructuralTree(
    tree,
    projected,
    createQaDeterministicSynthesizer(),
    {
      strategy: "application-read-qa",
      model_version: "qa-deterministic-synthesizer-v1",
      prompt_version: "qa-prompt-v1",
      policy_version: "qa-policy-v1",
      schema_version: "qa-schema-v1",
    },
  );
  return { tree, renders };
};

const nodeIds = (renders: readonly { node_id: string }[]): readonly string[] =>
  [...renders.map((render) => render.node_id)].sort();

describe("memory read granularity is a parameter of the read, not of the transport", () => {
  test("both doors select the SAME nodes for synthesized_all_nodes", async () => {
    // red-proof: let either door filter by view kind or leafness before the
    // shared selector runs, and the two node sets stop matching. This is the
    // exact divergence the ruling exists to prevent - leaves-only on one door,
    // rollups-and-leaves on the other.
    const projected = projectSeeded();
    const { tree, renders } = await restRenders(projected);

    const viaRest = selectRendersForGranularity(renders, tree, "synthesized_all_nodes");
    // The MCP path's own production, selected at the same granularity.
    const mcpProduced = await produceQaRenders(projectSeeded());
    const viaMcp = selectRendersForGranularity(mcpProduced, tree, "synthesized_all_nodes");

    expect(nodeIds(viaRest)).toEqual(nodeIds(viaMcp));
    expect(viaRest.length).toBeGreaterThan(0);
  });

  test("both doors select the SAME nodes for the app-facing leaf granularity", async () => {
    // red-proof: change the leaf predicate in one place only (say, drop the
    // child_node_ids check) and the sets diverge.
    const projected = projectSeeded();
    const { tree, renders } = await restRenders(projected);

    const viaRest = selectRendersForGranularity(renders, tree, "synthesized_temporal_leaf");
    const mcpProduced = await produceQaRenders(projectSeeded());
    const viaMcp = selectRendersForGranularity(mcpProduced, tree, "synthesized_temporal_leaf");

    expect(nodeIds(viaRest)).toEqual(nodeIds(viaMcp));
    expect(viaRest.length).toBe(MEMORIES);
  });

  test("the two granularities genuinely differ, so equality above is not vacuous", async () => {
    // red-proof: make synthesized_all_nodes an alias of the leaf granularity and
    // this fails - which would mean every equality assertion here proved nothing.
    const projected = projectSeeded();
    const { tree, renders } = await restRenders(projected);

    const leaves = selectRendersForGranularity(renders, tree, "synthesized_temporal_leaf");
    const everything = selectRendersForGranularity(renders, tree, "synthesized_all_nodes");

    expect(everything.length).toBeGreaterThan(leaves.length);
    // Every leaf is also present in the unfiltered selection.
    for (const id of nodeIds(leaves)) expect(nodeIds(everything)).toContain(id);
  });

  test("the app-facing default is the leaf granularity", () => {
    // red-proof: flip the default to synthesized_all_nodes and a person scrolling
    // memories starts seeing "2026" and "August 2026" as entries.
    expect(DEFAULT_APP_FACING_MEMORY_READ_GRANULARITY).toBe("synthesized_temporal_leaf");
  });

  test("selection is deterministic and ordered by node id", async () => {
    // red-proof: drop the sort and ordering follows render completion order.
    const projected = projectSeeded();
    const { tree, renders } = await restRenders(projected);
    const once = selectRendersForGranularity(renders, tree, "synthesized_all_nodes");
    const twice = selectRendersForGranularity(renders, tree, "synthesized_all_nodes");
    expect(nodeIds(twice)).toEqual(nodeIds(once));
    expect([...once.map((r) => r.node_id)]).toEqual([...nodeIds(once)]);
  });
});
