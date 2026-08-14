import { expect, test } from "bun:test";

import { predicateIdForName, predicateRevisionForObservation } from "../../../core/consolidate/predicate-identity";
import { predicateAlignmentBatchDigest, preparePredicateAlignmentQuestion } from "../../../core/consolidate/relations";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
  succeedDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { Predicate } from "../../../core/schema";
import { DeterministicFakeModel } from "../../../drivers/model/port";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkExecutionRepository,
  durableMemoryWorkInputManifestDigest,
} from "../stores/durable-memory-work-repository";
import {
  defineDurableMemoryWorkResultRepository,
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  materializeStagedDurableMemoryWorkResult,
  normalizeDurableMemoryWorkResultJson,
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
} from "./consolidation-work-service";
import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from "./durable-memory-graph-plan";
import {
  PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION,
  definePredicateBatchWorkAdapter,
  definePredicateBatchConsolidationWorkAdapter,
  predicateBatchWorkInputManifest,
  type PredicateBatchInputSnapshot,
} from "./predicate-batch-work-adapter";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";
const jobId = "job:predicate:one";
const frontier = "frontier:predicate:one";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:one",
  account_id: owner,
  application_id: "app:memory-worker",
  credential_id: "credential:one",
  credential_generation: 1,
  capability: "memories.work.execute",
  grant_id: "grant:one",
  grant_version: 1,
  account_epoch: 7,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const strategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:predicate:authority",
  work_kind: "predicate_batch",
  coordinates: {
    strategy_version: "predicate-alignment-v3",
    model_version: "model:fake:v1",
    prompt_version: "predicate-prompt-v2",
    policy_version: "predicate-policy-v1",
    code_version: "relations-exhaustive-v3",
    schema_version: "predicate-response-v2",
    tokenizer_version: "none",
    tool_version: "none",
    result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
    speaker_strategy_version: "none",
    boundary_strategy_version: "none",
  },
});

const predicate = (name: string, roles: readonly string[] = ["subject"]): Predicate =>
  predicateRevisionForObservation({
    owner_account_id: owner,
    predicate_id: predicateIdForName(name),
    display_name: name,
    roles,
    lifecycle: "canonical",
  }).predicate;

const predicates = [predicate("alpha relation", ["subject"]), predicate("bravo relation", ["object"])];
const contract = {
  model_version: strategy.coordinates.model_version,
  strategy: "predicate-alignment",
  prompt_version: strategy.coordinates.prompt_version,
  schema_version: strategy.coordinates.schema_version,
  code_version: strategy.coordinates.code_version,
};

const snapshot = (overrides: Partial<PredicateBatchInputSnapshot> = {}): PredicateBatchInputSnapshot => {
  const selected = overrides.predicates ?? predicates;
  const question = preparePredicateAlignmentQuestion(selected, overrides.owner_account_id ?? owner).request;
  return {
    version: PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION,
    owner_account_id: owner,
    job_id: jobId,
    input_frontier: frontier,
    batch_question_digest: predicateAlignmentBatchDigest(contract, question),
    predicates: selected,
    ...overrides,
  };
};

const leasedJob = (input: PredicateBatchInputSnapshot = snapshot()) => leaseDurableMemoryWork(
  acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: jobId,
    owner_account_id: owner,
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: "predicate_batch",
    input_frontier: frontier,
    input_digest: durableMemoryWorkInputManifestDigest(predicateBatchWorkInputManifest(input)),
    execution_contract_digest: strategy.execution_contract_digest,
    accepted_at_event_time: 100,
    max_attempts: 3,
  }),
  "worker:one",
  101,
  20,
);

const staged = (
  job: ReturnType<typeof leasedJob>,
  produced: Extract<Awaited<ReturnType<ReturnType<typeof definePredicateBatchWorkAdapter>["produce"]>>, { kind: "produced" }>,
): StagedDurableMemoryWorkResult => {
  const normalized = normalizeDurableMemoryWorkResultJson(produced.normalized_result);
  const body = {
    leased_job: job,
    result_contract_version: produced.result_contract_version,
    response_digest: produced.response_digest,
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest(produced.result_contract_version, normalized),
    normalized_result: normalized,
  };
  return materializeStagedDurableMemoryWorkResult({
    ...body,
    request_digest: durableMemoryWorkResultStageRequestDigest(body),
  });
};

