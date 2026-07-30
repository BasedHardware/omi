import { expect, test } from "bun:test";
import { projectTreeInputSnapshot, type GraphSnapshot } from "./index";
import { buildDeterministicAnchors, nodeId } from "./tree";

const entity = (id: string, handle: string) => ({ entity_id: id, owner_account_id: "owner", entity_revision_id: `${id}:r1`, handle, labels: [] });
const c = (id: string, subject: string, labels: string[] = [], status: "canonical" | "withheld_unresolved_subject" = "canonical") => ({ revision_id: id, placement_status: status, claim: { claim_lineage_id: `lineage:${id}`, claim_revision_id: id, owner_account_id: "owner", predicate: "met", arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref" as const, ref: subject } }], temporal_scope: { observed_at: "2026-01-02T10:00:00Z", precision: "instant" }, evidence_refs: ["e1"], policy_labels: labels, source_language: "en", scope: { locality: "durable" as const, scope_ref: subject }, lifecycle: status === "canonical" ? "canonical" as const : "provisional" as const, ...(status === "canonical" ? { canonical_claim_id: `canon:${id}`, source_provisional_revision_ids: [] } : { ambiguity_markers: ["unresolved_subject"], context_packet: null }) } });
const snapshot = (merged = true): GraphSnapshot => ({ owner_account_id: "owner", claims: [c("a", "old"), c("withheld", "old", [], "withheld_unresolved_subject"), c("private", "old", ["sensitivity:private"])], entities: [{ revision_id: "old:r1", entity: entity("old", "z") }, { revision_id: "survivor:r1", entity: entity("survivor", "a") }], identity_constraints: [{ revision_id: "merge", constraint: { constraint_id: "merge", owner_account_id: "owner", left_handle: "z", right_handle: "a", relation: "same", evidence_refs: ["e1"], effective_at: 1, reversed_at: merged ? null : 2 } }], events: [{ revision_id: "event", event: { event_id: "event", event_revision_id: "event", owner_account_id: "owner", capture_session_id: "capture", stream_id: "s", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-02", ingest_time: "2026-01-02", source_sequence: 0, evidence_addressable_refs: ["e1"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "h" } }], evidence: [{ revision_id: "e", evidence: { evidence_id: "e1", event_revision_id: "event", source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: "x", source_local_speaker_ref: null, source_local_mention_ref: null, state: "active", source_trust: "test", policy_labels: [], source_independence_key: "k" } }], adjacency: [] });

test("R1 merge moves entity members to survivor and split restores the original root", () => {
  const merged = buildDeterministicAnchors(projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC" }));
  expect(new Set(merged.nodes.filter((node) => node.view_kind === "entity").map((node) => node.anchor_key))).toEqual(new Set(["entity:survivor"]));
  const split = buildDeterministicAnchors(projectTreeInputSnapshot(snapshot(false), { account_timezone: "UTC" }));
  expect(split.nodes.filter((node) => node.view_kind === "entity").map((node) => node.anchor_key)).toContain("entity:old");
});

test("R1 keeps withheld content only in source anchors and partitions node identities", () => {
  const input = projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC", valid_time_by_claim_revision: { a: "2026-01-02T10:00:00Z", private: "2026-01-02T10:00:00Z" } });
  const tree = buildDeterministicAnchors(input);
  expect(tree.nodes.filter((node) => node.view_kind === "entity").flatMap((node) => node.member_claim_revision_ids)).not.toContain("withheld");
  expect(tree.nodes.filter((node) => node.view_kind === "source").flatMap((node) => node.member_claim_revision_ids)).toContain("withheld");
  const sameAnchor = tree.nodes.filter((node) => node.view_kind === "temporal" && node.anchor_key.endsWith("day:02"));
  expect(new Set(sameAnchor.map((node) => node.node_id)).size).toBe(2);
  expect(nodeId("owner", "temporal", sameAnchor[0]!.anchor_key, sameAnchor[0]!.policy_partition_label)).toBe(sameAnchor[0]!.node_id);
});
