import { expect, test } from "bun:test";
import { project, walk, type GraphSnapshot, type SafeSubgraph } from "./index";
import type { RequestContext } from "./grant";

const lineage = (claim_revision_id: string, capture_session_id: string, event_time: string) => ({ claim_revision_id, evidence_id: `e:${claim_revision_id}`, event_revision_id: `event:${claim_revision_id}`, capture_session_id, event_time, range: { start: 0, end: 3 }, excerpt: claim_revision_id });

test("B1.4 walks deterministic, citable temporal paths across capture sessions", () => {
  const safe: SafeSubgraph = { owner_account_id: "owner", reader_account_id: "owner", claims: [], adjacency: [], evidence_lineage: [lineage("a", "a", "2026-01-01T09:00:00Z"), lineage("b", "b", "2026-01-02T09:00:00Z"), lineage("c", "c", "2026-01-03T09:00:00Z")] };
  const result = walk(safe, { anchor: "capture:a", max_hops: 3, relation_kinds: ["temporal-proximity"], result_cap: 10, temporal_proximity_window_ms: 48 * 60 * 60 * 1000 });
  expect(result.paths.map((path) => path.nodes)).toEqual([["capture:a", "capture:b"], ["capture:a", "capture:b", "capture:c"]]);
  expect(result.paths[1]!.hops.map((hop) => hop.relation_kind)).toEqual(["temporal-proximity", "temporal-proximity"]);
  expect(result.paths[1]!.hops.every((hop) => hop.temporal_window_ms === 172800000)).toBe(true);
  expect(result.edge_count).toBe(2);
});

const claim = (revision_id: string) => ({ revision_id, placement_status: "canonical" as const, claim: { claim_lineage_id: revision_id, claim_revision_id: revision_id, owner_account_id: "owner", predicate: "fact", arguments: [], temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant", valid_time: { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-01-01T00:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-01-01T00:00:00Z", end: "2026-01-01T00:00:00Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } } }, evidence_refs: [], policy_labels: [], source_language: "en", scope: { locality: "durable" as const, scope_ref: null }, lifecycle: "canonical" as const, canonical_claim_id: `canonical:${revision_id}`, source_provisional_revision_ids: [] } });

test("B1.4 returns a three-hop, three-session path with its relation and citable span at every hop", () => {
  const safe: SafeSubgraph = {
    owner_account_id: "owner", reader_account_id: "owner", claims: [claim("a"), claim("b"), claim("bridge"), claim("c")],
    adjacency: [{ claim_revision_id: "a", entity_id: "entity:x", role_slot_id: "subject" }, { claim_revision_id: "b", entity_id: "entity:x", role_slot_id: "subject" }, { claim_revision_id: "bridge", entity_id: "entity:y", role_slot_id: "subject" }, { claim_revision_id: "c", entity_id: "entity:y", role_slot_id: "subject" }],
    evidence_lineage: [lineage("a", "session:one", "2026-01-01T00:00:00Z"), lineage("b", "session:two", "2026-01-02T00:00:00Z"), lineage("bridge", "session:two", "2026-01-02T00:00:00Z"), lineage("c", "session:three", "2026-01-03T00:00:00Z")],
  };
  const path = walk(safe, { anchor: "claim:a", max_hops: 3, relation_kinds: ["entity-shared", "source-shared"], result_cap: 100 }).paths.find((candidate) => candidate.nodes.join("|") === "claim:a|claim:b|claim:bridge|claim:c");
  expect(path?.hops.map((hop) => hop.relation_kind)).toEqual(["entity-shared", "source-shared", "entity-shared"]);
  expect(path?.hops.every((hop) => hop.evidence_span !== null)).toBe(true);
});

// The D46 property is about a claim the READER may not see, so the two inputs
// must differ by exactly that claim and must reach `walk` through `project`.
// The previous version of this test overwrote the only differing field before
// calling walk, so both calls received deep-equal input to a pure function and
// `walk = () => ({paths:[],node_count:0,edge_count:0})` would have passed it.
const labelled = (id: string, sensitivity: string) => ({ ...claim(id), claim: { ...claim(id).claim, policy_labels: ["subject:generic", `sensitivity:${sensitivity}`, "capture:generic"] } });
const genericGrant = { grant_id: "generic", policy_classes: [{ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }] };
const walkRequest = { anchor: "claim:a", max_hops: 3, relation_kinds: ["entity-shared"] as const, result_cap: 100 };

test("D46 a policy-excluded claim changes neither paths nor node/edge counts for the reader who cannot see it", () => {
  const reader: RequestContext = { reader_account_id: "reader", grant: genericGrant };
  const owner: RequestContext = { reader_account_id: "owner", grant: genericGrant };
  const shared = (revision_id: string) => ({ claim_revision_id: revision_id, entity_id: "entity:x", role_slot_id: "subject" });
  const withPrivate: GraphSnapshot = { owner_account_id: "owner", entities: [], evidence: [], events: [],
    claims: [labelled("a", "generic"), labelled("b", "generic"), labelled("private", "private")],
    adjacency: [shared("a"), shared("b"), shared("private")] };
  const withoutPrivate: GraphSnapshot = { ...withPrivate, claims: withPrivate.claims.slice(0, 2), adjacency: withPrivate.adjacency.slice(0, 2) };

  expect(walk(project(withPrivate, reader), walkRequest)).toEqual(walk(project(withoutPrivate, reader), walkRequest));

  // The excluded claim is not inert -- it really does change a walk for someone
  // authorized to see it -- so the equality above is a boundary, not a no-op.
  const ownerWalk = walk(project(withPrivate, owner), walkRequest);
  expect(ownerWalk).not.toEqual(walk(project(withoutPrivate, owner), walkRequest));
  expect(ownerWalk.node_count).toBeGreaterThan(walk(project(withPrivate, reader), walkRequest).node_count);
  expect(ownerWalk.edge_count).toBeGreaterThan(walk(project(withPrivate, reader), walkRequest).edge_count);
  expect(ownerWalk.paths.some((path) => path.nodes.includes("claim:private"))).toBe(true);
  expect(walk(project(withPrivate, reader), walkRequest).paths.some((path) => path.nodes.includes("claim:private"))).toBe(false);
});
