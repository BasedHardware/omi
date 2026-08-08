import { expect, test } from "bun:test";
import { sha256CanonicalRedacted } from "../ledger";
import type { TreeInputSnapshot } from "./index";
import {
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "./authorization-boundary";
import { buildOwnerBoundSynthesizedProjection, SynthesizedProjectionDenied } from "./projection-boundary";
import { renderStructuralTree, type RenderNode } from "./render";
import { buildDeterministicAnchors } from "./tree";
import { snapshot } from "./tree.fixture";

const authorizationRequest = (appId = "app:a"): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: { owner_account_id: "owner", credential_kind: "mcp_api_key", app_id: appId, key_id: `key:${appId}`, scopes: ["memories.read"], active: true },
  persisted_grant: { owner_account_id: "owner", consumer: "mcp", app_id: appId, key_id: `key:${appId}`, enabled: true, default_read: true, scopes: ["memories.read"] },
});

const projectedInput = (appId = "app:a"): ApplicationGrantProjectedTreeInputSnapshot =>
  readAfterApplicationAuthorization(authorizationRequest(appId), () => ({
    snapshot: snapshot(), options: { account_timezone: "UTC" },
  }));

const renderedFixture = async (appId = "app:a"): Promise<{ input: ApplicationGrantProjectedTreeInputSnapshot; render: RenderNode }> => {
  const input = projectedInput(appId);
  const tree = buildDeterministicAnchors(input);
  const renders = await renderStructuralTree(tree, input, {
    render: async () => ({ summary_text: "A synthesized summary.", citations: ["e1"] }),
  }, { strategy: "summary", model_version: "model:v1", prompt_version: "prompt:v1", policy_version: "policy:v1", schema_version: "schema:v1" });
  return { input, render: renders[0]! };
};

const resign = (render: RenderNode, patch: Partial<RenderNode>): RenderNode => {
  const changed = { ...render, ...patch };
  const render_hash = sha256CanonicalRedacted({
    owner_account_id: changed.owner_account_id,
    graph_generation: changed.graph_generation,
    reader_projection_digest: changed.reader_projection_digest,
    projection_authorization_digest: changed.projection_authorization_digest,
    projected_content_digest: changed.projected_content_digest,
    node_id: changed.node_id,
    rendered_from_digest: changed.rendered_from_digest,
    rendered_from_manifest: changed.rendered_from_manifest,
    summary_text: changed.summary_text,
    citations: [...changed.citations].sort(),
    effective_policy: changed.effective_policy,
  });
  return { ...changed, render_hash, render_generation: `render-v1:${render_hash}` };
};

const denial = (input: ApplicationGrantProjectedTreeInputSnapshot, render: RenderNode, reason: SynthesizedProjectionDenied["reason"]): void => {
  try {
    buildOwnerBoundSynthesizedProjection(input, render);
    throw new Error(`expected ${reason}`);
  } catch (error) {
    expect(error).toBeInstanceOf(SynthesizedProjectionDenied);
    expect((error as SynthesizedProjectionDenied).reason).toBe(reason);
  }
};

test("projection binds owner, generations, exact claims, citations, policy, and summary without raw L1", async () => {
  const { input, render } = await renderedFixture();
  const envelope = buildOwnerBoundSynthesizedProjection(input, render);
  expect(envelope.owner_account_id).toBe(input.owner_account_id);
  expect(envelope.graph_generation).toBe(input.graph_generation);
  expect(envelope.projection_authorization_digest).toBe(input.projection_authorization_digest);
  expect(envelope.reader_projection_digest).toBe(input.reader_projection_digest);
  expect(envelope.projected_content_digest).toBe(input.projected_content_digest);
  expect(envelope.live_claim_revision_ids).toEqual([...render.rendered_from_manifest.live_member_revisions].sort());
  expect(envelope.citations).toEqual([{ evidence_id: "e1", event_revision_id: "event", capture_session_id: "capture", claim_revision_ids: envelope.live_claim_revision_ids }]);
  expect(envelope.synthesized_summary).toBe("A synthesized summary.");
  const serialized = JSON.stringify(envelope);
  for (const hidden of ["excerpt", "payload", "range", "raw", "tier", "source_identity_ref", "source_unit_ref"]) expect(serialized).not.toContain(hidden);
  expect(Object.isFrozen(envelope)).toBe(true);
  expect(Object.isFrozen(envelope.citations)).toBe(true);
  expect(Object.isFrozen(envelope.citations[0])).toBe(true);
  expect(Object.isFrozen(envelope.citations[0]!.claim_revision_ids)).toBe(true);
  expect(Object.isFrozen(envelope.effective_policy)).toBe(true);
});

