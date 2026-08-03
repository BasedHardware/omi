import { expect, test } from "bun:test";
import { invokeMentionStrategy } from "./mention-edge";
import { DeterministicFakeModel } from "./port";
import { invokeEntityStrategy } from "./entity-edge";

test("T4 only the edge invokes the deterministic model port", async () => {
  const handles = await invokeMentionStrategy(new DeterministicFakeModel({ links: [] }), [
    { mention_ref: "mention:bare", text: "He", source_identity_ref: null, speaker_rendering: null },
  ]);
  expect(handles[0]).toMatchObject({ antecedent_handle: null });
});

test("C3 forwards only persisted, in-unit coreference support into entity planning", async () => {
  const result = await invokeEntityStrategy(new DeterministicFakeModel({ decision: "abstain" }), {
    owner_account_id: "owner", entities: [{ entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "r1", handle: "alice", labels: ["Alice"] }], constraints: [],
  }, "owner", { handle: "local:pronoun", mention_ref: "pronoun", antecedent_handle: "local:alice", uncertainty: [] }, ["She arrived."], ["entity:alice"], new Map([["local:alice", { entity_id: "entity:alice", mention_id: "alice", discourse_unit_ref: "unit:1" }]]), undefined, undefined, undefined, undefined, "unit:1", [{ coreference_support_id: "coref:1", owner_account_id: "owner", discourse_unit_ref: "unit:1", antecedent_mention_id: "alice", anaphor_mention_id: "pronoun", evidence_refs: ["She arrived."], lineage_refs: ["mention:alice", "mention:pronoun"], lifecycle: "active" }]);
  expect(result).toEqual({ outcome: "same", entity_id: "entity:alice", blockers: [] });
});
