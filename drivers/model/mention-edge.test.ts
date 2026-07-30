import { expect, test } from "bun:test";
import { invokeMentionStrategy } from "./mention-edge";
import { DeterministicFakeModel } from "./port";

test("T4 only the edge invokes the deterministic model port", async () => {
  const handles = await invokeMentionStrategy(new DeterministicFakeModel({ links: [] }), [
    { mention_ref: "mention:bare", text: "He", source_local_speaker_ref: null },
  ]);
  expect(handles[0]).toMatchObject({ antecedent_handle: null });
});
