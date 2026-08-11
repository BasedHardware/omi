import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { GraphSnapshot } from "../../../core/retrieve";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { buildContentSafeRecallTrace } from "../../../core/retrieve/recall-integrity";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";
import { defineMemoryReadGroundingRepository } from "../stores/memory-read-grounding-repository";
import {
  defineMemoryShadowResultRepository,
  memoryEvaluationResultId,
  type MemoryEvaluationPair,
  type MemoryShadowResultImplementation,
} from "../stores/memory-shadow-result-repository";
import { composeMemoryQueryEvaluation } from "./memory-query-evaluation";

const hex = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = () => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:query-composition", account_id: "account:alice",
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability: "memories.experiments.shadow",
  grant_id: "grant:evaluator", grant_version: 1, account_epoch: 7,
  destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
  authentication_strength: "service-workload", issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200, authorization_state_digest: hex("a"),
}, 150);

const strategies = ["authority", "candidate"].map((name) => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: `strategy:query-composition:${name}`,
  work_kind: "retrieval",
  coordinates: {
    strategy_version: `query-composition:${name}:v1`, model_version: "deepseek:v1",
    prompt_version: `prompt:${name}:v1`, policy_version: "policy:v1", code_version: "code:v1",
    schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
    result_contract_version: "memory-read-evaluation-result-v1",
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
}));
const policy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:query-composition:v1", work_kind: "retrieval", unit_kind: "session",
  key_version: "key:v1", authority_strategy_id: strategies[0]!.strategy_id,
  shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
}, strategies);
const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(17)).assign({
  owner_account_id: "account:alice", unit_ref: "session:query-composition", policy, strategies,
});

const graph = (empty = false): GraphSnapshot => ({
  owner_account_id: "account:alice",
  graph_generation: 31,
  claims: empty ? [] : [{
    revision_id: "claim:omi:r1",
    commit_sequence: 1,
    placement_status: "canonical",
    claim: {
      claim_lineage_id: "lineage:omi", claim_revision_id: "claim:omi:r1",
      owner_account_id: "account:alice", predicate: "states", arguments: [],
      temporal_scope: { observed_at: "2026-08-11T00:00:00Z", precision: "instant" },
      evidence_refs: ["evidence:omi"],
      policy_labels: ["subject:owner", "sensitivity:generic", "capture:voice"],
      source_language: "en", scope: { locality: "durable", scope_ref: null },
      lifecycle: "canonical", canonical_claim_id: "canonical:omi",
      source_provisional_revision_ids: [],
    },
  }],
  entities: [],
  events: empty ? [] : [{
    revision_id: "event:omi:r1",
    event: {
      event_id: "event:omi", event_revision_id: "event:omi:r1",
      owner_account_id: "account:alice", capture_session_id: "capture:omi",
      stream_id: "stream:voice", event_kind: "transcript", payload_schema_ref: "transcript:v1",
      schema_version: "v1", payload: {}, event_time: "2026-08-11T00:00:00Z",
      ingest_time: "2026-08-11T00:00:01Z", source_sequence: 1,
      evidence_addressable_refs: ["evidence:omi"], source_trust: "test",
      policy_labels: [], canonical_redacted_hash: "hash:omi",
    },
  }],
  evidence: empty ? [] : [{
    revision_id: "evidence:omi:r1",
    commit_sequence: 1,
    evidence: {
      evidence_id: "evidence:omi", event_revision_id: "event:omi:r1",
      source_unit_ref: "unit:omi", range: { start: 0, end: 29 },
      excerpt: "I said Omi builds memory tools.", source_identity_ref: null,
      speaker_rendering: null, source_local_mention_ref: null, state: "active",
      source_trust: "test", policy_labels: [], source_independence_key: "capture:omi",
    },
  }],
  adjacency: [],
});

const request = Object.freeze({
  assignment_bundle: assignment,
  evaluation_run_id: `mer1_${hex("b")}`,
  source_request: Object.freeze({
    source_kind: "authorized_graph_snapshot" as const,
    source_ref: "source:query-composition",
    input_frontier: "frontier:query-composition",
  }),
  repeats: 1,
});

