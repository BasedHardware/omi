import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { predicateAliasFrontier } from "../../core/consolidate/predicate-frontier";
import { prepareDerivation } from "../../core/ledger";
import { SqliteLedger } from "./index";

test("B1.2 persists predicate objects and vocabulary assertions into the retrieval snapshot", () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const predicate = { predicate_id: "predicate:travel", owner_account_id: "owner", predicate_revision_id: "predicate:travel:r1", identity_name: "travelled-from", display_name: "Travelled from", lifecycle: "provisional" as const, slot_ids: ["traveler"] };
  const assertion = { assertion_id: "alias:1", owner_account_id: "owner", predicate_id: "predicate:travel", relation: "alias_of" as const, target_predicate_id: "predicate:origin", slot_aliases: [{ from_slot_id: "traveler", to_slot_id: "person" }], alias_frontier: "declared-frontier", admission: "accepted" as const, lifecycle: "active" as const, supersedes_assertion_id: null };
  const versions = { strategy_version: "test", model_version: "none", prompt_version: "none", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "none", tool_version: "test" };
  const derivation = prepareDerivation({ attempt_id: "attempt", commit_id: "commit", owner_account_id: "owner", parent_commit: null, idempotency_key: "predicate-snapshot", input_revisions: [], output_revisions: [{ revision_id: predicate.predicate_revision_id, content: predicate }, { revision_id: "assertion:r1", content: assertion }], versions, success_kind: "success" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions: [{ kind: "predicate", revision_id: predicate.predicate_revision_id, predicate }, { kind: "predicate_assertion", revision_id: "assertion:r1", assertion }], adjacency: [], artifacts: [] });
  const snapshot = ledger.snapshot("owner");
  expect(snapshot.predicates?.map((item) => item.predicate.predicate_id)).toEqual(["predicate:travel"]);
  expect(predicateAliasFrontier(snapshot.predicate_assertions?.map((item) => item.assertion) ?? []).edges).toHaveLength(2);
});
