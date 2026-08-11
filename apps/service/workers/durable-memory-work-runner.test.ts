import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  expireDurableMemoryWorkLease,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
  succeedDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { prepareDerivation, type AtomicGraphTransition } from "../../../core/ledger";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  authoritativeAppendRequestDigest,
  type AuthoritativeLedgerAppend,
} from "../stores/authoritative-ledger-repository";
import { defineDurableMemoryWorkExecutionRepository } from "../stores/durable-memory-work-repository";
import {
  defineDurableMemoryWorkResultRepository,
  materializeStagedDurableMemoryWorkResult,
  type StagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import {
  defineDurableMemoryWorkSuccessRepository,
  durableMemoryWorkSuccessOutboxId,
} from "../stores/durable-memory-work-success-repository";
import { defineDurableMemoryWorkRunner } from "./durable-memory-work-runner";

const digest = (character: string): string => character.repeat(64);

const registeredStrategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:promotion:authority",
  work_kind: "promotion",
  coordinates: {
    strategy_version: "strategy:v1", model_version: "model:v1",
    prompt_version: "prompt:v1", policy_version: "policy:v1",
    code_version: "code:v1", schema_version: "schema:v1",
    tokenizer_version: "tokenizer:v1", tool_version: "tool:v1",
    result_contract_version: "promotion-result:v1",
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
});

const context = (principal = "worker:one") => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: principal,
  account_id: "account:alice",
  application_id: "app:worker",
  credential_id: "credential:one",
  credential_generation: 4,
  capability: "memories.work.execute",
  grant_id: "grant:one",
  grant_version: 9,
  account_epoch: 7,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const leased = () => leaseDurableMemoryWork(acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:promotion:one",
  owner_account_id: "account:alice",
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "promotion",
  input_frontier: "frontier:one",
  input_digest: digest("b"),
  execution_contract_digest: registeredStrategy.execution_contract_digest,
  accepted_at_event_time: 100,
  max_attempts: 3,
}), "worker:one", 101, 20);

const append = (attempt: number): AuthoritativeLedgerAppend => {
  const parent = attempt === 1 ? null : "commit:intervening";
  const transition: AtomicGraphTransition = {
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation: prepareDerivation({
      attempt_id: `attempt:promotion:${attempt}`,
      commit_id: `commit:promotion:${attempt}`,
      owner_account_id: "account:alice",
      parent_commit: parent,
      idempotency_key: `append:promotion:${attempt}`,
      input_revisions: [],
      output_revisions: [],
      versions: {
        strategy_version: "strategy:v1", model_version: "model:v1",
        prompt_version: "prompt:v1", policy_version: "policy:v1",
        code_version: "code:v1", schema_version: "schema:v1",
        tokenizer_version: "tokenizer:v1", tool_version: "tool:v1",
      },
      success_kind: "success",
    }),
    revisions: [], adjacency: [], artifacts: [],
  };
  const origin = { kind: "non_formation" as const, reason: "promotion" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: parent,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin,
    transition,
  };
};

const workRepository = (failures: string[], job = leased()) => defineDurableMemoryWorkExecutionRepository({
  leaseNext: async () => ({ kind: "none_available" }),
  load: async () => ({ kind: "not_found" }),
  recordFailure: async (_authorized, request) => {
    failures.push(request.error_code);
    return {
      kind: "recorded",
      job: failDurableMemoryWork(
        job,
        { worker_id: job.lease!.worker_id, fence: request.lease_fence },
        job.lease!.leased_at_event_time + 1,
        request.error_code,
        job.lease!.leased_at_event_time + 2,
      ),
    };
  },
  recoverExpired: async () => ({ kind: "not_expired" }),
});

