import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
  type MemoryStrategyAssignmentBundle,
} from "../../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineMemoryEvaluationEvidenceSource,
  type CopiedMemoryEvaluationInput,
} from "../stores/memory-evaluation-evidence-source";
import {
  defineMemoryShadowResultRepository,
  materializeMemoryEvaluationResult,
  memoryEvaluationResultId,
  type MemoryEvaluationPair,
  type MemoryEvaluationResult,
  type MemoryShadowResultImplementation,
} from "../stores/memory-shadow-result-repository";
import {
  defineMemoryOfflineReplayCoordinator,
} from "./memory-offline-replay-coordinator";

const digest = (character: string): string => character.repeat(64);

const context = (capability = "memories.experiments.shadow", owner = "account:alice") =>
  createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: "worker:evaluator",
    account_id: owner,
    application_id: "app:memory-evaluator",
    credential_id: "credential:evaluator",
    credential_generation: 1,
    capability,
    grant_id: "grant:evaluator",
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

const copiedInput = async (
  inputFrontier: string,
  payload: unknown,
  authorized = context(),
): Promise<Readonly<CopiedMemoryEvaluationInput>> => {
  const source = defineMemoryEvaluationEvidenceSource(async (sourceContext, request) => ({
    kind: "found",
    owner_account_id: sourceContext.account_id,
    account_epoch: sourceContext.account_epoch,
    source_kind: request.source_kind,
    source_ref: request.source_ref,
    input_frontier: request.input_frontier,
    payload,
  }));
  const loaded = await source.load(authorized, {
    source_kind: "formation_input_snapshot",
    source_ref: "source:snapshot:one",
    input_frontier: inputFrontier,
  });
  if (loaded.kind !== "found") throw new Error("test copied input unavailable");
  return loaded.copied_input;
};

const assignment = (shadowCount = 2): Readonly<MemoryStrategyAssignmentBundle> => {
  const strategy = (id: string, prompt: string) => registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: id,
    work_kind: "formation",
    coordinates: {
      strategy_version: "formation:v1", model_version: "deepseek:v1",
      prompt_version: prompt, policy_version: "policy:v1", code_version: "code:v1",
      schema_version: "schema:v1", tokenizer_version: "tokenizer:v1",
      tool_version: "none", result_contract_version: "formation-result:v2",
      speaker_strategy_version: "speaker:v1", boundary_strategy_version: "boundary:v1",
    },
  });
  const strategies = [
    strategy("strategy:authority", "prompt:v1"),
    strategy("strategy:shadow:a", "prompt:v2"),
    strategy("strategy:shadow:b", "prompt:v3"),
  ];
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: `policy:formation:${shadowCount}`,
    work_kind: "formation",
    unit_kind: "session",
    key_version: "assignment-key:v1",
    authority_strategy_id: strategies[0]!.strategy_id,
    shadow_candidates: strategies.slice(1, shadowCount + 1).map((candidate) => ({
      strategy_id: candidate.strategy_id,
      basis_points: 10_000,
    })),
  }, strategies);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(11)).assign({
    owner_account_id: "account:alice",
    unit_ref: "session:copied:one",
    policy,
    strategies,
  });
};

const evaluationRunId = `mer1_${digest("b")}`;

const memoryRepository = () => {
  const results = new Map<string, Readonly<MemoryEvaluationResult>>();
  const pairs = new Map<string, Readonly<MemoryEvaluationPair>>();
  const implementation: MemoryShadowResultImplementation = {
    load: async (authorized, coordinate) => {
      const found = results.get(memoryEvaluationResultId(authorized, coordinate));
      return found ? { kind: "found", result: found } : { kind: "missing" };
    },
    stage: async (authorized, request) => {
      const result = materializeMemoryEvaluationResult(authorized, request);
      const found = results.get(result.evaluation_result_id);
      if (found) {
        return found.stage_request_digest === result.stage_request_digest
          ? { kind: "replayed", result: found }
          : { kind: "idempotency_conflict" };
      }
      results.set(result.evaluation_result_id, result);
      return { kind: "staged", result };
    },
    recordPair: async (_authorized, pair) => {
      const found = pairs.get(pair.pair_id);
      if (found) return { kind: "replayed", pair: found };
      pairs.set(pair.pair_id, pair);
      return { kind: "recorded", pair };
    },
  };
  return { repository: defineMemoryShadowResultRepository(implementation), results, pairs };
};

