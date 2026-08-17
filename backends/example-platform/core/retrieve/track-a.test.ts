import { expect, test } from "bun:test";
import { projectTreeInputSnapshot, type TreeInputSnapshot } from "./index";
import { compareTrackA, incrementallyTransitionAnchors, type AnchorTransition, type TrackAPerturbation } from "./track-a";
import { buildDeterministicAnchors, type StructuralTree } from "./tree";
import { snapshot } from "./tree.fixture";

const ids = (tree: StructuralTree, predicate: (node: StructuralTree["nodes"][number]) => boolean) => tree.nodes.filter(predicate).map((node) => node.node_id);
const transition = (previous: TreeInputSnapshot, next: TreeInputSnapshot): AnchorTransition => {
  const old = new Map(previous.claims.map((claim) => [claim.claim_revision_id, claim]));
  const nextById = new Map(next.claims.map((claim) => [claim.claim_revision_id, claim]));
  const anchorContextChanged = previous.account_timezone !== next.account_timezone;
  const changed_claims = next.claims.flatMap((claim) => {
    const oldClaim = old.get(claim.claim_revision_id);
    return oldClaim && (anchorContextChanged || JSON.stringify(oldClaim) !== JSON.stringify(claim)) ? [{ previous_claim_revision_id: oldClaim.claim_revision_id, next: claim }] : [];
  });
  const changedOld = new Set(changed_claims.map((change) => change.previous_claim_revision_id));
  const changedNext = new Set(changed_claims.map((change) => change.next.claim_revision_id));
  return { owner_account_id: next.owner_account_id, account_timezone: next.account_timezone, next_graph_generation: next.graph_generation,
    added_claims: next.claims.filter((claim) => !old.has(claim.claim_revision_id) && !changedNext.has(claim.claim_revision_id)),
    removed_claim_revision_ids: previous.claims.filter((claim) => !nextById.has(claim.claim_revision_id) && !changedOld.has(claim.claim_revision_id)).map((claim) => claim.claim_revision_id),
    changed_claims };
};
const baseInput = () => projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC" });

