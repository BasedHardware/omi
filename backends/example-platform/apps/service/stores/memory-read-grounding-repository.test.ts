import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { buildContentSafeRecallTrace } from "../../../core/retrieve/recall-integrity";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkNormalizedResultDigest } from "./durable-memory-work-result-repository";
import { defineMemoryEvaluationEvidenceSource } from "./memory-evaluation-evidence-source";
import {
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  type MemoryEvaluationResult,
  type MemoryEvaluationStageRequest,
} from "./memory-shadow-result-repository";
import {
  defineMemoryReadGroundingRepository,
  materializeFinalizedMemoryReadGrounding,
} from "./memory-read-grounding-repository";
import { buildMemoryReadEvaluationResult } from "../workers/memory-read-evaluation-result";

const hex = (character: string): string => character.repeat(64);
const traceRef = (value: string): `tr1_${string}` => `tr1_${sha256CanonicalContent({ value })}`;
const CAPABILITY = "memories.experiments.shadow";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow", owner = "account:alice", epoch = 7) => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:grounding", account_id: owner,
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: epoch, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: hex("a"),
}, 150);

const bundle = () => {
  const strategy = registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: "strategy:retrieval:authority",
    work_kind: "retrieval",
    coordinates: {
      strategy_version: "retrieval:authority:v1", model_version: "deepseek:v1",
      prompt_version: "prompt:v1", policy_version: "policy:v1", code_version: "code:v1",
      schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
      result_contract_version: "memory-read-evaluation-result-v1",
      speaker_strategy_version: "none", boundary_strategy_version: "none",
    },
  });
  const candidate = registerMemoryStrategy({
    version: strategy.version,
    strategy_id: "strategy:retrieval:candidate",
    work_kind: strategy.work_kind,
    coordinates: { ...strategy.coordinates, strategy_version: "retrieval:candidate:v1" },
  });
  const strategies = [strategy, candidate];
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:retrieval:v1", work_kind: "retrieval", unit_kind: "session",
    key_version: "key:v1", authority_strategy_id: strategy.strategy_id,
    shadow_candidates: [{ strategy_id: candidate.strategy_id, basis_points: 10_000 }],
  }, strategies);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(6)).assign({
    owner_account_id: "account:alice", unit_ref: "session:grounding", policy, strategies,
  });
};

const result = async (): Promise<Readonly<MemoryEvaluationResult>> => {
  const assignment = bundle();
  const source = defineMemoryEvaluationEvidenceSource(async (authorized, request) => ({
    kind: "found", owner_account_id: authorized.account_id, account_epoch: authorized.account_epoch,
    source_kind: request.source_kind, source_ref: request.source_ref, input_frontier: request.input_frontier,
    payload: { query: "Where do I work?", authorized_projection: [] },
  }));
  const copied = await source.load(context(), {
    source_kind: "authorized_graph_snapshot", source_ref: "source:grounding", input_frontier: "frontier:grounding",
  });
  if (copied.kind !== "found") throw new Error("fixture copied input unavailable");
  const ref = traceRef("evidence");
  const trace = buildContentSafeRecallTrace({
    version: "recall-trace-v1", traceRef: traceRef("root"), strategyVersion: "retrieval:authority:v1",
    projectionFreshness: "fresh", outcome: "grounded", latencyMs: 1, tokenCounts: { input: 1, output: 1 },
    stages: { eligible: [ref], selected: [ref], hydrated: [ref], policyEligible: [ref], cited: [ref], grounded: [ref] },
  });
  const read = buildMemoryReadEvaluationResult(context(), {
    assignment_bundle: assignment,
    assignment_id: assignment.authority.assignment_id,
    copied_input: copied.copied_input,
    evaluation_role: "baseline", repeat_ordinal: 0,
    query_text: "Where do I work?", answer_text: "You work at Omi.", absence: null,
    assertions: [{ ordinal: 0, text: "You work at Omi.", citations: [ref] }], recall_trace: trace,
  });
  const body = {
    assignment_bundle: assignment,
    assignment_id: assignment.authority.assignment_id,
    account_epoch: 7,
    evaluation_role: "baseline" as const,
    evaluation_mode: "offline_replay" as const,
    evaluation_run_id: `mer1_${hex("b")}`,
    input_frontier: "frontier:grounding",
    input_digest: copied.copied_input.input_digest,
    repeat_ordinal: 0,
    result_contract_version: read.version,
    response_digest: sha256CanonicalContent({ read }),
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest(read.version, read as never),
    normalized_result: read,
  };
  const request: MemoryEvaluationStageRequest = {
    ...body,
    request_digest: memoryEvaluationStageRequestDigest(context(), body),
  };
  return { evaluationResult: materializeMemoryEvaluationResult(context(), request), stageRequest: request };
};

const artifact = async () => {
  const { evaluationResult, stageRequest } = await result();
  const ref = (evaluationResult.normalized_result as { recall_trace: { stages: { grounded: string[] } } })
    .recall_trace.stages.grounded[0]! as `tr1_${string}`;
  return {
    evaluationResult,
    stageRequest,
    artifact: materializeFinalizedMemoryReadGrounding({
      evaluation_result: evaluationResult,
      projection_authorization_digest: hex("c"),
      reader_projection_digest: hex("d"),
      projected_content_digest: hex("e"),
      rows: [{ trace_ref: ref, contributing_subject_classes: ["bystander"] }],
    }),
  };
};

