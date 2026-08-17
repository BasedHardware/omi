import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { predicateAliasFrontier } from "../../core/consolidate/predicate-frontier";
import { predicateIdForName, predicateRevisionForObservation } from "../../core/consolidate/predicate-identity";
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

test("name-v2 stores distinct immutable role-set revisions under one predicate identity", () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const subjectOnly = predicateRevisionForObservation({
    owner_account_id: "owner",
    predicate_id: predicateIdForName("visited place"),
    display_name: "visited place",
    roles: ["subject"],
    lifecycle: "canonical",
  });
  const subjectAndPlace = predicateRevisionForObservation({
    owner_account_id: "owner",
    predicate_id: predicateIdForName("visited-place"),
    display_name: "visited-place",
    roles: ["place", "subject"],
    lifecycle: "canonical",
  });
  expect(subjectOnly.predicate.predicate_id).toBe(subjectAndPlace.predicate.predicate_id);
  expect(subjectOnly.revision_id).not.toBe(subjectAndPlace.revision_id);

  const revisions = [subjectOnly, subjectAndPlace].map((revision) => ({
    kind: "predicate" as const,
    revision_id: revision.revision_id,
    predicate: revision.predicate,
  }));
  const derivation = prepareDerivation({
    attempt_id: "name-v2-role-revisions-attempt",
    commit_id: "name-v2-role-revisions",
    owner_account_id: "owner",
    parent_commit: null,
    idempotency_key: "name-v2-role-revisions",
    input_revisions: [],
    output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: revision.predicate })),
    versions: { strategy_version: "test", model_version: "none", prompt_version: "none", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "none", tool_version: "test" },
    success_kind: "success",
  });
  const plan = { placement: { offline_experiment: true as const, allocations: {}, results: [] }, derivation, revisions, adjacency: [], artifacts: [] };
  ledger.append(plan);
  ledger.append(plan);

  const stored = ledger.snapshot("owner").predicates ?? [];
  expect(stored).toHaveLength(2);
  expect(stored.map((row) => row.predicate.observed_roles).sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right))))
    .toEqual([["place", "subject"], ["subject"]]);

  const otherOwner = predicateRevisionForObservation({
    owner_account_id: "other-owner",
    predicate_id: predicateIdForName("visited place"),
    display_name: "visited place",
    roles: ["subject"],
    lifecycle: "canonical",
  });
  expect(otherOwner.revision_id).not.toBe(subjectOnly.revision_id);
  const otherRevision = { kind: "predicate" as const, revision_id: otherOwner.revision_id, predicate: otherOwner.predicate };
  ledger.append({
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation: prepareDerivation({
      attempt_id: "name-v2-other-owner-attempt",
      commit_id: "name-v2-other-owner",
      owner_account_id: "other-owner",
      parent_commit: null,
      idempotency_key: "name-v2-other-owner",
      input_revisions: [],
      output_revisions: [{ revision_id: otherRevision.revision_id, content: otherRevision.predicate }],
      versions: { strategy_version: "test", model_version: "none", prompt_version: "none", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "none", tool_version: "test" },
      success_kind: "success",
    }),
    revisions: [otherRevision],
    adjacency: [],
    artifacts: [],
  });
  expect(ledger.snapshot("other-owner").predicates).toHaveLength(1);
});

test("ledger rejects a malformed name-v2 predicate before persistence", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const malformed = {
    predicate_id: predicateIdForName("malformed"),
    owner_account_id: "owner",
    predicate_revision_id: "predicate:malformed:forged",
    identity_version: "name-v2",
    identity_name: "malformed",
    display_name: "malformed",
    lifecycle: "canonical",
    slot_ids: ["legacy-window-slot"],
  };
  const derivation = prepareDerivation({
    attempt_id: "malformed-predicate-attempt",
    commit_id: "malformed-predicate",
    owner_account_id: "owner",
    parent_commit: null,
    idempotency_key: "malformed-predicate",
    input_revisions: [],
    output_revisions: [{ revision_id: malformed.predicate_revision_id, content: malformed }],
    versions: { strategy_version: "test", model_version: "none", prompt_version: "none", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "none", tool_version: "test" },
    success_kind: "success",
  });
  expect(() => ledger.append({
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation,
    revisions: [{ kind: "predicate", revision_id: malformed.predicate_revision_id, predicate: malformed as never }],
    adjacency: [],
    artifacts: [],
  })).toThrow("invalid predicate");
  expect(ledger.snapshot("owner").predicates).toEqual([]);
});