const successRepository = (staleParents: { remaining: number }) =>
  defineDurableMemoryWorkSuccessRepository(async (_authorized, request) => {
    if (staleParents.remaining > 0) {
      staleParents.remaining -= 1;
      return { kind: "stale_parent" };
    }
    return {
      kind: "committed",
      job: succeedDurableMemoryWork(
        request.leased_job,
        {
          worker_id: request.leased_job.lease!.worker_id,
          fence: request.leased_job.lease!.fence,
        },
        request.leased_job.lease!.leased_at_event_time + 1,
        request.result_kind,
        request.response_digest,
        request.result_digest,
      ),
      commit_id: request.authoritative_append?.transition.derivation.commit.commit_id ?? null,
      sequence: request.authoritative_append === null ? null : 2,
      outbox_id: durableMemoryWorkSuccessOutboxId(request),
    };
  });

describe("production-neutral durable memory work runner", () => {
  test("stage miss calls the model once and stale parent rematerializes without calling it again", async () => {
    let stored: StagedDurableMemoryWorkResult | null = null;
    let modelCalls = 0;
    let materializations = 0;
    const resultRepository = defineDurableMemoryWorkResultRepository({
      load: async () => stored === null ? { kind: "missing" } : { kind: "found", result: stored },
      stage: async (_authorized, request) => {
        stored = materializeStagedDurableMemoryWorkResult(request);
        return { kind: "staged", result: stored };
      },
    });
    const runner = defineDurableMemoryWorkRunner({
      work_repository: workRepository([]),
      result_repository: resultRepository,
      success_repository: successRepository({ remaining: 1 }),
      resolve_strategy: async () => registeredStrategy,
      produce: async () => {
        modelCalls += 1;
        return {
          kind: "produced",
          result_contract_version: "promotion-result:v1",
          response_digest: digest("d"),
          normalized_result: { boundary_decision: "accept_ltm" },
        };
      },
      materialize: async () => {
        materializations += 1;
        return {
          kind: "ready",
          result_kind: "successful",
          authoritative_append: append(materializations),
        };
      },
      max_parent_rematerializations: 3,
    });

    await expect(runner.run(context(), leased())).resolves.toMatchObject({
      kind: "succeeded",
      model_calls: 1,
      materialization_attempts: 2,
      outcome: { commit_id: "commit:promotion:2", sequence: 2 },
    });
    expect(modelCalls).toBe(1);
    expect(materializations).toBe(2);
    expect(stored).not.toBeNull();
    expect(Object.keys(runner)).toEqual(["run"]);
  });

  test("restart under a later lease reuses the committed stage with zero model calls", async () => {
    const firstLease = leased();
    let stored: StagedDurableMemoryWorkResult | null = null;
    const bootstrap = defineDurableMemoryWorkResultRepository({
      load: async () => ({ kind: "missing" }),
      stage: async (_authorized, request) => {
        stored = materializeStagedDurableMemoryWorkResult(request);
        return { kind: "staged", result: stored };
      },
    });
    const firstRunner = defineDurableMemoryWorkRunner({
      work_repository: workRepository([]),
      result_repository: bootstrap,
      success_repository: defineDurableMemoryWorkSuccessRepository(async () => ({ kind: "stale_lease" })),
      resolve_strategy: async () => registeredStrategy,
      produce: async () => ({
        kind: "produced", result_contract_version: "promotion-result:v1",
        response_digest: digest("d"), normalized_result: { boundary_decision: "accept_ltm" },
      }),
      materialize: async () => ({
        kind: "ready", result_kind: "successful_empty", authoritative_append: null,
      }),
      max_parent_rematerializations: 1,
    });
    await firstRunner.run(context(), firstLease);
    expect(stored).not.toBeNull();

    const recovered = expireDurableMemoryWorkLease(firstLease, 121, 122);
    const laterLease = leaseDurableMemoryWork(recovered, "worker:two", 122, 20);
    let modelCalls = 0;
    const replayRepository = defineDurableMemoryWorkResultRepository({
      load: async () => ({ kind: "found", result: stored }),
      stage: async () => ({ kind: "idempotency_conflict" }),
    });
    const replayRunner = defineDurableMemoryWorkRunner({
      work_repository: workRepository([]),
      result_repository: replayRepository,
      success_repository: successRepository({ remaining: 0 }),
      resolve_strategy: async () => registeredStrategy,
      produce: async () => {
        modelCalls += 1;
        throw new Error("must not call model");
      },
      materialize: async () => ({
        kind: "ready", result_kind: "successful_empty", authoritative_append: null,
      }),
      max_parent_rematerializations: 1,
    });
    await expect(replayRunner.run(context("worker:two"), laterLease)).resolves.toMatchObject({
      kind: "succeeded", model_calls: 0, materialization_attempts: 1,
      outcome: { commit_id: null, sequence: null },
    });
    expect(modelCalls).toBe(0);
  });

  test("bounded stale-parent exhaustion records a closed failure without another model call", async () => {
    const failures: string[] = [];
    let materializations = 0;
    const runner = defineDurableMemoryWorkRunner({
      work_repository: workRepository(failures),
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => ({ kind: "missing" }),
        stage: async (_authorized, request) => ({
          kind: "staged", result: materializeStagedDurableMemoryWorkResult(request),
        }),
      }),
      success_repository: successRepository({ remaining: 5 }),
      resolve_strategy: async () => registeredStrategy,
      produce: async () => ({
        kind: "produced", result_contract_version: "promotion-result:v1",
        response_digest: digest("d"), normalized_result: { boundary_decision: "accept_ltm" },
      }),
      materialize: async () => {
        materializations += 1;
        return { kind: "ready", result_kind: "successful", authoritative_append: append(materializations) };
      },
      max_parent_rematerializations: 2,
    });
    await expect(runner.run(context(), leased())).resolves.toMatchObject({
      kind: "failure_recorded",
      error_code: "serialization_retryable",
      model_calls: 1,
      materialization_attempts: 2,
    });
    expect(failures).toEqual(["serialization_retryable"]);
  });

  test("worker resolves the exact registered strategy before model or staged-result use", async () => {
    const failures: string[] = [];
    let modelCalls = 0;
    const wrongStrategy = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: "strategy:promotion:wrong",
      work_kind: "promotion",
      coordinates: { ...registeredStrategy.coordinates, prompt_version: "prompt:wrong" },
    });
    const runner = defineDurableMemoryWorkRunner({
      work_repository: workRepository(failures),
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => { throw new Error("must not inspect staged result"); },
        stage: async () => { throw new Error("must not stage"); },
      }),
      success_repository: successRepository({ remaining: 0 }),
      resolve_strategy: async () => wrongStrategy,
      produce: async () => {
        modelCalls += 1;
        throw new Error("must not call model");
      },
      materialize: async () => { throw new Error("must not materialize"); },
      max_parent_rematerializations: 1,
    });
    await expect(runner.run(context(), leased())).resolves.toMatchObject({
      kind: "failure_recorded", error_code: "dependency_unavailable", model_calls: 0,
    });
    expect(modelCalls).toBe(0);
    expect(failures).toEqual(["dependency_unavailable"]);
  });

  test("worker rejects a producer result parsed under another result contract", async () => {
    const failures: string[] = [];
    const runner = defineDurableMemoryWorkRunner({
      work_repository: workRepository(failures),
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => ({ kind: "missing" }),
        stage: async () => { throw new Error("must not stage mismatched bytes"); },
      }),
      success_repository: successRepository({ remaining: 0 }),
      resolve_strategy: async () => registeredStrategy,
      produce: async () => ({
        kind: "produced", result_contract_version: "promotion-result:wrong",
        response_digest: digest("d"), normalized_result: { boundary_decision: "accept_ltm" },
      }),
      materialize: async () => { throw new Error("must not materialize"); },
      max_parent_rematerializations: 1,
    });
    await expect(runner.run(context(), leased())).resolves.toMatchObject({
      kind: "failure_recorded", error_code: "model_response_invalid", model_calls: 1,
      materialization_attempts: 0,
    });
    expect(failures).toEqual(["model_response_invalid"]);
  });
});