test("R3 Track A applies deltas and asserts each perturbation's exact blast radius", () => {
  const base = baseInput(), prior = buildDeterministicAnchors(base);
  const cases: readonly { perturbation: TrackAPerturbation; next: TreeInputSnapshot; expected: (full: StructuralTree) => readonly string[] }[] = [
    { perturbation: "late_arrival", next: { ...base, graph_generation: "late", claims: [...base.claims, { ...base.claims[0]!, claim_revision_id: "late", valid_time: { ...base.claims[0]!.valid_time!, resolved_interval: { kind: "instant", start: "2026-02-03T01:00:00.000Z", end: "2026-02-03T01:00:00.000Z", timezone: "UTC", granularity: "instant" } }, time_anchor: { kind: "valid_time", value: "2026-02-03T01:00:00Z" }, arguments: [{ ...base.claims[0]!.arguments[0]!, value: { kind: "entity_ref", ref: "entity:late" } }], evidence_spans: [{ ...base.claims[0]!.evidence_spans[0]!, capture_session_id: "capture:late" }] }] }, expected: (full) => [...ids(prior, (n) => n.view_kind === "temporal" && n.anchor_key === "year:2026" && n.policy_partition_label.includes("sensitivity=generic")), ...ids(full, (n) => !prior.nodes.some((old) => old.node_id === n.node_id))] },
    { perturbation: "correction", next: { ...base, graph_generation: "correction", claims: base.claims.map((claim) => claim.claim_revision_id === "a" ? { ...claim, claim_revision_id: "a-corrected" } : claim) }, expected: (full) => [...ids(prior, (n) => n.member_claim_revision_ids.includes("a")), ...ids(full, (n) => n.member_claim_revision_ids.includes("a-corrected"))] },
    { perturbation: "liveness_supersession", next: { ...base, graph_generation: "supersession", claims: base.claims.filter((claim) => claim.claim_revision_id !== "a") }, expected: () => ids(prior, (n) => n.member_claim_revision_ids.includes("a")) },
    { perturbation: "identity_merge", next: { ...base, graph_generation: "merge", claims: base.claims.map((claim) => ({ ...claim, arguments: claim.arguments.map((argument) => argument.value.kind === "entity_ref" ? { ...argument, value: { kind: "entity_ref", ref: "entity:survivor" } } : argument) })) }, expected: (full) => [...ids(prior, (n) => n.view_kind === "entity"), ...ids(full, (n) => n.view_kind === "entity")] },
    { perturbation: "identity_split", next: { ...base, graph_generation: "split", claims: base.claims.map((claim) => ({ ...claim, arguments: claim.arguments.map((argument) => argument.value.kind === "entity_ref" ? { ...argument, value: { kind: "entity_ref", ref: "entity:split" } } : argument) })) }, expected: (full) => [...ids(prior, (n) => n.view_kind === "entity"), ...ids(full, (n) => n.view_kind === "entity")] },
    { perturbation: "policy_classifier", next: { ...base, graph_generation: "policy", claims: base.claims.map((claim) => ({ ...claim, policy_class: { ...claim.policy_class, sensitivity: "private" } })) }, expected: () => ids(prior, () => true) },
    { perturbation: "timezone", next: { ...base, graph_generation: "timezone", account_timezone: "America/New_York" }, expected: (full) => [...ids(prior, (n) => n.view_kind === "temporal" && n.anchor_key.includes("month:")), ...ids(full, (n) => n.view_kind === "temporal" && n.anchor_key.endsWith("day:01"))] },
    { perturbation: "source_reassignment", next: { ...base, graph_generation: "source", claims: base.claims.map((claim) => ({ ...claim, evidence_spans: claim.evidence_spans.map((span) => ({ ...span, capture_session_id: "capture:reassigned" })) })) }, expected: (full) => [...ids(prior, (n) => n.view_kind === "source"), ...ids(full, (n) => n.view_kind === "source")] },
    { perturbation: "strategy", next: { ...base, graph_generation: "strategy" }, expected: () => [] },
    { perturbation: "render_model_swap", next: { ...base, graph_generation: "render-model" }, expected: () => [] },
  ];
  for (const item of cases) {
    const full = buildDeterministicAnchors(item.next);
    const incremental = incrementallyTransitionAnchors(prior, transition(base, item.next));
    const report = compareTrackA(item.perturbation, prior, full, incremental);
    expect(report.structure_converged).toBe(true);
    expect(report.invalidated_node_ids).toEqual([...new Set(item.expected(full))].sort());
    const invalidated = new Set(report.invalidated_node_ids);
    for (const node of prior.nodes.filter((node) => !invalidated.has(node.node_id))) expect(full.nodes.find((next) => next.node_id === node.node_id)?.structural_revision).toBe(node.structural_revision);
  }
});

test("R3 benign append under wholly new anchors preserves every prior ID and revision", () => {
  const base = baseInput(), prior = buildDeterministicAnchors(base);
  const appended = { ...base.claims[0]!, claim_revision_id: "benign-new-anchor", time_anchor: { kind: "imprecise_time" as const, observed_at: "2026-02-03" }, valid_time: null,
    arguments: [{ ...base.claims[0]!.arguments[0]!, value: { kind: "entity_ref" as const, ref: "entity:brand-new" } }], evidence_spans: [{ ...base.claims[0]!.evidence_spans[0]!, capture_session_id: "capture:brand-new" }] };
  const next = { ...base, graph_generation: "benign-append", claims: [...base.claims, appended] };
  // This transition has no full `claims` snapshot, so a rebuild(next) shortcut cannot pass.
  const delta = transition(base, next);
  expect("claims" in delta).toBe(false);
  const full = buildDeterministicAnchors(next), incremental = incrementallyTransitionAnchors(prior, delta);
  expect(compareTrackA("late_arrival", prior, full, incremental).structure_converged).toBe(true);
  for (const old of prior.nodes) expect(full.nodes.find((node) => node.node_id === old.node_id)).toMatchObject({ structural_revision: old.structural_revision });
});

// Track A validates deterministic anchors and projection integrity only; it does not gate D13/D14/D17 adaptive churn.
