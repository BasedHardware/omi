// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-007)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
import { expect, test } from "bun:test";
import { projectTreeInputSnapshot } from "./index";
import { renderStructuralTree, restrictivePolicyJoin, validateRestrictiveJoin } from "./render";
import { incrementallyTransitionAnchors } from "./track-a";
import { buildDeterministicAnchors, type StructuralTree } from "./tree";
import { snapshot } from "./tree.fixture";

const options = (model_version = "fake-v1", strategy = "summary") => ({ strategy, model_version, prompt_version: "p1", policy_version: "policy1", schema_version: "schema1" });
/** Test-only deterministic fake; no network/model edge is reachable from this core test. */
class DeterministicFakeModel {
  calls = 0;
  constructor(private readonly response: (request: { input: unknown }) => { summary_text: string; citations: string[] }) {}
  async render(request: { input: unknown }): Promise<{ summary_text: string; citations: readonly string[] }> { this.calls++; return this.response(request); }
}
const inputAndTree = () => {
  const input = projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC" });
  return { input, tree: buildDeterministicAnchors(input) };
};

test("R2 rebuild/incremental-equivalent structure and render cache behavior are real", async () => {
  const { input, tree } = inputAndTree();
  const freshTree = buildDeterministicAnchors(input);
  const previousInput = { ...input, graph_generation: "before-private", claims: [input.claims.find((claim) => claim.claim_revision_id === "a")!] };
  const incremental = incrementallyTransitionAnchors(buildDeterministicAnchors(previousInput), { owner_account_id: input.owner_account_id, account_timezone: input.account_timezone, next_graph_generation: input.graph_generation, added_claims: [input.claims.find((claim) => claim.claim_revision_id === "private")!], removed_claim_revision_ids: [], changed_claims: [] });
  expect(JSON.stringify(incremental.nodes)).toBe(JSON.stringify(freshTree.nodes));
  const firstModel = new DeterministicFakeModel((request) => ({ summary_text: `summary:${(request.input as { node: { node_id: string } }).node.node_id}`, citations: ["e1"] }));
  const first = await renderStructuralTree(tree, input, firstModel, options());
  const cache = new Map(first.map((render) => [render.rendered_from_digest, render]));
  const cacheModel = new DeterministicFakeModel(() => ({ summary_text: "SHOULD-NOT-RENDER", citations: [] }));
  const reused = await renderStructuralTree(freshTree, input, cacheModel, options(), cache);
  expect(cacheModel.calls).toBe(0);
  expect(reused.map((render) => ({ node_id: render.node_id, summary_text: render.summary_text, rendered_from_digest: render.rendered_from_digest }))).toEqual(first.map((render) => ({ node_id: render.node_id, summary_text: render.summary_text, rendered_from_digest: render.rendered_from_digest })));
  const newerModel = new DeterministicFakeModel(() => ({ summary_text: "new-model", citations: [] }));
  const newer = await renderStructuralTree(freshTree, input, newerModel, options("fake-v2"), cache);
  expect(newerModel.calls).toBeGreaterThan(0);
  expect(newer.map((render) => render.render_generation)).not.toEqual(first.map((render) => render.render_generation));
  const strategyModel = new DeterministicFakeModel(() => ({ summary_text: "new-strategy", citations: [] }));
  await renderStructuralTree(freshTree, input, strategyModel, options("fake-v1", "extractive"), cache);
  expect(strategyModel.calls).toBeGreaterThan(0);
});

test("R2 mixed structural node cannot use first-member policy and policy join is order-independent", async () => {
  const { input, tree } = inputAndTree();
  const seed = tree.nodes.find((node) => node.view_kind === "source" && node.policy_partition_label.includes("sensitivity=generic"))!;
  const mixed = { ...seed, member_claim_revision_ids: ["a", "private"], dependency_manifest: { ...seed.dependency_manifest, live_member_revisions: ["a", "private"] } };
  const mixedTree: StructuralTree = { ...tree, nodes: [mixed] };
  const fake = new DeterministicFakeModel(() => ({ summary_text: "safe", citations: [] }));
  const rendered = await renderStructuralTree(mixedTree, input, fake, options());
  expect(rendered[0]!.effective_policy).toEqual({ subject_class: "generic", sensitivity: "private", capture_class: "generic" });
  expect(restrictivePolicyJoin([input.claims[0]!.policy_class, input.claims[1]!.policy_class])).toEqual(restrictivePolicyJoin([input.claims[1]!.policy_class, input.claims[0]!.policy_class]));
  // This is the naive first-claim answer from the adversarial mixed node: it must be rejected.
  expect(validateRestrictiveJoin({ subject_class: "owner", sensitivity: "private", capture_class: "voice" }, [{ subject_class: "owner", sensitivity: "private", capture_class: "voice" }, { subject_class: "bystander", sensitivity: "health", capture_class: "screen" }])).toBe(false);
});

