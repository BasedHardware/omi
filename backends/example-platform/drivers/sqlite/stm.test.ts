import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { shouldConsolidate } from "../../core/consolidate/trigger";
import { SqliteStmStore, type DurableStmItem } from "./stm";

const claim = { claim_lineage_id: "l", claim_revision_id: "p", owner_account_id: "owner", predicate: "knows", arguments: [{ slot_id: "subject", role: "subject", surface: "Alice", span: { start: 0, end: 5 }, value: { kind: "source_local_ref" as const, ref: "speaker:1" } }], polarity: "positive" as const, temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: ["e"], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: null };

test("STM persists one ordered row set with its mentions", () => {
  const stm = new SqliteStmStore(new Database(":memory:"));
  stm.put([{ item: { id: "i", session_id: "s", event_time_watermark: "2026-01-01T00:00:00Z", capture_sequence: 1, revision_lineage: "r", ingest_sequence: 1, entity_refs: ["speaker:1"], lexical_terms: ["alice"], vector_key: "v", predicate_id: "knows", bytes: 10, claim, evidence: [], argument_origins: { subject: "independent" }, settled_window_id: "w" }, mentions: [{ mention_id: "m", owner_account_id: "owner", claim_revision_id: "p", span: { start: 0, end: 5 }, evidence_id: "e", source_identity_ref: null, speaker_rendering: null, slot_id: "subject", surface: "Alice", antecedent_handle: null, resolution: "unresolved", entity_id: null }] }]);
  expect(stm.all()[0]).toMatchObject({ claim, settled_window_id: "w" });
  expect(stm.mentions().map((mention) => mention.mention_id)).toEqual(["m"]);
});

const item = (id: string, bytes: number): { item: DurableStmItem; mentions: [] } => ({ item: { id, session_id: `session:${id}`, event_time_watermark: "2026-01-01T00:00:00Z", capture_sequence: 1, revision_lineage: "r", ingest_sequence: 1, entity_refs: [], lexical_terms: [], vector_key: "v", predicate_id: "knows", bytes, claim: { ...claim, claim_revision_id: id }, evidence: [], argument_origins: {}, settled_window_id: "w" }, mentions: [] });

test("consume tombstones items out of the live frontier but keeps them for resume bookkeeping", () => {
  const stm = new SqliteStmStore(new Database(":memory:"));
  stm.put([item("a", 10), item("b", 10)]);
  stm.consume(["a"]);
  expect(stm.unconsumed().map((entry) => entry.id)).toEqual(["b"]);
  expect(stm.all().map((entry) => entry.id)).toEqual(["a", "b"]);
});

test("a drained store lets the volume trigger fire a second time in one process", () => {
  const stm = new SqliteStmStore(new Database(":memory:"));
  const tokens = () => stm.unconsumed().reduce((sum, entry) => sum + entry.bytes, 0);
  // Same settled event time on both sides: the idle path stays cold and only
  // the volume watermark decides.
  const base = { high_watermark_tokens: 1_000_000, low_watermark_tokens: 500_000, previous_settled_window_id: "w0", previous_settled_event_time: "2026-01-01T00:00:00Z", settled_window_id: "w1", settled_event_time: "2026-01-01T00:00:00Z", idle_gap_ms: 6 * 60 * 60 * 1000 };

  stm.put([item("first", 1_200_000)]);
  expect(shouldConsolidate({ ...base, stm_tokens: tokens(), last_trigger_stm_tokens: 0 })).toMatchObject({ fire: true, kind: "volume" });
  const undrainedWatermark = tokens();

  // The pre-drain defect: the watermark recomputed from a never-shrinking
  // store stays above the low watermark, so a second crossing cannot fire.
  stm.put([item("second", 1_200_000)]);
  expect(shouldConsolidate({ ...base, stm_tokens: tokens(), last_trigger_stm_tokens: undrainedWatermark }).fire).toBe(false);

  // Drain what the first cycle consumed and recompute: the low-water reset is
  // real and the identical second crossing fires.
  stm.consume(["first", "second"]);
  const drainedWatermark = tokens();
  expect(drainedWatermark).toBe(0);
  stm.put([item("third", 1_200_000)]);
  expect(shouldConsolidate({ ...base, stm_tokens: tokens(), last_trigger_stm_tokens: drainedWatermark })).toMatchObject({ fire: true, kind: "volume" });
});
