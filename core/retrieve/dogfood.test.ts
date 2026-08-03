import { expect, test } from "bun:test";
import { projectTreeInputSnapshot } from "./index";
import { retrieveDogfood } from "./dogfood";
import { renderStructuralTree } from "./render";
import { buildDeterministicAnchors } from "./tree";
import { snapshot } from "./tree.fixture";

const renderModel = { render: async ({ input }: { input: unknown }) => ({ summary_text: `met ${(input as { claims: { predicate: string }[] }).claims.map((claim) => claim.predicate).join(" ")}`, citations: ["e1"] }) };
const composeModel = { compose: async () => ({ answer_text: "grounded", citations: ["e1", "invented"], assertions: [{ text: "grounded", citations: ["e1"] }] }), invoke: async () => ({ entailed: true }) };
const options = { strategy: "summary", model_version: "fake", prompt_version: "p", policy_version: "p", schema_version: "s" };
const ownerContext = { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } };
const genericReaderContext = { reader_account_id: "reader", grant: { grant_id: "generic", policy_classes: [{ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }] } };

test("R4 composes only hydrated evidence, reports query gaps, and never entity-leaks provisional content", async () => {
  const graph = snapshot();
  graph.claims = [...graph.claims, { ...graph.claims[0]!, revision_id: "provisional", placement_status: "provisional_unresolved_subject", claim: { ...graph.claims[0]!.claim, claim_revision_id: "provisional", claim_lineage_id: "provisional", lifecycle: "provisional", ambiguity_markers: ["unresolved"], context_packet: null } } as never];
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC" });
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, renderModel, options);
  const answer = await retrieveDogfood({ owner_account_id: "owner", query: "met", entity_id: "entity", request_context: ownerContext }, graph, input, renders, composeModel);
  expect(answer.citations).toEqual(["e1"]);
  expect(answer.hydrated_claim_revision_ids).not.toContain("provisional");
  expect((await retrieveDogfood({ owner_account_id: "owner", query: "missing", entity_id: "entity", request_context: ownerContext }, graph, input, renders, composeModel)).absence).toEqual({ kind: "query_gap", message: "no cited memory matched" });
});

test("R4 makes live supersession invisible and describes policy omission only by grant class", async () => {
  const graph = snapshot();
  const stale = { ...graph.claims[0]!, revision_id: "stale", claim: { ...graph.claims[0]!.claim, claim_revision_id: "stale", claim_lineage_id: "same", predicate: "stale" } };
  const live = { ...graph.claims[0]!, revision_id: "live", claim: { ...graph.claims[0]!.claim, claim_revision_id: "live", claim_lineage_id: "same", predicate: "met" } };
  graph.claims = [stale, live, graph.claims[1]!];
  graph.adjacency = [{ claim_revision_id: "live", entity_id: "entity", role_slot_id: "subject" }, { claim_revision_id: "private", entity_id: "entity", role_slot_id: "subject" }];
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC" });
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, renderModel, options);
  expect((await retrieveDogfood({ owner_account_id: "owner", query: "stale", entity_id: "entity", request_context: ownerContext }, graph, input, renders, composeModel)).absence).toEqual({ kind: "query_gap", message: "no cited memory matched" });
  expect((await retrieveDogfood({ owner_account_id: "owner", query: "private", entity_id: "entity", request_context: genericReaderContext }, graph, input, renders, composeModel)).absence).toEqual({ kind: "policy_omission", grant_class: "generic", message: "some matching memory is omitted by your grant class" });
});

test("S4 grounding manifest covers every answer assertion before span entailment", async () => {
  const graph = snapshot();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC" });
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, renderModel, options);
  const request = { owner_account_id: "owner", query: "met", entity_id: "entity", request_context: ownerContext };
  const smuggled = { compose: async () => ({ answer_text: "Evidence exists. Alice moved to Paris.", citations: ["e1"], assertions: [{ text: "Evidence exists.", citations: ["e1"] }] }), invoke: async () => ({ entailed: true }) };
  const smuggledResult = await retrieveDogfood(request, graph, input, renders, smuggled);
  expect(smuggledResult.grounding).toMatchObject({ status: "ungrounded" });
  expect(smuggledResult.grounding?.status === "ungrounded" && smuggledResult.grounding.failures).toContain("answer assertion is absent from grounding manifest: Alice moved to Paris.");

  const covered = { compose: async () => ({ answer_text: "Evidence exists. Alice moved to Paris.", citations: ["e1"], assertions: [{ text: "Evidence exists.", citations: ["e1"] }, { text: "Alice moved to Paris.", citations: ["e1"] }] }), invoke: async () => ({ entailed: true }) };
  expect((await retrieveDogfood(request, graph, input, renders, covered)).grounding).toEqual({ status: "grounded" });

  const unsupportedDeclared = { compose: async () => ({ answer_text: "Evidence exists. Alice moved to Paris.", citations: ["e1"], assertions: [{ text: "Evidence exists.", citations: ["e1"] }, { text: "Alice moved to Paris.", citations: ["e1"] }] }), invoke: async ({ input: invocation }: { input: unknown }) => ({ entailed: (invocation as { assertion: string }).assertion !== "Alice moved to Paris." }) };
  expect((await retrieveDogfood(request, graph, input, renders, unsupportedDeclared)).grounding).toMatchObject({ status: "ungrounded" });
});
