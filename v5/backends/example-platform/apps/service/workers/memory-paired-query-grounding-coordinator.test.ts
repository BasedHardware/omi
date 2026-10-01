import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
  type MemoryStrategyAssignmentBundle,
  type MemoryStrategyKind,
} from "../../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { buildContentSafeRecallTrace } from "../../../core/retrieve/recall-integrity";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { defineMemoryEvaluationEvidenceSource } from "../stores/memory-evaluation-evidence-source";
import { defineMemoryReadGroundingRepository } from "../stores/memory-read-grounding-repository";
import {
  defineMemoryShadowResultRepository,
  memoryEvaluationResultId,
  type MemoryEvaluationPair,
  type MemoryEvaluationResult,
  type MemoryShadowResultImplementation,
} from "../stores/memory-shadow-result-repository";
import {
  defineMemoryAuthorizedQueryGroundingProducer,
  type AuthorizedQueryEvaluationInput,
  type AuthorizedQueryModelRequest,
} from "./memory-authorized-query-grounding-producer";
import { defineMemoryPairedQueryGroundingCoordinator } from "./memory-paired-query-grounding-coordinator";

const hex = (character: string): string => character.repeat(64);
const traceRef = (value: string): `tr1_${string}` => `tr1_${sha256CanonicalContent({ value })}`;
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow", owner = "account:alice") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:paired-query", account_id: owner,
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: hex("a"),
}, 150);

const assignment = (
  shadowCount = 2,
  workKind: MemoryStrategyKind = "retrieval",
): Readonly<MemoryStrategyAssignmentBundle> => {
  const strategy = (name: string) => registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: `strategy:paired-query:${name}`,
    work_kind: workKind,
    coordinates: {
      strategy_version: `paired-query:${name}:v1`, model_version: "deepseek:v1",
      prompt_version: `prompt:${name}:v1`, policy_version: "policy:v1", code_version: "code:v1",
      schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
      result_contract_version: "memory-read-evaluation-result-v1",
      speaker_strategy_version: "none", boundary_strategy_version: "none",
    },
  });
  const strategies = [strategy("authority"), strategy("shadow-a"), strategy("shadow-b")];
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: `policy:paired-query:${shadowCount}:${workKind}`,
    work_kind: workKind, unit_kind: "session", key_version: "key:v1",
    authority_strategy_id: strategies[0]!.strategy_id,
    shadow_candidates: strategies.slice(1, shadowCount + 1).map((candidate) => ({
      strategy_id: candidate.strategy_id, basis_points: 10_000,
    })),
  }, strategies);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(13)).assign({
    owner_account_id: "account:alice", unit_ref: "session:paired-query", policy, strategies,
  });
};

const citedRef = traceRef("candidate");
const payload = (projected = hex("c"), empty = false): AuthorizedQueryEvaluationInput => ({
  version: "authorized-query-evaluation-input-v1",
  query_text: "What did I say about Omi?",
  projection_authorization_digest: hex("d"),
  reader_projection_digest: hex("e"),
  projected_content_digest: projected,
  classifier_version: "policy-classifier-generic-v1",
  candidates: empty ? [] : [{
    trace_ref: citedRef,
    text: "I said Omi builds memory tools.",
    contributing_subject_classes: ["bystander", "owner"],
  }],
});

const sourceRequest = Object.freeze({
  source_kind: "authorized_graph_snapshot" as const,
  source_ref: "source:paired-query",
  input_frontier: "frontier:paired-query",
});
const runId = `mer1_${hex("b")}`;

const produced = (request: AuthorizedQueryModelRequest) => ({
  kind: "produced" as const,
  response_digest: sha256CanonicalContent({
    strategy_id: request.strategy.strategy_id,
    repeat_ordinal: request.repeat_ordinal,
  }),
  answer_text: "You said Omi builds memory tools.",
  absence: null,
  assertions: [{ ordinal: 0, text: "You said Omi builds memory tools.", citations: [citedRef] }],
  recall_trace: buildContentSafeRecallTrace({
    version: "recall-trace-v1",
    traceRef: traceRef(`run:${request.strategy.strategy_id}:${request.repeat_ordinal}`),
    strategyVersion: request.strategy.coordinates.strategy_version,
    projectionFreshness: "fresh", outcome: "grounded", latencyMs: 1,
    tokenCounts: { input: 8, output: 6 },
    stages: {
      eligible: [citedRef], selected: [citedRef], hydrated: [citedRef],
      policyEligible: [citedRef], cited: [citedRef], grounded: [citedRef],
    },
  }),
});

