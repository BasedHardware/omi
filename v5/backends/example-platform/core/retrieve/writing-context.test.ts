import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { getWritingContext } from "./writing-context";

test("S2 writing context uses the read projection and has no storage reach", () => {
  const source = readFileSync(new URL("./writing-context.ts", import.meta.url), "utf8");
  expect(source).not.toContain("Sqlite"); expect(source).not.toContain(".query(");
  const context = getWritingContext({ owner_account_id: "owner", graph_generation: 2, claims: [], entities: [], adjacency: [] }, { account_timezone: "UTC", policy_version: "p", predicate_alias_generation: "a", authorization_generation: "i", stm_generation: "s" });
  expect(context.frontier).toEqual({ graph_head: "2", policy_version: "p", predicate_alias_generation: "a", authorization_generation: "i", stm_generation: "s" });
});

test("S2 ranks window-relevant candidates above lexical-first distractors", () => {
  const claims = Array.from({ length: 25 }, (_, index) => ({ revision_id: `r:${index}`, placement_status: "canonical" as const, claim: {
    claim_lineage_id: `l:${index}`, claim_revision_id: `r:${index}`, canonical_claim_id: `r:${index}`, owner_account_id: "owner", predicate: index === 24 ? "project.focus" : "alpha.noise", arguments: [{ slot_id: "subject", role: "subject", surface: index === 24 ? "Zebra Atlas" : `Alpha ${index}`, value: { kind: "source_local_ref" as const, ref: index === 24 ? "zebra" : `alpha:${index}` } }], polarity: "positive" as const, temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant", valid_time: { typed_expression: { kind: "absolute" as const, granularity: "day" as const, value: "2026-01-01" }, resolved_interval: { kind: "calendar_interval" as const, start: "2026-01-01T00:00:00Z", end: "2026-01-02T00:00:00Z", timezone: "UTC", granularity: "day" as const }, derivation: { resolver_version: "t", timezone: "UTC" } } }, evidence_refs: [], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "canonical" as const, source_provisional_revision_ids: []
  } }));
  const context = getWritingContext({ owner_account_id: "owner", graph_generation: 1, claims, entities: [], adjacency: [] }, { account_timezone: "UTC", policy_version: "p", predicate_alias_generation: "a", authorization_generation: "i", stm_generation: "s", window: { text: "Tell me about Zebra Atlas" } });
  expect(context.entity_candidates.map((candidate) => candidate.ref)).toContain("zebra");
  expect(context.entity_candidates.map((candidate) => candidate.ref)).not.toContain("alpha:0");
  expect(context.entity_candidates.find((candidate) => candidate.ref === "zebra")?.profile[0]).toContain("project.focus");
});
