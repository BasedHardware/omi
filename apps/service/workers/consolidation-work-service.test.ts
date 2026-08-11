import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  expireDurableMemoryWorkLease,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
  succeedDurableMemoryWork,
  type DurableMemoryWorkJob,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { createAuthorizedLedgerWriteContextIssuer } from
  "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkExecutionRepository,
  type DurableMemoryWorkExecutionRepository,
  type DurableMemoryWorkLeaseNextOutcome,
} from "../stores/durable-memory-work-repository";
import {
  defineDurableMemoryWorkResultRepository,
  materializeStagedDurableMemoryWorkResult,
  type StagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import {
  defineDurableMemoryWorkSuccessRepository,
  durableMemoryWorkSuccessOutboxId,
} from "../stores/durable-memory-work-success-repository";
import {
  CONSOLIDATION_WORK_KINDS,
  defineConsolidationWorkAdapter,
  defineConsolidationWorkService,
  type ConsolidationWorkAdapter,
  type ConsolidationWorkKind,
  type ConsolidationWorkServiceDependencies,
} from "./consolidation-work-service";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();

const context = (overrides: {
  readonly principal_id?: string;
  readonly account_id?: string;
  readonly account_epoch?: number;
  readonly capability?: string;
} = {}) => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: overrides.principal_id ?? "worker:one",
  account_id: overrides.account_id ?? "account:alice",
  application_id: "app:consolidation-worker",
  credential_id: "credential:one",
  credential_generation: 1,
  capability: overrides.capability ?? "memories.work.execute",
  grant_id: "grant:one",
  grant_version: 1,
  account_epoch: overrides.account_epoch ?? 7,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const strategies = Object.fromEntries(CONSOLIDATION_WORK_KINDS.map((kind) => [
  kind,
  registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: `strategy:${kind}:authority`,
    work_kind: kind,
    coordinates: {
      strategy_version: `${kind}:v1`, model_version: "model:fake:v1",
      prompt_version: "prompt:v1", policy_version: "policy:v1",
      code_version: "code:v1", schema_version: "schema:v1",
      tokenizer_version: "none", tool_version: "none",
      result_contract_version: `${kind}-result-v1`,
      speaker_strategy_version: "none", boundary_strategy_version: "none",
    },
  }),
])) as Record<ConsolidationWorkKind, Readonly<RegisteredMemoryStrategy>>;

const job = (
  kind: DurableMemoryWorkKind,
  worker = "worker:one",
): Readonly<DurableMemoryWorkJob> => leaseDurableMemoryWork(acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: `job:${kind}:one`,
  owner_account_id: "account:alice",
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: kind,
  input_frontier: "frontier:one",
  input_digest: digest("b"),
  execution_contract_digest: kind === "formation"
    ? digest("f")
    : strategies[kind].execution_contract_digest,
  accepted_at_event_time: 100,
  max_attempts: 3,
}), worker, 101, 20);

const executionRepository = (
  leasedOutcome: DurableMemoryWorkLeaseNextOutcome = { kind: "none_available" },
  failures: string[] = [],
  failureJob: Readonly<DurableMemoryWorkJob> = job("promotion"),
): DurableMemoryWorkExecutionRepository => defineDurableMemoryWorkExecutionRepository({
  leaseNext: async () => leasedOutcome,
  load: async () => ({ kind: "not_found" }),
  recordFailure: async (_authorized, request) => {
    failures.push(request.error_code);
    return {
      kind: "recorded",
      job: failDurableMemoryWork(
        failureJob,
        { worker_id: failureJob.lease!.worker_id, fence: request.lease_fence },
        102,
        request.error_code,
        103,
      ),
    };
  },
  recoverExpired: async () => ({ kind: "not_expired" }),
});

const successRepository = () => defineDurableMemoryWorkSuccessRepository(
  async (_authorized, request) => ({
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
    sequence: request.authoritative_append === null ? null : 1,
    outbox_id: durableMemoryWorkSuccessOutboxId(request),
  }),
);