type PairBehavior = (
  pair: Readonly<MemoryEvaluationPair>,
  call: number,
) => unknown | Promise<unknown>;

const setup = (options: {
  payload_for_source_call?: (call: number) => AuthorizedQueryEvaluationInput;
  pair_behavior?: PairBehavior;
  fail_model_call?: () => number | null;
} = {}) => {
  const results = new Map<string, unknown>();
  const artifacts = new Map<string, unknown>();
  const pairs = new Map<string, Readonly<MemoryEvaluationPair>>();
  let sourceCalls = 0;
  let modelCalls = 0;
  let pairCalls = 0;
  let active = 0;
  let peak = 0;
  const order: string[] = [];
  const repositoryImplementation: MemoryShadowResultImplementation = {
    load: async (authorized, coordinate) => {
      const found = results.get(memoryEvaluationResultId(authorized, coordinate));
      return found ? { kind: "found", result: found } : { kind: "missing" };
    },
    stage: async () => ({ kind: "serialization_retryable" }),
    recordPair: async (_authorized, pair) => {
      pairCalls += 1;
      if (options.pair_behavior) return options.pair_behavior(pair, pairCalls);
      const found = pairs.get(pair.pair_id);
      if (found) return { kind: "replayed", pair: found };
      pairs.set(pair.pair_id, pair);
      return { kind: "recorded", pair };
    },
  };
  const resultRepository = defineMemoryShadowResultRepository(repositoryImplementation);
  const groundingRepository = defineMemoryReadGroundingRepository({
    stage: async (_authorized, result, artifact) => {
      results.set(result.evaluation_result_id, JSON.parse(JSON.stringify(result)));
      artifacts.set(result.evaluation_result_id, JSON.parse(JSON.stringify(artifact)));
      return { kind: "staged", artifact: artifacts.get(result.evaluation_result_id) };
    },
    load: async (_authorized, result) => {
      const artifact = artifacts.get(result.evaluation_result_id);
      return artifact ? { kind: "found", artifact } : { kind: "missing" };
    },
  });
  const evidenceSource = defineMemoryEvaluationEvidenceSource(async (authorized, selected) => {
    sourceCalls += 1;
    return {
      kind: "found",
      owner_account_id: authorized.account_id,
      account_epoch: authorized.account_epoch,
      source_kind: selected.source_kind,
      source_ref: selected.source_ref,
      input_frontier: selected.input_frontier,
      payload: options.payload_for_source_call?.(sourceCalls) ?? payload(),
    };
  });
  const producer = defineMemoryAuthorizedQueryGroundingProducer({
    evidence_source: evidenceSource,
    result_repository: resultRepository,
    grounding_repository: groundingRepository,
    produce: async (request) => {
      modelCalls += 1;
      active += 1;
      peak = Math.max(peak, active);
      order.push(`${request.repeat_ordinal}:${request.evaluation_role}:${request.strategy.strategy_id}`);
      await Promise.resolve();
      active -= 1;
      if (modelCalls === options.fail_model_call?.()) {
        return { kind: "failed", error_code: "model_timeout" };
      }
      return produced(request);
    },
  });
  const coordinator = defineMemoryPairedQueryGroundingCoordinator({
    producer,
    pair_repository: resultRepository,
  });
  return {
    coordinator,
    results,
    artifacts,
    pairs,
    counts: () => ({ sourceCalls, modelCalls, pairCalls, peak }),
    order,
  };
};

const request = (bundle = assignment(), repeats = 2) => Object.freeze({
  assignment_bundle: bundle,
  evaluation_run_id: runId,
  source_request: sourceRequest,
  repeats,
});

