import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkNormalizedResultDigest } from "./durable-memory-work-result-repository";
import {
  defineMemoryShadowResultRepository,
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  pairMemoryEvaluationResults,
  type MemoryEvaluationRole,
  type MemoryEvaluationStageRequest,
} from "./memory-shadow-result-repository";

const digest = (character: string): string => character.repeat(64);

const context = (owner = "account:alice", epoch = 7, capability = "memories.experiments.shadow") =>
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
    account_epoch: epoch,
    destination_activation_revision: 17,
    lifecycle_state: "active",
    deletion_epoch: null,
    authentication_strength: "service-workload",
    issued_at_epoch_seconds: 100,
    expires_at_epoch_seconds: 200,
    authorization_state_digest: digest("a"),
  }, 150);

const assignments = () => {
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
  const authority = strategy("strategy:authority", "prompt:v1");
  const shadow = strategy("strategy:shadow", "prompt:v2");
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:formation:v1", work_kind: "formation", unit_kind: "session",
    key_version: "assignment-key:v1", authority_strategy_id: authority.strategy_id,
    shadow_candidates: [{ strategy_id: shadow.strategy_id, basis_points: 10_000 }],
  }, [authority, shadow]);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(9)).assign({
    owner_account_id: "account:alice", unit_ref: "session:one",
    policy, strategies: [authority, shadow],
  });
};

const request = (role: MemoryEvaluationRole, repeat = 0): MemoryEvaluationStageRequest => {
  const assignment = assignments();
  const selected = role === "baseline" ? assignment.authority : assignment.shadows[0]!;
  const result = { claims: [{ predicate: "works_at", confidence: "high" }] } as const;
  const body = {
    assignment_bundle: assignment,
    assignment_id: selected.assignment_id,
    account_epoch: 7,
    evaluation_role: role,
    evaluation_mode: "offline_replay" as const,
    evaluation_run_id: `mer1_${digest("b")}`,
    input_frontier: "frontier:copied:one",
    input_digest: digest("c"),
    repeat_ordinal: repeat,
    result_contract_version: "formation-result:v2",
    response_digest: role === "baseline" ? digest("d") : digest("e"),
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest("formation-result:v2", result),
    normalized_result: result,
  };
  return { ...body, request_digest: memoryEvaluationStageRequestDigest(context(), body) };
};

const coordinateOf = (value: MemoryEvaluationStageRequest) => ({
  assignment_bundle: value.assignment_bundle,
  assignment_id: value.assignment_id,
  account_epoch: value.account_epoch,
  evaluation_role: value.evaluation_role,
  evaluation_mode: value.evaluation_mode,
  evaluation_run_id: value.evaluation_run_id,
  input_frontier: value.input_frontier,
  input_digest: value.input_digest,
  repeat_ordinal: value.repeat_ordinal,
});

