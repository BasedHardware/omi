import { describe, expect, test } from "bun:test";

import {
  attributionEvidenceFactorRef,
  type AttributionEvidenceFactor,
} from "../../../core/consolidate/attribution-belief";
import {
  hypothesisIdForCalibrationCandidate,
  type AttributionCalibrationRequest,
} from "../../../core/consolidate/attribution-calibration";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
  type MemoryStrategyAssignmentBundle,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
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
  ATTRIBUTION_BELIEF_SHADOW_INPUT_VERSION,
  ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
  defineAttributionBeliefShadowProducer,
} from "./attribution-belief-shadow-producer";
import { defineMemoryOfflineReplayCoordinator } from "./memory-offline-replay-coordinator";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;
const owner = "account:alice";
const frontier = digest("1");
const candidates = [
  { kind: "owner" as const, target_ref: null },
  { kind: "unknown" as const, target_ref: null },
];

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:evaluator",
  account_id: owner,
  application_id: "app:memory-evaluator",
  credential_id: "credential:evaluator",
  credential_generation: 1,
  capability: "memories.experiments.shadow",
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

const strategy = (id = "strategy:belief:authority", prompt = "belief:prompt:v1") =>
  registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: id,
    work_kind: "identity_cluster",
    coordinates: {
      strategy_version: "belief-shadow:v1",
      model_version: "calibrator:test:v1",
      prompt_version: prompt,
      policy_version: "belief-policy:v1",
      code_version: "belief-code:v1",
      schema_version: "belief-schema:v1",
      tokenizer_version: "none",
      tool_version: "none",
      result_contract_version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
      speaker_strategy_version: "none",
      boundary_strategy_version: "none",
    },
  });

const payload = () => {
  const hypothesisId = hypothesisIdForCalibrationCandidate({
    owner_account_id: owner,
    belief_kind: "source_identity",
    about_ref: ref("about1", "b"),
  }, candidates[0]!);
  const factorCore = {
    evidence_ref: ref("atevidence1", "c"),
    independence_group_ref: ref("atind1", "d"),
    hypothesis_id: hypothesisId,
    direction: "support" as const,
    factor_contract_digest: digest("e"),
  };
  const factor: AttributionEvidenceFactor = {
    factor_ref: attributionEvidenceFactorRef(factorCore),
    ...factorCore,
  };
  return {
    version: ATTRIBUTION_BELIEF_SHADOW_INPUT_VERSION,
    owner_account_id: owner,
    belief_kind: "source_identity" as const,
    about_ref: ref("about1", "b"),
    observation_ref: ref("obsref1", "f"),
    observation_content_digest: digest("2"),
    graph_frontier: frontier,
    hypothesis_candidates: candidates,
    evidence_factors: [factor],
    attribution_contract_digest: digest("3"),
    aggregation_contract_digest: digest("4"),
    created_at_event_time: 101,
    previous_revision: null,
  };
};

const copiedInput = async (value: unknown = payload()): Promise<Readonly<CopiedMemoryEvaluationInput>> => {
  const source = defineMemoryEvaluationEvidenceSource(async (authorized, request) => ({
    kind: "found",
    owner_account_id: authorized.account_id,
    account_epoch: authorized.account_epoch,
    source_kind: request.source_kind,
    source_ref: request.source_ref,
    input_frontier: request.input_frontier,
    payload: value,
  }));
  const loaded = await source.load(context(), {
    source_kind: "authorized_graph_snapshot",
    source_ref: "snapshot:belief:one",
    input_frontier: frontier,
  });
  if (loaded.kind !== "found") throw new Error("missing test copied input");
  return loaded.copied_input;
};

const calibrated = (request: AttributionCalibrationRequest, ownerMicros = 700_000) => ({
  probabilities: request.hypotheses.map((hypothesis) => ({
    hypothesis_id: hypothesis.hypothesis_id,
    probability_micros: hypothesis.kind === "owner" ? ownerMicros : 1_000_000 - ownerMicros,
  })),
});

const assignment = (): Readonly<MemoryStrategyAssignmentBundle> => {
  const strategies = [
    strategy(),
    strategy("strategy:belief:candidate", "belief:prompt:v2"),
  ];
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:belief:paired",
    work_kind: "identity_cluster",
    unit_kind: "session",
    key_version: "assignment-key:v1",
    authority_strategy_id: strategies[0]!.strategy_id,
    shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
  }, strategies);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(9)).assign({
    owner_account_id: owner,
    unit_ref: "session:belief:one",
    policy,
    strategies,
  });
};

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
      if (found) return found.stage_request_digest === result.stage_request_digest
        ? { kind: "replayed", result: found } : { kind: "idempotency_conflict" };
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