test("projection fails closed for cross-owner, graph mismatch, stale, failed, or tampered render", async () => {
  const { input, render } = await renderedFixture();
  denial(input, { ...render, owner_account_id: "owner:b" }, "owner_mismatch");
  denial(input, { ...render, graph_generation: "graph:stale" }, "generation_mismatch");
  denial(input, { ...render, stale: true }, "render_stale");
  denial(input, { ...render, status: "failed", summary_text: null, failure: "model failed" }, "render_not_ready");
  denial(input, { ...render, summary_text: "tampered" }, "render_identity_invalid");
});

test("projection rejects an owner view or a render from a differently authorized application", async () => {
  const { input, render } = await renderedFixture("app:a");
  const unbrandedOwnerView = structuredClone(input) as ApplicationGrantProjectedTreeInputSnapshot;
  denial(unbrandedOwnerView, render, "authorization_binding_mismatch");
  const other = await renderedFixture("app:b");
  denial(input, other.render, "authorization_binding_mismatch");
});

test("copying every discoverable runtime brand cannot forge a projected input", async () => {
  const { input, render } = await renderedFixture();
  const forged = structuredClone(input) as ApplicationGrantProjectedTreeInputSnapshot;
  for (const key of Reflect.ownKeys(input)) if (typeof key === "symbol") {
    Object.defineProperty(forged, key, Object.getOwnPropertyDescriptor(input, key)!);
  }
  denial(forged, render, "authorization_binding_mismatch");
});

test("projection rejects claim, policy, and complete-citation mismatches", async () => {
  const { input, render } = await renderedFixture();
  denial(input, resign(render, { rendered_from_manifest: { ...render.rendered_from_manifest, live_member_revisions: ["missing"] } }), "claim_revision_mismatch");
  denial(input, resign(render, { effective_policy: { ...render.effective_policy, sensitivity: "restricted" } }), "policy_mismatch");
  denial(input, resign(render, { citations: [] }), "citation_mismatch");
  denial(input, resign(render, { citations: [...render.citations, "evidence:uncited"] }), "citation_mismatch");
});

test("projection is detached from later mutation of citation inputs", async () => {
  const { input, render } = await renderedFixture();
  const mutableInput = input;
  const mutableRender = structuredClone(render) as RenderNode;
  const envelope = buildOwnerBoundSynthesizedProjection(mutableInput, mutableRender);
  expect(() => { (mutableInput.evidence_index[0] as { event_revision_id: string }).event_revision_id = "event:mutated"; }).toThrow();
  (mutableRender.citations as string[])[0] = "evidence:mutated";
  expect(envelope.citations[0]!.event_revision_id).toBe("event");
  expect(envelope.citations[0]!.evidence_id).toBe("e1");
});

test("rendering itself refuses mixed graph generations", async () => {
  const input = projectedInput();
  const tree = buildDeterministicAnchors(input);
  await expect(renderStructuralTree({ ...tree, input_generation: "graph:other" }, input, {
    render: async () => ({ summary_text: "must not render", citations: ["e1"] }),
  }, { strategy: "summary", model_version: "m", prompt_version: "p", policy_version: "p", schema_version: "s" })).rejects.toThrow("render tree/input generation mismatch");
});

