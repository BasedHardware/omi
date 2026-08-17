import { expect, test } from "bun:test";
import { assertNoLookahead, replaySessions } from "./replay";

const item = (id: string, session: string, sequence: number) => ({ id, session_id: session, event_time_watermark: "2026-01-01T00:00:00Z", capture_sequence: sequence, revision_lineage: `r:${sequence}`, ingest_sequence: sequence, entity_refs: [], lexical_terms: [], vector_key: id, predicate_id: "p", bytes: 1 });

test("S1 session N cannot read state at or after N", () => {
  const observed = replaySessions([{ session_id: "two", item: item("two", "two", 2) }, { session_id: "one", item: item("one", "one", 1) }], (session, visible) => ({ session: session.session_id, visible: visible.map((value) => value.id) }));
  expect(observed).toEqual([{ session: "one", visible: [] }, { session: "two", visible: ["one"] }]);
});

test("S1 the no-lookahead assertion trips if a future item is presented", () => {
  const future = item("future", "future", 2), current = item("current", "current", 1);
  expect(() => assertNoLookahead(current, [future])).toThrow("lookahead");
});

test("E6 replay rejects a handler that returns a future session item", () => {
  const sessions = [{ session_id: "s1", item: item("s1", "s1", 1) }, { session_id: "s2", item: item("s2", "s2", 2) }];
  expect(() => replaySessions(sessions, () => sessions[1]!.item.id)).toThrow("lookahead");
});
