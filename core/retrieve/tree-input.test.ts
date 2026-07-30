import { expect, test } from "bun:test";
import { projectTreeInputSnapshot, type GraphSnapshot, type PolicyClassifier } from "./index";

const entity = (id: string, handle = id) => ({ entity_id: id, owner_account_id: "owner", entity_revision_id: `${id}:r1`, handle, labels: [] });
const claim = (revision: string, lineage: string, subject = "entity:old", labels: string[] = []) => ({
  claim_lineage_id: lineage, claim_revision_id: revision, owner_account_id: "owner", predicate: "knows",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref" as const, ref: subject } }],
  temporal_scope: { observed_at: "2026-05-02T10:00:00Z", precision: "instant" }, evidence_refs: ["e1"], policy_labels: labels,
  source_language: "en", scope: { locality: "durable" as const, scope_ref: subject }, lifecycle: "canonical" as const,
  canonical_claim_id: `canonical:${lineage}`, source_provisional_revision_ids: [],
});
const graph = (): GraphSnapshot => ({
  owner_account_id: "owner",
  claims: [
    { revision_id: "old", placement_status: "canonical", claim: claim("old", "lineage:one") },
    { revision_id: "survivor", placement_status: "canonical", claim: claim("survivor", "lineage:one") },
  ],
  entities: [{ revision_id: "old:r1", entity: entity("entity:old", "zeta") }, { revision_id: "new:r1", entity: entity("entity:new", "alpha") }],
  identity_constraints: [{ revision_id: "merge:r1", constraint: { constraint_id: "merge", owner_account_id: "owner", left_handle: "zeta", right_handle: "alpha", relation: "same", evidence_refs: ["e1"], effective_at: 1, reversed_at: null } }],
  events: [{ revision_id: "event:r1", event: { event_id: "event", event_revision_id: "event:r1", owner_account_id: "owner", capture_session_id: "capture:1", stream_id: "stream:1", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-05-02", ingest_time: "2026-05-02", source_sequence: 0, evidence_addressable_refs: ["e1"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "hash" } }],
  evidence: [{ revision_id: "e1:r1", evidence: { evidence_id: "e1", event_revision_id: "event:r1", source_unit_ref: "unit", range: { start: 0, end: 8 }, excerpt: "supported", source_local_speaker_ref: null, source_local_mention_ref: null, state: "active", source_trust: "test", policy_labels: [], source_independence_key: "capture:1" } }],
  adjacency: [],
});

test("R0 projects only one live supersession member and binds roles to the merge survivor", () => {
  const result = projectTreeInputSnapshot(graph(), { account_timezone: "America/New_York" });
  expect(result.claims.map((item) => item.claim_revision_id)).toEqual(["survivor"]);
  expect(result.claims[0]!.arguments[0]!.value).toEqual({ kind: "entity_ref", ref: "entity:new" });
  expect(result.claims[0]!.evidence_spans).toEqual([expect.objectContaining({ capture_session_id: "capture:1", excerpt: "supported" })]);
});

test("R0 never guesses valid time and classifier changes create a new generation", () => {
  const one = projectTreeInputSnapshot(graph(), { account_timezone: "America/New_York" });
  expect(one.claims[0]!.valid_time).toBeNull();
  expect(one.claims[0]!.time_anchor).toEqual({ kind: "imprecise_time", observed_at: "2026-05-02T10:00:00Z", marker: "observed_at_fallback_imprecise" });
  const changed: PolicyClassifier = { version: "policy-classifier-v2", classify: () => ({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }) };
  const two = projectTreeInputSnapshot(graph(), { account_timezone: "America/New_York", classifier: changed });
  expect(two.graph_generation).not.toBe(one.graph_generation);
});
