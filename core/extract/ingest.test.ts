import { expect, test } from "bun:test";
import { placementConversation } from "../../harness/fixtures";
import { ingestSyntheticConversation } from "./ingest";

test("T2 synthetic conversation maps to addressable L1 evidence with stable hashes", () => {
  const first = ingestSyntheticConversation(placementConversation);
  const second = ingestSyntheticConversation(placementConversation);
  expect(first).toEqual(second);
  expect(first.events).toHaveLength(3);
  expect(first.evidence[1]).toMatchObject({ source_local_speaker_ref: "speaker:bob", source_local_mention_ref: "mention:he", range: { start: 0, end: 33 } });
  expect(first.events[1]!.evidence_addressable_refs).toContain(first.evidence[1]!.evidence_id);
  expect(first.evidence[1]!.excerpt).toBe((first.events[1]!.payload as { text: string }).text);
});