test("one exact predicate question produces one assertion plan and rematerializes only its parent", async () => {
  let modelCalls = 0;
  let modelSignal: AbortSignal | undefined;
  const lossController = new AbortController();
  const input = snapshot();
  const job = leasedJob(input);
  const adapter = definePredicateBatchWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: input }),
    resolve_model: async () => new DeterministicFakeModel((request) => {
      modelCalls += 1;
      modelSignal = request.signal;
      expect(request.strategy).toBe("predicate-alignment");
      expect(request.version).toBe(strategy.coordinates.prompt_version);
      return { assertions: [{
        predicate_id: predicateIdForName("alpha relation"),
        target_predicate_id: predicateIdForName("bravo relation"),
        slot_aliases: [{ from_slot_id: "subject", to_slot_id: "object" }],
      }] };
    }),
    load_current_parent: async () => ({ kind: "found", parent_commit: null }),
  });
  const produced = await adapter.produce(context, job, strategy, lossController.signal);
  expect(produced).toMatchObject({ kind: "produced", result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION });
  if (produced.kind !== "produced") throw new Error("expected produced");
  expect(modelCalls).toBe(1);
  expect(modelSignal).toBe(lossController.signal);
  const stored = staged(job, produced);
  const first = await adapter.materialize(context, job, stored, strategy);
  expect(first).toMatchObject({ kind: "ready", result_kind: "successful" });
  if (first.kind !== "ready" || first.authoritative_append === null) throw new Error("expected append");
  expect(first.authoritative_append.transition.revisions).toHaveLength(1);
  expect(first.authoritative_append.transition.revisions[0]).toMatchObject({ kind: "predicate_assertion" });

  const secondAdapter = definePredicateBatchWorkAdapter({
    load_input: async () => { throw new Error("materialize never reloads semantic input"); },
    resolve_model: async () => { throw new Error("materialize never resolves model"); },
    load_current_parent: async () => ({ kind: "found", parent_commit: "commit:later" }),
  });
  const second = await secondAdapter.materialize(context, job, stored, strategy);
  expect(second).toMatchObject({ kind: "ready", result_kind: "successful" });
  if (second.kind !== "ready" || second.authoritative_append === null) throw new Error("expected append");
  expect(second.authoritative_append.transition.derivation.commit.parent_commit).toBe("commit:later");
  expect(second.authoritative_append.transition.revisions).toEqual(first.authoritative_append.transition.revisions);
  expect(modelCalls).toBe(1);

  const unavailableParent = definePredicateBatchWorkAdapter({
    load_input: async () => { throw new Error("not used"); },
    resolve_model: async () => { throw new Error("not used"); },
    load_current_parent: async () => ({ kind: "failed", error_code: "serialization_retryable" }),
  });
  await expect(unavailableParent.materialize(context, job, stored, strategy)).resolves.toEqual({
    kind: "failed", error_code: "serialization_retryable",
  });
});

test("a valid empty answer is durable successful-empty with no graph append", async () => {
  const input = snapshot();
  const job = leasedJob(input);
  const adapter = definePredicateBatchWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: input }),
    resolve_model: async () => new DeterministicFakeModel({ assertions: [] }),
    load_current_parent: async () => { throw new Error("empty result needs no parent"); },
  });
  const produced = await adapter.produce(context, job, strategy);
  if (produced.kind !== "produced") throw new Error("expected produced");
  await expect(adapter.materialize(context, job, staged(job, produced), strategy)).resolves.toEqual({
    kind: "ready",
    result_kind: "successful_empty",
    authoritative_append: null,
  });
});

