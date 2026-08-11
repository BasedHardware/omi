// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
// domain-pending(DIV-DOMX-006)
import { readFileSync } from "node:fs";

import { expect, test } from "bun:test";

import {
  isPlacementDecision,
  parseFormationOutcomeEnvelope,
  retainsAcceptedWork,
} from "../../core/consolidate/formation-outcome";
import type { GraphSnapshot } from "../../core/retrieve";
import {
  readAfterApplicationAuthorization,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../core/retrieve/authorization-boundary";
import { buildOwnerBoundSynthesizedProjection } from "../../core/retrieve/projection-boundary";
import { renderStructuralTree } from "../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";

type ComparisonFixture = {
  schema_version: string;
  versions: Record<string, string>;
  formation: unknown;
  graph: GraphSnapshot;
  expected_semantic_manifest: unknown;
};

const fixture = JSON.parse(readFileSync(
  new URL("./fixtures/first-slice.json", import.meta.url),
  "utf8",
)) as ComparisonFixture;

const exactKeys = (value: object, expected: readonly string[]): boolean => {
  const actual = Object.keys(value).sort();
  const sorted = [...expected].sort();
  return actual.length === sorted.length && actual.every((key, index) => key === sorted[index]);
};

const authorizationRequest = (): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: fixture.graph.owner_account_id,
  credential: {
    owner_account_id: fixture.graph.owner_account_id,
    credential_kind: "mcp_api_key",
    app_id: "app:synthetic-comparison",
    key_id: "key:synthetic-comparison",
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: fixture.graph.owner_account_id,
    consumer: "mcp",
    app_id: "app:synthetic-comparison",
    key_id: "key:synthetic-comparison",
    enabled: true,
    default_read: true,
    scopes: ["memories.read"],
  },
});

test("P0 comparison fixture is synthetic, explicit, and has no implicit strategy switch", () => {
  const formation = parseFormationOutcomeEnvelope(fixture.formation);
  expect(exactKeys(fixture, [
    "schema_version", "versions", "formation", "graph", "expected_semantic_manifest",
  ])).toBe(true);
  expect(fixture.schema_version).toBe("memory-productionization-comparison-v1");
  expect(fixture.versions).toEqual({
    kernel_contract: "memory-productionization-v1",
    extraction_strategy: "grounded-reference-v1",
    speaker_strategy: "session-frame-reference-v1",
    boundary_strategy: "unit-boundary-reference-v1",
    projection_strategy: "proposition-per-lineage-v1",
    read_strategy: "authorized-synthesized-v1",
  });
  expect(formation.coordinates).toMatchObject({
    strategy_version: fixture.versions.extraction_strategy,
    speaker_strategy_version: fixture.versions.speaker_strategy,
    boundary_strategy_version: fixture.versions.boundary_strategy,
    code_version: fixture.versions.kernel_contract,
  });
  expect(fixture.graph.owner_account_id).toBe("owner:synthetic");
  expect(fixture.graph.events?.every((item) =>
    item.event.source_trust === "synthetic-fixture"
    && item.event.payload_schema_ref === "synthetic-text-v1")).toBe(true);
});

