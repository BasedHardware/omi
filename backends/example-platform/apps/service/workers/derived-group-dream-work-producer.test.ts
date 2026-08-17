import { describe, expect, test } from "bun:test";

import {
  DERIVED_GROUP_DREAM_VERSION,
  derivedGroupDreamPreservesOriginals,
  derivedGroupDreamProjectionContractDigest,
} from "../../../core/consolidate/derived-group-dream";
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
  DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
} from "./derived-group-dream-contract";
import {
  derivedGroupDreamWorkInputManifest,
  parseDerivedGroupDreamInputSnapshot,
} from "./derived-group-dream-work-adapter";
import { defineDerivedGroupDreamConsolidationAdapter, defineDerivedGroupDreamWorkAdapter } from "./derived-group-dream-work-producer";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;
const owner = "account:alice";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:one",
  account_id: owner, application_id: "app:dream", credential_id: "credential:one",
  credential_generation: 1, capability: "memories.work.execute", grant_id: "grant:one",
  grant_version: 1, account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const strategyCoordinates = Object.freeze({
  strategy_version: "derived-group-dream:v1",
  model_version: "none",
  prompt_version: "none",
  policy_version: "dream-policy:v1",
  code_version: "derived-group-dream:v1",
  schema_version: "derived-group-dream-response:v1",
  tokenizer_version: "none",
  tool_version: "none",
  result_contract_version: DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
  speaker_strategy_version: "none",
  boundary_strategy_version: "none",
});

const strategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:dream:authority",
  work_kind: "derived_group_dream",
  coordinates: strategyCoordinates,
});

const snapshot = () => parseDerivedGroupDreamInputSnapshot({
  version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  owner_account_id: owner,
  job_id: "job:dream:one",
  input_frontier: digest("f"),
  projection_contract_digest: derivedGroupDreamProjectionContractDigest({
    strategy_version: strategyCoordinates.strategy_version,
    code_version: strategyCoordinates.code_version,
  }),
  original_claims: [
    {
      claim_revision_id: "claim:one:r1",
      proposition_id: "proposition:one",
      evidence_ref: ref("atevidence1", "a"),
    },
    {
      claim_revision_id: "claim:two:r1",
      proposition_id: "proposition:two",
      evidence_ref: ref("atevidence1", "b"),
    },
  ],
  group_memberships: [{
    group_key: "group:launch-week",
    proposition_ids: ["proposition:one", "proposition:two"],
  }],
  people_cluster_beliefs: [{
    cluster_about_ref: ref("about1", "a"),
    cluster_entity_target_ref: ref("attrtarget1", "a"),
    member_evidence_refs: [ref("atevidence1", "a"), ref("atevidence1", "b")],
    belief_contract_digest: digest("1"),
    aggregation_contract_digest: digest("2"),
    calibration_contract_digest: digest("3"),
  }],
  created_at_event_time: 1_700_000_000,
});

const leasedJob = (input = snapshot()) => leaseDurableMemoryWork(
  acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: input.job_id,
    owner_account_id: owner,
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: "derived_group_dream",
    input_frontier: input.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(derivedGroupDreamWorkInputManifest(input)),
    execution_contract_digest: strategy.execution_contract_digest,
    accepted_at_event_time: 100,
    max_attempts: 2,
  }),
  "worker:one",
  101,
  20,
);

describe("derived group dream work adapter", () => {
  test("loads the staged snapshot under a leased job and plans rebuildable groups without a model", async () => {
    let loadCalls = 0;
    const adapter = defineDerivedGroupDreamWorkAdapter({
      load_input: async () => {
        loadCalls += 1;
        return { kind: "found", snapshot: snapshot() };
      },
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
      load_witness_claims: async () => ({ kind: "found", committed_revisions: [] }),
    });
    const job = leasedJob();
    const produced = await adapter.produce(context, job, strategy);
    expect(produced).toMatchObject({
      kind: "produced",
      result_contract_version: DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
      response_digest: expect.stringMatching(/^[a-f0-9]{64}$/),
    });
    if (produced.kind !== "produced") throw new Error("expected produced outcome");
    expect(produced.normalized_result["version"]).toBe(DERIVED_GROUP_DREAM_VERSION);
    expect(produced.normalized_result["original_claim_revision_ids"]).toEqual([
      "claim:one:r1", "claim:two:r1",
    ]);
    expect(produced.normalized_result["group_projections"]).toHaveLength(1);
    expect(JSON.stringify(produced.normalized_result)).not.toContain("subject:owner");
    expect(derivedGroupDreamPreservesOriginals({
      version: DERIVED_GROUP_DREAM_VERSION,
      owner_account_id: owner,
      input_frontier: snapshot().input_frontier,
      projection_contract_digest: snapshot().projection_contract_digest,
      original_claims: snapshot().original_claims,
      group_memberships: snapshot().group_memberships,
      people_cluster_beliefs: snapshot().people_cluster_beliefs,
      created_at_event_time: snapshot().created_at_event_time,
    }, produced.normalized_result as never)).toBeTrue();
    expect(loadCalls).toBe(1);
  });

  test("fails closed on missing input, strategy mismatch, and withheld witness claims", async () => {
    const adapter = defineDerivedGroupDreamWorkAdapter({
      load_input: async () => ({ kind: "not_found" }),
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
      load_witness_claims: async () => ({ kind: "found", committed_revisions: [] }),
    });
    await expect(adapter.produce(context, leasedJob(), strategy)).resolves.toMatchObject({
      kind: "failed",
      error_code: "dependency_unavailable",
    });

    const mismatchStrategy = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: "strategy:dream:mismatch",
      work_kind: "derived_group_dream",
      coordinates: {
        ...strategyCoordinates,
        result_contract_version: "derived-group-dream-result:v0",
      },
    });
    const mismatchAdapter = defineDerivedGroupDreamWorkAdapter({
      load_input: async () => ({ kind: "found", snapshot: snapshot() }),
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
      load_witness_claims: async () => ({ kind: "found", committed_revisions: [] }),
    });
    await expect(mismatchAdapter.produce(context, leasedJob(), mismatchStrategy)).resolves.toMatchObject({
      kind: "failed",
      error_code: "dependency_unavailable",
    });

    await expect(adapter.materialize(context, leasedJob(), {} as never, strategy)).resolves.toMatchObject({
      kind: "failed",
      error_code: "dependency_unavailable",
    });
  });

  test("rejects a projection contract that does not match the registered strategy", async () => {
    const adapter = defineDerivedGroupDreamWorkAdapter({
      load_input: async () => ({
        kind: "found",
        snapshot: parseDerivedGroupDreamInputSnapshot({
          ...snapshot(),
          projection_contract_digest: digest("z"),
        }),
      }),
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
      load_witness_claims: async () => ({ kind: "found", committed_revisions: [] }),
    });
    await expect(adapter.produce(context, leasedJob(), strategy)).resolves.toMatchObject({
      kind: "failed",
      error_code: "dependency_unavailable",
    });
  });

  test("admits derived_group_dream as a consolidation adapter without activation", async () => {
    const adapter = defineDerivedGroupDreamConsolidationAdapter({
      load_input: async () => ({ kind: "found", snapshot: snapshot() }),
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
      load_witness_claims: async () => ({ kind: "found", committed_revisions: [] }),
    });
    expect(adapter.work_kind).toBe("derived_group_dream");
    await expect(adapter.produce(context, leasedJob(), strategy)).resolves.toMatchObject({
      kind: "produced",
    });
  });
});