const adapters = (calls: ConsolidationWorkKind[]): Record<ConsolidationWorkKind, ConsolidationWorkAdapter> =>
  Object.fromEntries(CONSOLIDATION_WORK_KINDS.map((kind) => [
    kind,
    defineConsolidationWorkAdapter(kind, {
      produce: async (_authorized, leasedJob, strategy) => {
        calls.push(kind);
        expect(leasedJob.work_kind).toBe(kind);
        expect(strategy).toEqual(strategies[kind]);
        return {
          kind: "produced",
          result_contract_version: `${kind}-result-v1`,
          response_digest: digest("d"),
          normalized_result: { kind, outcome: "success" },
        };
      },
      materialize: async (_authorized, leasedJob, staged, strategy) => {
        expect(leasedJob.work_kind).toBe(kind);
        expect(staged.result_contract_version).toBe(`${kind}-result-v1`);
        expect(strategy).toEqual(strategies[kind]);
        return { kind: "ready", result_kind: "successful_empty", authoritative_append: null };
      },
    }),
  ])) as Record<ConsolidationWorkKind, ConsolidationWorkAdapter>;

const dependencies = (
  calls: ConsolidationWorkKind[],
  overrides: Partial<ConsolidationWorkServiceDependencies> = {},
): ConsolidationWorkServiceDependencies => ({
  execution_repository: executionRepository(),
  result_repository: defineDurableMemoryWorkResultRepository({
    load: async () => ({ kind: "missing" }),
    stage: async (_authorized, request) => ({
      kind: "staged", result: materializeStagedDurableMemoryWorkResult(request),
    }),
  }),
  success_repository: successRepository(),
  resolve_strategy: async (leasedJob) =>
    strategies[leasedJob.work_kind as ConsolidationWorkKind] ?? null,
  adapters: adapters(calls),
  max_parent_rematerializations: 2,
  ...overrides,
});

