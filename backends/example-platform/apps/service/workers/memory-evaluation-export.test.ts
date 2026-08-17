import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
  type MemoryStrategyAssignmentBundle,
} from "../../../core/consolidate/strategy-assignment";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkNormalizedResultDigest } from "../stores/durable-memory-work-result-repository";
import {
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  pairMemoryEvaluationResults,
  type MemoryEvaluationRole,
  type MemoryEvaluationStageRequest,
} from "../stores/memory-shadow-result-repository";
import { buildMemoryEvaluationExport } from "./memory-evaluation-export";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:evaluator", account_id: "account:alice",
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const assignmentSetup = (() => {
  const strategy = (id: string, prompt: string) => registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION, strategy_id: id, work_kind: "formation",
    coordinates: {
      strategy_version: "formation:v1", model_version: "deepseek:v1",
      prompt_version: prompt, policy_version: "policy:v1", code_version: "code:v1",
      schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
      result_contract_version: "formation-result:v2", speaker_strategy_version: "speaker:v1",
      boundary_strategy_version: "boundary:v1",
    },
  });
  const authority = strategy("strategy:raw:authority", "prompt:v1");
  const candidate = strategy("strategy:raw:candidate", "prompt:v2");
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:formation:v1", work_kind: "formation", unit_kind: "session",
    key_version: "assignment-key:v1", authority_strategy_id: authority.strategy_id,
    shadow_candidates: [{ strategy_id: candidate.strategy_id, basis_points: 10_000 }],
  }, [authority, candidate]);
  return {
    assigner: createMemoryStrategyAssigner(new Uint8Array(32).fill(5)),
    policy,
    strategies: [authority, candidate],
  };
})();
const assignedBundle = (unitRef: string) => assignmentSetup.assigner.assign({
  owner_account_id: "account:alice", unit_ref: unitRef,
  policy: assignmentSetup.policy, strategies: assignmentSetup.strategies,
});
const bundle = assignedBundle("session:one");
const alternateBundle = assignedBundle("session:two");

const result = (
  role: MemoryEvaluationRole,
  repeat: number,
  run = `mer1_${digest("b")}`,
  contentTag = "one",
  evaluationBundle: Readonly<MemoryStrategyAssignmentBundle> = bundle,
) => {
  const selected = role === "baseline" ? evaluationBundle.authority : evaluationBundle.shadows[0]!;
  const normalized = { secret_claims: [{ person: "David", content_tag: contentTag }] };
  const body = {
    assignment_bundle: evaluationBundle,
    assignment_id: selected.assignment_id,
    account_epoch: 7,
    evaluation_role: role,
    evaluation_mode: "offline_replay" as const,
    evaluation_run_id: run,
    input_frontier: "frontier:raw:secret",
    input_digest: digest("c"),
    repeat_ordinal: repeat,
    result_contract_version: "formation-result:v2",
    response_digest: role === "baseline" ? digest("d") : digest("e"),
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest("formation-result:v2", normalized),
    normalized_result: normalized,
  };
  const request: MemoryEvaluationStageRequest = {
    ...body,
    request_digest: memoryEvaluationStageRequestDigest(context(), body),
  };
  return materializeMemoryEvaluationResult(context(), request);
};

const pair = (repeat: number, run?: string, evaluationBundle = bundle) =>
  pairMemoryEvaluationResults(
    result("baseline", repeat, run, "one", evaluationBundle),
    result("candidate", repeat, run, "one", evaluationBundle),
  );

describe("content-safe memory evaluation export", () => {
  test("is deterministic, opaque, and sufficient to join paired repeats", () => {
    const first = pair(0);
    const second = pair(1);
    const manifest = buildMemoryEvaluationExport(context(), [second, first]);
    expect(manifest).toMatchObject({
      version: "memory-evaluation-export-v1", evaluation_mode: "offline_replay",
      pair_count: 2, repeat_count: 2, candidate_strategy_count: 1,
    });
    expect(manifest.pairs.map((row) => row.repeat_ordinal)).toEqual([0, 1]);
    expect(buildMemoryEvaluationExport(context(), [first, second])).toEqual(manifest);
    const serialized = JSON.stringify(manifest);
    for (const forbidden of [
      "account:alice", "strategy:raw", "frontier:raw", "secret_claims", "David",
      first.input_digest, first.baseline_result_digest, first.candidate_result_digest,
    ]) expect(serialized).not.toContain(forbidden);
    expect(manifest.export_digest).toMatch(/^[a-f0-9]{64}$/);
  });

  test("strategy references stay stable across assignment bundles", () => {
    const first = buildMemoryEvaluationExport(context(), [pair(0, undefined, bundle)]);
    const second = buildMemoryEvaluationExport(context(), [pair(0, undefined, alternateBundle)]);
    expect(first.assignment_bundle_ref).not.toBe(second.assignment_bundle_ref);
    expect(first.pairs[0]!.baseline_strategy_ref).toBe(second.pairs[0]!.baseline_strategy_ref);
    expect(first.pairs[0]!.candidate_strategy_ref).toBe(second.pairs[0]!.candidate_strategy_ref);
  });

  test("forged, duplicated, mixed-run, and wrong-capability inputs fail closed", () => {
    const first = pair(0);
    expect(() => buildMemoryEvaluationExport(context(), [{ ...first }])).toThrow("unverified_pair");
    expect(() => buildMemoryEvaluationExport(context(), [first, first])).toThrow("duplicate_pair");
    expect(() => buildMemoryEvaluationExport(context(), [first, pair(1, `mer1_${digest("f")}`)]))
      .toThrow("mixed_export_coordinates");
    const conflicting = pairMemoryEvaluationResults(
      result("baseline", 0, undefined, "two"),
      result("candidate", 0, undefined, "two"),
    );
    expect(() => buildMemoryEvaluationExport(context(), [first, conflicting]))
      .toThrow("duplicate_pair_coordinate");
    expect(() => buildMemoryEvaluationExport(context("memories.work.execute"), [first]))
      .toThrow("capability_denied");
    expect(() => buildMemoryEvaluationExport(context(), []))
      .toThrow("invalid_pairs");
    expect(() => buildMemoryEvaluationExport(context(), new Proxy([first], {}) as never))
      .toThrow("invalid_pairs");
    const accessor: unknown[] = [];
    Object.defineProperty(accessor, "0", { enumerable: true, get: () => first });
    Object.defineProperty(accessor, "length", { value: 1 });
    expect(() => buildMemoryEvaluationExport(context(), accessor as never))
      .toThrow("invalid_pairs");
  });
});
