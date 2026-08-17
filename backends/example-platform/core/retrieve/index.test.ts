import { expect, test } from "bun:test";
import { retrieveCommittedGraph, retrieveCommittedGraphInternal, type GraphSnapshot } from "./index";

const entity = { entity_id: "entity:alice", owner_account_id: "owner-1", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] };
const canonical = { claim_lineage_id: "lineage:c1", claim_revision_id: "c-1", owner_account_id: "owner-1", predicate: "preference", arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref" as const, ref: "entity:alice" } }], temporal_scope: { observed_at: "2026-01-01", precision: "day" }, evidence_refs: ["e-citation"], policy_labels: [], source_language: "en", scope: { locality: "durable" as const, scope_ref: "entity:alice" }, lifecycle: "canonical" as const, canonical_claim_id: "canonical:c1", source_provisional_revision_ids: ["p-1"] };
const provisional = { claim_lineage_id: "lineage:p2", claim_revision_id: "p-unresolved", owner_account_id: "owner-1", predicate: "preference", arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal" as const, value: "He" } }], temporal_scope: { observed_at: "2026-01-02", precision: "day" }, evidence_refs: ["e-unresolved"], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "provisional" as const, ambiguity_markers: ["unresolved_subject"], context_packet: { version: "v1", referent_refs: [], topic_refs: [] } };
const graph: GraphSnapshot = {
  owner_account_id: "owner-1",
  claims: [{ revision_id: "c-1", claim: canonical, placement_status: "canonical" }, { revision_id: "p-unresolved", claim: provisional, placement_status: "provisional_unresolved_subject" }],
  entities: [{ revision_id: "entity:alice:r1", entity }],
  evidence: [{ revision_id: "e-citation:r1", evidence: { evidence_id: "e-citation", event_revision_id: "event:missing", source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: null, source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state: "active", source_trust: "test", policy_labels: [], source_independence_key: "test" } }],
  adjacency: [{ claim_revision_id: "c-1", entity_id: "entity:alice", role_slot_id: "subject" }],
};

test("T10 entity retrieval never reader-surfaces a provisional claim as related content", () => {
  const result = retrieveCommittedGraph(graph, { owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" });
  expect(result.claims).toHaveLength(1);
  expect(result.claims[0]).toMatchObject({ revision_id: "c-1", entities: [entity], scope: canonical.scope, evidence_citations: ["e-citation"], dates: canonical.temporal_scope, status: "canonical" });
  expect(result).toEqual({ claims: [result.claims[0]], absence: null });
  expect(retrieveCommittedGraphInternal(graph, { owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" }).omission_accounting).toEqual({ total_committed_claims: 2, returned_canonical: 1, provisional_items: 1, provisional_by_status: { provisional_unresolved_subject: 1, provisional_abstained: 0 }, omitted_items: 1 });
});

test("T10 source/time provisional retrieval returns provisional content only when explicitly requested", () => {
  expect(retrieveCommittedGraph(graph, { owner_account_id: "owner-1", kind: "as_of", date: "2026-01-01" }).claims.map((claim) => claim.revision_id)).toEqual(["c-1"]);
  const asOf = retrieveCommittedGraph(graph, { owner_account_id: "owner-1", kind: "as_of", date: "2026-01-02", include_provisional: true });
  expect(asOf.claims.map((claim) => claim.revision_id)).toEqual(["c-1", "p-unresolved"]);
  expect(asOf.claims[1]?.status).toBe("provisional_unresolved_subject");
});
