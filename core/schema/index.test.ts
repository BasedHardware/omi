import { expect, test } from "bun:test";
import fc from "fast-check";
import { CanonicalClaimSchema, EnvelopeJsonSchemas2020, ProvisionalClaimSchema, isValidLifecycleTransition, transitionClaimLifecycle } from "./index";
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
  const canonical = { ...fixtureClaim(), lifecycle: "canonical", canonical_claim_id: "canonical-1", source_provisional_revision_ids: [], supersedes_revision_ids: ["revision-0"] };
  delete (canonical as { ambiguity_markers?: unknown }).ambiguity_markers;
  delete (canonical as { context_packet?: unknown }).context_packet;
  expect(validateStrict(CanonicalClaimSchema, canonical)).toBe(true);
});