test("snapshot, manifest, question, owner, and strategy drift fail before model use", async () => {
  let modelCalls = 0;
  const base = snapshot();
  const cases: { input: PredicateBatchInputSnapshot; job: ReturnType<typeof leasedJob>; usedStrategy?: typeof strategy }[] = [
    { input: { ...base, batch_question_digest: digest("f") }, job: leasedJob(base) },
    { input: { ...base, owner_account_id: "account:bob" }, job: leasedJob(base) },
    { input: { ...base, input_frontier: "frontier:other" }, job: leasedJob(base) },
  ];
  for (const item of cases) {
    const adapter = definePredicateBatchWorkAdapter({
      load_input: async () => ({ kind: "found", snapshot: item.input }),
      resolve_model: async () => { modelCalls += 1; return new DeterministicFakeModel({ assertions: [] }); },
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
    });
    await expect(adapter.produce(context, item.job, item.usedStrategy ?? strategy)).resolves.toEqual({
      kind: "failed", error_code: "dependency_unavailable",
    });
  }
  const wrongStrategy = registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: "strategy:predicate:wrong",
    work_kind: "predicate_batch",
    coordinates: { ...strategy.coordinates, prompt_version: "predicate-prompt-wrong" },
  });
  const strategyAdapter = definePredicateBatchWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: base }),
    resolve_model: async () => { modelCalls += 1; return new DeterministicFakeModel({ assertions: [] }); },
    load_current_parent: async () => ({ kind: "found", parent_commit: null }),
  });
  await expect(strategyAdapter.produce(context, leasedJob(base), wrongStrategy)).resolves.toEqual({
    kind: "failed", error_code: "dependency_unavailable",
  });
  expect(modelCalls).toBe(0);
});

test("malformed model output is not empty success and invoke failures stay content-safe", async () => {
  const input = snapshot();
  const job = leasedJob(input);
  for (const response of [{ assertions: "bad" }, new Error("SECRET transcript echo")]) {
    const adapter = definePredicateBatchWorkAdapter({
      load_input: async () => ({ kind: "found", snapshot: input }),
      resolve_model: async () => response instanceof Error
        ? ({
            invoke: async () => { throw response; },
            render: async () => ({ summary_text: "", citations: [] }),
            compose: async () => ({ answer_text: "", citations: [], assertions: [] }),
          })
        : new DeterministicFakeModel(response),
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
    });
    const result = await adapter.produce(context, job, strategy);
    expect(result.kind).toBe("failed");
    expect(JSON.stringify(result)).not.toContain("SECRET");
    expect(result).toEqual({
      kind: "failed",
      error_code: response instanceof Error ? "dependency_unavailable" : "model_response_invalid",
    });
  }
});

test("invented, self, cross-question, and invalid-role proposals cannot enter authority", async () => {
  const input = snapshot();
  const job = leasedJob(input);
  const adapter = definePredicateBatchWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: input }),
    resolve_model: async () => new DeterministicFakeModel({ assertions: [
      { predicate_id: "predicate:invented", target_predicate_id: predicateIdForName("bravo relation") },
      { predicate_id: predicateIdForName("alpha relation"), target_predicate_id: predicateIdForName("alpha relation") },
      { predicate_id: predicateIdForName("alpha relation"), target_predicate_id: predicateIdForName("bravo relation"), slot_aliases: [{ from_slot_id: "invented", to_slot_id: "object" }] },
    ] }),
    load_current_parent: async () => ({ kind: "found", parent_commit: null }),
  });
  const produced = await adapter.produce(context, job, strategy);
  if (produced.kind !== "produced") throw new Error("expected rejected-proposal success");
  await expect(adapter.materialize(context, job, staged(job, produced), strategy)).resolves.toEqual({
    kind: "ready", result_kind: "successful_empty", authoritative_append: null,
  });
});

test("dependency containers and stored inputs reject proxies and accessors without invocation", async () => {
  expect(() => definePredicateBatchWorkAdapter(new Proxy({
    load_input: async () => ({ kind: "not_found" }),
    resolve_model: async () => null,
    load_current_parent: async () => ({ kind: "failed", error_code: "dependency_unavailable" }),
  }, {}) as never)).toThrow("invalid_dependencies");

  const accessor = {} as Record<string, unknown>;
  Object.defineProperty(accessor, "predicates", { get: () => predicates });
  const adapter = definePredicateBatchWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: accessor as never }),
    resolve_model: async () => { throw new Error("must not resolve"); },
    load_current_parent: async () => ({ kind: "found", parent_commit: null }),
  });
  await expect(adapter.produce(context, leasedJob(), strategy)).resolves.toEqual({
    kind: "failed", error_code: "dependency_unavailable",
  });
});

test("an exact oversized question fails with prompt budget before model or parent access", async () => {
  const huge = "x".repeat(12_000);
  const input = snapshot({ predicates: [predicate(`${huge} alpha`), predicate(`${huge} bravo`)] });
  const job = leasedJob(input);
  let modelCalls = 0;
  const adapter = definePredicateBatchWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: input }),
    resolve_model: async () => { modelCalls += 1; return new DeterministicFakeModel({ assertions: [] }); },
    load_current_parent: async () => { throw new Error("must not load parent"); },
  });
  await expect(adapter.produce(context, job, strategy)).resolves.toEqual({
    kind: "failed", error_code: "prompt_budget_exceeded",
  });
  expect(modelCalls).toBe(0);
});

