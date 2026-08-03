import { expect, test } from "bun:test";
import { placementConversation } from "../../harness/fixtures";
import { ingestConversation } from "./ingest";

test("T2 synthetic conversation maps to addressable L1 evidence with stable hashes", () => {
  const first = ingestConversation(placementConversation);
  const second = ingestConversation(placementConversation);
  expect(first).toEqual(second);
  expect(first.events).toHaveLength(3);
  expect(first.evidence[1]).toMatchObject({ speaker_rendering: "speaker:bob", source_local_mention_ref: "mention:he", range: { start: 0, end: 33 }, source_identity_ref: { namespace_instance_ref: "unscoped:synthetic-session-1:turn-2", local_key: "mention:he" } });
  expect(first.events[1]!.evidence_addressable_refs).toContain(first.evidence[1]!.evidence_id);
  expect(first.evidence[1]!.excerpt).toBe((first.events[1]!.payload as { text: string }).text);
});
