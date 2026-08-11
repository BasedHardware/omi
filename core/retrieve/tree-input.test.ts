import { expect, test } from "bun:test";
import { isLive, liveCommittedClaims, project, projectTreeInputSnapshot, type D35LivenessCauses, type GraphSnapshot, type PolicyClassifier } from "./index";

const entity = (id: string, handle = id) => ({ entity_id: id, owner_account_id: "owner", entity_revision_id: `${id}:r1`, handle, labels: [] });
const claim = (revision: string, lineage: string, subject = "entity:old", labels: string[] = []) => ({
  claim_lineage_id: lineage, claim_revision_id: revision, owner_account_id: "owner", predicate: "knows",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref" as const, ref: subject } }],
  temporal_scope: { observed_at: "2026-05-02T10:00:00Z", precision: "instant", valid_time: { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-05-02T10:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-05-02T10:00:00.000Z", end: "2026-05-02T10:00:00.000Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "g0-v1", timezone: "UTC" } } }, evidence_refs: ["e1"], policy_labels: labels,
  source_language: "en", scope: { locality: "durable" as const, scope_ref: subject }, lifecycle: "canonical" as const,
  canonical_claim_id: `canonical:${lineage}`, source_provisional_revision_ids: [],
});
const graph = (): GraphSnapshot => ({
  owner_account_id: "owner",
  graph_generation: 1,
  claims: [
    { revision_id: "old", commit_sequence: 1, placement_status: "canonical", claim: claim("old", "lineage:one") },
    { revision_id: "survivor", commit_sequence: 2, placement_status: "canonical", claim: claim("survivor", "lineage:one") },
  ],
  entities: [{ revision_id: "old:r1", entity: entity("entity:old", "zeta") }, { revision_id: "new:r1", entity: entity("entity:new", "alpha") }],
  identity_constraints: [{ revision_id: "merge:r1", constraint: { constraint_id: "merge", owner_account_id: "owner", endpoints: [{ kind: "entity", entity_id: "entity:old" }, { kind: "entity", entity_id: "entity:new" }], left_handle: "legacy:zeta", right_handle: "legacy:alpha", relation: "same", evidence_refs: ["e1"], identity_authorization: { authorization_id: "auth:merge", owner_account_id: "owner", endpoints: [{ kind: "entity", entity_id: "entity:old" }, { kind: "entity", entity_id: "entity:new" }], relation: "same", support: { kind: "owner_confirmation", confirmation_ref: "confirm:merge" }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: null, identity_domain: null, scope_ref: null }, authority_policy_version: "identity-policy:v1", evaluated_frontier: 1, actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active", superseded_by: null }, effective_at: 1, reversed_at: null } }],
  events: [{ revision_id: "event:r1", event: { event_id: "event", event_revision_id: "event:r1", owner_account_id: "owner", capture_session_id: "capture:1", stream_id: "stream:1", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-05-02", ingest_time: "2026-05-02", source_sequence: 0, evidence_addressable_refs: ["e1"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "hash" } }],
  evidence: [{ revision_id: "e1:r1", evidence: { evidence_id: "e1", event_revision_id: "event:r1", source_unit_ref: "unit", range: { start: 0, end: 8 }, excerpt: "supported", source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state: "active", source_trust: "test", policy_labels: [], source_independence_key: "capture:1" } }],
  adjacency: [],
});

test("R0 projects only one live supersession member and binds roles to the merge survivor", () => {
  const result = projectTreeInputSnapshot(graph(), { account_timezone: "America/New_York" });
  expect(result.claims.map((item) => item.claim_revision_id)).toEqual(["survivor"]);
  expect(result.claims[0]!.arguments[0]!.value).toEqual({ kind: "entity_ref", ref: "entity:new" });
  expect(result.claims[0]!.evidence_spans).toEqual([expect.objectContaining({ capture_session_id: "capture:1", excerpt: "supported" })]);
});

test("D35 builds private evidence and fence indexes once per live selection", () => {
  const input = graph();
  let evidenceIterations = 0;
  input.evidence = new Proxy(input.evidence!, {
    get(target, property, receiver) {
      if (property === Symbol.iterator) evidenceIterations++;
      return Reflect.get(target, property, receiver);
    },
  });
  expect(liveCommittedClaims(input).map((item) => item.revision_id)).toEqual(["survivor"]);
  expect(evidenceIterations).toBe(1);
});

test("D35 public liveness cannot be changed by caller-supplied derived indexes", () => {
  const item = graph().claims[1]!;
  const forged = {
    evidence: graph().evidence!.map((revision) => ({ ...revision, evidence: { ...revision.evidence, state: "tombstoned" as const } })),
    purged_claim_revision_ids: [],
    forgotten_claim_revision_ids: [],
    lineage_members: [item],
    evidence_by_id: new Map([["e1", graph().evidence![0]!.evidence]]),
    purged_set: new Set<string>(),
    forgotten_set: new Set<string>(),
  } as D35LivenessCauses & Record<string, unknown>;
  expect(isLive(item, forged)).toBe(false);
});

test("R0 preserves persisted imprecision and classifier changes create a new generation", () => {
  const one = projectTreeInputSnapshot(graph(), { account_timezone: "America/New_York" });
  expect(one.claims[0]!.valid_time?.resolved_interval.kind).toBe("instant");
  const changed: PolicyClassifier = { version: "policy-classifier-v2", classify: () => ({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }) };
  const two = projectTreeInputSnapshot(graph(), { account_timezone: "America/New_York", classifier: changed });
  expect(two.graph_generation).not.toBe(one.graph_generation);
});

test("R0 chooses later commit sequence over lexicographic revision IDs and reports broken evidence chains", () => {
  const input = graph();
  input.claims = [
    { revision_id: "r10", commit_sequence: 4, placement_status: "canonical", claim: claim("r10", "lineage:one") },
    { revision_id: "r2", commit_sequence: 5, placement_status: "canonical", claim: claim("r2", "lineage:one") },
  ];
  input.claims[1]!.claim.evidence_refs = ["e1", "missing-evidence"];
  input.claims[1]!.claim.temporal_scope.valid_time = { typed_expression: { kind: "absolute", granularity: "instant", value: "2026-05-03T00:00:00Z" }, resolved_interval: { kind: "instant", start: "2026-05-03T00:00:00.000Z", end: "2026-05-03T00:00:00.000Z", timezone: "UTC", granularity: "instant" }, derivation: { resolver_version: "g0-v1", timezone: "UTC" } };
  const projected = projectTreeInputSnapshot(input, { account_timezone: "UTC" });
  expect(projected.claims.map((item) => item.claim_revision_id)).toEqual(["r2"]);
  expect(projected.claims[0]!.valid_time?.resolved_interval).toMatchObject({ start: "2026-05-03T00:00:00.000Z" });
  expect(projected.diagnostics).toEqual([expect.objectContaining({ kind: "missing_evidence", claim_revision_id: "r2", evidence_ref: "missing-evidence" })]);
  expect(input.claims[1]!.claim.temporal_scope.valid_time).toBeDefined();
  const explicit = graph();
  explicit.claims = [
    { revision_id: "r10", commit_sequence: 99, placement_status: "canonical", claim: claim("r10", "lineage:one") },
    { revision_id: "r2", commit_sequence: 1, placement_status: "canonical", claim: { ...claim("r2", "lineage:one"), source_provisional_revision_ids: ["r10"] } },
  ];
  expect(projectTreeInputSnapshot(explicit, { account_timezone: "UTC" }).claims.map((item) => item.claim_revision_id)).toEqual(["r2"]);
});

test("R0 missing multi-revision commit sequences diagnose and use an order-independent winner", () => {
  const unordered = (revisions: readonly string[]): GraphSnapshot => ({ ...graph(), claims: revisions.map((revision) => ({ revision_id: revision, placement_status: "canonical" as const, claim: claim(revision, "lineage:one") })) });
  const forward = projectTreeInputSnapshot(unordered(["r10", "r2"]), { account_timezone: "UTC" });
  const reversed = projectTreeInputSnapshot(unordered(["r2", "r10"]), { account_timezone: "UTC" });
  expect(forward.claims.map((item) => item.claim_revision_id)).toEqual(reversed.claims.map((item) => item.claim_revision_id));
  expect(forward.diagnostics).toEqual(reversed.diagnostics);
  expect(forward.diagnostics).toContainEqual(expect.objectContaining({ kind: "missing_commit_sequence", claim_lineage_id: "lineage:one", claim_revision_ids: ["r10", "r2"] }));

  const withEdge = (revisions: readonly string[]): GraphSnapshot => ({ ...graph(), claims: revisions.map((revision) => ({ revision_id: revision, commit_sequence: revision === "r10" ? 99 : 1, placement_status: "canonical" as const, claim: revision === "r2" ? { ...claim("r2", "lineage:one"), supersedes_revision_ids: ["r10"] } : claim("r10", "lineage:one") })) });
  // Counterexample: r10 has the larger sequence, but r2's canonical edge must win in either order.
  expect(projectTreeInputSnapshot(withEdge(["r10", "r2"]), { account_timezone: "UTC" }).claims.map((item) => item.claim_revision_id)).toEqual(["r2"]);
  expect(projectTreeInputSnapshot(withEdge(["r2", "r10"]), { account_timezone: "UTC" }).claims.map((item) => item.claim_revision_id)).toEqual(["r2"]);
});

test("R0 diagnoses evidence that exists but has no Event-to-Capture lineage", () => {
  const input = graph();
  input.events = [];
  const projected = projectTreeInputSnapshot(input, { account_timezone: "UTC" });
  expect(projected.claims[0]!.evidence_spans).toEqual([]);
  expect(projected.diagnostics).toContainEqual(expect.objectContaining({ kind: "missing_event", evidence_ref: "e1" }));
});

test("D47 P0: rendering equality never merges projection; authorized same is frontier-reversible", () => {
  const noAuthorization = graph();
  noAuthorization.claims = [
    { revision_id: "left", placement_status: "canonical", claim: claim("left", "lineage:left", "entity:old") },
    { revision_id: "right", placement_status: "canonical", claim: claim("right", "lineage:right", "entity:new") },
  ];
  noAuthorization.adjacency = [{ claim_revision_id: "left", entity_id: "entity:old", role_slot_id: "subject" }, { claim_revision_id: "right", entity_id: "entity:new", role_slot_id: "subject" }];
  noAuthorization.identity_constraints = [{ ...noAuthorization.identity_constraints![0]!, constraint: { ...noAuthorization.identity_constraints![0]!.constraint, identity_authorization: undefined } }];
  // Different renderings stay distinct through both argument and adjacency projection.
  const unmerged = project(noAuthorization, { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } });
  expect(projectTreeInputSnapshot(noAuthorization, { account_timezone: "UTC" }).claims.map((item) => item.arguments[0]!.value)).toEqual([{ kind: "entity_ref", ref: "entity:old" }, { kind: "entity_ref", ref: "entity:new" }]);
  expect(unmerged.adjacency.map((edge) => edge.entity_id)).toEqual(["entity:old", "entity:new"]);

  // Exact duplicate handles fail closed rather than selecting a lexical survivor.
  const duplicateHandle = { ...noAuthorization, entities: noAuthorization.entities.map((item) => ({ ...item, entity: { ...item.entity, handle: "speaker" } })) };
  expect(() => projectTreeInputSnapshot(duplicateHandle, { account_timezone: "UTC" })).toThrow("duplicate entity handle without authorized identity merge");

  const authorized = graph();
  authorized.claims = noAuthorization.claims;
  authorized.adjacency = noAuthorization.adjacency;
  const merged = projectTreeInputSnapshot(authorized, { account_timezone: "UTC" });
  expect(merged.claims.map((item) => item.arguments[0]!.value)).toEqual([{ kind: "entity_ref", ref: "entity:new" }, { kind: "entity_ref", ref: "entity:new" }]);
  expect(project(authorized, { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } }).adjacency.map((edge) => edge.entity_id)).toEqual(["entity:new", "entity:new"]);

  const reversed = { ...authorized, graph_generation: 2, identity_constraints: [{ ...authorized.identity_constraints![0]!, constraint: { ...authorized.identity_constraints![0]!.constraint, reversed_at: 2 } }] };
  expect(projectTreeInputSnapshot(reversed, { account_timezone: "UTC" }).claims.map((item) => item.arguments[0]!.value)).toEqual([{ kind: "entity_ref", ref: "entity:old" }, { kind: "entity_ref", ref: "entity:new" }]);
});