test("legacy predicate identity cannot become a successful durable question", async () => {
  const legacy: Predicate = {
    predicate_id: "predicate:legacy-window-slots",
    owner_account_id: owner,
    predicate_revision_id: "predicate:legacy-window-slots:revision:one",
    identity_version: "name-slots-v1",
    identity_name: "legacy relation",
    display_name: "legacy relation",
    lifecycle: "canonical",
    slot_ids: ["window-slot-1"],
  };
  const input = snapshot({ predicates: [legacy, predicates[1]!] });
  const job = leasedJob(input);
  let modelCalls = 0;
  const adapter = definePredicateBatchWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: input }),
    resolve_model: async () => { modelCalls += 1; return new DeterministicFakeModel({ assertions: [] }); },
    load_current_parent: async () => ({ kind: "found", parent_commit: null }),
  });
  await expect(adapter.produce(context, job, strategy)).resolves.toEqual({
    kind: "failed", error_code: "dependency_unavailable",
  });
  expect(modelCalls).toBe(0);
});

test("the sealed predicate adapter runs through the single consolidation service and replays the stage", async () => {
  const input = snapshot();
  const job = leasedJob(input);
  let modelCalls = 0;
  let stored: StagedDurableMemoryWorkResult | null = null;
  const predicateAdapter = definePredicateBatchConsolidationWorkAdapter({
    load_input: async () => ({ kind: "found", snapshot: input }),
    resolve_model: async () => new DeterministicFakeModel(() => {
      modelCalls += 1;
      return { assertions: [{
        predicate_id: predicateIdForName("alpha relation"),
        target_predicate_id: predicateIdForName("bravo relation"),
      }] };
    }),
    load_current_parent: async () => ({ kind: "found", parent_commit: null }),
  });
  const inert = (kind: "promotion" | "identity_cluster" | "derived_group_dream") => defineConsolidationWorkAdapter(kind, {
    produce: async () => ({ kind: "failed", error_code: "dependency_unavailable" }),
    materialize: async () => ({ kind: "failed", error_code: "dependency_unavailable" }),
  });
  const adapterMap = {
    predicate_batch: predicateAdapter,
    promotion: inert("promotion"),
    identity_cluster: inert("identity_cluster"),
    derived_group_dream: inert("derived_group_dream"),
  } satisfies Record<typeof CONSOLIDATION_WORK_KINDS[number], ConsolidationWorkAdapter>;
  const resultRepository = defineDurableMemoryWorkResultRepository({
    load: async () => stored === null ? { kind: "missing" } : { kind: "found", result: stored },
    stage: async (_authorized, request) => {
      stored = materializeStagedDurableMemoryWorkResult(request);
      return { kind: "staged", result: stored };
    },
  });
  const service = defineConsolidationWorkService({
    execution_repository: defineDurableMemoryWorkExecutionRepository({
      leaseNext: async () => ({ kind: "none_available" }),
      load: async () => ({ kind: "found", job }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({ kind: "not_expired" }),
    }),
    result_repository: resultRepository,
    success_repository: defineDurableMemoryWorkSuccessRepository(async (_authorized, request) => ({
      kind: "committed",
      job: succeedDurableMemoryWork(
        request.leased_job,
        { worker_id: request.leased_job.lease!.worker_id, fence: request.leased_job.lease!.fence },
        102,
        request.result_kind,
        request.response_digest,
        request.result_digest,
      ),
      commit_id: request.authoritative_append?.transition.derivation.commit.commit_id ?? null,
      sequence: request.authoritative_append === null ? null : 1,
      outbox_id: durableMemoryWorkSuccessOutboxId(request),
    })),
    resolve_strategy: async () => strategy,
    adapters: adapterMap,
    max_parent_rematerializations: 2,
  });
  await expect(service.run(context, job)).resolves.toMatchObject({
    kind: "succeeded", producer_calls: 1, materialization_attempts: 1,
  });
  await expect(service.run(context, job)).resolves.toMatchObject({
    kind: "succeeded", producer_calls: 0, materialization_attempts: 1,
  });
  expect(modelCalls).toBe(1);
  expect(stored?.work_kind).toBe("predicate_batch");
});