test("model request mutation cannot rewrite the retained render manifest", async () => {
  const input = projectedInput();
  const tree = buildDeterministicAnchors(input);
  const original = tree.nodes[0]!.dependency_manifest.live_member_revisions;
  const renders = await renderStructuralTree(tree, input, {
    render: async (request) => {
      const node = (request.input as { node: { dependency_manifest: { live_member_revisions: string[] } } }).node;
      node.dependency_manifest.live_member_revisions.push("forged");
      return { summary_text: "safe", citations: ["e1"] };
    },
  }, { strategy: "summary", model_version: "m", prompt_version: "p", policy_version: "p", schema_version: "s" });
  expect(renders[0]!.rendered_from_manifest.live_member_revisions).toEqual(original);
  expect(renders[0]!.rendered_from_manifest.live_member_revisions).not.toContain("forged");
});

test("render snapshots input, tree, options, and cache before the awaited model edge", async () => {
  const mutableInput = structuredClone(projectedInput()) as TreeInputSnapshot;
  const tree = buildDeterministicAnchors(mutableInput);
  const options = { strategy: "summary", model_version: "model:before", prompt_version: "p", policy_version: "p", schema_version: "s" };
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const seenPredicates: string[] = [];
  const pending = renderStructuralTree(tree, mutableInput, {
    render: async (request) => {
      await gate;
      seenPredicates.push((request.input as { claims: { predicate: string }[] }).claims[0]!.predicate);
      return { summary_text: "stable", citations: ["e1"] };
    },
  }, options);
  await Promise.resolve();
  (mutableInput.claims[0] as { predicate: string }).predicate = "mutated-after-call";
  options.model_version = "model:after";
  (tree.nodes[0]!.dependency_manifest.live_member_revisions as string[]).push("forged-after-call");
  release();
  const renders = await pending;
  expect(seenPredicates.every((predicate) => predicate === "met")).toBe(true);
  expect(renders.every((render) => render.model_version === "model:before")).toBe(true);
  expect(renders.every((render) => !render.rendered_from_manifest.live_member_revisions.includes("forged-after-call"))).toBe(true);
});

test("cache identity changes when projected content changes without a graph frontier", async () => {
  const firstGraph = snapshot();
  const secondGraph = snapshot();
  secondGraph.claims = secondGraph.claims.map((item) => item.revision_id === "a"
    ? { ...item, claim: { ...item.claim, predicate: "changed-predicate" } }
    : item);
  const project = (graph: ReturnType<typeof snapshot>) => readAfterApplicationAuthorization(authorizationRequest(), () => ({
    snapshot: graph, options: { account_timezone: "UTC" },
  }));
  const firstInput = project(firstGraph);
  const secondInput = project(secondGraph);
  const firstRenders = await renderStructuralTree(buildDeterministicAnchors(firstInput), firstInput, {
    render: async () => ({ summary_text: "first", citations: ["e1"] }),
  }, { strategy: "summary", model_version: "m", prompt_version: "p", policy_version: "p", schema_version: "s" });
  const cache = new Map(firstRenders.map((render) => [render.rendered_from_digest, render]));
  let calls = 0;
  const secondRenders = await renderStructuralTree(buildDeterministicAnchors(secondInput), secondInput, {
    render: async () => { calls++; return { summary_text: "second", citations: ["e1"] }; },
  }, { strategy: "summary", model_version: "m", prompt_version: "p", policy_version: "p", schema_version: "s" }, cache);
  expect(secondInput.graph_generation).not.toBe(firstInput.graph_generation);
  expect(calls).toBeGreaterThan(0);
  expect(secondRenders.some((render) => render.summary_text === "second")).toBe(true);

  const evidenceGraph = snapshot();
  evidenceGraph.evidence = evidenceGraph.evidence!.map((item) => ({ ...item, evidence: { ...item.evidence, excerpt: "changed evidence with the same ids" } }));
  const evidenceInput = project(evidenceGraph);
  expect(evidenceInput.graph_generation).not.toBe(firstInput.graph_generation);
  expect(evidenceInput.projected_content_digest).not.toBe(firstInput.projected_content_digest);

  const hiddenPrivateChange = snapshot();
  hiddenPrivateChange.claims = hiddenPrivateChange.claims.map((item) => item.revision_id === "private"
    ? { ...item, claim: { ...item.claim, predicate: "changed-hidden-private" } }
    : item);
  const hiddenPrivateInput = project(hiddenPrivateChange);
  expect(hiddenPrivateInput.graph_generation).toBe(firstInput.graph_generation);
  expect(hiddenPrivateInput.projected_content_digest).toBe(firstInput.projected_content_digest);
});

