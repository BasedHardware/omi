import { expect, test } from "bun:test";
import { project, projectTypedAdjacency, type GraphSnapshot, type SafeSubgraph } from "./index";

const valid = (year: string) => ({ typed_expression: { kind: "absolute" as const, granularity: "year" as const, value: year }, resolved_interval: { kind: "calendar_interval" as const, start: `${year}-01-01T00:00:00.000Z`, end: `${Number(year) + 1}-01-01T00:00:00.000Z`, timezone: "UTC", granularity: "year" as const }, derivation: { resolver_version: "g0-v1", timezone: "UTC" } });
const claim = (revision_id: string, year: string, evidence_ref: string, lineage: string, supersedes_revision_ids: readonly string[] = []) => ({
  revision_id, placement_status: "canonical" as const, claim: {
    claim_lineage_id: lineage, claim_revision_id: revision_id, owner_account_id: "owner", predicate: "fact",
    arguments: [], temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "year", valid_time: valid(year) }, evidence_refs: [evidence_ref], policy_labels: [], source_language: "en", scope: { locality: "durable" as const, scope_ref: null }, lifecycle: "canonical" as const, canonical_claim_id: `canonical:${revision_id}`, source_provisional_revision_ids: [], supersedes_revision_ids,
  },
});
const context = { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } };
const evidenceLineage = (id: string, capture = "capture:shared") => ({ claim_revision_id: id, evidence_id: `e-${id}`, event_revision_id: `event-${id}`, capture_session_id: capture });

test("G5 emits all four typed relations only from its already-live safe input", () => {
  // SafeSubgraph is the post-D46 boundary.
  const safe: SafeSubgraph = {
    owner_account_id: "owner", reader_account_id: "owner",
    claims: [claim("prior", "2020", "e-prior", "lineage:prior"), claim("next", "2020", "e-next", "lineage:next"), claim("disjoint", "2022", "e-disjoint", "lineage:other")],
    adjacency: [{ claim_revision_id: "prior", entity_id: "entity:shared", role_slot_id: "subject" }, { claim_revision_id: "next", entity_id: "entity:shared", role_slot_id: "subject" }, { claim_revision_id: "disjoint", entity_id: "entity:other", role_slot_id: "subject" }],
    evidence_lineage: [evidenceLineage("prior"), evidenceLineage("next"), evidenceLineage("disjoint", "capture:other")],
  };
  const edges = projectTypedAdjacency(safe).edges;
  expect(new Set(edges.map((edge) => edge.kind))).toEqual(new Set(["when-adjacent", "entity-shared", "evidence-lineage", "source-shared"]));
  expect(edges).toContainEqual({ kind: "when-adjacent", from: "claim:prior", to: "claim:next" });
  expect(edges).toContainEqual({ kind: "entity-shared", from: "claim:prior", to: "claim:next" });
  expect(edges).toContainEqual({ kind: "evidence-lineage", from: "claim:prior", to: "evidence:e-prior" });
  expect(edges).toContainEqual({ kind: "source-shared", from: "claim:prior", to: "claim:next" });
  expect(edges).not.toContainEqual({ kind: "when-adjacent", from: "claim:prior", to: "claim:disjoint" });
});

const coherentGraph = (includeOld: boolean): GraphSnapshot => ({
  owner_account_id: "owner",
  claims: [
    ...(includeOld ? [{ ...claim("old", "2020", "e-old", "lineage:L"), commit_sequence: 1 }] : []),
    { ...claim("new", "2020", "e-new", "lineage:L", ["old"]), commit_sequence: 2 },
  ],
  entities: [],
  events: ["old", "new"].map((id) => ({ revision_id: `event-${id}`, event: { event_id: `event-${id}`, event_revision_id: `event-${id}`, owner_account_id: "owner", capture_session_id: "capture", stream_id: "stream", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:00Z", ingest_time: "2026-01-01T00:00:00Z", source_sequence: 0, evidence_addressable_refs: [`e-${id}`], source_trust: "test", policy_labels: [], canonical_redacted_hash: `h-${id}` } })),
  evidence: ["old", "new"].map((id, sequence) => ({ revision_id: `e-${id}:r1`, commit_sequence: sequence + 1, evidence: { evidence_id: `e-${id}`, event_revision_id: `event-${id}`, source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: `fact ${id}`, source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: `capture:${id}` } })),
  adjacency: [
    ...(includeOld ? [{ claim_revision_id: "old", entity_id: "entity:shared", role_slot_id: "subject" }] : []),
    { claim_revision_id: "new", entity_id: "entity:shared", role_slot_id: "subject" },
  ],
});

test("G5 coherent shared-lineage supersession excludes the non-live old revision from all four relations and is byte-noninterfering", () => {
  const withOld = project(coherentGraph(true), context);
  expect(withOld.claims.map((item) => item.revision_id)).toEqual(["new"]);
  const adjacencyWithOld = projectTypedAdjacency(withOld);
  for (const kind of ["when-adjacent", "entity-shared", "evidence-lineage", "source-shared"] as const) {
    expect(adjacencyWithOld.edges.some((edge) => edge.kind === kind && (edge.from === "claim:old" || edge.to === "claim:old"))).toBe(false);
  }
  const adjacencyWithoutOld = projectTypedAdjacency(project(coherentGraph(false), context));
  expect(JSON.stringify(adjacencyWithOld)).toBe(JSON.stringify(adjacencyWithoutOld));
});

test("B1.1 chains consecutive capture watermarks inside its declared window instead of making a clique", () => {
  const safe: SafeSubgraph = {
    owner_account_id: "owner", reader_account_id: "owner", claims: [], adjacency: [],
    evidence_lineage: [
      { ...evidenceLineage("a", "capture:a"), event_time: "2026-01-01T09:00:00Z" },
      { ...evidenceLineage("b", "capture:b"), event_time: "2026-01-02T09:00:00Z" },
      { ...evidenceLineage("c", "capture:c"), event_time: "2026-01-03T09:00:00Z" },
      { ...evidenceLineage("far", "capture:far"), event_time: "2026-01-08T09:00:00Z" },
    ],
  };
  const proximity = projectTypedAdjacency(safe, { temporal_proximity_window_ms: 48 * 60 * 60 * 1000 }).edges.filter((edge) => edge.kind === "temporal-proximity");
  expect(proximity).toEqual([
    { kind: "temporal-proximity", from: "capture:capture:a", to: "capture:capture:b", temporal_window_ms: 172800000, identity_evidence: false },
    { kind: "temporal-proximity", from: "capture:capture:b", to: "capture:capture:c", temporal_window_ms: 172800000, identity_evidence: false },
  ]);
  expect(proximity).toHaveLength(2);
});
