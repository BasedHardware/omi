import { describe, expect, test } from "bun:test";

import type { GraphSnapshot } from "../../../core/retrieve";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineMemoryShadowResultRepository,
  materializeMemoryEvaluationResult,
  memoryEvaluationResultId,
  type MemoryEvaluationPair,
  type MemoryEvaluationResult,
} from "../stores/memory-shadow-result-repository";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../stores/listen-store";
import { formationWorkInputSnapshotDigest } from "../workers/formation-work-input-repository";
import {
  ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
  defineAttributionBeliefShadowProducer,
} from "../workers/attribution-belief-shadow-producer";
import { defineMemoryOfflineReplayCoordinator } from "../workers/memory-offline-replay-coordinator";
import {
  materializeListenFormationSnapshot,
  sealListenFormationFinalization,
} from "./formation-ingestion";
import {
  defineAcceptedFormationBeliefSource,
  defineListenAttributionBeliefEvaluationSource,
  defineListenAttributionBeliefInputRepository,
  defineListenAttributionBeliefInputStager,
  listenAttributionBeliefInputStageRequestDigest,
  materializeListenAttributionBeliefInputSet,
  materializeStoredListenAttributionBeliefInput,
  parseListenAttributionBeliefInputSet,
  type ListenAttributionBeliefInputSet,
  type StoredListenAttributionBeliefInput,
} from "./attribution-belief-input-source";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:belief-source", account_id: owner,
  application_id: "app:belief-source", credential_id: "credential:belief-source",
  credential_generation: 1, capability: "memories.experiments.shadow",
  grant_id: "grant:belief-source", grant_version: 1, account_epoch: 7,
  destination_activation_revision: 1, lifecycle_state: "active", deletion_epoch: null,
  authentication_strength: "service-workload", issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200, authorization_state_digest: digest("a"),
}, 150);

const segments = (): readonly ListenTranscriptSegment[] => Object.freeze([
  Object.freeze({
    id: "segment:one", text: "I am planning the Atlas launch.", is_user: true,
    start: 1, end: 3,
  }),
  Object.freeze({
    id: "segment:two", text: "A second speaker prefers Friday.", is_user: false,
    start: 4, end: 7,
  }),
]);

const session = (): ListenSessionRecord => Object.freeze({
  id: "listen-session:belief-source", conversationId: "conversation:belief-source",
  clientConversationId: null, startedAt: "2026-08-12T12:00:00.000Z",
  updatedAt: "2026-08-12T12:01:00.000Z", endedAt: "2026-08-12T12:01:00.000Z",
  status: "completed", source: "omi", codec: "pcm16", sampleRate: 16_000, channels: 1,
});

const graph = (): GraphSnapshot => ({
  owner_account_id: owner, graph_generation: 7, claims: [], entities: [], predicates: [],
  identity_authorizations: [], adjacency: [],
});

const snapshot = () => materializeListenFormationSnapshot({
  finalization: sealListenFormationFinalization({
    owner_account_id: owner, session: session(), segments: segments(),
  }),
  graph_snapshot: graph(), source_language: "en", account_timezone: "America/New_York",
  reference_clock_query_at: "2026-08-12T12:01:01.000Z", policy_version: "policy:listen:v1",
  predicate_alias_generation: "predicate:7", authorization_generation: "authorization:7",
  stm_generation: "stm:7",
});

const sourceRow = () => {
  const value = snapshot();
  return Object.freeze({
    formation_work_id: value.work_id,
    source_snapshot_digest: formationWorkInputSnapshotDigest(value),
    snapshot: value,
  });
};

