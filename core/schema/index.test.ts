import { expect, test } from "bun:test";
import fc from "fast-check";
import { CanonicalClaimSchema, EnvelopeJsonSchemas2020, PredicateSchema, ProvisionalClaimSchema, isValidLifecycleTransition, transitionClaimLifecycle } from "./index";
import { validateStrict } from "./json";

const fixtureClaim = (predicate = "unknown.future/predicate") => ({
  claim_lineage_id: "lineage-1", claim_revision_id: "revision-1", owner_account_id: "owner-1",
  predicate, arguments: [{ slot_id: "subject-1", role: "subject", value: { kind: "entity_ref", ref: "local:alice" } }],
  temporal_scope: { observed_at: "2026-07-29T00:00:00Z", precision: "instant" }, evidence_refs: ["evidence-1"],
  policy_labels: [], source_language: "en", scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional",
  ambiguity_markers: [], context_packet: { version: "context-v1", referent_refs: [], topic_refs: [] },
});

test("T1 accepts unknown predicates and requires stable argument slots", () => {
  expect(Object.values(EnvelopeJsonSchemas2020).every((document) => document.$schema === "https://json-schema.org/draft/2020-12/schema")).toBe(true);
  expect(validateStrict(ProvisionalClaimSchema, fixtureClaim())).toBe(true);
  expect(validateStrict(ProvisionalClaimSchema, { ...fixtureClaim(), arguments: [{ role: "subject", value: { kind: "literal", value: "x" } }] })).toBe(false);
  expect(validateStrict(ProvisionalClaimSchema, { ...fixtureClaim(), arguments: [
    { slot_id: "party", role: "subject", value: { kind: "literal", value: "Alice" } },
    { slot_id: "party", role: "object", value: { kind: "literal", value: "Bob" } },
  ] })).toBe(false);
  // Native n-ary facts remain valid because each filler has its own slot.
  expect(validateStrict(ProvisionalClaimSchema, { ...fixtureClaim(), arguments: [
    { slot_id: "subject", role: "subject", value: { kind: "literal", value: "Alice" } },
    { slot_id: "object", role: "object", value: { kind: "literal", value: "Bob" } },
    { slot_id: "place", role: "place", value: { kind: "literal", value: "Paris" } },
  ] })).toBe(true);
});

test("S5a source-local argument is typed and remains distinct from entity identity", () => {
  const claim = fixtureClaim();
  claim.arguments = [{ slot_id: "speaker", role: "subject", value: { kind: "source_local_ref", ref: "capture:synthetic:speaker" } }];
  expect(validateStrict(ProvisionalClaimSchema, claim)).toBe(true);
});

test("T1 lifecycle kernel has only declared transitions", () => {
  expect(isValidLifecycleTransition("provisional", "canonical")).toBe(true);
  expect(transitionClaimLifecycle("canonical", "provisional")).toEqual({ error: "invalid lifecycle transition: canonical -> provisional" });
  fc.assert(fc.property(fc.constantFrom<"provisional" | "canonical" | "deferred" | "rejected">("provisional", "canonical", "deferred", "rejected"), fc.constantFrom<"provisional" | "canonical" | "deferred" | "rejected">("provisional", "canonical", "deferred", "rejected"), (from, to) => {
    const result = transitionClaimLifecycle(from, to);
    return "error" in result ? !isValidLifecycleTransition(from, to) : isValidLifecycleTransition(from, to);
  }));
});

test("T1 canonical claims carry explicit revision supersession edges", () => {
  const canonical = { ...fixtureClaim(), temporal_scope: { observed_at: "2026-07-29T00:00:00Z", precision: "instant", valid_time: { typed_expression: { kind: "absolute", granularity: "instant", value: "2026-07-29T00:00:00Z" }, resolved_interval: { kind: "instant", start: "2026-07-29T00:00:00.000Z", end: "2026-07-29T00:00:00.000Z", timezone: "UTC", granularity: "instant" }, derivation: { resolver_version: "g0-v1", timezone: "UTC" } } }, lifecycle: "canonical", canonical_claim_id: "canonical-1", source_provisional_revision_ids: [], supersedes_revision_ids: ["revision-0"] };
  delete (canonical as { ambiguity_markers?: unknown }).ambiguity_markers;
  delete (canonical as { context_packet?: unknown }).context_packet;
  expect(validateStrict(CanonicalClaimSchema, canonical)).toBe(true);
  const missingTemporalTruth = structuredClone(canonical);
  delete (missingTemporalTruth.temporal_scope as { valid_time?: unknown }).valid_time;
  expect(validateStrict(CanonicalClaimSchema, missingTemporalTruth)).toBe(false);
});

test("C6 core canonical schema contains no confidence field", () => {
  expect(JSON.stringify(EnvelopeJsonSchemas2020.canonical_claim)).not.toContain("confidence");
});

test("predicate schema keeps legacy slots and name-v2 semantic roles disjoint", () => {
  const base = {
    predicate_id: "predicate:test",
    owner_account_id: "owner",
    predicate_revision_id: "predicate:test:r1",
    identity_name: "test",
    display_name: "test",
    lifecycle: "canonical",
  };
  expect(validateStrict(PredicateSchema, { ...base, slot_ids: ["window-slot-1"] })).toBe(true);
  expect(validateStrict(PredicateSchema, {
    ...base,
    identity_version: "name-v2",
    slot_ids: [],
    observed_roles: ["subject", "object"],
  })).toBe(true);
  expect(validateStrict(PredicateSchema, { ...base, identity_version: "name-v2", slot_ids: [] })).toBe(false);
  expect(validateStrict(PredicateSchema, {
    ...base,
    identity_version: "name-v2",
    slot_ids: ["window-slot-1"],
    observed_roles: ["subject"],
  })).toBe(false);
  expect(validateStrict(PredicateSchema, {
    ...base,
    identity_version: "name-v2",
    slot_ids: [],
    observed_roles: ["subject", "subject"],
  })).toBe(false);
});