test("R2 policy dimensions use a real peer-safe partial-order join", () => {
  const labels = {
    subject_class: ["generic", "owner", "bystander", "restricted"],
    sensitivity: ["generic", "private", "health", "restricted"],
    capture_class: ["generic", "voice", "screen", "restricted"],
  } as const;
  const policy = (dimension: keyof typeof labels, value: string) => ({ subject_class: "generic", sensitivity: "generic", capture_class: "generic", [dimension]: value });
  for (const [dimension, values] of Object.entries(labels) as [keyof typeof labels, readonly string[]][]) for (const left of values) for (const right of values) {
    const expected = left === right ? left : left === "generic" ? right : right === "generic" ? left : "restricted";
    expect(restrictivePolicyJoin([policy(dimension, left), policy(dimension, right)])[dimension]).toBe(expected);
  }
  const ownerPrivateVoice = { subject_class: "owner", sensitivity: "private", capture_class: "voice" };
  const bystanderHealthScreen = { subject_class: "bystander", sensitivity: "health", capture_class: "screen" };
  expect(restrictivePolicyJoin([ownerPrivateVoice, bystanderHealthScreen])).toEqual({ subject_class: "restricted", sensitivity: "restricted", capture_class: "restricted" });
  // Counterexample: a first-contributor render fails every incomparable peer check.
  expect(validateRestrictiveJoin(ownerPrivateVoice, [ownerPrivateVoice, bystanderHealthScreen])).toBe(false);
});

test("R2 persists complete child render hashes and rejects an unrenderable child dependency", async () => {
  const { input, tree } = inputAndTree();
  const success = new DeterministicFakeModel(() => ({ summary_text: "ok", citations: [] }));
  const successfulRenders = await renderStructuralTree(tree, input, success, options());
  const monthNode = tree.nodes.find((node) => node.anchor_key.includes("month:"))!;
  const childHashes = monthNode.child_node_ids.map((id) => successfulRenders.find((render) => render.node_id === id)?.render_hash).filter((hash): hash is string => hash !== null && hash !== undefined).sort();
  expect(monthNode.dependency_manifest.child_render_hashes).toEqual(childHashes);
  expect(monthNode.dependency_manifest.child_render_hashes).not.toEqual([]);

  const staleTree = buildDeterministicAnchors(input);
  const fake = new DeterministicFakeModel((request) => {
    const node = (request.input as { node: { anchor_key: string; dependency_manifest: unknown } }).node;
    if (node.anchor_key.includes("day:")) throw new Error("child failure");
    return { summary_text: "ok", citations: [] };
  });
  await expect(renderStructuralTree(staleTree, input, fake, options())).rejects.toThrow("incomplete child render provenance");
});

test("R2 concurrent roots render each node once and retain only returned child hashes", async () => {
  const { input, tree } = inputAndTree();
  const calls = new Map<string, number>();
  const renders = await renderStructuralTree(tree, input, {
    render: async (request) => {
      const nodeId = (request.input as { node: { node_id: string } }).node.node_id;
      calls.set(nodeId, (calls.get(nodeId) ?? 0) + 1);
      await Promise.resolve();
      return { summary_text: nodeId, citations: [] };
    },
  }, options());
  expect(calls.size).toBe(tree.nodes.length);
  expect([...calls.values()].every((count) => count === 1)).toBe(true);
  const returnedHashes = new Set(renders.flatMap((render) => render.render_hash === null ? [] : [render.render_hash]));
  expect(renders.every((render) => render.rendered_from_manifest.child_render_hashes.every((hash) => returnedHashes.has(hash)))).toBe(true);

  const broken = buildDeterministicAnchors(input);
  (broken.nodes[0] as { child_node_ids: string[] }).child_node_ids = ["missing"];
  await expect(renderStructuralTree(broken, input, { render: async () => ({ summary_text: "no", citations: [] }) }, options()))
    .rejects.toThrow("incomplete child provenance");
});

test("R2 rejects non-index array state before model or cache semantics can observe it", async () => {
  const { input, tree } = inputAndTree();
  const smuggledInput = structuredClone(input);
  const evidenceRefs = smuggledInput.claims[0]!.evidence_refs as string[];
  Object.defineProperty(evidenceRefs, "4294967295", { value: "smuggled", enumerable: true });
  let calls = 0;
  await expect(renderStructuralTree(tree, smuggledInput, {
    render: async () => { calls++; return { summary_text: "must-not-run", citations: [] }; },
  }, options())).rejects.toThrow("plain JSON rejects array properties");
  expect(calls).toBe(0);

  const leaf = buildDeterministicAnchors(input).nodes.find((node) => node.child_node_ids.length === 0)!;
  const citations = ["e1"];
  Object.defineProperty(citations, "4294967295", { value: "smuggled", enumerable: true });
  const failed = await renderStructuralTree({ input_generation: input.graph_generation, nodes: [leaf] }, input, {
    render: async () => ({ summary_text: "invalid", citations }),
  }, options());
  expect(failed[0]!.status).toBe("failed");
  expect(JSON.stringify(failed)).not.toContain("smuggled");
});