test("poisoned or re-signed cache entries are rejected and recomputed", async () => {
  const input = projectedInput();
  const tree = buildDeterministicAnchors(input);
  const options = { strategy: "summary", model_version: "m", prompt_version: "p", policy_version: "p", schema_version: "s" };
  const first = await renderStructuralTree(tree, input, { render: async () => ({ summary_text: "first", citations: ["e1"] }) }, options);
  const seed = first[0]!;
  const poisonedManifest = { ...seed.rendered_from_manifest, live_member_revisions: ["forged"] };
  const poisonedHash = sha256CanonicalRedacted({
    owner_account_id: seed.owner_account_id,
    graph_generation: seed.graph_generation,
    reader_projection_digest: seed.reader_projection_digest,
    projection_authorization_digest: seed.projection_authorization_digest,
    projected_content_digest: seed.projected_content_digest,
    node_id: seed.node_id,
    rendered_from_digest: seed.rendered_from_digest,
    rendered_from_manifest: poisonedManifest,
    summary_text: seed.summary_text,
    citations: seed.citations,
    effective_policy: seed.effective_policy,
  });
  const poisoned = { ...seed, rendered_from_manifest: poisonedManifest, render_hash: poisonedHash, render_generation: `render-v1:${poisonedHash}` };
  let calls = 0;
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, {
    render: async () => { calls++; return { summary_text: "recomputed", citations: ["e1"] }; },
  }, options, new Map([[seed.rendered_from_digest, poisoned]]));
  expect(calls).toBeGreaterThan(0);
  expect(renders.every((render) => !render.rendered_from_manifest.live_member_revisions.includes("forged"))).toBe(true);

  const resignedPolicy = resign(seed, { effective_policy: { ...seed.effective_policy, sensitivity: "private" } });
  calls = 0;
  const policyRenders = await renderStructuralTree(buildDeterministicAnchors(input), input, {
    render: async () => { calls++; return { summary_text: "policy-recomputed", citations: ["e1"] }; },
  }, options, new Map([[seed.rendered_from_digest, resignedPolicy]]));
  expect(calls).toBeGreaterThan(0);
  expect(policyRenders.every((render) => render.effective_policy.sensitivity === "generic")).toBe(true);

  calls = 0;
  const malformed = { ...seed, citations: undefined } as never;
  await renderStructuralTree(buildDeterministicAnchors(input), input, {
    render: async () => { calls++; return { summary_text: "malformed-recomputed", citations: ["e1"] }; },
  }, options, new Map([[seed.rendered_from_digest, malformed]]));
  expect(calls).toBeGreaterThan(0);

  calls = 0;
  const extraField = { ...seed, raw: "must-never-survive-cache-validation" } as never;
  const exactRenders = await renderStructuralTree(buildDeterministicAnchors(input), input, {
    render: async () => { calls++; return { summary_text: "exact-recomputed", citations: ["e1"] }; },
  }, options, new Map([[seed.rendered_from_digest, extraField]]));
  expect(calls).toBeGreaterThan(0);
  expect(JSON.stringify(exactRenders)).not.toContain("must-never-survive-cache-validation");
});
