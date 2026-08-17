import { expect, test } from "bun:test";
import { buildScopeRoleRequest, planScopeAndRoles } from "./placement";
import type { ProvisionalClaim } from "../schema";

const entity = { entity_id: "entity:owner", owner_account_id: "owner-1", entity_revision_id: "r1", handle: "owner", labels: [] };
const claim = (ambiguity_markers: string[] = []): ProvisionalClaim => ({
  claim_lineage_id: "p", claim_revision_id: "pr", owner_account_id: "owner-1", predicate: "statement/ai_use",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref", ref: "local:owner" } }],
  temporal_scope: { observed_at: "2026-07-29T00:00:00Z", precision: "instant" }, evidence_refs: ["e1"], policy_labels: [], source_language: "en",
  scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers,
  context_packet: { version: "context-v1", referent_refs: [], topic_refs: [] },
});
const evidence = [{ evidence_id: "e1", event_revision_id: "event", source_unit_ref: null, range: { start: 0, end: 20 }, excerpt: "Owner uses AI daily.", source_identity_ref: null, speaker_rendering: "speaker:owner", source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture" }];

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

test("C4 scope request exposes predicate, argument surfaces, evidence text, and candidate labels; missing context never reaches a model", () => {
  const request = buildScopeRoleRequest(claim(), [{ ...entity, labels: ["Owner profile"] }], evidence);
  expect(request).toMatchObject({ version: "v2", predicate: "statement/ai_use", argument_surfaces: [{ slot_id: "subject", role: "subject", surface: "local:owner" }], evidence: [{ evidence_id: "e1", excerpt: "Owner uses AI daily." }], candidate_scope_labels: ["Owner profile"] });
  expect(() => buildScopeRoleRequest(claim(), [entity], [])).toThrow("lacks retained evidence excerpt");
});

test("scope request drops ambiguous_surface bookkeeping markers but keeps durability markers", () => {
  const request = buildScopeRoleRequest(claim(["ambiguous_surface:subject", "one_off", "hedged"]), [entity], evidence);
  expect(request.ambiguity_markers).toEqual(["one_off", "hedged"]);
  // Planner still sees the raw claim markers for hedged+one_off downgrade.
  const plan = planScopeAndRoles(claim(["ambiguous_surface:subject", "hedged", "one_off"]), [entity], { bindings: { subject: "entity:owner" }, scope: { locality: "durable", scope_ref: "topic:ai" } });
  expect(plan.scope).toEqual({ locality: "source_local", scope_ref: null });
});

test("source-local refs render their ref rather than the literal undefined", () => {
  const request = buildScopeRoleRequest({ ...claim(), arguments: [{ slot_id: "subject", role: "subject", value: { kind: "source_local_ref", ref: "speaker:7" } }] }, [], evidence);
  expect(request.argument_surfaces[0]?.surface).toBe("speaker:7");
  expect(request.candidate_scope_labels).toEqual([]);
});
