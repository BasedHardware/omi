import { expect, test } from "bun:test";
import { BatchValidationError, validateAndAllocatePlacement, type PlacementBatch } from "./plan";

const batch = (results: PlacementBatch["results"]): PlacementBatch => ({
  batch_id: "batch-1",
  leased_inputs: [
    { provisional_revision_id: "p-coffee", entity_id: "entity:owner", proposition_key: "preference:coffee", review_attempt: 0, max_review_attempts: 2 },
    { provisional_revision_id: "p-tea", entity_id: "entity:owner", proposition_key: "preference:tea", review_attempt: 0, max_review_attempts: 2 },
  ],
  snapshot: [{ canonical_claim_id: "c-coffee", proposition_key: "preference:coffee" }], results,
});

test("T7 labels identity linkage, consolidation, and justified synthesis separately", () => {
  const plan = validateAndAllocatePlacement(batch([
    { input_provisional_revision_id: "p-coffee", disposition: "reinforce", operation: { kind: "consolidation", canonical_claim_id: "c-coffee", proposition_key: "preference:coffee" } },
    { input_provisional_revision_id: "p-tea", disposition: "admit", operation: { kind: "identity_linkage", entity_id: "entity:owner" } },
  ]));
  expect(plan.offline_experiment).toBe(true);
  expect(plan.allocations["p-tea"]).toStartWith("canonical:");
});

test("T7 rejects an unrelated same-entity claim instead of merging propositions", () => {
  expect(() => validateAndAllocatePlacement(batch([
    { input_provisional_revision_id: "p-coffee", disposition: "reinforce", operation: { kind: "consolidation", canonical_claim_id: "c-coffee", proposition_key: "preference:coffee" } },
    { input_provisional_revision_id: "p-tea", disposition: "reinforce", operation: { kind: "consolidation", canonical_claim_id: "c-coffee", proposition_key: "preference:coffee" } },
  ]))).toThrow(BatchValidationError);
});

test("T7 exact partition and references reject a whole offline batch before ID allocation", () => {
  expect(() => validateAndAllocatePlacement(batch([
    { input_provisional_revision_id: "p-coffee", disposition: "admit", operation: null },
    { input_provisional_revision_id: "p-tea", disposition: "reinforce", operation: { kind: "consolidation", canonical_claim_id: "missing", proposition_key: "preference:tea" } },
  ]))).toThrow("unknown canonical reference: missing");
  expect(() => validateAndAllocatePlacement(batch([
    { input_provisional_revision_id: "p-coffee", disposition: "defer_review", operation: null, re_resolution_trigger: "new_identity_evidence" },
  ]))).toThrow("exact partition count mismatch");
});

test("T7 defer_review is bounded and carries a re-resolution trigger", () => {
  const reviewed = batch([
    { input_provisional_revision_id: "p-coffee", disposition: "defer_review", operation: null, re_resolution_trigger: "new_identity_evidence" },
    { input_provisional_revision_id: "p-tea", disposition: "reject", operation: null },
  ]);
  expect(validateAndAllocatePlacement(reviewed).results[0]!.disposition).toBe("defer_review");
  const exhausted = { ...reviewed, leased_inputs: [{ ...reviewed.leased_inputs[0]!, review_attempt: 2 }, reviewed.leased_inputs[1]!] };
  expect(() => validateAndAllocatePlacement(exhausted)).toThrow("unbounded or triggerless defer_review: p-coffee");
});

test("B1.3 rejects consolidation across alias-frontier generations", () => {
  const source = batch([
    { input_provisional_revision_id: "p-coffee", disposition: "reinforce", operation: { kind: "consolidation", canonical_claim_id: "c-coffee", proposition_key: "resolved:coffee" } },
    { input_provisional_revision_id: "p-tea", disposition: "reject", operation: null },
  ]);
  const input = { ...source, leased_inputs: [{ ...source.leased_inputs[0]!, proposition_key_resolved: "resolved:coffee", alias_frontier_generation: "frontier:new" }, source.leased_inputs[1]!], snapshot: [{ ...source.snapshot[0]!, proposition_key_resolved: "resolved:coffee", alias_frontier_generation: "frontier:old" }] };
  expect(() => validateAndAllocatePlacement(input)).toThrow("frontier mismatch consolidation: p-coffee");
});