describe("production-neutral paired query grounding coordinator", () => {
  test("runs two repeats and two shadows sequentially, then replays with zero model calls", async () => {
    const fixture = setup();
    const first = await fixture.coordinator.run(context(), request());
    expect(first).toMatchObject({
      kind: "completed", observed_model_calls: 6, staged_results: 6, replayed_results: 0,
      recorded_pairs: 4, replayed_pairs: 0,
    });
    expect(first.pair_receipts).toHaveLength(4);
    expect(new Set(first.pair_receipts.map((receipt) => receipt.pair_ref)).size).toBe(4);
    expect(first.pair_receipts.map((receipt) => receipt.repeat_ordinal)).toEqual([0, 0, 1, 1]);
    expect(fixture.counts()).toEqual({ sourceCalls: 12, modelCalls: 6, pairCalls: 4, peak: 1 });
    expect(fixture.order).toEqual([
      "0:baseline:strategy:paired-query:authority",
      "0:candidate:strategy:paired-query:shadow-a",
      "0:candidate:strategy:paired-query:shadow-b",
      "1:baseline:strategy:paired-query:authority",
      "1:candidate:strategy:paired-query:shadow-a",
      "1:candidate:strategy:paired-query:shadow-b",
    ]);

    const serialized = JSON.stringify(first);
    for (const forbidden of [
      "account:alice", "What did", "You said", "I said", "tr1_", "bystander", "owner",
      "source:paired", "frontier:paired", "deepseek", "prompt", "response_digest",
    ]) expect(serialized).not.toContain(forbidden);

    fixture.order.length = 0;
    const replay = await fixture.coordinator.run(context(), request());
    expect(replay).toEqual({
      kind: "completed",
      pair_receipts: first.pair_receipts,
      observed_model_calls: 0,
      staged_results: 0,
      replayed_results: 6,
      recorded_pairs: 0,
      replayed_pairs: 4,
    });
    expect(fixture.counts()).toEqual({ sourceCalls: 24, modelCalls: 6, pairCalls: 8, peak: 1 });
    expect(fixture.order).toEqual([]);
  });

  test("a stopped prefix is resumable without rerunning its completed arms", async () => {
    let failAt: number | null = 3;
    const fixture = setup({ fail_model_call: () => failAt });
    const first = await fixture.coordinator.run(context(), request());
    expect(first).toMatchObject({
      kind: "stopped", stop_code: "producer_failed", failure_code: "model_timeout",
      observed_model_calls: 3, staged_results: 2, replayed_results: 0,
      recorded_pairs: 1, replayed_pairs: 0,
    });
    expect(first.pair_receipts).toHaveLength(1);

    failAt = null;
    const resumed = await fixture.coordinator.run(context(), request());
    expect(resumed).toMatchObject({
      kind: "completed", observed_model_calls: 4, staged_results: 4, replayed_results: 2,
      recorded_pairs: 3, replayed_pairs: 1,
    });
    expect(resumed.pair_receipts).toHaveLength(4);
    expect(resumed.pair_receipts[0]).toEqual(first.pair_receipts[0]);
  });

  test("empty authorized projections pair every arm with zero model calls", async () => {
    const fixture = setup({ payload_for_source_call: () => payload(hex("c"), true) });
    const outcome = await fixture.coordinator.run(context(), request());
    expect(outcome).toMatchObject({
      kind: "completed", observed_model_calls: 0, staged_results: 6, replayed_results: 0,
      recorded_pairs: 4, replayed_pairs: 0,
    });
    expect(outcome.pair_receipts).toHaveLength(4);
    expect(fixture.counts()).toEqual({ sourceCalls: 12, modelCalls: 0, pairCalls: 4, peak: 0 });
  });

  test("source drift between arms cannot become a pair", async () => {
    const fixture = setup({
      payload_for_source_call: (call) => call <= 2 ? payload(hex("c")) : payload(hex("9")),
    });
    const outcome = await fixture.coordinator.run(context(), request(assignment(1), 1));
    expect(outcome).toMatchObject({
      kind: "stopped", stop_code: "pair_invalid", failure_code: null,
      observed_model_calls: 2, staged_results: 2, recorded_pairs: 0,
    });
    expect(outcome.pair_receipts).toEqual([]);
    expect(fixture.pairs.size).toBe(0);
  });

  test("final source invalidation stops before any pair is written", async () => {
    const fixture = setup({
      payload_for_source_call: (call) => call === 1 ? payload(hex("c")) : payload(hex("8")),
    });
    const outcome = await fixture.coordinator.run(context(), request(assignment(1), 1));
    expect(outcome).toEqual({
      kind: "stopped", stop_code: "read_invalidated", failure_code: null,
      pair_receipts: [], observed_model_calls: 1, staged_results: 0, replayed_results: 0,
      recorded_pairs: 0, replayed_pairs: 0,
    });
    expect(fixture.counts().pairCalls).toBe(0);
  });

  test("pair repository outcomes stay closed and pair-write failures expose no text", async () => {
    const run = async (behavior: PairBehavior) => {
      const fixture = setup({ pair_behavior: behavior });
      return fixture.coordinator.run(context(), request(assignment(1), 1));
    };
    await expect(run(async () => ({ kind: "serialization_retryable" }))).resolves.toMatchObject({
      kind: "stopped", stop_code: "pair_storage_retryable",
    });
    await expect(run(async () => ({ kind: "authorization_denied", reason: "grant_inactive" })))
      .resolves.toMatchObject({ kind: "stopped", stop_code: "pair_authorization_or_context" });
    await expect(run(async () => ({ kind: "idempotency_conflict" }))).resolves.toMatchObject({
      kind: "stopped", stop_code: "pair_idempotency_conflict",
    });
    const thrown = await run(async () => { throw new Error("raw database owner query secret"); });
    expect(thrown).toMatchObject({ kind: "stopped", stop_code: "pair_storage_unavailable" });
    expect(JSON.stringify(thrown)).not.toMatch(/database|owner query|secret|account:alice/i);
    await expect(run(async () => ({ kind: "recorded", pair: {} }))).resolves.toMatchObject({
      kind: "stopped", stop_code: "pair_storage_unavailable",
    });
  });

  test("authority and request defects fail before source, model, or pair access", async () => {
    const fixture = setup();
    await expect(fixture.coordinator.run(context("memories.work.execute"), request()))
      .rejects.toThrow("capability_denied");
    await expect(fixture.coordinator.run(context(), request(assignment(0), 1)))
      .rejects.toThrow("no_selected_shadow");
    await expect(fixture.coordinator.run(context(), request(assignment(1, "formation"), 1)))
      .rejects.toThrow("not_read_strategy");
    await expect(fixture.coordinator.run(context(), { ...request(), repeats: 21 }))
      .rejects.toThrow("invalid_repeats");
    await expect(fixture.coordinator.run(context(), {
      ...request(), source_request: { ...sourceRequest, source_kind: "formation_input_snapshot" as const },
    })).rejects.toThrow("invalid_source_request");
    expect(fixture.counts()).toEqual({ sourceCalls: 0, modelCalls: 0, pairCalls: 0, peak: 0 });
  });

  test("dependency and request accessors are rejected without execution", async () => {
    let getterCalls = 0;
    const fixture = setup();
    const hostile = Object.defineProperty({}, "repeats", {
      enumerable: true,
      get() { getterCalls += 1; return 1; },
    });
    Object.defineProperties(hostile, {
      assignment_bundle: { enumerable: true, value: assignment(1) },
      evaluation_run_id: { enumerable: true, value: runId },
      source_request: { enumerable: true, value: sourceRequest },
    });
    await expect(fixture.coordinator.run(context(), hostile as never)).rejects.toThrow("invalid_request");
    expect(getterCalls).toBe(0);
    expect(fixture.counts()).toEqual({ sourceCalls: 0, modelCalls: 0, pairCalls: 0, peak: 0 });

    const dependencies = Object.defineProperty({}, "producer", {
      enumerable: true,
      get() { getterCalls += 1; return fixture.coordinator; },
    });
    Object.defineProperty(dependencies, "pair_repository", { enumerable: true, value: {} });
    expect(() => defineMemoryPairedQueryGroundingCoordinator(dependencies as never)).toThrow("invalid_dependencies");
    expect(getterCalls).toBe(0);
  });
});
