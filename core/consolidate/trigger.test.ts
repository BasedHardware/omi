import { expect, test } from "bun:test";
import { shouldConsolidate } from "./trigger";
import { scanContradictions } from "./contradiction";
import { singleValuedKey } from "./cardinality";

test("B2 trigger uses settled event-time gaps and token hysteresis, never wall time", () => {
  expect(shouldConsolidate({ stm_tokens: 20, last_trigger_stm_tokens: 5, high_watermark_tokens: 10, low_watermark_tokens: 6, previous_settled_window_id: "w1", previous_settled_event_time: "2026-01-01T00:00:00Z", settled_window_id: "w2", settled_event_time: "2026-01-01T00:00:01Z", idle_gap_ms: 100000 })).toMatchObject({ fire: true, kind: "volume" });
  expect(shouldConsolidate({ stm_tokens: 8, last_trigger_stm_tokens: 8, high_watermark_tokens: 10, low_watermark_tokens: 6, previous_settled_window_id: "w1", previous_settled_event_time: "2026-01-01T00:00:00Z", settled_window_id: "w2", settled_event_time: "2026-01-03T00:00:00Z", idle_gap_ms: 1000 })).toMatchObject({ fire: true, kind: "idle" });
});

test("B2 only calls a cardinality contradiction when a data policy declares it", () => {
  const policy = [{ policy_id: "policy", predicate_id: "employment", role_slot_id: "employer", cardinality: "single" as const }];
  expect(singleValuedKey([], "employment", "employer")).toBeUndefined();
  const key = singleValuedKey(policy, "employment", "employer")!;
  expect(scanContradictions([{ claim_revision_id: "a", entity_id: "person", proposition_key_resolved: "a", single_valued_key: key, value_key: "one" }, { claim_revision_id: "b", entity_id: "person", proposition_key_resolved: "b", single_valued_key: key, value_key: "two" }])[0]?.kind).toBe("single_valued");
});