describe("finalized memory read grounding repository", () => {
  test("stages and reloads one exact artifact with the result in the same adapter call", async () => {
    const stored = new Map<string, unknown>();
    let receivedResult: MemoryEvaluationResult | null = null;
    const repository = defineMemoryReadGroundingRepository({
      stage: async (_authorized, selectedResult, selectedArtifact) => {
        receivedResult = selectedResult;
        const persisted = JSON.parse(JSON.stringify(selectedArtifact));
        stored.set(selectedResult.evaluation_result_id, persisted);
        return { kind: "staged", artifact: persisted };
      },
      load: async (_authorized, selectedResult) => {
        const persisted = stored.get(selectedResult.evaluation_result_id);
        return persisted ? { kind: "found", artifact: persisted } : { kind: "missing" };
      },
    });
    const fixture = await artifact();
    const staged = await repository.stage(context(), fixture.evaluationResult, fixture.artifact, fixture.stageRequest);
    expect(staged).toMatchObject({ kind: "staged", artifact: { grounded_reference_count: 1 } });
    expect(receivedResult).toBe(fixture.evaluationResult);
    expect(await repository.load(context(), fixture.evaluationResult)).toEqual({
      kind: "found", artifact: staged.kind === "staged" ? staged.artifact : null,
    });
    expect(JSON.stringify(staged)).not.toMatch(/Where do I work|You work at Omi|source:grounding/);
    expect(Object.keys(repository)).toEqual(["stage", "load"]);
  });

  test("total closure, ordering, coordinates, brands, and authority fail before the adapter", async () => {
    let calls = 0;
    const repository = defineMemoryReadGroundingRepository({
      stage: async () => { calls += 1; return { kind: "idempotency_conflict" }; },
      load: async () => { calls += 1; return { kind: "missing" }; },
    });
    const fixture = await artifact();
    expect(() => materializeFinalizedMemoryReadGrounding({
      evaluation_result: fixture.evaluationResult,
      projection_authorization_digest: hex("c"), reader_projection_digest: hex("d"), projected_content_digest: hex("e"),
      rows: [],
    })).toThrow("incomplete_grounding");
    expect(() => materializeFinalizedMemoryReadGrounding({
      evaluation_result: fixture.evaluationResult,
      projection_authorization_digest: hex("c"), reader_projection_digest: hex("d"), projected_content_digest: hex("e"),
      rows: [{ trace_ref: fixture.artifact.rows[0]!.trace_ref, contributing_subject_classes: ["owner", "bystander"] }],
    })).toThrow("invalid_row");
    expect(() => materializeFinalizedMemoryReadGrounding({
      evaluation_result: fixture.evaluationResult,
      projection_authorization_digest: "not-a-digest", reader_projection_digest: hex("d"), projected_content_digest: hex("e"),
      rows: fixture.artifact.rows,
    })).toThrow("invalid_projection_coordinate");
    await expect(repository.stage(context("memories.work.execute"), fixture.evaluationResult, fixture.artifact, fixture.stageRequest))
      .rejects.toThrow("capability_denied");
    await expect(repository.stage(context(CAPABILITY, "account:bob"), fixture.evaluationResult, fixture.artifact, fixture.stageRequest))
      .rejects.toThrow("authority_mismatch");
    await expect(repository.stage(context(), fixture.evaluationResult, { ...fixture.artifact } as never, fixture.stageRequest))
      .rejects.toThrow("unverified_artifact");
    const { request_digest: _requestDigest, ...changedBody } = {
      ...fixture.stageRequest, response_digest: hex("f"),
    };
    await expect(repository.stage(context(), fixture.evaluationResult, fixture.artifact, {
      ...changedBody,
      request_digest: memoryEvaluationStageRequestDigest(context(), changedBody),
    })).rejects.toThrow("stage_request_result_mismatch");
    expect(calls).toBe(0);
  });

  test("adapter failures are contained and changed persisted bytes cannot masquerade as replay", async () => {
    const fixture = await artifact();
    const unavailable = defineMemoryReadGroundingRepository({
      stage: async () => { throw new Error("secret database error"); },
      load: async () => { throw new Error("secret database error"); },
    });
    await expect(unavailable.stage(context(), fixture.evaluationResult, fixture.artifact, fixture.stageRequest))
      .resolves.toEqual({ kind: "source_unavailable" });
    await expect(unavailable.load(context(), fixture.evaluationResult))
      .resolves.toEqual({ kind: "source_unavailable" });

    const forged = defineMemoryReadGroundingRepository({
      stage: async () => ({ kind: "replayed", artifact: { ...fixture.artifact, projected_content_digest: hex("f") } }),
      load: async () => ({ kind: "missing" }),
    });
    await expect(forged.stage(context(), fixture.evaluationResult, fixture.artifact, fixture.stageRequest))
      .rejects.toThrow("artifact_digest_mismatch");
  });
});
