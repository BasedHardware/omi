import { expect, test } from "bun:test";
import { sha256CanonicalRedacted } from "../ledger";
import type { TreeInputSnapshot } from "./index";
import {
  projectApplicationDefaultReadTreeInput,
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
  readAfterApplicationAuthorization(authorizationRequest(appId), (authorization) =>
    projectApplicationDefaultReadTreeInput(snapshot(), { account_timezone: "UTC" }, authorization));

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
