import { expect, test } from "bun:test";
import { project } from "../retrieve";
import { walk } from "../retrieve/walk";
import { reprojectBoundClaims, type ReprojectionBinding } from "./reprojection";
import type { GraphSnapshot } from "../retrieve";

const valid = { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-01-01T00:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-01-01T00:00:00Z", end: "2026-01-01T00:00:00Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } };
const local = "source-local:session-1:evidence:s1:t1:0:5";
const sourceIdentity = { namespace_instance_ref: "source-local:evidence:s1:t1", local_key: local, producer: { producer_ref: null, contract_ref: null }, asserted_identity: { domain: null, scope_ref: null } };

test("B2 acceptance: a later binding reprojects an old source-local claim into a walk from its durable entity", () => {
  const sourceClaim = { claim_lineage_id: "lineage:old", claim_revision_id: "claim:old", owner_account_id: "owner", predicate: "works_with", arguments: [{ slot_id: "person", role: "person", value: { kind: "source_local_ref" as const, ref: local } }, { slot_id: "project", role: "project", value: { kind: "literal" as const, value: "Omi" } }], temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant", valid_time: valid }, evidence_refs: ["e1"], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "canonical" as const, canonical_claim_id: "claim:old", source_provisional_revision_ids: ["provisional:old"] };
  const peerClaim = { ...sourceClaim, claim_lineage_id: "lineage:peer", claim_revision_id: "claim:peer", canonical_claim_id: "claim:peer", source_provisional_revision_ids: ["provisional:peer"], arguments: [{ slot_id: "person", role: "person", value: { kind: "entity_ref" as const, ref: "entity:alice" } }] };
  const snapshot = {
    owner_account_id: "owner", graph_generation: 1,
    claims: [{ revision_id: "claim:old", claim: sourceClaim, placement_status: "canonical" as const }, { revision_id: "claim:peer", claim: peerClaim, placement_status: "canonical" as const }],
    entities: [{ revision_id: "entity:alice:r1", entity: { entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] } }],
    mentions: [{ revision_id: "mention:m1", mention: { mention_id: "m1", owner_account_id: "owner", claim_revision_id: "provisional:old", span: { start: 0, end: 5 }, evidence_id: "e1", source_identity_ref: sourceIdentity, speaker_rendering: null, slot_id: "person", surface: "Alice", antecedent_handle: null, resolution: "unresolved" as const, entity_id: null } }],
    evidence: [{ revision_id: "evidence:e1", evidence: { evidence_id: "e1", event_revision_id: "event:e1", source_unit_ref: "t1", range: { start: 0, end: 5 }, excerpt: "Alice", source_identity_ref: sourceIdentity, speaker_rendering: null, source_local_mention_ref: "speaker-1", state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture:s1" } }],
    events: [{ revision_id: "event:e1", event: { event_id: "event:e1", event_revision_id: "event:e1", owner_account_id: "owner", capture_session_id: "s1", stream_id: "test", event_kind: "test", payload_schema_ref: "test", schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:00Z", ingest_time: "2026-01-01T00:00:00Z", source_sequence: 0, evidence_addressable_refs: ["e1"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "hash" } }],
    adjacency: [{ claim_revision_id: "claim:peer", entity_id: "entity:alice", role_slot_id: "person" }],
  };
  const reprojection = reprojectBoundClaims(snapshot, [{ mention_id: "m1", entity_id: "entity:alice" }], 8);
  const after = { ...snapshot, graph_generation: 2, claims: [...snapshot.claims, ...reprojection.revisions], adjacency: [...snapshot.adjacency, ...reprojection.adjacency] };
  const beforeWalk = walk(project(snapshot, { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } }), { anchor: "entity:entity:alice", max_hops: 2, relation_kinds: ["entity-shared"] });
  const afterWalk = walk(project(after, { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } }), { anchor: "entity:entity:alice", max_hops: 2, relation_kinds: ["entity-shared"] });
  expect(beforeWalk.paths.some((path) => path.nodes.includes("claim:claim:old"))).toBe(false);
  expect(afterWalk.paths.some((path) => path.nodes.includes(`claim:${reprojection.revisions[0]!.revision_id}`))).toBe(true);
  expect(after.claims.filter((item) => item.claim.claim_lineage_id === "lineage:old")).toHaveLength(2);
  // D35 sees the append-only successor, not a duplicate live graph node.
  expect(project(after, { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } }).claims.map((item) => item.revision_id)).not.toContain("claim:old");
});

/** One canonical claim per lineage, plus however many mentions name its slot. */
const slotSnapshot = (claims: readonly { lineage: string; provisional: string }[], mentions: readonly { mention_id: string; claim_revision_id: string }[]): GraphSnapshot => ({
  owner_account_id: "owner",
  graph_generation: 1,
  claims: claims.map(({ lineage, provisional }) => ({
    revision_id: `claim:${lineage}`,
    placement_status: "canonical" as const,
    claim: { claim_lineage_id: `lineage:${lineage}`, claim_revision_id: `claim:${lineage}`, owner_account_id: "owner", predicate: "works_with", arguments: [{ slot_id: "person", role: "person", value: { kind: "source_local_ref" as const, ref: local } }], temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant", valid_time: valid }, evidence_refs: ["e1"], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "canonical" as const, canonical_claim_id: `claim:${lineage}`, source_provisional_revision_ids: [provisional] },
  })),
  entities: [],
  evidence: [{ revision_id: "evidence:e1", evidence: { evidence_id: "e1", event_revision_id: "event:e1", source_unit_ref: "t1", range: { start: 0, end: 5 }, excerpt: "Alice", source_identity_ref: sourceIdentity, speaker_rendering: null, source_local_mention_ref: "speaker-1", state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture:s1" } }],
  mentions: mentions.map((mention) => ({ revision_id: `mention:${mention.mention_id}`, mention: { mention_id: mention.mention_id, owner_account_id: "owner", claim_revision_id: mention.claim_revision_id, span: { start: 0, end: 5 }, evidence_id: "e1", source_identity_ref: sourceIdentity, speaker_rendering: null, slot_id: "person", surface: "Alice", antecedent_handle: null, resolution: "unresolved" as const, entity_id: null } })),
  adjacency: [],
}) as unknown as GraphSnapshot;

test("reprojection binds a slot from its BOUND mention even when an unbound mention is reached first", () => {
  // Both mentions name the same slot of the same claim; only the second is
  // bound. Iteration-order selection would hand the slot to the unbound one and
  // silently drop the claim from the pass.
  const snapshot = slotSnapshot([{ lineage: "old", provisional: "provisional:old" }], [{ mention_id: "m0-unbound", claim_revision_id: "provisional:old" }, { mention_id: "m1-bound", claim_revision_id: "provisional:old" }]);
  const reprojection = reprojectBoundClaims(snapshot, [{ mention_id: "m1-bound", entity_id: "entity:alice" }], 8);
  expect(reprojection.revisions).toHaveLength(1);
  expect(reprojection.revisions[0]!.claim.arguments[0]!.value).toEqual({ kind: "entity_ref", ref: "entity:alice" });
  expect(reprojection.adjacency).toEqual([{ claim_revision_id: reprojection.revisions[0]!.revision_id, entity_id: "entity:alice", role_slot_id: "person" }]);
  expect(reprojection.consumed_claim_revision_ids).toEqual(["claim:old"]);
});

test("reprojection skips a claim whose slot has bound mentions naming different entities and leaves other claims alone", () => {
  const snapshot = slotSnapshot(
    [{ lineage: "conflict", provisional: "provisional:conflict" }, { lineage: "ok", provisional: "provisional:ok" }],
    [{ mention_id: "m-alice", claim_revision_id: "provisional:conflict" }, { mention_id: "m-bob", claim_revision_id: "provisional:conflict" }, { mention_id: "m-ok", claim_revision_id: "provisional:ok" }],
  );
  const bindings: ReprojectionBinding[] = [{ mention_id: "m-alice", entity_id: "entity:alice" }, { mention_id: "m-bob", entity_id: "entity:bob" }, { mention_id: "m-ok", entity_id: "entity:alice" }];
  const reprojection = reprojectBoundClaims(snapshot, bindings, 8);
  // Nothing here can decide which of the two entities owns the slot, so the
  // claim is deterministically excluded rather than silently bound to one.
  expect(reprojection.revisions).toHaveLength(1);
  expect(reprojection.revisions[0]!.claim.claim_lineage_id).toBe("lineage:ok");
  expect(reprojection.consumed_claim_revision_ids).toEqual(["claim:ok"]);
  expect(reprojection.remaining_live_claim_revision_ids).toEqual([]);
  expect(reprojection.adjacency.every((edge) => edge.entity_id === "entity:alice")).toBe(true);
});
