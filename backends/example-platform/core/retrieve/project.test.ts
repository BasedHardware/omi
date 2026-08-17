import { expect, test } from "bun:test";
import { project, type GraphSnapshot } from "./index";

const policy = (sensitivity: string) => [`subject:generic`, `sensitivity:${sensitivity}`, "capture:generic"];
const claim = (id: string, labels: readonly string[]) => ({
  revision_id: id, placement_status: "canonical" as const, claim: { claim_lineage_id: `lineage:${id}`, claim_revision_id: id, owner_account_id: "owner", predicate: "met", arguments: [], temporal_scope: { observed_at: "2026-01-01", precision: "day" }, evidence_refs: [], policy_labels: labels, source_language: "en", scope: { locality: "durable" as const, scope_ref: null }, lifecycle: "canonical" as const, canonical_claim_id: `canonical:${id}`, source_provisional_revision_ids: [] },
});
const consumedProvisional = (id: string, labels: readonly string[]) => ({ revision_id: id, placement_status: "consumed" as const, claim: { claim_lineage_id: `lineage:${id}`, claim_revision_id: id, owner_account_id: "owner", predicate: "met", arguments: [], temporal_scope: { observed_at: "2026-01-01", precision: "day" }, evidence_refs: [], policy_labels: labels, source_language: "en", scope: { locality: "durable" as const, scope_ref: null }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: null } });
const graph = (): GraphSnapshot => ({ owner_account_id: "owner", claims: [claim("visible", policy("generic")), claim("private", policy("private")), consumedProvisional("consumed-input", policy("generic"))], entities: [], adjacency: [{ claim_revision_id: "visible", entity_id: "entity:a", role_slot_id: "subject" }, { claim_revision_id: "private", entity_id: "entity:a", role_slot_id: "subject" }, { claim_revision_id: "consumed-input", entity_id: "entity:a", role_slot_id: "subject" }] });
const genericGrant = { grant_id: "generic", policy_classes: [{ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }] };

test("G2 projects only current-live, grant-eligible claims and their own adjacency", () => {
  const result = project(graph(), { reader_account_id: "reader", grant: genericGrant });
  expect(result.claims.map((item) => item.revision_id)).toEqual(["visible"]);
  expect(result.adjacency).toEqual([{ claim_revision_id: "visible", entity_id: "entity:a", role_slot_id: "subject" }]);
});
test("G2 owner projection is dormant for grants but still applies current-live liveness", () => {
  const result = project(graph(), { reader_account_id: "owner", grant: genericGrant });
  expect(result.claims.map((item) => item.revision_id)).toEqual(["private", "visible"]);
  expect(result.adjacency.map((edge) => edge.claim_revision_id)).toEqual(["private", "visible"]);
});
test("G2 keeps the owner's live provisional claim and its status", () => {
  const snapshot: GraphSnapshot = { owner_account_id: "owner", claims: [{ ...claim("unresolved", policy("generic")), placement_status: "provisional_unresolved_subject", claim: { ...claim("unresolved", policy("generic")).claim, lifecycle: "provisional", ambiguity_markers: ["unresolved_subject"], context_packet: null } }], entities: [], adjacency: [] };
  expect(project(snapshot, { reader_account_id: "owner", grant: genericGrant }).claims[0]?.placement_status).toBe("provisional_unresolved_subject");
});
