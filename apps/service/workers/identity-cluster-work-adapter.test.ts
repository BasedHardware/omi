import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import {
  IDENTITY_PEOPLE_CLUSTER_RESULT_CONTRACT_VERSION,
  IDENTITY_PEOPLE_CLUSTER_INPUT_SNAPSHOT_VERSION,
  defineIdentityPeopleClusterConsolidationAdapter,
  identityPeopleClusterWorkInputManifest,
  parseIdentityPeopleClusterInputSnapshot,
  parseIdentityPeopleClusterOutcome,
} from "./identity-cluster-work-adapter";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;
const owner = "account:alice";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:one",
  account_id: owner, application_id: "app:identity", credential_id: "credential:one",
  credential_generation: 1, capability: "memories.work.execute", grant_id: "grant:one",
  grant_version: 1, account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const strategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:identity-cluster:people",
  work_kind: "identity_cluster",
  coordinates: {
    strategy_version: "identity-people-cluster:v1",
    model_version: "none",
    prompt_version: "none",
    policy_version: "identity-people-policy:v1",
    code_version: "identity-people-cluster:v1",
    schema_version: "identity-people-cluster-response:v1",
    tokenizer_version: "none",
    tool_version: "none",
    result_contract_version: IDENTITY_PEOPLE_CLUSTER_RESULT_CONTRACT_VERSION,
    speaker_strategy_version: "none",
    boundary_strategy_version: "none",
  },
});

const snapshot = () => parseIdentityPeopleClusterInputSnapshot({
  version: IDENTITY_PEOPLE_CLUSTER_INPUT_SNAPSHOT_VERSION,
  owner_account_id: owner,
  job_id: "job:identity:one",
  input_frontier: digest("f"),
  people_cluster_beliefs: [{
    cluster_about_ref: ref("about1", "a"),
    cluster_entity_target_ref: ref("attrtarget1", "b"),
    member_evidence_refs: [ref("atevidence1", "c")],
    belief_contract_digest: digest("1"),
    aggregation_contract_digest: digest("2"),
    calibration_contract_digest: digest("3"),
  }],
  created_at_event_time: 42,
});

const leasedJob = () => leaseDurableMemoryWork(acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:identity:one",
  owner_account_id: owner,
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "identity_cluster",
  input_frontier: digest("f"),
  input_digest: durableMemoryWorkInputManifestDigest(identityPeopleClusterWorkInputManifest(snapshot())),
  execution_contract_digest: strategy.execution_contract_digest,
  accepted_at_event_time: 100,
  max_attempts: 3,
}), "worker:one", 101, 20);

describe("identity people-cluster consolidation adapter", () => {
  test("plans probabilistic people beliefs and never mints owner authority", async () => {
    const adapter = defineIdentityPeopleClusterConsolidationAdapter({
      load_input: async () => ({ kind: "found", snapshot: snapshot() }),
    });
    const produced = await adapter.produce(context, leasedJob(), strategy);
    expect(produced.kind).toBe("produced");
    if (produced.kind !== "produced") return;
    const outcome = parseIdentityPeopleClusterOutcome(produced.normalized_result);
    expect(outcome.people_cluster_beliefs).toHaveLength(1);
    expect(outcome.people_cluster_beliefs[0]?.belief_kind).toBe("claim_subject");
    expect(outcome.people_cluster_beliefs[0]?.hypotheses.map((item) => item.kind).sort())
      .toEqual(["entity", "unknown"]);
    expect(outcome.people_cluster_beliefs[0]?.hypotheses.some((item) => item.kind === "owner")).toBe(false);
    const staged = {
      work_kind: "identity_cluster" as const,
      result_contract_version: IDENTITY_PEOPLE_CLUSTER_RESULT_CONTRACT_VERSION,
      response_digest: produced.response_digest,
      result_digest: produced.response_digest,
      normalized_result: produced.normalized_result,
    };
    await expect(adapter.materialize(context, leasedJob(), staged as never, strategy)).resolves.toEqual({
      kind: "ready",
      result_kind: "successful_empty",
      authoritative_append: null,
    });
  });

  test("does not import or invoke the rejected SQLite dream path", async () => {
    const source = await Bun.file(new URL("./identity-cluster-work-adapter.ts", import.meta.url)).text();
    expect(source).not.toContain("drivers/sqlite/dream");
    expect(source).not.toContain("invokeBlockedIdentityAdjudication");
    expect(source).not.toContain("identity_authority_context");
  });
});
