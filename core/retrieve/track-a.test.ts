import { expect, test } from "bun:test";
import { projectTreeInputSnapshot } from "./index";
import { compareTrackA, incrementallyTransitionAnchors, type TrackAPerturbation } from "./track-a";
import { buildDeterministicAnchors } from "./tree";
import { snapshot } from "./tree.fixture";

test("R3 Track A independently converges on structure for all adversarial perturbation labels", () => {
  const base = projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC", valid_time_by_claim_revision: { a: "2026-01-02T10:00:00Z", private: "2026-01-02T10:00:00Z" } });
  const prior = buildDeterministicAnchors(base);
  const perturbations: TrackAPerturbation[] = ["late_arrival", "correction", "liveness_supersession", "identity_merge", "identity_split", "policy_classifier", "timezone", "source_reassignment", "strategy", "render_model_swap"];
  for (const perturbation of perturbations) {
    const next = structuredClone(base);
    if (perturbation === "late_arrival") next.claims = [...next.claims, { ...next.claims[0]!, claim_revision_id: "late" }];
    if (perturbation === "correction") next.claims = next.claims.map((claim) => claim.claim_revision_id === "a" ? { ...claim, claim_revision_id: "a-corrected" } : claim);
    if (perturbation === "liveness_supersession") next.claims = next.claims.filter((claim) => claim.claim_revision_id !== "a");
    if (perturbation === "identity_merge") next.claims = next.claims.map((claim) => ({ ...claim, arguments: claim.arguments.map((argument) => argument.value.kind === "entity_ref" ? { ...argument, value: { ...argument.value, ref: "entity:survivor" } } : argument) }));
    if (perturbation === "identity_split") next.claims = next.claims.map((claim) => ({ ...claim, arguments: claim.arguments.map((argument) => argument.value.kind === "entity_ref" ? { ...argument, value: { ...argument.value, ref: "entity:split" } } : argument) }));
    if (perturbation === "policy_classifier") next.claims = next.claims.map((claim) => ({ ...claim, policy_class: { ...claim.policy_class, sensitivity: "private" } }));
    if (perturbation === "timezone") { next.account_timezone = "America/New_York"; next.graph_generation = "timezone-v2"; }
    if (perturbation === "source_reassignment") next.claims = next.claims.map((claim) => ({ ...claim, evidence_spans: claim.evidence_spans.map((span) => ({ ...span, capture_session_id: "capture:reassigned" })) }));
    if (perturbation === "strategy") next.graph_generation = "strategy-v2";
    const full = buildDeterministicAnchors(next);
    const report = compareTrackA(perturbation, prior, full, incrementallyTransitionAnchors(prior, next));
    expect(report.structure_converged).toBe(true);
    expect(report.eligible_node_denominator).toBe(full.nodes.length);
    if (perturbation === "render_model_swap") expect(report.invalidated_node_ids).toEqual([]);
    else expect(report.invalidated_node_ids.length).toBeGreaterThan(0);
  }
  const append = structuredClone(base);
  const report = compareTrackA("late_arrival", prior, buildDeterministicAnchors(append), incrementallyTransitionAnchors(prior, append));
  expect(report.stable_node_ids / report.eligible_node_denominator).toBe(1);
});
