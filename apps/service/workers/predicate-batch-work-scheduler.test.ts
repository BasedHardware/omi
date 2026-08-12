import { describe, expect, test } from "bun:test";

import { planPredicateAlignmentQuestions } from "../../../core/consolidate/relations";
import { predicateIdForName, predicateRevisionForObservation } from "../../../core/consolidate/predicate-identity";
import { leaseDurableMemoryWork } from "../../../core/consolidate/state-machine";
import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../../core/consolidate/execution-policy";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { Predicate } from "../../../core/schema";
import { DeterministicFakeModel } from "../../../drivers/model/port";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkAcceptanceRepository,
  type NormalizedDurableMemoryWorkAcceptanceRequest,
} from "../stores/durable-memory-work-repository";
import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from "./durable-memory-graph-plan";
import {
  PREDICATE_BATCH_PROMPT_BUDGET,
  predicateBatchAdjudicationContract,
  predicateBatchPromptCost,
} from "./predicate-batch-contract";
import { definePredicateBatchWorkAdapter } from "./predicate-batch-work-adapter";
import {
  definePredicateBatchWorkInputRepository,
  materializeStagedPredicateBatchWorkInput,
} from "./predicate-batch-work-input-repository";
import {
  MAX_PREDICATE_JOBS_PER_SCHEDULING_CALL,
  PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION,
  definePredicateBatchWorkScheduler,
  type PredicateBatchSchedulingSnapshot,
} from "./predicate-batch-work-scheduler";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";
const frontier = "graph-frontier:predicate:one";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability: "memories.work.accept" | "memories.work.execute" = "memories.work.accept") =>
  issuer.issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: capability === "memories.work.accept" ? "scheduler:one" : "worker:one",
    account_id: owner,
    application_id: capability === "memories.work.accept" ? "app:scheduler" : "app:worker",
    credential_id: "credential:one",
    credential_generation: 1,
    capability,
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

const accountPolicy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:predicate:account:v1",
  work_kind: "predicate_batch",
  unit_kind: "account",
  key_version: "assignment-key:v1",
  authority_strategy_id: strategy.strategy_id,
  shadow_candidates: [],
}, [strategy]);

const workPolicy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:predicate:work:v1",
  work_kind: "predicate_batch",
  unit_kind: "work",
  key_version: "assignment-key:v1",
  authority_strategy_id: strategy.strategy_id,
  shadow_candidates: [],
}, [strategy]);

const assigner = createMemoryStrategyAssigner(new Uint8Array(32).fill(9));
const assignment = (scope: "account" | "work" = "account") => assigner.assign({
  owner_account_id: owner,
  unit_ref: scope === "account" ? owner : "work:wrong-scope",
  policy: scope === "account" ? accountPolicy : workPolicy,
  strategies: [strategy],
});

const executionPolicy = (contract = strategy.execution_contract_digest) =>
  registerDurableMemoryWorkExecutionPolicy({
    version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
    policy_id: "execution-policy:predicate:v1",
    work_kind: "predicate_batch",
    execution_contract_digest: contract,
    max_attempts: 3,
    lease_duration_seconds: 20,
    retry_delays_seconds: [10, 30],
  });

const predicate = (name: string): Predicate => predicateRevisionForObservation({
  owner_account_id: owner,
  predicate_id: predicateIdForName(name),
  display_name: name,
  roles: ["subject"],
  lifecycle: "canonical",
}).predicate;

const names = (count: number, width = 0): string[] => Array.from({ length: count }, (_, index) =>
  width === 0 ? `relation_${String(index).padStart(3, "0")}`
    : `relation_${String(index).padStart(3, "0")}_${"x".repeat(width)}`);

const snapshot = (
  predicates = names(4).map(predicate),
  successful_questions: PredicateBatchSchedulingSnapshot["successful_questions"] = [],
): PredicateBatchSchedulingSnapshot => ({
  version: PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION,
  owner_account_id: owner,
  input_frontier: frontier,
  predicates,
  successful_questions,
});

