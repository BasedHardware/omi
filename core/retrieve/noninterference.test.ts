import { expect, test } from "bun:test";
import { genericPolicyClassifier, project, projectTreeInputSnapshot, readerVisibleSubgraph, retrieveCommittedGraph, type GraphSnapshot, type ReaderVisibleAbsence } from "./index";
import type { RequestContext } from "./grant";

const labels = (sensitivity: string, extra: readonly string[] = []) => [`subject:generic`, `sensitivity:${sensitivity}`, "capture:generic", ...extra];
const claim = (id: string, policyLabels: readonly string[], lineage = `lineage:${id}`, evidence_refs: readonly string[] = []) => ({
  revision_id: id, placement_status: "canonical" as const, claim: { claim_lineage_id: lineage, claim_revision_id: id, owner_account_id: "owner", predicate: "met", arguments: [], temporal_scope: { observed_at: "2026-01-01", precision: "day" }, evidence_refs, policy_labels: policyLabels, source_language: "en", scope: { locality: "durable" as const, scope_ref: null }, lifecycle: "canonical" as const, canonical_claim_id: `canonical:${id}`, source_provisional_revision_ids: [] },
});
const evidence = (id: string, state: "active" | "tombstoned") => ({ revision_id: `${id}:r1`, evidence: { evidence_id: id, event_revision_id: "event:unused", source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: null, source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state, source_trust: "test", policy_labels: [], source_independence_key: id } });
const without = (graph: GraphSnapshot, revisionIds: readonly string[]): GraphSnapshot => ({ ...graph, claims: graph.claims.filter((item) => !revisionIds.includes(item.revision_id)), adjacency: graph.adjacency.filter((edge) => !revisionIds.includes(edge.claim_revision_id)) });
const bytes = (graph: GraphSnapshot, ctx: RequestContext): string => JSON.stringify(readerVisibleSubgraph(project(graph, ctx)));
const genericGrant = { grant_id: "generic", policy_classes: [{ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }] };
const owner: RequestContext = { reader_account_id: "owner", grant: genericGrant };
const reader: RequestContext = { reader_account_id: "reader", grant: genericGrant };

test("G2/G3 adversarial D35: a tombstoned last citation and a purge fence leave zero owner-visible trace, while active evidence restores the claim", () => {
  const retracted = claim("retracted", labels("generic"), "lineage:retracted", ["e:retracted"]);
  const purged = claim("purged", labels("generic"));
  const graph: GraphSnapshot = { owner_account_id: "owner", claims: [retracted, purged], entities: [], evidence: [evidence("e:retracted", "tombstoned")], liveness_causes: { purged_claim_revision_ids: ["purged"], forgotten_claim_revision_ids: [] }, adjacency: [{ claim_revision_id: "retracted", entity_id: "entity:hidden", role_slot_id: "subject" }, { claim_revision_id: "purged", entity_id: "entity:hidden", role_slot_id: "subject" }] };
  const removed = without(graph, ["retracted", "purged"]);
  expect(bytes(graph, owner)).toBe(bytes(removed, owner));
  expect(readerVisibleSubgraph(project(graph, owner))).toEqual({ claims: [], adjacency: [], absence: { kind: "query_gap", message: "no cited memory matched" } });
  // The same predicate is exercised by index/tree eligibility and B5 retrieval.
  expect(projectTreeInputSnapshot(graph, { account_timezone: "UTC" }).claims).toEqual([]);
  expect(retrieveCommittedGraph(graph, { owner_account_id: "owner", kind: "as_of", date: "2026-01-02" }).claims).toEqual([]);

  const restored: GraphSnapshot = { ...graph, claims: [retracted], adjacency: [graph.adjacency[0]!], liveness_causes: { purged_claim_revision_ids: [], forgotten_claim_revision_ids: [] }, evidence: [evidence("e:retracted", "active")] };
  expect(project(restored, owner).claims.map((item) => item.revision_id)).toEqual(["retracted"]);
  expect(projectTreeInputSnapshot(restored, { account_timezone: "UTC" }).claims.map((item) => item.claim_revision_id)).toEqual(["retracted"]);
  expect(retrieveCommittedGraph(restored, { owner_account_id: "owner", kind: "as_of", date: "2026-01-02" }).claims.map((item) => item.revision_id)).toEqual(["retracted"]);
});

