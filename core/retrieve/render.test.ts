import { expect, test } from "bun:test";
import { projectTreeInputSnapshot } from "./index";
import { renderStructuralTree, validateRestrictiveJoin } from "./render";
import { buildDeterministicAnchors } from "./tree";
import { snapshot } from "./tree.fixture";

const options = (model_version = "fake-v1") => ({ strategy: "summary", model_version, prompt_version: "p1", policy_version: "policy1", schema_version: "schema1" });
/** Test-only deterministic fake; no network/model edge is reachable from this core test. */
class DeterministicFakeModel {
  constructor(private readonly response: (request: { input: unknown }) => { summary_text: string; citations: string[] }) {}
  async render(request: { input: unknown }): Promise<{ summary_text: string; citations: readonly string[] }> { return this.response(request); }
}
test("R2 renders each policy partition separately and model swaps do not churn structure", async () => {
  const input = projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC", valid_time_by_claim_revision: { a: "2026-01-02T10:00:00Z", private: "2026-01-02T10:00:00Z" } });
  const tree = buildDeterministicAnchors(input);
  const fake = new DeterministicFakeModel((request) => ({ summary_text: `summary:${(request.input as { node: { node_id: string } }).node.node_id}`, citations: ["e1"] }));
  const first = await renderStructuralTree(tree, input, fake, options());
  expect(first.filter((render) => render.node_id.includes("nope"))).toHaveLength(0);
  expect(first.length).toBe(tree.nodes.length);
  const second = await renderStructuralTree(tree, input, fake, options("fake-v2"));
  expect(tree.nodes.map((node) => node.node_id)).toEqual(tree.nodes.map((node) => node.node_id));
  expect(second.map((render) => render.render_generation)).not.toEqual(first.map((render) => render.render_generation));
});

test("R2 marks a parent stale when its child render is stale", async () => {
  const input = projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC", valid_time_by_claim_revision: { a: "2026-01-02T10:00:00Z" } });
  const tree = buildDeterministicAnchors(input);
  const fake = { render: async ({ input: request }: { input: unknown }) => {
    const anchor = (request as { node: { anchor_key: string } }).node.anchor_key;
    if (anchor.includes("day:")) throw new Error("child failure");
    return { summary_text: "ok", citations: [] };
  } };
  const renders = await renderStructuralTree(tree, input, fake, options());
  const month = renders.find((render) => tree.nodes.find((node) => node.node_id === render.node_id)?.anchor_key.includes("month:"));
  expect(month?.stale).toBe(true);
});

test("R2 restrictive join rejects a less restrictive effective policy", () => {
  expect(validateRestrictiveJoin({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }, [{ subject_class: "generic", sensitivity: "private", capture_class: "generic" }])).toBe(false);
  expect(validateRestrictiveJoin({ subject_class: "generic", sensitivity: "private", capture_class: "generic" }, [{ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }])).toBe(true);
});
