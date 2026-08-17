import { describe, expect, test } from "bun:test";

import {
  appendProductMembership,
  birthProductProposition,
} from "../../../core/retrieve/product-projection";
import {
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../../core/retrieve/authorization-boundary";
import { renderStructuralTree, type RenderNode, type RenderOptions } from
  "../../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../../core/retrieve/tree";
import { snapshot } from "../../../core/retrieve/tree.fixture";
import { createAuthorizedLedgerWriteContextIssuer } from
  "../auth/authorized-context-internal";
import {
  assertProductProjectionWriteRequest,
  type ProductGraphCoordinate,
} from "../stores/product-projection-repository";
import {
  buildAuthorizedProductProjectionWriteRequest,
  PRODUCT_RENDERED_CONTENT_VERSION,
  type AuthorizedProductProjectionMaterializationInput,
} from "./product-projection-materialization";

const authorizationRequest = (): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: {
    owner_account_id: "owner",
    credential_kind: "mcp_api_key",
    app_id: "app:reader",
    key_id: "key:reader",
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: "owner",
    consumer: "mcp",
    app_id: "app:reader",
    key_id: "key:reader",
    enabled: true,
    default_read: true,
    scopes: ["memories.read"],
  },
});

const authorizedInput = (): ApplicationGrantProjectedTreeInputSnapshot =>
  readAfterApplicationAuthorization(authorizationRequest(), () => ({
    snapshot: snapshot(),
    options: { account_timezone: "UTC" },
  }));

const renderOptions = (patch: Partial<RenderOptions> = {}): RenderOptions => ({
  strategy: "summary",
  model_version: "model:v1",
  prompt_version: "prompt:v1",
  policy_version: "policy:v1",
  schema_version: "schema:v1",
  ...patch,
});

const renderOne = async (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  citations: readonly string[] = ["e1"],
  options: RenderOptions = renderOptions(),
  summary = "A synthesized summary.",
): Promise<RenderNode> => {
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, {
    render: async () => ({ summary_text: summary, citations: [...citations] }),
  }, options);
  const render = renders.find((item) => item.rendered_from_manifest.live_member_revisions.length === 1
    && item.rendered_from_manifest.live_member_revisions[0] === "a");
  if (!render) throw new Error("fixture has no single-claim render");
  return render;
};

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "principal:projector",
  account_id: "owner",
  application_id: "app:projector",
  credential_id: "credential:projector",
  credential_generation: 1,
  capability: "memories.project",
  grant_id: "grant:projector",
  grant_version: 1,
  account_epoch: 1,
  destination_activation_revision: 1,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: "a".repeat(64),
}, 150);

const fixture = async (options: RenderOptions = renderOptions(), citations: readonly string[] = ["e1"], summary?: string) => {
  const authorized_input = authorizedInput();
  const render = await renderOne(authorized_input, citations, options, summary);
  const claim = authorized_input.claims.find((item) => item.claim_revision_id === "a")!;
  const born = birthProductProposition({
    owner_account_id: authorized_input.owner_account_id,
    proposition_id: "proposition:opaque-one",
    birth_claim_lineage_id: claim.claim_lineage_id,
    origin: "native",
    graph_frontier: authorized_input.graph_generation,
    input_digest: "b".repeat(64),
    result_digest: "c".repeat(64),
    created_at_event_time: 10,
  });
  const graph: ProductGraphCoordinate = Object.freeze({
    owner_account_id: authorized_input.owner_account_id,
    graph_frontier: authorized_input.graph_generation,
    graph_commit_id: "commit:one",
    graph_commit_sequence: 1,
  });
  const input: AuthorizedProductProjectionMaterializationInput = {
    authorized_input,
    render,
    identity: born.identity,
    membership: born.membership,
    graph,
    projection_sequence: 1,
    created_at_event_time: 20,
  };
  return { input, claim, born };
};