const request = (input = snapshot(), overrides: Record<string, unknown> = {}) => ({
  snapshot: input,
  strategy_assignment: assignment(),
  execution_policy: executionPolicy(),
  accepted_at_event_time: 100,
  max_jobs_per_invocation: 64,
  ...overrides,
});

const memoryAcceptance = () => {
  const stored = new Map<string, { digest: string; job: NormalizedDurableMemoryWorkAcceptanceRequest["pending_job"] }>();
  const requests: NormalizedDurableMemoryWorkAcceptanceRequest[] = [];
  const repository = defineDurableMemoryWorkAcceptanceRepository(async (_authorized, accepted) => {
    requests.push(accepted);
    const prior = stored.get(accepted.pending_job.job_id);
    if (prior) return prior.digest === accepted.request_digest
      ? { kind: "replayed", job: prior.job }
      : { kind: "idempotency_conflict" };
    stored.set(accepted.pending_job.job_id, { digest: accepted.request_digest, job: accepted.pending_job });
    return { kind: "accepted", job: accepted.pending_job };
  });
  return { repository, requests };
};

const memoryInput = () => {
  const stored = new Map<string, ReturnType<typeof materializeStagedPredicateBatchWorkInput>>();
  const requests: Parameters<ReturnType<typeof definePredicateBatchWorkInputRepository>["stage"]>[1][] = [];
  const repository = definePredicateBatchWorkInputRepository({
    async stage(_authorized, request) {
      requests.push(request);
      const expected = materializeStagedPredicateBatchWorkInput(request);
      const prior = stored.get(expected.job_id);
      if (prior) return JSON.stringify(prior) === JSON.stringify(expected)
        ? { kind: "replayed", input: prior }
        : { kind: "idempotency_conflict" };
      stored.set(expected.job_id, expected);
      return { kind: "staged", input: expected };
    },
    async load(_authorized, job) {
      const input = stored.get(job.job_id);
      return input ? { kind: "found", input } : { kind: "not_found" };
    },
  });
  return { repository, requests, stored };
};

const schedulerFor = (repository: ReturnType<typeof memoryAcceptance>["repository"]) =>
  definePredicateBatchWorkScheduler(repository, memoryInput().repository);

