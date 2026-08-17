import { expect, test } from "bun:test";
import { buildMentionRequest, planLocalHandles } from "./mentions";

test("T4 D-a resolves a pronoun only to a source-local antecedent and preserves a bare pronoun", () => {
  const handles = planLocalHandles(buildMentionRequest([
    { mention_ref: "mention:alice", text: "Alice", source_identity_ref: null, speaker_rendering: "speaker:alice" },
    { mention_ref: "mention:he", text: "He", source_identity_ref: null, speaker_rendering: "speaker:bob" },
    { mention_ref: "mention:bare-he", text: "He", source_identity_ref: null, speaker_rendering: "speaker:unknown" },
  ]), { links: [
    { mention_ref: "mention:alice", antecedent_mention_ref: null, uncertainty: [] },
    { mention_ref: "mention:he", antecedent_mention_ref: "mention:alice", uncertainty: [] },
    { mention_ref: "mention:bare-he", antecedent_mention_ref: null, uncertainty: ["no_antecedent"] },
  ] });
  expect(handles[1]).toMatchObject({ antecedent_handle: "local:mention:alice", uncertainty: [] });
  expect(handles[2]).toMatchObject({ handle: "local:mention:bare-he", antecedent_handle: null });
  expect(handles[2]!.uncertainty).toContain("unresolved_local_mention");
});