describe("authorized product projection materialization", () => {
  test("derives one deterministic repository-accepted request from authorized ledger state", async () => {
    const { input, claim } = await fixture();
    const first = buildAuthorizedProductProjectionWriteRequest(input);
    const second = buildAuthorizedProductProjectionWriteRequest(input);
    expect(JSON.stringify(first)).toBe(JSON.stringify(second));
    expect(assertProductProjectionWriteRequest(context(), first)).toEqual(first);
    expect(first.projection.renderer_contract_digest).toBe(input.render.renderer_contract_digest);
    expect(first.projection.citations).toEqual([{
      claim_lineage_id: claim.claim_lineage_id,
      claim_revision_id: claim.claim_revision_id,
      evidence_refs: [...claim.evidence_refs].sort(),
    }]);
    expect(first.payload.payload_contract_version).toBe(PRODUCT_RENDERED_CONTENT_VERSION);
    expect(first.payload.rendered_content).toEqual({
      version: PRODUCT_RENDERED_CONTENT_VERSION,
      summary_text: "A synthesized summary.",
      source_language: "en",
      effective_policy: { subject_class: "generic", sensitivity: "generic", capture_class: "generic" },
    });
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.payload.rendered_content)).toBe(true);
    expect(() => {
      (first.payload.rendered_content as { summary_text: string }).summary_text = "mutated";
    }).toThrow();
  });

  test("payload is content-only while normalized citations retain exact support", async () => {
    const { input } = await fixture();
    const request = buildAuthorizedProductProjectionWriteRequest(input);
    const payload = JSON.stringify(request.payload.rendered_content);
    expect(Object.keys(request.payload.rendered_content).sort()).toEqual([
      "effective_policy", "source_language", "summary_text", "version",
    ]);
    for (const hidden of [
      input.authorized_input.owner_account_id,
      input.authorized_input.graph_generation,
      input.authorized_input.reader_projection_digest,
      input.authorized_input.projection_authorization_digest,
      input.identity.proposition_id,
      input.membership.membership_revision_id,
      request.projection.projection_revision_id,
    ]) expect(payload).not.toContain(hidden);
    for (const forbiddenKey of [
      "owner_account_id", "graph_frontier", "reader_projection_digest",
      "projection_authorization_digest", "proposition_id", "membership_revision_id",
      "projection_revision_id", "claim_lineage_id", "claim_revision_id", "evidence_refs",
    ]) expect(payload).not.toContain(forbiddenKey);
  });

  test("renderer coordinates are explicit and change projection identity", async () => {
    const firstFixture = await fixture(renderOptions());
    const secondFixture = await fixture(renderOptions({ prompt_version: "prompt:v2" }));
    const first = buildAuthorizedProductProjectionWriteRequest(firstFixture.input);
    const second = buildAuthorizedProductProjectionWriteRequest(secondFixture.input);
    expect(first.projection.renderer_contract_digest)
      .not.toBe(second.projection.renderer_contract_digest);
    expect(first.projection.projection_revision_id)
      .not.toBe(second.projection.projection_revision_id);
    expect(first.request_digest).not.toBe(second.request_digest);
  });

  test("clones, cross-owner state, stale graph coordinates, and membership drift fail closed", async () => {
    const { input, born } = await fixture();
    expect(() => buildAuthorizedProductProjectionWriteRequest({
      ...input,
      authorized_input: structuredClone(input.authorized_input),
    })).toThrow("untrusted_input");
    expect(() => buildAuthorizedProductProjectionWriteRequest({
      ...input,
      render: structuredClone(input.render),
    })).toThrow("untrusted_input");
    expect(() => buildAuthorizedProductProjectionWriteRequest({
      ...input,
      graph: { ...input.graph, owner_account_id: "owner:other" },
    })).toThrow("graph_coordinate_mismatch");
    expect(() => buildAuthorizedProductProjectionWriteRequest({
      ...input,
      graph: { ...input.graph, graph_frontier: "frontier:stale" },
    })).toThrow("graph_coordinate_mismatch");

    const expanded = appendProductMembership({
      identity: born.identity,
      parent: born.membership,
      member_claim_lineage_ids: [
        born.identity.birth_claim_lineage_id,
        "lineage:unrendered",
      ].sort(),
      cause: "ledger_consolidation",
      graph_frontier: input.authorized_input.graph_generation,
      input_digest: "d".repeat(64),
      result_digest: "e".repeat(64),
      created_at_event_time: 11,
    });
    expect(() => buildAuthorizedProductProjectionWriteRequest({
      ...input,
      membership: expanded,
    })).toThrow("membership_render_mismatch");
  });

  test("model citation drift and hostile request containers cannot become product support", async () => {
    const omitted = await fixture(renderOptions(), []);
    expect(() => buildAuthorizedProductProjectionWriteRequest(omitted.input))
      .toThrow("citation_mismatch");
    const added = await fixture(renderOptions(), ["e1", "evidence:invented"]);
    expect(() => buildAuthorizedProductProjectionWriteRequest(added.input))
      .toThrow("citation_mismatch");

    const { input } = await fixture();
    expect(() => buildAuthorizedProductProjectionWriteRequest(new Proxy(input, {}) as never))
      .toThrow("invalid_input");
    const accessor = { ...input };
    Object.defineProperty(accessor, "graph", { enumerable: true, get: () => input.graph });
    expect(() => buildAuthorizedProductProjectionWriteRequest(accessor))
      .toThrow("invalid_input");
    expect(() => buildAuthorizedProductProjectionWriteRequest({
      ...input,
      created_at_event_time: -1,
    })).toThrow("invalid_event_time");
    expect(() => buildAuthorizedProductProjectionWriteRequest({
      ...input,
      projection_sequence: 0,
    })).toThrow("invalid_projection_sequence");
  });

  test("oversized rendered content is rejected before a repository request exists", async () => {
    const oversized = await fixture(renderOptions(), ["e1"], "x".repeat(300_000));
    expect(() => buildAuthorizedProductProjectionWriteRequest(oversized.input))
      .toThrow("payload_too_large");
  });
});