describe("attribution belief shadow producer", () => {
  test("uses the strategy calibration contract and sends only opaque owner-digested input", async () => {
    const selected = strategy();
    const seen: AttributionCalibrationRequest[] = [];
    const produce = defineAttributionBeliefShadowProducer({
      resolve_calibrator: async (resolved, role) => {
        expect(resolved).toEqual(selected);
        expect(role).toBe("baseline");
        return { calibrate: async (request) => {
          seen.push(request);
          return calibrated(request);
        } };
      },
    });
    const result = await produce({
      copied_input: await copiedInput(),
      strategy: selected,
      evaluation_role: "baseline",
      repeat_ordinal: 0,
    });
    expect(result.kind).toBe("produced");
    if (result.kind !== "produced") throw new Error("expected produced belief");
    expect(result.result_contract_version).toBe(ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION);
    expect(result.normalized_result["belief"]).toMatchObject({
      owner_account_id: owner,
      calibration_contract_digest: selected.execution_contract_digest,
    });
    expect(result.normalized_result["calibration_receipt"]).toMatchObject({
      response_digest: result.response_digest,
      calibration_contract_digest: selected.execution_contract_digest,
    });
    expect(seen).toHaveLength(1);
    expect(seen[0]!.owner_scope_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(seen[0]!.calibration_contract_digest).toBe(selected.execution_contract_digest);
    expect(JSON.stringify(seen[0])).not.toContain(owner);
    expect(JSON.stringify(seen[0])).not.toMatch(/transcript|observation text/i);
  });

  test("rejects coordinate, strategy, and hostile payload failures before calibration", async () => {
    let resolves = 0;
    let calls = 0;
    const produce = defineAttributionBeliefShadowProducer({
      resolve_calibrator: async () => {
        resolves += 1;
        return { calibrate: async (request) => { calls += 1; return calibrated(request); } };
      },
    });
    const selected = strategy();
    const copied = await copiedInput();
    const run = (copied_input: unknown, selectedStrategy: unknown = selected) => produce({
      copied_input,
      strategy: selectedStrategy,
      evaluation_role: "candidate",
      repeat_ordinal: 0,
    } as never);
    await expect(run({ ...copied, owner_account_id: "account:bob" }))
      .resolves.toEqual({ kind: "failed", error_code: "dependency_unavailable" });
    const wrongPayload = { ...payload(), graph_frontier: digest("9") };
    await expect(run(await copiedInput(wrongPayload)))
      .resolves.toEqual({ kind: "failed", error_code: "dependency_unavailable" });
    await expect(run(copied, registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: selected.strategy_id,
      work_kind: "promotion",
      coordinates: selected.coordinates,
    }))).resolves.toEqual({ kind: "failed", error_code: "dependency_unavailable" });
    await expect(run(copied, registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: selected.strategy_id,
      work_kind: "identity_cluster",
      coordinates: { ...selected.coordinates, result_contract_version: "belief-result:wrong" },
    }))).resolves.toEqual({ kind: "failed", error_code: "dependency_unavailable" });
    const hostile = new Proxy(payload(), { ownKeys: () => { throw new Error("raw observation"); } });
    await expect(copiedInput(hostile)).rejects.toThrow("invalid_result");
    expect(resolves).toBe(0);
    expect(calls).toBe(0);
  });

  test("maps malformed calibration and dependency failures to closed codes", async () => {
    const copied = await copiedInput();
    const selected = strategy();
    const request = { copied_input: copied, strategy: selected, evaluation_role: "baseline" as const, repeat_ordinal: 0 };
    await expect(defineAttributionBeliefShadowProducer({
      resolve_calibrator: async () => ({ calibrate: async () => ({ probabilities: [] }) }),
    })(request)).resolves.toEqual({ kind: "failed", error_code: "model_response_invalid" });
    await expect(defineAttributionBeliefShadowProducer({
      resolve_calibrator: async () => ({ calibrate: async () => { throw new Error("raw provider body"); } }),
    })(request)).resolves.toEqual({ kind: "failed", error_code: "dependency_unavailable" });
    await expect(defineAttributionBeliefShadowProducer({
      resolve_calibrator: async () => null,
    })(request)).resolves.toEqual({ kind: "failed", error_code: "dependency_unavailable" });
  });

  test("pairs baseline and candidate beliefs and replays with zero calibrator calls", async () => {
    const storage = memoryRepository();
    let calls = 0;
    const producer = defineAttributionBeliefShadowProducer({
      resolve_calibrator: async () => ({ calibrate: async (request) => {
        calls += 1;
        return calibrated(request, 650_000);
      } }),
    });
    const coordinator = defineMemoryOfflineReplayCoordinator({
      result_repository: storage.repository,
      produce: producer,
    });
    const request = {
      assignment_bundle: assignment(),
      evaluation_run_id: `mer1_${digest("8")}`,
      copied_input: await copiedInput(),
      repeats: 2,
    };
    await expect(coordinator.run(context(), request)).resolves.toMatchObject({
      kind: "completed", model_calls: 4, reused_results: 0,
    });
    expect(calls).toBe(4);
    expect(storage.results.size).toBe(4);
    expect(storage.pairs.size).toBe(2);
    calls = 0;
    await expect(coordinator.run(context(), request)).resolves.toMatchObject({
      kind: "completed", model_calls: 0, reused_results: 4,
    });
    expect(calls).toBe(0);
  });
});