const setup = (empty = false) => {
  const results = new Map<string, unknown>();
  const artifacts = new Map<string, unknown>();
  const pairs = new Map<string, Readonly<MemoryEvaluationPair>>();
  let graphLoads = 0;
  let traceEncodes = 0;
  let modelCalls = 0;
  let pairWrites = 0;
  let modelBytes = "";
  const repositoryImplementation: MemoryShadowResultImplementation = {
    load: async (authorized, coordinate) => {
      const found = results.get(memoryEvaluationResultId(authorized, coordinate));
      return found ? { kind: "found", result: found } : { kind: "missing" };
    },
    stage: async () => ({ kind: "serialization_retryable" }),
    recordPair: async (_authorized, pair) => {
      pairWrites += 1;
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
  const coordinator = composeMemoryQueryEvaluation({
    load_graph: async (authorized, selected) => {
      graphLoads += 1;
      return {
        kind: "found", owner_account_id: authorized.account_id,
        account_epoch: authorized.account_epoch, source_ref: selected.source_ref,
        input_frontier: selected.input_frontier, query_text: "What did I say about Omi?",
        account_timezone: "America/New_York", graph_snapshot: graph(empty),
      };
    },
    encode_trace_ref: ({ reader_projection_digest, evidence_closure_digest }) => {
      traceEncodes += 1;
      return createReaderScopedOpaqueCodecs({
        root_secret: new Uint8Array(32).fill(19), reader_projection_digest,
      }).encodeTraceRef(evidence_closure_digest);
    },
    result_repository: resultRepository,
    grounding_repository: groundingRepository,
    produce: async (modelRequest) => {
      modelCalls += 1;
      modelBytes = JSON.stringify(modelRequest);
      const cited = modelRequest.candidates[0]!.trace_ref;
      return {
        kind: "produced",
        response_digest: sha256CanonicalContent({
          strategy_id: modelRequest.strategy.strategy_id,
          repeat_ordinal: modelRequest.repeat_ordinal,
        }),
        answer_text: "You said Omi builds memory tools.", absence: null,
        assertions: [{ ordinal: 0, text: "You said Omi builds memory tools.", citations: [cited] }],
        recall_trace: buildContentSafeRecallTrace({
          version: "recall-trace-v1",
          traceRef: `tr1_${sha256CanonicalContent({ run: modelRequest.strategy.strategy_id })}`,
          strategyVersion: modelRequest.strategy.coordinates.strategy_version,
          projectionFreshness: "fresh", outcome: "grounded", latencyMs: 1,
          tokenCounts: { input: 8, output: 6 },
          stages: {
            eligible: [cited], selected: [cited], hydrated: [cited],
            policyEligible: [cited], cited: [cited], grounded: [cited],
          },
        }),
      };
    },
  });
  return {
    coordinator,
    counts: () => ({ graphLoads, traceEncodes, modelCalls, pairWrites }),
    modelBytes: () => modelBytes,
    results, artifacts, pairs,
  };
};

describe("single memory query evaluation composition", () => {
  test("grounds and pairs end to end, exposing only opaque receipts and zero-call replay", async () => {
    const fixture = setup();
    expect(Object.keys(fixture.coordinator)).toEqual(["run"]);
    const first = await fixture.coordinator.run(context(), request);
    expect(first).toMatchObject({
      kind: "completed", observed_model_calls: 2, staged_results: 2, replayed_results: 0,
      recorded_pairs: 1, replayed_pairs: 0,
    });
    expect(first.pair_receipts).toHaveLength(1);
    expect(fixture.counts()).toEqual({ graphLoads: 4, traceEncodes: 4, modelCalls: 2, pairWrites: 1 });
    expect(fixture.results.size).toBe(2);
    expect(fixture.artifacts.size).toBe(2);
    expect(fixture.pairs.size).toBe(1);
    expect(fixture.modelBytes()).toContain("I said Omi builds memory tools.");
    expect(fixture.modelBytes()).not.toMatch(/subject|owner|account:alice|evidence:omi|source:query/);

    const serialized = JSON.stringify(first);
    for (const forbidden of [
      "account:alice", "What did", "You said", "I said", "tr1_", "subject", "owner",
      "evidence:omi", "source:query", "deepseek", "prompt", "response_digest",
    ]) expect(serialized).not.toContain(forbidden);

    const replay = await fixture.coordinator.run(context(), request);
    expect(replay).toEqual({
      kind: "completed", pair_receipts: first.pair_receipts,
      observed_model_calls: 0, staged_results: 0, replayed_results: 2,
      recorded_pairs: 0, replayed_pairs: 1,
    });
    expect(fixture.counts()).toEqual({ graphLoads: 8, traceEncodes: 8, modelCalls: 2, pairWrites: 2 });
  });

  test("an empty owner projection pairs without calling the model or trace codec", async () => {
    const fixture = setup(true);
    const outcome = await fixture.coordinator.run(context(), request);
    expect(outcome).toMatchObject({
      kind: "completed", observed_model_calls: 0, staged_results: 2,
      recorded_pairs: 1,
    });
    expect(fixture.counts()).toEqual({ graphLoads: 4, traceEncodes: 0, modelCalls: 0, pairWrites: 1 });
  });

  test("outer accessors, extras, and forged repositories fail before dependency use", () => {
    let getterCalls = 0;
    const fixture = setup();
    const hostile = Object.defineProperty({}, "load_graph", {
      enumerable: true,
      get() { getterCalls += 1; return () => null; },
    });
    for (const [key, value] of Object.entries({
      encode_trace_ref: () => "", result_repository: {}, grounding_repository: {}, produce: () => null,
    })) Object.defineProperty(hostile, key, { enumerable: true, value });
    expect(() => composeMemoryQueryEvaluation(hostile as never)).toThrow("invalid_config");
    expect(getterCalls).toBe(0);

    expect(() => composeMemoryQueryEvaluation({
      load_graph: async () => ({ kind: "not_found" }),
      encode_trace_ref: () => "",
      result_repository: {} as never,
      grounding_repository: {} as never,
      produce: async () => ({ kind: "failed", error_code: "dependency_unavailable" }),
    })).toThrow("unverified_repository");
    expect(fixture.counts()).toEqual({ graphLoads: 0, traceEncodes: 0, modelCalls: 0, pairWrites: 0 });
  });
});
