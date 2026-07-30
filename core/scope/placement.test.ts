import { expect, test } from "bun:test";
import { planScopeAndRoles } from "./placement";
import type { ProvisionalClaim } from "../schema";

const entity = { entity_id: "entity:owner", owner_account_id: "owner-1", entity_revision_id: "r1", handle: "owner", labels: [] };
const claim = (ambiguity_markers: string[] = []): ProvisionalClaim => ({
  claim_lineage_id: "p", claim_revision_id: "pr", owner_account_id: "owner-1", predicate: "statement/ai_use",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref", ref: "local:owner" } }],
  temporal_scope: { observed_at: "2026-07-29T00:00:00Z", precision: "instant" }, evidence_refs: ["e1"], policy_labels: [], source_language: "en",
  scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers,
  context_packet: { version: "context-v1", referent_refs: [], topic_refs: [] },
});

test("T6 binds entity-valued roles or abstains rather than guessing", () => {
  const bound = planScopeAndRoles(claim(), [entity], { bindings: { subject: "entity:owner" }, scope: { locality: "durable", scope_ref: "topic:ai" } });
  const abstained = planScopeAndRoles(claim(), [entity], { bindings: { subject: "entity:unknown" }, scope: null });
  expect(bound).toMatchObject({ bindings: { subject: "entity:owner" }, confidently_placed: true });
  expect(abstained).toMatchObject({ bindings: { subject: null }, scope_abstained: true, confidently_placed: false });
});

test("T6 one-off hedged claims are source-local, never durable", () => {
  const plan = planScopeAndRoles(claim(["hedged", "one_off"]), [entity], { bindings: { subject: "entity:owner" }, scope: { locality: "durable", scope_ref: "topic:ai" } });
  expect(plan.scope).toEqual({ locality: "source_local", scope_ref: null });
});