const inMemoryRepository = () => {
  let storedSet: Readonly<ListenAttributionBeliefInputSet> | null = null;
  const records = new Map<string, Readonly<StoredListenAttributionBeliefInput>>();
  return {
    get storedSet() { return storedSet; },
    repository: defineListenAttributionBeliefInputRepository({
      stage: async (_authorized, request) => {
        if (storedSet !== null) return storedSet.set_digest === request.set.set_digest
          ? { kind: "replayed", set: storedSet }
          : { kind: "idempotency_conflict" };
        storedSet = request.set;
        request.set.inputs.forEach((_entry, ordinal) => {
          const record = materializeStoredListenAttributionBeliefInput(
            request.set, ordinal, request.request_digest,
          );
          records.set(record.input_ref, record);
        });
        return { kind: "staged", set: request.set };
      },
      load: async (_authorized, inputRef) => {
        const record = records.get(inputRef);
        return record ? { kind: "found", record } : { kind: "not_found" };
      },
    }),
  };
};

const strategy = (id: string, prompt: string) => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION, strategy_id: id, work_kind: "identity_cluster",
  coordinates: {
    strategy_version: "belief-source:v1", model_version: "calibrator:test:v1",
    prompt_version: prompt, policy_version: "belief:policy:v1", code_version: "belief:code:v1",
    schema_version: "belief:schema:v1", tokenizer_version: "none", tool_version: "none",
    result_contract_version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
});

const assignment = () => {
  const strategies = [
    strategy("strategy:belief-source:baseline", "belief:prompt:v1"),
    strategy("strategy:belief-source:candidate", "belief:prompt:v2"),
  ];
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:belief-source:paired", work_kind: "identity_cluster",
    unit_kind: "session", key_version: "assignment-key:v1",
    authority_strategy_id: strategies[0]!.strategy_id,
    shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
  }, strategies);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(5)).assign({
    owner_account_id: owner, unit_ref: "session:belief-source", policy, strategies,
  });
};

const resultRepository = () => {
  const results = new Map<string, Readonly<MemoryEvaluationResult>>();
  const pairs = new Map<string, Readonly<MemoryEvaluationPair>>();
  return defineMemoryShadowResultRepository({
    load: async (authorized, coordinate) => {
      const result = results.get(memoryEvaluationResultId(authorized, coordinate));
      return result ? { kind: "found", result } : { kind: "missing" };
    },
    stage: async (authorized, request) => {
      const result = materializeMemoryEvaluationResult(authorized, request);
      const prior = results.get(result.evaluation_result_id);
      if (prior) return prior.stage_request_digest === result.stage_request_digest
        ? { kind: "replayed", result: prior } : { kind: "idempotency_conflict" };
      results.set(result.evaluation_result_id, result);
      return { kind: "staged", result };
    },
    recordPair: async (_authorized, pair) => {
      const prior = pairs.get(pair.pair_id);
      if (prior) return { kind: "replayed", pair: prior };
      pairs.set(pair.pair_id, pair);
      return { kind: "recorded", pair };
    },
  });
};

