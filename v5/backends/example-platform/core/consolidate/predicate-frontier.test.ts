import { expect, test } from "bun:test";
import { predicateAliasFrontier, rawPropositionKey, resolveClaimProposition } from "./predicate-frontier";

const claim = {
  claim_lineage_id: "lineage", claim_revision_id: "revision", owner_account_id: "owner", predicate_id: "predicate:travel", predicate: "travelled-from",
  arguments: [{ slot_id: "traveler", role: "traveler", value: { kind: "source_local_ref" as const, ref: "speaker" } }], polarity: "positive" as const,
  temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: [], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: null,
};

test("B1.2/B1.3 resolves a persisted vocabulary alias without changing the raw historical proposition", () => {
  const assertion = { assertion_id: "alias:1", owner_account_id: "owner", predicate_id: "predicate:travel", relation: "alias_of" as const, target_predicate_id: "predicate:origin", slot_aliases: [{ from_slot_id: "traveler", to_slot_id: "person" }], alias_frontier: "declared-frontier", admission: "accepted" as const, lifecycle: "active" as const, supersedes_assertion_id: null };
  const empty = predicateAliasFrontier([]);
  const aliased = predicateAliasFrontier([assertion]);
  const before = resolveClaimProposition(claim, empty);
  const after = resolveClaimProposition(before, aliased);
  expect(after.proposition_key_raw).toBe(rawPropositionKey({ predicate_id: "predicate:travel", slots: [{ slot_id: "traveler", value_key: "source_local_ref:speaker" }] }));
  expect(after.proposition_key_raw).toBe(before.proposition_key_raw);
  expect(after.proposition_key_resolved).not.toBe(before.proposition_key_resolved);
  expect(after.predicate_alias_frontier).toBe(aliased.generation);
  expect(predicateAliasFrontier([{ ...assertion, assertion_id: "proposal", admission: "proposal" }]).edges).toEqual([]);
});
