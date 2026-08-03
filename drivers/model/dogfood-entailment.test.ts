import { expect, test } from "bun:test";
import { retrieveDogfood } from "../../core/retrieve/dogfood";
import { projectTreeInputSnapshot } from "../../core/retrieve";
import { renderStructuralTree } from "../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";
import { snapshot } from "../../core/retrieve/tree.fixture";
import { DeterministicFakeModel } from "./port";

const renderModel = { render: async ({ input }: { input: unknown }) => ({ summary_text: `met ${(input as { claims: { predicate: string }[] }).claims.map((claim) => claim.predicate).join(" ")}`, citations: ["e1"] }) };
const options = { strategy: "summary", model_version: "fake", prompt_version: "p", policy_version: "p", schema_version: "s" };
const ownerContext = { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } };
const prepared = async () => {
  const graph = snapshot();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC" });
  return { graph, input, renders: await renderStructuralTree(buildDeterministicAnchors(input), input, renderModel, options) };
};

test("S4 adversarial entailment rejects a permitted citation whose excerpt does not support its asserted fact", async () => {
  const { graph, input, renders } = await prepared();
  let entailmentCalls = 0;
  const model = new DeterministicFakeModel((request) => request.strategy === "citation-grounded-compose"
    ? { answer_text: "Alice moved to Paris.", citations: ["e1"], assertions: [{ text: "Alice moved to Paris.", citations: ["e1"] }] }
    : (entailmentCalls += 1, { entailed: false }));
  const response = await retrieveDogfood({ owner_account_id: "owner", query: "met", entity_id: "entity", request_context: ownerContext }, graph, input, renders, model);
  expect(entailmentCalls).toBe(1);
  expect(response).toMatchObject({ answer_text: null, citations: [], grounding: { status: "ungrounded" } });
  expect(response.grounding).toMatchObject({ failures: ["cited span does not entail assertion: Alice moved to Paris."] });
});

test("S4 entailment accepts an assertion supported by its permitted cited span", async () => {
  const { graph, input, renders } = await prepared();
  const model = new DeterministicFakeModel((request) => request.strategy === "citation-grounded-compose"
    ? { answer_text: "The cited evidence supports this.", citations: ["e1"], assertions: [{ text: "The cited evidence supports this.", citations: ["e1"] }] }
    : { entailed: true });
  const response = await retrieveDogfood({ owner_account_id: "owner", query: "met", entity_id: "entity", request_context: ownerContext }, graph, input, renders, model);
  expect(response).toMatchObject({ answer_text: "The cited evidence supports this.", citations: ["e1"], grounding: { status: "grounded" } });
});