describe("persisted Listen attribution belief input source", () => {
  test("materializes one complete text-free set bound to the accepted snapshot", () => {
    const set = materializeListenAttributionBeliefInputSet(context(), sourceRow());
    expect(set.inputs).toHaveLength(2);
    expect(parseListenAttributionBeliefInputSet(set)).toEqual(set);
    expect(set.inputs.map((entry) => entry.input_ref)).toEqual(
      [...set.inputs.map((entry) => entry.input_ref)].sort(),
    );
    const encoded = JSON.stringify(set);
    expect(encoded).not.toContain("Atlas launch");
    expect(encoded).not.toContain("second speaker");
    expect(encoded).not.toContain("person:owner");
  });

  test("stages the accepted set and serves it through the authorized evidence source", async () => {
    const storage = inMemoryRepository();
    const source = defineAcceptedFormationBeliefSource(async () => ({ kind: "found", ...sourceRow() }));
    const stager = defineListenAttributionBeliefInputStager({
      source, repository: storage.repository,
    });
    const staged = await stager.stageAcceptedFormation(context(), snapshot().work_id);
    expect(staged.kind).toBe("staged");
    if (staged.kind !== "staged") throw new Error("expected staged set");
    await expect(stager.stageAcceptedFormation(context(), snapshot().work_id))
      .resolves.toMatchObject({ kind: "replayed" });
    const selected = staged.set.inputs[0]!;
    const evidence = defineListenAttributionBeliefEvaluationSource(storage.repository);
    const copied = await evidence.load(context(), {
      source_kind: "formation_input_snapshot", source_ref: selected.input_ref,
      input_frontier: selected.input.graph_frontier,
    });
    expect(copied.kind).toBe("found");
    if (copied.kind !== "found") throw new Error("expected copied input");
    expect(copied.copied_input.payload).toEqual(selected.input);
  });

  test("drives paired replay and exact rerun uses zero calibrator calls", async () => {
    const storage = inMemoryRepository();
    const set = materializeListenAttributionBeliefInputSet(context(), sourceRow());
    await storage.repository.stage(context(), {
      set, request_digest: listenAttributionBeliefInputStageRequestDigest(set),
    });
    const evidence = defineListenAttributionBeliefEvaluationSource(storage.repository);
    const selected = set.inputs[0]!;
    const copied = await evidence.load(context(), {
      source_kind: "formation_input_snapshot", source_ref: selected.input_ref,
      input_frontier: selected.input.graph_frontier,
    });
    if (copied.kind !== "found") throw new Error("expected copied input");
    let calls = 0;
    const producer = defineAttributionBeliefShadowProducer({
      resolve_calibrator: async () => ({ calibrate: async (request) => {
        calls += 1;
        return { probabilities: request.hypotheses.map((hypothesis) => ({
          hypothesis_id: hypothesis.hypothesis_id,
          probability_micros: hypothesis.kind === "owner" ? 600_000
            : hypothesis.kind === "unknown" ? 250_000 : 150_000,
        })) };
      } }),
    });
    const coordinator = defineMemoryOfflineReplayCoordinator({
      result_repository: resultRepository(), produce: producer,
    });
    const request = {
      assignment_bundle: assignment(), evaluation_run_id: `mer1_${digest("8")}`,
      copied_input: copied.copied_input, repeats: 2,
    };
    await expect(coordinator.run(context(), request)).resolves.toMatchObject({
      kind: "completed", model_calls: 4, reused_results: 0,
    });
    expect(calls).toBe(4);
    calls = 0;
    await expect(coordinator.run(context(), request)).resolves.toMatchObject({
      kind: "completed", model_calls: 0, reused_results: 4,
    });
    expect(calls).toBe(0);
  });

  test("rejects source, set, frontier, capability, and hostile drift", async () => {
    const source = sourceRow();
    expect(() => materializeListenAttributionBeliefInputSet(context(), {
      ...source, source_snapshot_digest: digest("f"),
    })).toThrow("source_mismatch");
    const set = materializeListenAttributionBeliefInputSet(context(), source);
    expect(() => parseListenAttributionBeliefInputSet({ ...set, set_digest: digest("e") }))
      .toThrow("invalid_set");
    const storage = inMemoryRepository();
    await storage.repository.stage(context(), {
      set, request_digest: listenAttributionBeliefInputStageRequestDigest(set),
    });
    const evidence = defineListenAttributionBeliefEvaluationSource(storage.repository);
    await expect(evidence.load(context(), {
      source_kind: "formation_input_snapshot", source_ref: set.inputs[0]!.input_ref,
      input_frontier: digest("9"),
    })).resolves.toEqual({ kind: "not_found" });
    const hostile = new Proxy(set, { ownKeys: () => { throw new Error("raw transcript"); } });
    expect(() => parseListenAttributionBeliefInputSet(hostile)).toThrow("invalid_set");
    expect(() => materializeListenAttributionBeliefInputSet({
      ...context(), capability: "memories.work.accept",
    } as never, source)).toThrow();
  });
});