test("G2 adversarial policy join: mixed generic/private labels classify as private and cannot leak through a generic grant", () => {
  const mixed = claim("mixed", labels("generic", ["sensitivity:private"]));
  const graph: GraphSnapshot = { owner_account_id: "owner", claims: [mixed], entities: [], adjacency: [{ claim_revision_id: "mixed", entity_id: "entity:hidden", role_slot_id: "subject" }] };
  expect(genericPolicyClassifier.classify(mixed.claim, [])).toEqual({ subject_class: "generic", sensitivity: "private", capture_class: "generic" });
  expect(project(graph, reader).claims).toEqual([]);
  expect(bytes(graph, reader)).toBe(bytes(without(graph, ["mixed"]), reader));
});

test("G3 adversarial reader-relative liveness: an out-of-grant private head cannot hide the old generic member", () => {
  const first = claim("a-visible", labels("generic"));
  const old = claim("old-generic", labels("generic"), "lineage:shared");
  const hidden = { ...claim("new-private", labels("private"), "lineage:shared"), commit_sequence: 2, claim: { ...claim("new-private", labels("private"), "lineage:shared").claim, supersedes_revision_ids: ["old-generic"] } };
  const graph: GraphSnapshot = { owner_account_id: "owner", claims: [{ ...first, commit_sequence: 1 }, { ...old, commit_sequence: 1 }, hidden], entities: [], adjacency: [{ claim_revision_id: "a-visible", entity_id: "entity:visible", role_slot_id: "subject" }, { claim_revision_id: "old-generic", entity_id: "entity:visible", role_slot_id: "subject" }, { claim_revision_id: "new-private", entity_id: "entity:visible", role_slot_id: "subject" }] };
  const withoutHidden = without(graph, ["new-private"]);
  expect(bytes(graph, reader)).toBe(bytes(withoutHidden, reader));
  expect(project(graph, reader).claims.map((item) => item.revision_id)).toEqual(["a-visible", "old-generic"]);
  expect(projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: reader }).claims.map((item) => item.claim_revision_id)).toEqual(["a-visible", "old-generic"]);
  expect(retrieveCommittedGraph(graph, { owner_account_id: "owner", kind: "as_of", date: "2026-01-02", reader_context: reader }).claims.map((item) => item.revision_id)).toEqual(["a-visible", "old-generic"]);
  // Single-owner behavior is unchanged: the owner sees the actual private head.
  expect(project(graph, owner).claims.map((item) => item.revision_id)).toEqual(["a-visible", "new-private"]);
});

// Every value asserted here comes out of `readerVisibleSubgraph`. The previous
// version compared a test-local literal against a test-local array and never
// called the implementation at all, so it held for any implementation.
test("G3 reader-visible absence is produced by the projection and has exactly the two allowed classifications", () => {
  const omission: ReaderVisibleAbsence = { kind: "policy_omission", grant_class: "generic", message: "some matching memory is omitted by your grant class" };
  const empty: GraphSnapshot = { owner_account_id: "owner", claims: [], entities: [], adjacency: [] };
  const privateOnly: GraphSnapshot = { owner_account_id: "owner", claims: [claim("private", labels("private"))], entities: [], adjacency: [{ claim_revision_id: "private", entity_id: "entity:hidden", role_slot_id: "subject" }] };
  const visibleOnly: GraphSnapshot = { owner_account_id: "owner", claims: [claim("shown", labels("generic"))], entities: [], adjacency: [{ claim_revision_id: "shown", entity_id: "entity:shown", role_slot_id: "subject" }] };

  // No caller-supplied absence: the projection must still classify, and it must
  // classify a policy exclusion indistinguishably from having nothing to say.
  const gap = readerVisibleSubgraph(project(empty, reader)).absence;
  const hiddenByPolicy = readerVisibleSubgraph(project(privateOnly, reader)).absence;
  expect(gap).toEqual({ kind: "query_gap", message: "no cited memory matched" });
  expect(hiddenByPolicy).toEqual(gap);

  // A caller that knows the grant omitted something may say so, and nothing else
  // may appear: the two kinds below are the complete produced set.
  const declared = readerVisibleSubgraph(project(privateOnly, reader), omission).absence;
  expect(declared).toEqual(omission);
  // A non-empty projection reports no absence at all, so absence can never be a
  // count of what was withheld.
  expect(readerVisibleSubgraph(project(visibleOnly, reader), omission).absence).toBeNull();
  expect(new Set([gap!.kind, declared!.kind])).toEqual(new Set<ReaderVisibleAbsence["kind"]>(["query_gap", "policy_omission"]));
});
