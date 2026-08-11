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
import { defineMemoryEvaluationEvidenceSource } from "../stores/memory-evaluation-evidence-source";
import { defineMemoryReadGroundingRepository } from "../stores/memory-read-grounding-repository";
import { defineMemoryShadowResultRepository } from "../stores/memory-shadow-result-repository";
import {
  defineMemoryAuthorizedQueryGroundingProducer,
  type AuthorizedQueryEvaluationInput,
  type AuthorizedQueryGroundingProducerRequest,
  type AuthorizedQueryModelRequest,
} from "./memory-authorized-query-grounding-producer";

const hex = (character: string): string => character.repeat(64);
const traceRef = (value: string): `tr1_${string}` => `tr1_${sha256CanonicalContent({ value })}`;
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:query-grounding", account_id: "account:alice",
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: hex("a"),
}, 150);

const strategies = (["authority", "candidate"] as const).map((role) => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: `strategy:authorized-query:${role}`,
  work_kind: "retrieval",
  coordinates: {
    strategy_version: `authorized-query:${role}:v1`, model_version: "deepseek:v1",
    prompt_version: `prompt:${role}:v1`, policy_version: "policy:v1", code_version: "code:v1",
    schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
    result_contract_version: "memory-read-evaluation-result-v1",
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
}));
const policy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:authorized-query:v1", work_kind: "retrieval", unit_kind: "session",
  key_version: "key:v1", authority_strategy_id: strategies[0]!.strategy_id,
  shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
}, strategies);
const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(7)).assign({
  owner_account_id: "account:alice", unit_ref: "session:authorized-query", policy, strategies,
});
const refs = [traceRef("alpha"), traceRef("beta")].sort();

const validPayload = (): AuthorizedQueryEvaluationInput => ({
  version: "authorized-query-evaluation-input-v1",
  query_text: "Where do I work?",
  projection_authorization_digest: hex("c"),
  reader_projection_digest: hex("d"),
  projected_content_digest: hex("e"),
  classifier_version: "policy-classifier-generic-v1",
  candidates: [
    { trace_ref: refs[0]!, text: "I work at Omi.", contributing_subject_classes: ["bystander", "owner"] },
    { trace_ref: refs[1]!, text: "Omi builds memory tools.", contributing_subject_classes: ["owner"] },
  ],
});

const request: AuthorizedQueryGroundingProducerRequest = {
  assignment_bundle: assignment,
  assignment_id: assignment.authority.assignment_id,
  evaluation_role: "baseline",
  evaluation_run_id: `mer1_${hex("b")}`,
  repeat_ordinal: 0,
  source_request: {
    source_kind: "authorized_graph_snapshot",
    source_ref: "source:authorized-query",
    input_frontier: "frontier:authorized-query",
  },
};

const produced = (modelRequest: AuthorizedQueryModelRequest, cited = refs[0]!) => ({
  kind: "produced" as const,
  response_digest: hex("f"),
  answer_text: "You work at Omi.",
  absence: null,
  assertions: [{ ordinal: 0, text: "You work at Omi.", citations: [cited] }],
  recall_trace: buildContentSafeRecallTrace({
    version: "recall-trace-v1", traceRef: traceRef("run"),
    strategyVersion: modelRequest.strategy.coordinates.strategy_version,
    projectionFreshness: "fresh", outcome: "grounded", latencyMs: 1,
    tokenCounts: { input: 10, output: 5 },
    stages: {
      eligible: [cited], selected: [cited], hydrated: [cited],
      policyEligible: [cited], cited: [cited], grounded: [cited],
    },
  }),
});

const setup = (
  payloadForCall: (call: number) => AuthorizedQueryEvaluationInput = validPayload,
  model: (request: AuthorizedQueryModelRequest) => Promise<unknown> = async (value) => produced(value),
) => {
  let sourceCalls = 0;
  let modelCalls = 0;
  let stageCalls = 0;
  let storedResult: unknown = null;
  let storedArtifact: unknown = null;
  let capturedModelRequest: AuthorizedQueryModelRequest | null = null;
  const source = defineMemoryEvaluationEvidenceSource(async (authorized, selected) => {
    sourceCalls += 1;
    return {
      kind: "found", owner_account_id: authorized.account_id, account_epoch: authorized.account_epoch,
      source_kind: selected.source_kind, source_ref: selected.source_ref, input_frontier: selected.input_frontier,
      payload: payloadForCall(sourceCalls),
    };
  });
  const resultRepository = defineMemoryShadowResultRepository({
    load: async () => storedResult === null ? { kind: "missing" } : { kind: "found", result: storedResult },
    stage: async () => ({ kind: "serialization_retryable" }),
    recordPair: async () => ({ kind: "serialization_retryable" }),
  });
  const groundingRepository = defineMemoryReadGroundingRepository({
    stage: async (_authorized, result, artifact) => {
      stageCalls += 1;
      storedResult = JSON.parse(JSON.stringify(result));
      storedArtifact = JSON.parse(JSON.stringify(artifact));
      return { kind: "staged", artifact: storedArtifact };
    },
    load: async () => storedArtifact === null ? { kind: "missing" } : { kind: "found", artifact: storedArtifact },
  });
  const producer = defineMemoryAuthorizedQueryGroundingProducer({
    evidence_source: source,
    result_repository: resultRepository,
    grounding_repository: groundingRepository,
    produce: async (value) => {
      modelCalls += 1;
      capturedModelRequest = value;
      return model(value);
    },
  });
  return {
    producer,
    counts: () => ({ sourceCalls, modelCalls, stageCalls }),
    captured: () => capturedModelRequest,
    clearArtifact: () => { storedArtifact = null; },
  };
};