describe("predicate batch work scheduler", () => {
  test("accepts deterministic jobs, replays them, and emits adapter-consumable manifests", async () => {
    const store = memoryAcceptance();
    const inputs = memoryInput();
    const scheduler = definePredicateBatchWorkScheduler(store.repository, inputs.repository);
    const input = snapshot();
    const first = await scheduler.schedule(context(), request(input));
    expect(first.kind).toBe("accepted");
    expect(first.scheduled.length).toBeGreaterThan(0);
    expect(first.scheduled.every((item) => item.acceptance === "accepted")).toBe(true);
    expect(JSON.stringify(first)).not.toContain(owner);
    expect(JSON.stringify(first)).not.toContain("relation_000");

    const second = await scheduler.schedule(context(), request({
      ...input, predicates: [...input.predicates].reverse(),
    }));
    expect(second.scheduled.map(({ job_id, batch_question_digest }) => ({ job_id, batch_question_digest })))
      .toEqual(first.scheduled.map(({ job_id, batch_question_digest }) => ({ job_id, batch_question_digest })));
    expect(second.scheduled.every((item) => item.acceptance === "replayed")).toBe(true);
    expect(inputs.requests).toHaveLength(first.scheduled.length * 2);
    expect(inputs.stored.size).toBe(first.scheduled.length);

    const accepted = store.requests[0]!;
    const revisionIds = new Set(accepted.input_manifest
      .filter((entry) => entry.input_kind === "predicate_revision").map((entry) => entry.input_ref));
    const selected = input.predicates.filter((item) => revisionIds.has(item.predicate_revision_id));
    const scheduled = first.scheduled.find((item) => item.job_id === accepted.pending_job.job_id)!;
    const leased = leaseDurableMemoryWork(accepted.pending_job, "worker:one", 101, 20);
    const adapter = definePredicateBatchWorkAdapter({
      load_input: async () => ({ kind: "found", snapshot: {
        version: "predicate-batch-input-snapshot-v1",
        owner_account_id: owner,
        job_id: leased.job_id,
        input_frontier: frontier,
        batch_question_digest: scheduled.batch_question_digest,
        predicates: selected,
      } }),
      resolve_model: async () => new DeterministicFakeModel({ assertions: [] }),
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
    });
    await expect(adapter.produce(context("memories.work.execute"), leased, strategy))
      .resolves.toMatchObject({ kind: "produced" });
  });

  test("only durable successful questions unlock the next deterministic block", async () => {
    const predicates = names(8, 5_500).map(predicate);
    const input = snapshot(predicates);
    const plan = planPredicateAlignmentQuestions(predicates, {
      owner_account_id: owner,
      batch_prompt_budget: PREDICATE_BATCH_PROMPT_BUDGET,
      max_questions_per_invocation: 1,
      prompt_cost: predicateBatchPromptCost,
      adjudication_contract: predicateBatchAdjudicationContract(strategy),
    });
    expect(plan.questions).toHaveLength(1);
    expect(plan.coverage.remaining_pairs_after_plan).toBeGreaterThan(0);
    const store = memoryAcceptance();
    const scheduler = schedulerFor(store.repository);
    const first = await scheduler.schedule(context(), request(input, { max_jobs_per_invocation: 1 }));
    const replay = await scheduler.schedule(context(), request(input, { max_jobs_per_invocation: 1 }));
    expect(replay.scheduled[0]?.job_id).toBe(first.scheduled[0]?.job_id);
    expect(replay.scheduled[0]?.acceptance).toBe("replayed");

    const question = plan.questions[0]!;
    const success = {
      batch_question_digest: question.batch_question_digest,
      predicate_frontier: question.predicate_frontier,
      predicate_ids: question.predicate_ids,
      response_digest: digest("b"),
      result_digest: digest("c"),
    };
    const advanced = await scheduler.schedule(context(), request(snapshot(predicates, [success]), {
      max_jobs_per_invocation: 1,
    }));
    expect(advanced.scheduled[0]?.job_id).not.toBe(first.scheduled[0]?.job_id);
    expect(advanced.coverage.covered_pairs_before_plan).toBeGreaterThan(0);
  });

  test("changed schedule bytes conflict with the existing deterministic job identity", async () => {
    const store = memoryAcceptance();
    const scheduler = schedulerFor(store.repository);
    const first = await scheduler.schedule(context(), request());
    expect(first.kind).toBe("accepted");
    const changed = await scheduler.schedule(context(), request(snapshot(), { accepted_at_event_time: 101 }));
    expect(changed).toMatchObject({
      kind: "halted",
      scheduled: [],
      halt: {
        job_id: first.scheduled[0]?.job_id,
        batch_question_digest: first.scheduled[0]?.batch_question_digest,
        code: "idempotency_conflict",
      },
    });
  });

  test("the 64-job cap is hard and leaves later uncovered pairs unscheduled", async () => {
    const input = snapshot(names(30, 5_500).map(predicate));
    let calls = 0;
    const scheduler = definePredicateBatchWorkScheduler(
      defineDurableMemoryWorkAcceptanceRepository(async (_authorized, accepted) => {
        calls += 1;
        return { kind: "accepted", job: accepted.pending_job };
      }),
      memoryInput().repository,
    );
    const outcome = await scheduler.schedule(context(), request(input, {
      max_jobs_per_invocation: MAX_PREDICATE_JOBS_PER_SCHEDULING_CALL,
    }));
    expect(outcome.kind).toBe("partial");
    expect(outcome.planned_jobs).toBe(MAX_PREDICATE_JOBS_PER_SCHEDULING_CALL);
    expect(outcome.scheduled).toHaveLength(MAX_PREDICATE_JOBS_PER_SCHEDULING_CALL);
    expect(outcome.coverage.remaining_pairs_after_plan).toBeGreaterThan(0);
    expect(calls).toBe(MAX_PREDICATE_JOBS_PER_SCHEDULING_CALL);
  });

  test("one refusal or thrown dependency stops later acceptance and reports closed progress", async () => {
    const input = snapshot(names(8, 5_500).map(predicate));
    for (const mode of ["refuse", "throw"] as const) {
      let calls = 0;
      const scheduler = definePredicateBatchWorkScheduler(
        defineDurableMemoryWorkAcceptanceRepository(async (_authorized, accepted) => {
          calls += 1;
          if (calls === 2) {
            if (mode === "throw") throw new Error("SECRET provider detail");
            return { kind: "serialization_retryable" };
          }
          return { kind: "accepted", job: accepted.pending_job };
        }),
        memoryInput().repository,
      );
      const outcome = await scheduler.schedule(context(), request(input, { max_jobs_per_invocation: 8 }));
      expect(outcome.kind).toBe("halted");
      expect(outcome.scheduled).toHaveLength(1);
      expect(outcome.halt?.code).toBe(mode === "throw" ? "repository_unavailable" : "serialization_retryable");
      expect(JSON.stringify(outcome)).not.toContain("SECRET");
      expect(calls).toBe(2);
    }
  });

  test("input staging refusal or failure prevents work acceptance", async () => {
    for (const mode of ["refuse", "throw"] as const) {
      let acceptanceCalls = 0;
      let stagingCalls = 0;
      const acceptance = defineDurableMemoryWorkAcceptanceRepository(async (_authorized, accepted) => {
        acceptanceCalls += 1;
        return { kind: "accepted", job: accepted.pending_job };
      });
      const inputs = definePredicateBatchWorkInputRepository({
        async stage() {
          stagingCalls += 1;
          if (mode === "throw") throw new Error("SECRET input store detail");
          return { kind: "idempotency_conflict" };
        },
        async load() { return { kind: "not_found" }; },
      });
      const outcome = await definePredicateBatchWorkScheduler(acceptance, inputs)
        .schedule(context(), request());
      expect(outcome).toMatchObject({
        kind: "halted",
        scheduled: [],
        halt: { code: mode === "throw" ? "repository_unavailable" : "idempotency_conflict" },
      });
      expect(JSON.stringify(outcome)).not.toContain("SECRET");
      expect(stagingCalls).toBe(1);
      expect(acceptanceCalls).toBe(0);
    }
  });

  test("complete durable coverage produces no new accepted work", async () => {
    const predicates = names(4).map(predicate);
    const plan = planPredicateAlignmentQuestions(predicates, {
      owner_account_id: owner,
      batch_prompt_budget: PREDICATE_BATCH_PROMPT_BUDGET,
      max_questions_per_invocation: 64,
      prompt_cost: predicateBatchPromptCost,
      adjudication_contract: predicateBatchAdjudicationContract(strategy),
    });
    const successes = plan.questions.map((question, index) => ({
      batch_question_digest: question.batch_question_digest,
      predicate_frontier: question.predicate_frontier,
      predicate_ids: question.predicate_ids,
      response_digest: digest(index % 2 ? "d" : "e"),
      result_digest: digest(index % 2 ? "f" : "0"),
    }));
    let calls = 0;
    const scheduler = definePredicateBatchWorkScheduler(
      defineDurableMemoryWorkAcceptanceRepository(async () => { calls += 1; throw new Error("unused"); }),
      memoryInput().repository,
    );
    const outcome = await scheduler.schedule(context(), request(snapshot(predicates, successes)));
    expect(outcome).toMatchObject({ kind: "already_complete", planned_jobs: 0, scheduled: [], halt: null });
    expect(outcome.coverage.remaining_pairs_before_plan).toBe(0);
    expect(calls).toBe(0);
  });

  test("authority, assignment scope, source rows, and schedule fail before repository access", async () => {
    let calls = 0;
    const scheduler = definePredicateBatchWorkScheduler(
      defineDurableMemoryWorkAcceptanceRepository(async (_authorized, accepted) => {
        calls += 1;
        return { kind: "accepted", job: accepted.pending_job };
      }),
      memoryInput().repository,
    );
    await expect(scheduler.schedule(context("memories.work.execute"), request()))
      .rejects.toThrow("capability_denied");
    await expect(scheduler.schedule(context(), request(snapshot(), { strategy_assignment: assignment("work") })))
      .rejects.toThrow("coordinate_mismatch");
    await expect(scheduler.schedule(context(), request(snapshot(), { max_jobs_per_invocation: 65 })))
      .rejects.toThrow("invalid_schedule");
    const foreign = { ...snapshot().predicates[0]!, owner_account_id: "account:bob" } as Predicate;
    await expect(scheduler.schedule(context(), request(snapshot([foreign, snapshot().predicates[1]!]))))
      .rejects.toThrow("invalid_source_snapshot");
    const legacy: Predicate = {
      predicate_id: "predicate:legacy",
      owner_account_id: owner,
      predicate_revision_id: "predicate:legacy:revision:one",
      identity_version: "name-slots-v1",
      identity_name: "legacy_relation",
      display_name: "legacy_relation",
      lifecycle: "canonical",
      slot_ids: ["window-slot-1"],
    };
    await expect(scheduler.schedule(context(), request(snapshot([legacy, snapshot().predicates[1]!]))))
      .rejects.toThrow("invalid_source_snapshot");
    const plan = planPredicateAlignmentQuestions(snapshot().predicates, {
      owner_account_id: owner,
      batch_prompt_budget: PREDICATE_BATCH_PROMPT_BUDGET,
      max_questions_per_invocation: 64,
      prompt_cost: predicateBatchPromptCost,
      adjudication_contract: predicateBatchAdjudicationContract(strategy),
    });
    const valid = plan.questions[0]!;
    const duplicate = {
      batch_question_digest: valid.batch_question_digest,
      predicate_frontier: valid.predicate_frontier,
      predicate_ids: valid.predicate_ids,
      response_digest: digest("b"), result_digest: digest("c"),
    };
    await expect(scheduler.schedule(context(), request(snapshot(snapshot().predicates, [
      duplicate, { ...duplicate, predicate_ids: [...duplicate.predicate_ids] },
    ]))))
      .rejects.toThrow("invalid_snapshot");
    await expect(scheduler.schedule(context(), request(snapshot(snapshot().predicates, [{
      ...duplicate, batch_question_digest: digest("f"),
    }])))).rejects.toThrow("invalid_source_snapshot");
    expect(calls).toBe(0);
  });

  test("an individually oversize exact question is rejected before acceptance", async () => {
    let calls = 0;
    const scheduler = definePredicateBatchWorkScheduler(
      defineDurableMemoryWorkAcceptanceRepository(async (_authorized, accepted) => {
        calls += 1;
        return { kind: "accepted", job: accepted.pending_job };
      }),
      memoryInput().repository,
    );
    const huge = names(2, 11_000).map(predicate);
    await expect(scheduler.schedule(context(), request(snapshot(huge))))
      .rejects.toThrow("unplannable_prompt");
    expect(calls).toBe(0);
  });

  test("hostile request and snapshot containers are rejected without invoking accessors", async () => {
    let accessed = 0;
    let calls = 0;
    const scheduler = definePredicateBatchWorkScheduler(
      defineDurableMemoryWorkAcceptanceRepository(async (_authorized, accepted) => {
        calls += 1;
        return { kind: "accepted", job: accepted.pending_job };
      }),
    );
    await expect(scheduler.schedule(context(), new Proxy(request(), {}) as never)).rejects.toThrow("invalid_request");
    const hostile = {} as Record<string, unknown>;
    Object.defineProperty(hostile, "predicates", { enumerable: true, get: () => { accessed += 1; return []; } });
    await expect(scheduler.schedule(context(), request(hostile as never))).rejects.toThrow();
    expect(accessed).toBe(0);
    expect(calls).toBe(0);
  });
});
