import { expect, test } from "bun:test";
import { authorizeIdentity } from "../resolve/identity-authority";
import { detectAliasCollisions, aliasFrontierGeneration, resolvedPropositionKey } from "./predicate-frontier";
import { scanContradictions } from "./contradiction";
import { groundedExtractionInvariantPrefix, groundedPrompt } from "../extract/grounded";

test("S5c preserves raw history and exposes an alias collision as a proposal", () => {
  const edges = [{ from_predicate_id: "p:old", to_predicate_id: "p:new" }];
  const frontier = { generation: aliasFrontierGeneration(edges), edges };
  const a = resolvedPropositionKey({ predicate_id: "p:old", slots: [] }, frontier);
  const b = resolvedPropositionKey({ predicate_id: "p:new", slots: [] }, frontier);
  expect(detectAliasCollisions([{ raw_key: "raw:a", resolved_key: a }, { raw_key: "raw:b", resolved_key: b }])).toEqual([{ raw_keys: ["raw:a", "raw:b"], resolved_key: a }]);
});

test("S5d grounding-suggested support never corroborates an identity authorization", () => {
  const endpoint = { kind: "entity" as const, entity_id: "entity:a" };
  const authorization = { authorization_id: "auth", owner_account_id: "owner", endpoints: [endpoint, { kind: "entity" as const, entity_id: "entity:b" }] as const, relation: "same" as const, support: { kind: "consolidation_adjudication" as const, support_refs: ["support:a", "support:b"], proposal_lineage_ref: "proposal" }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: null, identity_domain: null, scope_ref: null }, authority_policy_version: "p", evaluated_frontier: 1, actor_provenance: { actor_ref: "dream", producer_ref: null }, lifecycle: "active" as const, superseded_by: null };
  const context = { owner_confirmations: [], producer_assertions: [], standing_policies: [], identity_support: [
    { support_ref: "support:a", owner_account_id: "owner", evidence_ref: "e:a", claim_revision_id: "c:a", source_independence_key: "capture:a", provenance_bearing: true, entity_link_support: "independent" as const },
    { support_ref: "support:b", owner_account_id: "owner", evidence_ref: "e:b", claim_revision_id: "c:b", source_independence_key: "capture:b", provenance_bearing: true, entity_link_support: "suggested" as const },
  ] };
  expect(authorizeIdentity(authorization, { owner_account_id: "owner", endpoints: authorization.endpoints, relation: "same", evaluated_frontier: 1 }, context)).toEqual({ authorized: false, reason: "non_independent_or_unprovenanced_support" });
});

test("S4b detects time-overlapping opposite polarity without a model", () => {
  expect(scanContradictions([
    { claim_revision_id: "a", entity_id: "entity", proposition_key_resolved: "p", polarity: "positive", valid_time: { start: "2026-01-01", end: "2026-02-01" } },
    { claim_revision_id: "b", entity_id: "entity", proposition_key_resolved: "p", polarity: "negative", valid_time: { start: "2026-01-15", end: "2026-03-01" } },
  ])).toHaveLength(1);
});

test("S6a holds its invariant prompt prefix byte-stable", () => {
  const context = { frontier: { graph_head: "g", policy_version: "p", predicate_alias_generation: "a", authorization_generation: "i", stm_generation: "s" }, entity_candidates: [], predicate_signatures: [], open_propositions: [] };
  const evidence = (excerpt: string) => [{ evidence_id: "e", event_revision_id: "event", source_unit_ref: null, range: { start: 0, end: excerpt.length }, excerpt, source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "t", policy_labels: [], source_independence_key: "t" }];
  expect(groundedPrompt(context, evidence("synthetic")).startsWith(groundedExtractionInvariantPrefix)).toBe(true);
  expect(groundedPrompt(context, evidence("other")).slice(0, groundedExtractionInvariantPrefix.length)).toBe(groundedExtractionInvariantPrefix);
});
