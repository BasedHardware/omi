import { expect, test } from "bun:test";
import { ingestConversation } from "./ingest";
import { checkStmSufficiency } from "./provisional";
import { placementConversation } from "../../harness/fixtures";
import type { ProvisionalClaim } from "../schema";

const claim = (): ProvisionalClaim => ({
  claim_lineage_id: "p-1", claim_revision_id: "p-r-1", owner_account_id: "owner-david", predicate: "preference/status_updates",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref", ref: "local:alice" } }],
  temporal_scope: { observed_at: "2026-07-29T10:00:00Z", precision: "instant" }, evidence_refs: ["evidence:synthetic-session-1:turn-1"],
  policy_labels: [], source_language: "en", scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional",
  ambiguity_markers: [], context_packet: { version: "context-v1", referent_refs: ["local:alice"], topic_refs: ["topic:updates"] },
});

test("T3 accepts a provisional claim only with retained role/evidence/context structure", () => {
  const { evidence } = ingestConversation(placementConversation);
  expect(checkStmSufficiency(claim(), evidence, ["subject"]).ok).toBe(true);
  const incomplete = { ...claim(), arguments: [], evidence_refs: [], context_packet: null };
  const result = checkStmSufficiency(incomplete, evidence, ["subject"]);
  expect(result).toMatchObject({ ok: false });
  if (!result.ok) expect(result.errors).toEqual(expect.arrayContaining(["missing required role slot: subject", "missing evidence references", "missing versioned referent/topic context packet"]));
});
