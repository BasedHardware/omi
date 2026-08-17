import { expect, test } from "bun:test";
import { buildFlywheelArtifacts } from "./flywheel";

const unresolved = { bindings: { subject: null }, scope: null, abstained_slots: ["subject"], scope_abstained: true, confidently_placed: false };

test("C6 queue and abstention are mutually exclusive strata, while low margin remains artifact-only risk provenance", () => {
  const queued = buildFlywheelArtifacts({ provisional_revision_id: "p-queue", canonical_claim_revision_id: null, scope_plan: unresolved, unit_boundary: { decision: "accept_ltm", margin: "low" } });
  const abstained = buildFlywheelArtifacts({ provisional_revision_id: "p-abstain", canonical_claim_revision_id: null, scope_plan: unresolved, unit_boundary: { decision: "abstain", reason: "lost context" } });
  expect(queued.map((item) => item.kind)).toEqual(["confirmation_queue"]);
  expect(abstained.map((item) => item.kind)).toEqual(["abstention_set"]);
  expect(queued[0]!.risk_markers).toContain("low_margin");
});

test("D41 graph-derived provenance recognizes a resolved pronoun and a session-minted entity", () => {
  const artifacts = buildFlywheelArtifacts({
    provisional_revision_id: "p-new", canonical_claim_revision_id: "c-new",
    scope_plan: { bindings: { subject: "entity:new" }, scope: { locality: "durable", scope_ref: "project:new" }, abstained_slots: [], scope_abstained: false, confidently_placed: true },
    unit_boundary: { decision: "accept_ltm", margin: "high" },
    mentions: [{ mention_id: "m-she", owner_account_id: "owner", claim_revision_id: "p-new", span: { start: 0, end: 3 }, evidence_id: "e-new", speaker_ref: null, slot_id: "subject", surface: "She", antecedent_handle: null, resolution: "resolved", entity_id: "entity:new" }],
    newly_minted_entity_ids: ["entity:new"],
  });
  expect(artifacts[0]!.risk_markers).toEqual(expect.arrayContaining(["new_entity", "resolved_pronoun"]));
});
