import { expect, test } from "bun:test";
import { projectTreeInputSnapshot } from "./index";
import { retrieveDogfood } from "./dogfood";
import { renderStructuralTree } from "./render";
import { buildDeterministicAnchors } from "./tree";
import { snapshot } from "./tree.fixture";

const renderModel = { render: async ({ input }: { input: unknown }) => ({ summary_text: `met ${(input as { claims: { predicate: string }[] }).claims.map((claim) => claim.predicate).join(" ")}`, citations: ["e1"] }) };
const composeModel = { compose: async () => ({ answer_text: "grounded", citations: ["e1", "invented"] }) };
const options = { strategy: "summary", model_version: "fake", prompt_version: "p", policy_version: "p", schema_version: "s" };

test("R4 composes only hydrated evidence, reports query gaps, and never entity-leaks withheld content", async () => {
  const graph = snapshot();
  graph.claims = [...graph.claims, { ...graph.claims[0]!, revision_id: "withheld", placement_status: "withheld_unresolved_subject", claim: { ...graph.claims[0]!.claim, claim_revision_id: "withheld", claim_lineage_id: "withheld", lifecycle: "provisional", ambiguity_markers: ["unresolved"], context_packet: null } } as never];
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", valid_time_by_claim_revision: { a: "2026-01-02T10:00:00Z", private: "2026-01-02T10:00:00Z" } });
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, renderModel, options);
  const answer = await retrieveDogfood({ owner_account_id: "owner", query: "met", entity_id: "entity", grant_class: "all" }, graph, input, renders, composeModel);
  expect(answer.citations).toEqual(["e1"]);
  expect(answer.hydrated_claim_revision_ids).not.toContain("withheld");
  expect((await retrieveDogfood({ owner_account_id: "owner", query: "missing", entity_id: "entity", grant_class: "all" }, graph, input, renders, composeModel)).absence).toEqual({ kind: "query_gap", message: "no cited memory matched" });
});

test("R4 makes live supersession invisible and describes policy omission only by grant class", async () => {
  const graph = snapshot();
  const stale = { ...graph.claims[0]!, revision_id: "stale", claim: { ...graph.claims[0]!.claim, claim_revision_id: "stale", claim_lineage_id: "same", predicate: "stale" } };
  const live = { ...graph.claims[0]!, revision_id: "live", claim: { ...graph.claims[0]!.claim, claim_revision_id: "live", claim_lineage_id: "same", predicate: "met" } };
  graph.claims = [stale, live, graph.claims[1]!];
  graph.adjacency = [{ claim_revision_id: "live", entity_id: "entity", role_slot_id: "subject" }, { claim_revision_id: "private", entity_id: "entity", role_slot_id: "subject" }];
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", valid_time_by_claim_revision: { live: "2026-01-02T10:00:00Z", private: "2026-01-02T10:00:00Z" } });
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, renderModel, options);
  expect((await retrieveDogfood({ owner_account_id: "owner", query: "stale", entity_id: "entity", grant_class: "all" }, graph, input, renders, composeModel)).absence).toEqual({ kind: "query_gap", message: "no cited memory matched" });
  expect((await retrieveDogfood({ owner_account_id: "owner", query: "private", entity_id: "entity", grant_class: "generic" }, graph, input, renders, composeModel)).absence).toEqual({ kind: "policy_omission", grant_class: "generic", message: "some matching memory is omitted by your grant class" });
});