describe("production-neutral consolidation work service", () => {
  test("all three kinds use exactly their durable adapter and atomic-success path", async () => {
    const calls: ConsolidationWorkKind[] = [];
    const service = defineConsolidationWorkService(dependencies(calls));
    for (const kind of CONSOLIDATION_WORK_KINDS) {
      await expect(service.run(context(), job(kind))).resolves.toMatchObject({
        kind: "succeeded",
        producer_calls: 1,
        materialization_attempts: 1,
        outcome: { commit_id: null, sequence: null },
      });
    }
    expect(calls).toEqual([...CONSOLIDATION_WORK_KINDS]);
    expect(Object.keys(service)).toEqual(["run", "runNext"]);
  });

  test("authority, lease, and formation fences stop before any dependency", async () => {
    let strategyCalls = 0;
    const adapterCalls: ConsolidationWorkKind[] = [];
    const service = defineConsolidationWorkService(dependencies(adapterCalls, {
      resolve_strategy: async () => { strategyCalls += 1; throw new Error("must not resolve"); },
    }));
    const pending = acceptDurableMemoryWork({
      version: DURABLE_MEMORY_WORK_VERSION,
      job_id: "job:promotion:pending",
      owner_account_id: "account:alice",
      account_epoch: 7,
      lifecycle_state: "active",
      deletion_epoch: null,
      work_kind: "promotion",
      input_frontier: "frontier:one",
      input_digest: digest("b"),
      execution_contract_digest: strategies.promotion.execution_contract_digest,
      accepted_at_event_time: 100,
      max_attempts: 3,
    });

    for (const [authorized, candidate, stop] of [
      [context({ capability: "memories.work.accept" }), job("promotion"), "authorization_or_context"],
      [context({ account_id: "account:bob" }), job("promotion"), "authorization_or_context"],
      [context({ account_epoch: 8 }), job("promotion"), "authorization_or_context"],
      [context(), pending, "ineligible_state"],
      [context(), job("formation"), "ineligible_state"],
    ] as const) {
      await expect(service.run(authorized, candidate)).resolves.toMatchObject({
        kind: "stopped", stop_code: stop, producer_calls: 0, materialization_attempts: 0,
      });
    }
    expect({ strategyCalls, adapterCalls }).toEqual({ strategyCalls: 0, adapterCalls: [] });
  });

  test("strategy mismatch records a closed durable failure without adapter access", async () => {
    const failures: string[] = [];
    const adapterCalls: ConsolidationWorkKind[] = [];
    const identityJob = job("identity_cluster");
    const service = defineConsolidationWorkService(dependencies(adapterCalls, {
      execution_repository: executionRepository({ kind: "none_available" }, failures, identityJob),
      resolve_strategy: async () => strategies.promotion,
    }));
    await expect(service.run(context(), identityJob)).resolves.toMatchObject({
      kind: "failure_recorded",
      error_code: "dependency_unavailable",
      producer_calls: 0,
      materialization_attempts: 0,
    });
    expect(adapterCalls).toEqual([]);
    expect(failures).toEqual(["dependency_unavailable"]);
  });

  test("invalid semantic output becomes an attributable durable failure", async () => {
    const failures: string[] = [];
    const promotionJob = job("promotion");
    const invalidAdapters = adapters([]);
    invalidAdapters.promotion = defineConsolidationWorkAdapter("promotion", {
      produce: async () => ({
        kind: "produced",
        result_contract_version: "promotion-result-v1",
        response_digest: digest("d"),
        normalized_result: {},
        unexpected_raw_field: "transcript sentinel",
      } as never),
      materialize: async () => { throw new Error("must not materialize invalid output"); },
    });
    const service = defineConsolidationWorkService(dependencies([], {
      execution_repository: executionRepository({ kind: "none_available" }, failures, promotionJob),
      adapters: invalidAdapters,
    }));
    const outcome = await service.run(context(), promotionJob);
    expect(outcome).toMatchObject({
      kind: "failure_recorded", error_code: "model_response_invalid",
      producer_calls: 1, materialization_attempts: 0,
    });
    expect(JSON.stringify(outcome)).not.toContain("transcript sentinel");
    expect(failures).toEqual(["model_response_invalid"]);

    const materializeFailures: string[] = [];
    const invalidMaterializer = adapters([]);
    invalidMaterializer.promotion = defineConsolidationWorkAdapter("promotion", {
      produce: async () => ({
        kind: "produced", result_contract_version: "promotion-result-v1",
        response_digest: digest("d"), normalized_result: {},
      }),
      materialize: async () => ({
        kind: "ready", result_kind: "successful_empty", authoritative_append: null,
        unexpected_raw_field: "another transcript sentinel",
      } as never),
    });
    const materializeService = defineConsolidationWorkService(dependencies([], {
      execution_repository: executionRepository(
        { kind: "none_available" }, materializeFailures, promotionJob,
      ),
      adapters: invalidMaterializer,
    }));
    const materializeOutcome = await materializeService.run(context(), promotionJob);
    expect(materializeOutcome).toMatchObject({
      kind: "failure_recorded", error_code: "model_response_invalid",
      producer_calls: 1, materialization_attempts: 1,
    });
    expect(JSON.stringify(materializeOutcome)).not.toContain("another transcript sentinel");
    expect(materializeFailures).toEqual(["model_response_invalid"]);
  });

  test("a later lease reuses the immutable stage with zero producer calls", async () => {
    const first = job("promotion");
    let staged: StagedDurableMemoryWorkResult | null = null;
    let firstCalls = 0;
    const firstAdapterCalls: ConsolidationWorkKind[] = [];
    const firstService = defineConsolidationWorkService(dependencies(firstAdapterCalls, {
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => ({ kind: "missing" }),
        stage: async (_authorized, request) => {
          firstCalls += 1;
          staged = materializeStagedDurableMemoryWorkResult(request);
          return { kind: "staged", result: staged };
        },
      }),
      success_repository: defineDurableMemoryWorkSuccessRepository(async () => ({ kind: "stale_lease" })),
    }));
    await expect(firstService.run(context(), first)).resolves.toMatchObject({
      kind: "stopped", stop_code: "stale_lease", producer_calls: 1,
    });
    expect(staged).not.toBeNull();
    expect(firstCalls).toBe(1);

    const recovered = expireDurableMemoryWorkLease(first, 121, 122);
    const later = leaseDurableMemoryWork(recovered, "worker:two", 122, 20);
    let replayProducerCalls = 0;
    const replayAdapters = adapters([]);
    replayAdapters.promotion = defineConsolidationWorkAdapter("promotion", {
      produce: async () => {
        replayProducerCalls += 1;
        throw new Error("must not produce twice");
      },
      materialize: async () => ({
        kind: "ready", result_kind: "successful_empty", authoritative_append: null,
      }),
    });
    const replayService = defineConsolidationWorkService(dependencies([], {
      execution_repository: executionRepository({ kind: "none_available" }, [], later),
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => ({ kind: "found", result: staged }),
        stage: async () => ({ kind: "idempotency_conflict" }),
      }),
      adapters: replayAdapters,
    }));
    await expect(replayService.run(context({ principal_id: "worker:two" }), later))
      .resolves.toMatchObject({ kind: "succeeded", producer_calls: 0, materialization_attempts: 1 });
    expect(replayProducerCalls).toBe(0);
  });

  test("one-shot dispatch is deterministic, bounded, and content-safe", async () => {
    const promotionJob = job("promotion");
    const requested: DurableMemoryWorkKind[][] = [];
    let leases = 0;
    const repository = defineDurableMemoryWorkExecutionRepository({
      leaseNext: async (_authorized, request) => {
        requested.push([...request.work_kinds]);
        leases += 1;
        return { kind: "leased", job: promotionJob };
      },
      load: async () => ({ kind: "not_found" }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({ kind: "not_expired" }),
    });
    const service = defineConsolidationWorkService(dependencies([], {
      execution_repository: repository,
    }));
    const outcome = await service.runNext(context());
    expect(outcome).toEqual({
      kind: "completed", result: "succeeded", error_code: null,
      leased: 1, producer_calls: 1, materialization_attempts: 1,
    });
    expect({ requested, leases }).toEqual({ requested: [[...CONSOLIDATION_WORK_KINDS]], leases: 1 });
    expect(JSON.stringify(outcome)).not.toMatch(/account:|job:|commit:|frontier:|credential:/);
  });

  test("idle, repository exceptions, and hostile adapters fail closed", async () => {
    const idle = defineConsolidationWorkService(dependencies([], {
      execution_repository: executionRepository({ kind: "none_available" }),
    }));
    await expect(idle.runNext(context())).resolves.toEqual({
      kind: "idle", leased: 0, producer_calls: 0, materialization_attempts: 0,
    });

    const unavailable = defineConsolidationWorkService(dependencies([], {
      execution_repository: defineDurableMemoryWorkExecutionRepository({
        leaseNext: async () => { throw new Error("database echoed raw transcript"); },
        load: async () => ({ kind: "not_found" }),
        recordFailure: async () => ({ kind: "ineligible_state" }),
        recoverExpired: async () => ({ kind: "not_expired" }),
      }),
    }));
    await expect(unavailable.runNext(context())).resolves.toEqual({
      kind: "stopped", stop_code: "storage_retryable", leased: 0,
      producer_calls: 0, materialization_attempts: 0,
    });

    expect(() => defineConsolidationWorkAdapter(
      "promotion",
      new Proxy({ produce: async () => ({}), materialize: async () => ({}) }, {}) as never,
    )).toThrow("invalid_adapter");
    const forged = { ...adapters([]), promotion: {
      work_kind: "promotion",
      produce: async () => ({}),
      materialize: async () => ({}),
    } as unknown as ConsolidationWorkAdapter };
    expect(() => defineConsolidationWorkService(dependencies([], { adapters: forged })))
      .toThrow("unsealed_adapter");
  });
});
