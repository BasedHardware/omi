import { expect, test } from "bun:test";
import { canonicalizeRedacted, prepareDerivation, sha256CanonicalRedacted, validateAtomicGraphTransition, type AtomicGraphTransition } from "./index";

const versions = { strategy_version: "placement-v1", model_version: "none", prompt_version: "none", policy_version: "p1", code_version: "c1", schema_version: "s1", tokenizer_version: "none", tool_version: "none" };

test("T9 canonical hashing sorts keys, preserves array order, and redacts fixed raw fields", () => {
  expect(canonicalizeRedacted({ z: 1, a: ["first", "second"], token: "not-hashed" })).toBe('{"a":["first","second"],"token":"[REDACTED]","z":1}');
  expect(sha256CanonicalRedacted({ b: 2, a: 1 })).toBe(sha256CanonicalRedacted({ a: 1, b: 2 }));
  expect(sha256CanonicalRedacted(["first", "second"])).not.toBe(sha256CanonicalRedacted(["second", "first"]));
});

test("T9 ledger records ordered digests and a successful-empty outcome", () => {
  const prepared = prepareDerivation({ attempt_id: "attempt-empty", commit_id: "commit-empty", owner_account_id: "owner-1", parent_commit: null, idempotency_key: "empty-key", input_revisions: [{ revision_id: "p-1", content: { value: 1 } }], output_revisions: [], versions, success_kind: "successful_empty" });
  expect(prepared.commit).toMatchObject({
    success_kind: "successful_empty",
    input_revision_ids: ["p-1"],
    input_revisions: [{ revision_id: "p-1", content: { value: 1 } }],
    output_revision_ids: [],
    sequence: null,
  });
  expect(prepared.commit.input_revisions[0]?.content_hash).toBe(
    sha256CanonicalRedacted({ value: 1 }),
  );
  expect(prepared.commit.input_version_digest).not.toBe(prepared.commit.input_digest);
});

const canonicalClaim = (arguments_: readonly { slot_id: string; role: string; value: { kind: "entity_ref"; ref: string } }[]) => ({
  claim_lineage_id: "lineage:claim", claim_revision_id: "canonical:claim", owner_account_id: "owner",
  predicate: "met", arguments: arguments_, temporal_scope: {
    observed_at: "2026-01-01T00:00:00Z", precision: "instant",
    valid_time: { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-01-01T00:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-01-01T00:00:00.000Z", end: "2026-01-01T00:00:00.000Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } },
  }, evidence_refs: [], policy_labels: [], source_language: "en", scope: { locality: "durable" as const, scope_ref: null },
  lifecycle: "canonical" as const, canonical_claim_id: "canonical:claim", source_provisional_revision_ids: [],
});

const ledgerValidationTransition = (claim: ReturnType<typeof canonicalClaim>): AtomicGraphTransition => ({
  placement: { offline_experiment: true, allocations: {}, results: [] },
  derivation: prepareDerivation({ attempt_id: "attempt:claim-validation", commit_id: "commit:claim-validation", owner_account_id: "owner", parent_commit: null, idempotency_key: "claim-validation", input_revisions: [], output_revisions: [{ revision_id: claim.claim_revision_id, content: claim }], versions, success_kind: "success" }),
  revisions: [{ kind: "claim", revision_id: claim.claim_revision_id, claim, placement_status: "canonical" }],
  adjacency: [{ claim_revision_id: claim.claim_revision_id, entity_id: claim.arguments[0]!.value.ref, role_slot_id: claim.arguments[0]!.slot_id }], artifacts: [],
});

test("A2 ledger canonical validation rejects duplicate slots and unauthorised durable role bindings", () => {
  const duplicateSlots = canonicalClaim([
    { slot_id: "party", role: "subject", value: { kind: "entity_ref", ref: "entity:alice" } },
    { slot_id: "party", role: "object", value: { kind: "entity_ref", ref: "entity:bob" } },
  ]);
  expect(() => validateAtomicGraphTransition(ledgerValidationTransition(duplicateSlots))).toThrow("invalid canonical claim");

  const nary = canonicalClaim([
    { slot_id: "subject", role: "subject", value: { kind: "entity_ref", ref: "entity:alice" } },
    { slot_id: "object", role: "object", value: { kind: "entity_ref", ref: "entity:bob" } },
    { slot_id: "place", role: "place", value: { kind: "entity_ref", ref: "entity:paris" } },
  ]);
  expect(() => validateAtomicGraphTransition(ledgerValidationTransition(nary))).toThrow("durable role binding lacks typed mention lineage");
});

test("S5a source-local roles do not require or satisfy durable adjacency", () => {
  const claim = canonicalClaim([{ slot_id: "subject", role: "subject", value: { kind: "source_local_ref", ref: "capture:synthetic:subject" } } as never]);
  const transition = ledgerValidationTransition(claim as never);
  transition.adjacency = [];
  expect(() => validateAtomicGraphTransition(transition)).not.toThrow();
});

test("D35 liveness fences require unique owner-local claim witnesses", () => {
  const claim = canonicalClaim([{ slot_id: "subject", role: "subject", value: { kind: "source_local_ref", ref: "capture:synthetic:subject" } } as never]);
  const transition = ledgerValidationTransition(claim as never);
  transition.adjacency = [];
  transition.liveness_fences = [{ claim_revision_id: claim.claim_revision_id, cause: "purged" }];
  expect(() => validateAtomicGraphTransition(transition)).not.toThrow();

  transition.liveness_fences = [
    { claim_revision_id: claim.claim_revision_id, cause: "purged" },
    { claim_revision_id: claim.claim_revision_id, cause: "purged" },
  ];
  expect(() => validateAtomicGraphTransition(transition)).toThrow("duplicate claim liveness fence");

  transition.liveness_fences = [{ claim_revision_id: "claim:missing", cause: "forgotten" }];
  expect(() => validateAtomicGraphTransition(transition)).toThrow("lacks an owner-local claim witness");
});