const produced = (strategyId: string, repeat: number) => ({
  kind: "produced" as const,
  result_contract_version: "formation-result:v2",
  response_digest: sha256CanonicalContent({ strategy_id: strategyId, repeat }),
  normalized_result: { admissions: [{ strategy_id: strategyId, repeat }] },
});

describe("production-neutral memory offline replay coordinator", () => {
  test("runs explicit repeats sequentially, records exact pairs, and replays with zero model calls", async () => {
    const storage = memoryRepository();
    const source = { transcript: [{ speaker: "A", text: "raw copied sentinel" }] };
    const copied = await copiedInput("frontier:raw:sentinel", source);
    source.transcript[0]!.text = "mutated after copy";
    let active = 0;
    let peak = 0;
    const calls: string[] = [];
    const coordinator = defineMemoryOfflineReplayCoordinator({
      result_repository: storage.repository,
      produce: async (request) => {
        active += 1;
        peak = Math.max(peak, active);
        await Promise.resolve();
        expect(Object.isFrozen(request)).toBe(true);
        expect(Object.isFrozen(request.copied_input.payload)).toBe(true);
        expect(JSON.stringify(request.copied_input.payload)).toContain("raw copied sentinel");
        expect(JSON.stringify(request.copied_input.payload)).not.toContain("mutated after copy");
        calls.push(`${request.repeat_ordinal}:${request.evaluation_role}:${request.strategy.strategy_id}`);
        active -= 1;
        return produced(request.strategy.strategy_id, request.repeat_ordinal);
      },
    });
    const request = {
      assignment_bundle: assignment(),
      evaluation_run_id: evaluationRunId,
      copied_input: copied,
      repeats: 2,
    };

    const first = await coordinator.run(context(), request);
    expect(first).toMatchObject({
      kind: "completed", model_calls: 6, reused_results: 0,
    });
    expect(first.pairs).toHaveLength(4);
    expect(new Set(first.pairs.map((pair) => pair.pair_id)).size).toBe(4);
    expect(peak).toBe(1);
    expect(calls).toEqual([
      "0:baseline:strategy:authority",
      "0:candidate:strategy:shadow:a",
      "0:candidate:strategy:shadow:b",
      "1:baseline:strategy:authority",
      "1:candidate:strategy:shadow:a",
      "1:candidate:strategy:shadow:b",
    ]);
    expect(storage.results.size).toBe(6);
    expect(storage.pairs.size).toBe(4);

    calls.length = 0;
    const replay = await coordinator.run(context(), request);
    expect(replay).toEqual({
      kind: "completed",
      pairs: first.pairs,
      model_calls: 0,
      reused_results: 6,
    });
    expect(calls).toEqual([]);
    const serialized = JSON.stringify(replay);
    for (const forbidden of [
      "raw copied sentinel", "frontier:raw:sentinel", "admissions", "response_digest",
      "transcript", "prompt", "answer",
    ]) expect(serialized).not.toContain(forbidden);
    expect(Object.keys(coordinator)).toEqual(["run"]);
  });

  test("a longer restart reuses the completed prefix and produces only missing repeats", async () => {
    const storage = memoryRepository();
    let calls = 0;
    const coordinator = defineMemoryOfflineReplayCoordinator({
      result_repository: storage.repository,
      produce: async (request) => {
        calls += 1;
        return produced(request.strategy.strategy_id, request.repeat_ordinal);
      },
    });
    const copied = await copiedInput("frontier:one", { events: [1, 2, 3] });
    const base = { assignment_bundle: assignment(), evaluation_run_id: evaluationRunId, copied_input: copied };
    await expect(coordinator.run(context(), { ...base, repeats: 1 })).resolves.toMatchObject({
      kind: "completed", model_calls: 3, reused_results: 0,
    });
    calls = 0;
    await expect(coordinator.run(context(), { ...base, repeats: 2 })).resolves.toMatchObject({
      kind: "completed", model_calls: 3, reused_results: 3,
    });
    expect(calls).toBe(3);
  });

  test("forged inputs, assignments, capabilities, and invalid repeat bounds fail before production", async () => {
    let calls = 0;
    const coordinator = defineMemoryOfflineReplayCoordinator({
      result_repository: memoryRepository().repository,
      produce: async () => { calls += 1; return produced("strategy:authority", 0); },
    });
    const copied = await copiedInput("frontier:one", { events: [] });
    const valid = { assignment_bundle: assignment(), evaluation_run_id: evaluationRunId, copied_input: copied, repeats: 1 };
    await expect(coordinator.run(context("memories.work.execute"), valid)).rejects.toThrow("capability_denied");
    await expect(coordinator.run(context(), { ...valid, copied_input: { ...copied } })).rejects.toThrow("unverified_copied_input");
    const foreign = await copiedInput("frontier:one", { events: [] }, context("memories.experiments.shadow", "account:bob"));
    await expect(coordinator.run(context(), { ...valid, copied_input: foreign }))
      .rejects.toThrow("copied_input_authority_mismatch");
    await expect(coordinator.run(context(), { ...valid, assignment_bundle: { ...valid.assignment_bundle } }))
      .rejects.toThrow("memory strategy unminted_assignment");
    await expect(coordinator.run(context(), { ...valid, repeats: 0 })).rejects.toThrow("invalid_repeats");
    await expect(coordinator.run(context(), { ...valid, repeats: 21 })).rejects.toThrow("invalid_repeats");
    await expect(coordinator.run(context(), { ...valid, assignment_bundle: assignment(0) }))
      .rejects.toThrow("no_selected_shadow");
    expect(calls).toBe(0);
  });

  test("producer failures and hostile results stop closed without content leakage", async () => {
    const run = async (produce: () => Promise<unknown>) => defineMemoryOfflineReplayCoordinator({
      result_repository: memoryRepository().repository,
      produce: produce as never,
    }).run(context(), {
      assignment_bundle: assignment(1),
      evaluation_run_id: evaluationRunId,
      copied_input: await copiedInput("frontier:secret", { transcript: "raw secret" }),
      repeats: 1,
    });
    await expect(run(async () => ({ kind: "failed", error_code: "model_timeout" }))).resolves.toMatchObject({
      kind: "stopped", stop_code: "producer_failed", failure_code: "model_timeout", model_calls: 1,
    });
    const thrown = await run(async () => { throw new Error("provider raw secret"); });
    expect(thrown).toMatchObject({
      kind: "stopped", stop_code: "producer_failed", failure_code: "dependency_unavailable",
    });
    expect(JSON.stringify(thrown)).not.toMatch(/provider|secret|transcript|frontier/i);
    await expect(run(async () => ({
      ...produced("strategy:authority", 0),
      result_contract_version: "formation-result:wrong",
    }))).resolves.toMatchObject({
      kind: "stopped", stop_code: "invalid_result", failure_code: null,
    });
    await expect(run(async () => new Proxy({}, { ownKeys: () => { throw new Error("raw secret"); } })))
      .resolves.toMatchObject({ kind: "stopped", stop_code: "invalid_result" });
  });

  test("storage retry, authorization stop, and idempotency conflict remain distinct", async () => {
    const outcome = async (implementation: MemoryShadowResultImplementation) => {
      const coordinator = defineMemoryOfflineReplayCoordinator({
        result_repository: defineMemoryShadowResultRepository(implementation),
        produce: async (request) => produced(request.strategy.strategy_id, request.repeat_ordinal),
      });
      return coordinator.run(context(), {
        assignment_bundle: assignment(1),
        evaluation_run_id: evaluationRunId,
        copied_input: await copiedInput("frontier:one", { events: [] }),
        repeats: 1,
      });
    };
    const unused = async () => ({ kind: "idempotency_conflict" as const });
    await expect(outcome({
      load: async () => ({ kind: "serialization_retryable" }), stage: unused, recordPair: unused,
    })).resolves.toMatchObject({ kind: "stopped", stop_code: "storage_retryable" });
    await expect(outcome({
      load: async () => ({ kind: "authorization_denied", reason: "grant_inactive" }),
      stage: unused,
      recordPair: unused,
    })).resolves.toMatchObject({ kind: "stopped", stop_code: "authorization_or_context" });
    await expect(outcome({
      load: async () => ({ kind: "missing" }), stage: unused, recordPair: unused,
    })).resolves.toMatchObject({ kind: "stopped", stop_code: "idempotency_conflict" });
  });
});