test("P0 semantic comparison reaches the canonical authorized projection without a model or network edge", async () => {
  const formation = parseFormationOutcomeEnvelope(fixture.formation);
  const projected = readAfterApplicationAuthorization(authorizationRequest(), () => ({
    snapshot: fixture.graph,
    options: { account_timezone: "UTC" },
  }));
  const tree = buildDeterministicAnchors(projected);
  let fakeRenderCalls = 0;
  const renders = await renderStructuralTree(tree, projected, {
    render: async (request) => {
      fakeRenderCalls += 1;
      const node = (request.input as { node: { dependency_manifest: { live_member_revisions: string[] } } }).node;
      return {
        summary_text: "Synthetic subject prefers synthetic tea.",
        citations: node.dependency_manifest.live_member_revisions.length > 0
          ? ["evidence:synthetic:1"]
          : [],
      };
    },
  }, {
    strategy: fixture.versions.read_strategy!,
    model_version: "deterministic-fake-v1",
    prompt_version: "none",
    policy_version: "policy-classifier-generic-v1",
    schema_version: fixture.schema_version,
  });
  const render = renders.find((candidate) =>
    candidate.rendered_from_manifest.live_member_revisions.includes("claim:canonical:1"));
  expect(render).toBeDefined();
  const envelope = buildOwnerBoundSynthesizedProjection(projected, render!);

  const canonicalClaims = fixture.graph.claims
    .filter((item) => item.placement_status === "canonical")
    .sort((left, right) => left.revision_id.localeCompare(right.revision_id));
  const actual = {
    schema_version: fixture.schema_version,
    versions: fixture.versions,
    evidence_ids: [...new Set(formation.extraction_outcomes.flatMap((outcome) =>
      outcome.kind === "accepted" ? outcome.evidence_ids : []))].sort(),
    extraction_dispositions: formation.extraction_outcomes.map((outcome) =>
      outcome.kind === "accepted"
        ? `${outcome.claim_revision_id}:${outcome.kind}`
        : [outcome.candidate_ref, outcome.kind, outcome.reason_code, outcome.reason_detail]
          .filter((value) => value !== null).join(":")),
    placement_dispositions: formation.placement_outcomes.map((outcome) => {
      if (outcome.kind === "admitted") {
        return `${outcome.input_provisional_revision_id}:${outcome.kind}:${outcome.canonical_claim_revision_id}`;
      }
      if (outcome.kind === "retryable_error" || outcome.kind === "dead_letter") {
        return `${outcome.input_provisional_revision_id}:${outcome.kind}:${outcome.error_code}`;
      }
      return `${outcome.input_provisional_revision_id}:${outcome.kind}:${outcome.reason_code}`;
    }),
    canonical_claim_heads: canonicalClaims.map((item) =>
      `${item.claim.claim_lineage_id}:${item.revision_id}`),
    predicate_identities: (fixture.graph.predicates ?? []).map((item) =>
      `${item.predicate.predicate_id}:${item.predicate.identity_name}:${[...item.predicate.slot_ids].sort().join(",")}`),
    argument_roles: canonicalClaims.flatMap((item) => item.claim.arguments.map((argument) =>
      `${item.revision_id}:${argument.slot_id}:${argument.role}`)).sort(),
    policy_labels: [...new Set(canonicalClaims.flatMap((item) => item.claim.policy_labels))].sort(),
    scope_localities: canonicalClaims.map((item) =>
      `${item.revision_id}:${item.claim.scope.locality}`),
    lifecycle_heads: canonicalClaims.map((item) =>
      `${item.revision_id}:${item.claim.lifecycle}`),
    entity_adjacency: fixture.graph.adjacency.map((edge) =>
      `${edge.claim_revision_id}:${edge.entity_id}:${edge.role_slot_id}`).sort(),
    authorized_projected_claim_ids: projected.claims.map((claim) => claim.claim_revision_id).sort(),
    citation_ids: envelope.citations.map((citation) => citation.evidence_id).sort(),
    citation_claim_ids: envelope.citations.flatMap((citation) => citation.claim_revision_ids.map((claimId) =>
      `${citation.evidence_id}:${claimId}`)).sort(),
    recall: {
      diagnostic_count: projected.diagnostics.length,
      cited: envelope.citations.length > 0,
    },
  };

  expect(fakeRenderCalls).toBeGreaterThan(0);
  expect(actual).toEqual(fixture.expected_semantic_manifest);
  const retryable = formation.placement_outcomes.find((outcome) =>
    outcome.kind === "retryable_error");
  expect(retryable).toMatchObject({
    kind: "retryable_error",
    error_code: "model_timeout",
  });
  expect(retryable && isPlacementDecision(retryable)).toBe(false);
  expect(retryable && retainsAcceptedWork(retryable)).toBe(true);
  expect(formation.placement_outcomes.some((outcome) =>
    outcome.input_provisional_revision_id === retryable?.input_provisional_revision_id
    && outcome.kind === "admitted")).toBe(false);
});
