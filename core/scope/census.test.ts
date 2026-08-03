import { expect, test } from "bun:test";
import { aggregateOperationalCensus } from "./census";

test("C6 census deterministically counts distinct placement strata and only operational proxies", () => {
  const graph = {
    owner_account_id: "owner", adjacency: [],
    claims: [{ revision_id: "c1", placement_status: "canonical" as const, claim: { lifecycle: "canonical" as const, temporal_scope: { valid_time: { typed_expression: { kind: "absolute" as const } } }, scope: { locality: "durable" as const }, evidence_refs: ["e1"] } }, { revision_id: "c2", placement_status: "canonical" as const, claim: { lifecycle: "canonical" as const, temporal_scope: { valid_time: { typed_expression: { kind: "imprecise" as const } } }, scope: { locality: "source_local" as const }, evidence_refs: ["e2"] } }],
    evidence: [{ revision_id: "e1r", evidence: { evidence_id: "e1", event_revision_id: "ev1" } }, { revision_id: "e2r", evidence: { evidence_id: "e2", event_revision_id: "ev2" } }],
    events: [{ revision_id: "ev1", event: { event_revision_id: "ev1", capture_session_id: "s1" } }, { revision_id: "ev2", event: { event_revision_id: "ev2", capture_session_id: "s1" } }],
    placement_artifacts: [
      { artifact_id: "a", kind: "auto_placement_log" as const, provisional_revision_id: "p1", canonical_claim_revision_id: "c1", margin: "low" as const, risk_markers: ["low_margin" as const], unit_boundary_decision: "accept_ltm" as const, scope_locality: "durable" as const },
      { artifact_id: "q", kind: "confirmation_queue" as const, provisional_revision_id: "p2", canonical_claim_revision_id: null, margin: null, risk_markers: [], unit_boundary_decision: "accept_ltm" as const, scope_locality: null },
      { artifact_id: "z", kind: "abstention_set" as const, provisional_revision_id: "p3", canonical_claim_revision_id: null, margin: null, risk_markers: ["new_entity" as const], unit_boundary_decision: "abstain" as const, scope_locality: null },
    ],
  } as any;
  expect(aggregateOperationalCensus(graph)).toEqual({ placement_counts: { auto: 1, queued: 1, abstained: 1 }, predicted_temporal_kinds: { absolute: 1, imprecise: 1 }, scope_distribution: { durable: 1, source_local: 1 }, boundary_distribution: { accept_ltm: 2, abstain: 1 }, claims_per_session: { s1: 2 }, proxy_risk_counts: { low_margin: 1, new_entity: 1 } });
});