describe("authorized query grounding producer", () => {
  test("stages exact result plus source-derived grounding and replays with zero model calls", async () => {
    const fixture = setup();
    const first = await fixture.producer.run(context(), request);
    expect(first).toMatchObject({
      kind: "completed", completion: "staged", model_calls: 1,
      artifact: {
        projection_authorization_digest: hex("c"),
        reader_projection_digest: hex("d"),
        projected_content_digest: hex("e"),
        rows: [{ trace_ref: refs[0], contributing_subject_classes: ["bystander", "owner"] }],
      },
    });
    expect(fixture.counts()).toEqual({ sourceCalls: 2, modelCalls: 1, stageCalls: 1 });
    const modelInput = fixture.captured()!;
    expect(Object.keys(modelInput.candidates[0]!)).toEqual(["trace_ref", "text"]);
    expect(JSON.stringify(modelInput)).not.toMatch(/bystander|projection_authorization|account:alice|source:authorized-query/);

    const replay = await fixture.producer.run(context(), request);
    expect(replay).toMatchObject({ kind: "completed", completion: "replayed", model_calls: 0 });
    expect(fixture.counts()).toEqual({ sourceCalls: 4, modelCalls: 1, stageCalls: 1 });
    expect(replay.kind === "completed" && first.kind === "completed"
      ? replay.artifact.artifact_digest : null).toBe(first.kind === "completed" ? first.artifact.artifact_digest : null);
  });

  test("a final projection change invalidates after the model and before staging", async () => {
    const fixture = setup((call) => call === 1 ? validPayload() : {
      ...validPayload(), projected_content_digest: hex("9"),
    });
    await expect(fixture.producer.run(context(), request)).resolves.toEqual({
      kind: "stopped", stop_code: "read_invalidated", failure_code: null, model_calls: 1,
    });
    expect(fixture.counts()).toEqual({ sourceCalls: 2, modelCalls: 1, stageCalls: 0 });
  });

  test("replay revalidates before releasing stored bytes", async () => {
    const fixture = setup((call) => call < 4 ? validPayload() : {
      ...validPayload(), reader_projection_digest: hex("8"),
    });
    expect((await fixture.producer.run(context(), request)).kind).toBe("completed");
    await expect(fixture.producer.run(context(), request)).resolves.toEqual({
      kind: "stopped", stop_code: "read_invalidated", failure_code: null, model_calls: 0,
    });
    expect(fixture.counts()).toEqual({ sourceCalls: 4, modelCalls: 1, stageCalls: 1 });
  });

  test("malformed source classes and model refs outside the copied set fail before stage", async () => {
    const malformed = setup(() => ({
      ...validPayload(),
      candidates: [{
        trace_ref: refs[0]!, text: "I work at Omi.",
        contributing_subject_classes: ["owner", "bystander"],
      }],
    }));
    await expect(malformed.producer.run(context(), request)).resolves.toEqual({
      kind: "stopped", stop_code: "invalid_input", failure_code: null, model_calls: 0,
    });
    expect(malformed.counts()).toEqual({ sourceCalls: 1, modelCalls: 0, stageCalls: 0 });

    const unknown = traceRef("outside");
    const forged = setup(validPayload, async (value) => produced(value, unknown));
    await expect(forged.producer.run(context(), request)).resolves.toEqual({
      kind: "stopped", stop_code: "invalid_result", failure_code: null, model_calls: 1,
    });
    expect(forged.counts()).toEqual({ sourceCalls: 1, modelCalls: 1, stageCalls: 0 });
  });

  test("a stored result without grounding is corruption and never regenerates", async () => {
    const fixture = setup();
    expect((await fixture.producer.run(context(), request)).kind).toBe("completed");
    fixture.clearArtifact();
    await expect(fixture.producer.run(context(), request)).resolves.toEqual({
      kind: "stopped", stop_code: "incomplete_persistence", failure_code: null, model_calls: 0,
    });
    expect(fixture.counts()).toEqual({ sourceCalls: 3, modelCalls: 1, stageCalls: 1 });
  });

  test("request authority and assignment fail before source/model/store access", async () => {
    const fixture = setup();
    await expect(fixture.producer.run(context("memories.work.execute"), request)).rejects.toThrow("capability_denied");
    await expect(fixture.producer.run(context(), {
      ...request, assignment_id: assignment.shadows[0]!.assignment_id,
    })).rejects.toThrow("assignment_role_mismatch");
    expect(fixture.counts()).toEqual({ sourceCalls: 0, modelCalls: 0, stageCalls: 0 });
  });

  test("hostile model and dependency accessors are rejected without execution", async () => {
    let getterCalls = 0;
    const hostile = setup(validPayload, async () => Object.defineProperty({}, "kind", {
      enumerable: true,
      get() { getterCalls += 1; return "produced"; },
    }));
    await expect(hostile.producer.run(context(), request)).resolves.toEqual({
      kind: "stopped", stop_code: "invalid_result", failure_code: null, model_calls: 1,
    });
    expect(getterCalls).toBe(0);

    const dependencies = Object.defineProperty({}, "produce", {
      enumerable: true,
      get() { getterCalls += 1; return async () => ({}); },
    }) as never;
    expect(() => defineMemoryAuthorizedQueryGroundingProducer(dependencies)).toThrow("invalid_dependencies");
    expect(getterCalls).toBe(0);
  });
});
