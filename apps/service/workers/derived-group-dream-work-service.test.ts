import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { derivedGroupDreamProjectionContractDigest } from "../../../core/consolidate/derived-group-dream";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkExecutionRepository,
  durableMemoryWorkInputManifestDigest,
} from "../stores/durable-memory-work-repository";
import {
  defineDurableMemoryWorkResultRepository,
  materializeStagedDurableMemoryWorkResult,
  type StagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import { defineDurableMemoryWorkSuccessRepository } from "../stores/durable-memory-work-success-repository";
import {
  DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
} from "./derived-group-dream-contract";
import {
  derivedGroupDreamWorkInputManifest,
  parseDerivedGroupDreamInputSnapshot,
} from "./derived-group-dream-work-adapter";
import {
  defineDerivedGroupDreamWorkInputRepository,
  derivedGroupDreamWorkInputStageRequestDigest,
  materializeStagedDerivedGroupDreamWorkInput,
} from "./derived-group-dream-work-input-repository";
import { defineDerivedGroupDreamWorkService } from "./derived-group-dream-work-service";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;
const owner = "account:alice";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const executeContext = issuer.issue({
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
  strategy_id: "strategy:dream:service",
  work_kind: "derived_group_dream",
  coordinates: strategyCoordinates,
});

const snapshot = () => parseDerivedGroupDreamInputSnapshot({
  version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  owner_account_id: owner,
  job_id: "job:dream:service",
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

const pendingJob = () => acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: snapshot().job_id,
  owner_account_id: owner,
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "derived_group_dream",
  input_frontier: snapshot().input_frontier,
  input_digest: durableMemoryWorkInputManifestDigest(derivedGroupDreamWorkInputManifest(snapshot())),
  execution_contract_digest: strategy.execution_contract_digest,
  accepted_at_event_time: 100,
  max_attempts: 2,
});

const leasedJob = () => leaseDurableMemoryWork(pendingJob(), "worker:one", 101, 20);

describe("derived group dream work service", () => {
  test("fences work kind and withholds success commit after planning", async () => {
    const failures: string[] = [];
    const job = leasedJob();
    const pending = pendingJob();
    const stagedInput = materializeStagedDerivedGroupDreamWorkInput({
      pending_job: pending,
      snapshot: snapshot(),
      request_digest: derivedGroupDreamWorkInputStageRequestDigest({
        pending_job: pending,
        snapshot: snapshot(),
      }),
    });
    let storedResult: StagedDurableMemoryWorkResult | null = null;
    const service = defineDerivedGroupDreamWorkService({
      execution_repository: defineDurableMemoryWorkExecutionRepository({
        leaseNext: async () => ({ kind: "none_available" }),
        load: async () => ({ kind: "found", job }),
        recordFailure: async (_authorized, request) => {
          failures.push(request.error_code);
          return {
            kind: "recorded",
            job: failDurableMemoryWork(
              job,
              { worker_id: "worker:one", fence: job.lease!.fence },
              102,
              request.error_code,
              103,
            ),
          };
        },
        recoverExpired: async () => ({ kind: "not_expired" }),
      }),
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => (storedResult ? { kind: "found", result: storedResult } : { kind: "missing" }),
        stage: async (_authorized, request) => {
          storedResult = materializeStagedDurableMemoryWorkResult(request);
          return { kind: "staged", result: storedResult };
        },
      }),
      success_repository: defineDurableMemoryWorkSuccessRepository(async () => ({
        kind: "ineligible_state",
      })),
      input_repository: defineDerivedGroupDreamWorkInputRepository({
        stage: async () => ({ kind: "idempotency_conflict" }),
        load: async () => ({ kind: "found", input: stagedInput }),
      }),
      resolve_strategy: async () => strategy,
      dream: {},
      max_parent_rematerializations: 1,
    });

    await expect(service.run(executeContext, leaseDurableMemoryWork(
      acceptDurableMemoryWork({
        version: DURABLE_MEMORY_WORK_VERSION,
        job_id: "job:predicate:fence",
        owner_account_id: owner,
        account_epoch: 7,
        lifecycle_state: "active",
        deletion_epoch: null,
        work_kind: "predicate_batch",
        input_frontier: digest("1"),
        input_digest: digest("2"),
        execution_contract_digest: strategy.execution_contract_digest,
        accepted_at_event_time: 100,
        max_attempts: 2,
      }),
      "worker:one",
      101,
      20,
    ))).resolves.toMatchObject({
      kind: "stopped",
      stop_code: "ineligible_state",
      producer_calls: 0,
    });

    await expect(service.run(executeContext, job)).resolves.toMatchObject({
      kind: "failure_recorded",
      error_code: "dependency_unavailable",
      producer_calls: 1,
      materialization_attempts: 1,
    });
    expect(failures).toEqual(["dependency_unavailable"]);
    expect(storedResult?.work_kind).toBe("derived_group_dream");
  });
});