describe("memory shadow result repository", () => {
  test("stages immutable baseline and selected shadow results in the isolated capability", async () => {
    const stored = new Map<string, ReturnType<typeof materializeMemoryEvaluationResult>>();
    const repository = defineMemoryShadowResultRepository({
      load: async (_authorized, coordinate) => {
        const result = [...stored.values()].find((item) =>
          item.assignment_id === coordinate.assignment_id
          && item.repeat_ordinal === coordinate.repeat_ordinal);
        return result ? { kind: "found", result } : { kind: "missing" };
      },
      stage: async (authorized, stage) => {
        const result = materializeMemoryEvaluationResult(authorized, stage);
        stored.set(result.evaluation_result_id, result);
        return { kind: "staged", result };
      },
      recordPair: async (_authorized, pair) => ({ kind: "recorded", pair }),
    });
    const baselineRequest = request("baseline");
    const candidateRequest = request("candidate");
    const baseline = await repository.stage(context(), baselineRequest);
    const candidate = await repository.stage(context(), candidateRequest);
    expect(baseline.kind).toBe("staged");
    expect(candidate.kind).toBe("staged");
    if (baseline.kind !== "staged" || candidate.kind !== "staged") throw new Error("unreachable");
    expect(baseline.result.evaluation_result_id).toStartWith("msr1_");
    expect(candidate.result.strategy_id).toBe("strategy:shadow");
    expect(Object.isFrozen(candidate.result.normalized_result)).toBe(true);
    await expect(repository.load(context(), coordinateOf(candidateRequest))).resolves.toEqual({
      kind: "found", result: candidate.result,
    });
    const pair = pairMemoryEvaluationResults(baseline.result, candidate.result);
    await expect(repository.recordPair(context(), pair)).resolves.toEqual({ kind: "recorded", pair });
    await expect(repository.recordPair(context(), { ...pair })).rejects.toThrow("unverified_pair");
    expect(Object.keys(repository)).toEqual(["load", "stage", "recordPair"]);
    expect("commit" in repository).toBe(false);
    expect("project" in repository).toBe(false);
  });

  test("role, capability, owner, epoch, contract, digest, and hostile result fail before adapter", async () => {
    let calls = 0;
    const repository = defineMemoryShadowResultRepository({
      load: async () => { calls += 1; return { kind: "missing" }; },
      stage: async () => { calls += 1; return { kind: "idempotency_conflict" }; },
      recordPair: async () => { calls += 1; return { kind: "idempotency_conflict" }; },
    });
    const baseline = request("baseline");
    await expect(repository.stage(context("account:alice", 7, "memories.work.execute"), baseline))
      .rejects.toThrow("capability_denied");
    await expect(repository.stage(context("account:bob"), baseline)).rejects.toThrow("owner_mismatch");
    await expect(repository.stage(context("account:alice", 8), baseline)).rejects.toThrow("epoch_mismatch");
    await expect(repository.stage(context(), {
      ...baseline, evaluation_role: "candidate",
    })).rejects.toThrow("assignment_role_mismatch");
    await expect(repository.stage(context(), {
      ...baseline, result_contract_version: "formation-result:wrong",
    })).rejects.toThrow("result_contract_mismatch");
    await expect(repository.stage(context(), {
      ...baseline, normalized_result_digest: digest("f"),
    })).rejects.toThrow("result_digest_mismatch");
    await expect(repository.stage(context(), {
      ...baseline,
      normalized_result: new Proxy({}, { ownKeys: () => { throw new Error("secret"); } }),
    })).rejects.toThrow("invalid_result");
    expect(calls).toBe(0);
  });

  test("request identity changes with every comparison coordinate and same bytes replay", async () => {
    const original = request("candidate");
    const replay = request("candidate");
    expect(replay).toEqual(original);
    expect(request("candidate", 1).request_digest).not.toBe(original.request_digest);
    const { request_digest: _requestDigest, ...originalBody } = original;
    const changed = { ...originalBody, response_digest: digest("f") };
    expect(memoryEvaluationStageRequestDigest(context(), changed)).not.toBe(original.request_digest);
  });

  test("adapter replay cannot forge staged bytes or their request identity", async () => {
    const repository = defineMemoryShadowResultRepository({
      load: async () => ({ kind: "missing" }),
      stage: async (authorized, stage) => ({
        kind: "replayed",
        result: { ...materializeMemoryEvaluationResult(authorized, stage), stage_request_digest: digest("f") },
      }),
      recordPair: async () => ({ kind: "idempotency_conflict" }),
    });
    await expect(repository.stage(context(), request("candidate")))
      .rejects.toThrow("invalid_result");
  });

  test("pairing is stable, content-safe, and requires exact paired coordinates", () => {
    const baselineRequest = request("baseline");
    const candidateRequest = request("candidate");
    const baseline = materializeMemoryEvaluationResult(context(), baselineRequest);
    const candidate = materializeMemoryEvaluationResult(context(), candidateRequest);
    const pair = pairMemoryEvaluationResults(baseline, candidate);
    expect(pair.pair_id).toStartWith("mep1_");
    expect(pairMemoryEvaluationResults(baseline, candidate)).toEqual(pair);
    const serialized = JSON.stringify(pair);
    expect(serialized).not.toContain("works_at");
    expect(serialized).not.toContain("claims");
    expect(serialized).not.toContain("frontier:copied:one");
    const repeatedCandidate = materializeMemoryEvaluationResult(context(), request("candidate", 1));
    expect(() => pairMemoryEvaluationResults(baseline, repeatedCandidate)).toThrow("unpaired_results");
    expect(() => pairMemoryEvaluationResults(candidate, baseline)).toThrow("invalid_pair");
  });
});
