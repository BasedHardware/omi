import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { SqliteStmStore } from "./stm";

const claim = { claim_lineage_id: "l", claim_revision_id: "p", owner_account_id: "owner", predicate: "knows", arguments: [{ slot_id: "subject", role: "subject", surface: "Alice", span: { start: 0, end: 5 }, value: { kind: "source_local_ref" as const, ref: "speaker:1" } }], polarity: "positive" as const, temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: ["e"], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: null };

test("STM persists one ordered row set with its mentions", () => {
  const stm = new SqliteStmStore(new Database(":memory:"));
  stm.put([{ item: { id: "i", session_id: "s", event_time_watermark: "2026-01-01T00:00:00Z", capture_sequence: 1, revision_lineage: "r", ingest_sequence: 1, entity_refs: ["speaker:1"], lexical_terms: ["alice"], vector_key: "v", predicate_id: "knows", bytes: 10, claim, evidence: [], argument_origins: { subject: "independent" }, settled_window_id: "w" }, mentions: [{ mention_id: "m", owner_account_id: "owner", claim_revision_id: "p", span: { start: 0, end: 5 }, evidence_id: "e", source_identity_ref: null, speaker_rendering: null, slot_id: "subject", surface: "Alice", antecedent_handle: null, resolution: "unresolved", entity_id: null }] }]);
  expect(stm.all()[0]).toMatchObject({ claim, settled_window_id: "w" });
  expect(stm.mentions().map((mention) => mention.mention_id)).toEqual(["m"]);
});
