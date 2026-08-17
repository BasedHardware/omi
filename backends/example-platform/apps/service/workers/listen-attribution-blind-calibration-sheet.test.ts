import { describe, expect, test } from "bun:test";

import {
  buildAttributionBeliefRevision,
  parseAttributionBeliefRevision,
} from "../../../core/consolidate/attribution-belief";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { sha256CanonicalRedacted } from "../../../core/ledger";
import type { GraphSnapshot } from "../../../core/retrieve";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineMemoryEvaluationEvidenceSource,
} from "../stores/memory-evaluation-evidence-source";
import {
  defineMemoryShadowResultRepository,
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  memoryEvaluationResultId,
  pairMemoryEvaluationResults,
  type MemoryEvaluationPair,
  type MemoryEvaluationResult,
} from "../stores/memory-shadow-result-repository";
import { durableMemoryWorkNormalizedResultDigest } from
  "../stores/durable-memory-work-result-repository";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../stores/listen-store";
import { formationWorkInputSnapshotDigest } from "./formation-work-input-repository";
import {
  listenAttributionBeliefInputStageRequestDigest,
  materializeListenAttributionBeliefInputSet,
  materializeStoredListenAttributionBeliefInput,
} from "../listen/attribution-belief-input-source";
import {
  materializeListenFormationSnapshot,
  sealListenFormationFinalization,
} from "../listen/formation-ingestion";
import {
  ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
  defineAttributionBeliefShadowProducer,
} from "./attribution-belief-shadow-producer";
import { buildMemoryEvaluationExport } from "./memory-evaluation-export";
import { buildMemoryEvaluationCohort } from "./memory-evaluation-statistics";
import { defineMemoryOfflineReplayCoordinator } from "./memory-offline-replay-coordinator";
import {
  analyzeListenAttributionCalibration,
} from "./listen-attribution-calibration-statistics";
import {
  buildListenAttributionBlindArtifacts,
  expandListenAttributionBlindLabels,
  parseListenAttributionBlindKey,
  parseListenAttributionBlindLabels,
  parseListenAttributionBlindSheet,
} from "./listen-attribution-blind-calibration-sheet";

const hex = (character: string): string => character.repeat(64);
const owner = "account:blind-calibration-owner";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:blind-calibration", account_id: owner,
  application_id: "app:blind-calibration", credential_id: "credential:blind-calibration",
  credential_generation: 1, capability, grant_id: "grant:blind-calibration", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 1, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: hex("a"),
}, 150);

const graph = (): GraphSnapshot => ({
  owner_account_id: owner, graph_generation: 7, claims: [], entities: [], predicates: [],
  identity_authorizations: [], adjacency: [],
});

const segments = (suffix: string): readonly ListenTranscriptSegment[] => Object.freeze([
  Object.freeze({
    id: `segment:${suffix}:one`, text: `First transcript ${suffix} sentinel.`,
    is_user: true, start: 1, end: 3,
  }),
  Object.freeze({
    id: `segment:${suffix}:two`, text: `Second transcript ${suffix} sentinel.`,
    is_user: false, start: 4, end: 7,
  }),
]);

const snapshot = (suffix: string) => {
  const session: ListenSessionRecord = Object.freeze({
    id: `listen-session:blind:${suffix}`, conversationId: `conversation:blind:${suffix}`,
    clientConversationId: null, startedAt: "2026-08-13T12:00:00.000Z",
    updatedAt: "2026-08-13T12:01:00.000Z", endedAt: "2026-08-13T12:01:00.000Z",
    status: "completed", source: "omi", codec: "pcm16", sampleRate: 16_000, channels: 1,
  });
  return materializeListenFormationSnapshot({
    finalization: sealListenFormationFinalization({
      owner_account_id: owner, session, segments: segments(suffix),
    }),
    graph_snapshot: graph(), source_language: "en", account_timezone: "America/New_York",
    reference_clock_query_at: "2026-08-13T12:01:01.000Z", policy_version: "policy:listen:v1",
    predicate_alias_generation: "predicate:7", authorization_generation: "authorization:7",
    stm_generation: "stm:7",
  });
};

const strategy = (role: "baseline" | "candidate") => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: `strategy:blind-calibration:${role}:must-not-leak`,
  work_kind: "identity_cluster",
  coordinates: {
    strategy_version: `belief:${role}:v1`, model_version: "calibrator:test:v1",
    prompt_version: `prompt:${role}:must-not-leak`, policy_version: "belief:policy:v1",
    code_version: "belief:code:v1", schema_version: "belief:schema:v1",
    tokenizer_version: "none", tool_version: "none",
    result_contract_version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
});
const strategies = [strategy("baseline"), strategy("candidate")];
const policy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:blind-calibration:paired", work_kind: "identity_cluster",
  unit_kind: "session", key_version: "assignment-key:v1",
  authority_strategy_id: strategies[0]!.strategy_id,
  shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
}, strategies);
const assigner = createMemoryStrategyAssigner(new Uint8Array(32).fill(9));

const fixture = async () => {
  const results = new Map<string, Readonly<MemoryEvaluationResult>>();
  const pairs = new Map<string, Readonly<MemoryEvaluationPair>>();
  const repository = defineMemoryShadowResultRepository({
    load: async (authorized, coordinate) => {
      const found = results.get(memoryEvaluationResultId(authorized, coordinate));
      return found ? { kind: "found", result: found } : { kind: "missing" };
    },
    stage: async (authorized, request) => {
      const result = materializeMemoryEvaluationResult(authorized, request);
      const found = results.get(result.evaluation_result_id);
      if (found) return { kind: "replayed", result: found };
      results.set(result.evaluation_result_id, result);
      return { kind: "staged", result };
    },
    recordPair: async (_authorized, pair) => {
      pairs.set(pair.pair_id, pair);
      return { kind: "recorded", pair };
    },
  });
  const coordinator = defineMemoryOfflineReplayCoordinator({
    result_repository: repository,
    produce: defineAttributionBeliefShadowProducer({
      resolve_calibrator: async (_strategy, role) => ({
        calibrate: async (request) => {
          const ownerProbability = role === "baseline" ? 800_000 : 600_000;
          const remainder = request.hypotheses.filter((item) => item.kind !== "owner");
          const each = Math.floor((1_000_000 - ownerProbability) / remainder.length);
          let allocated = ownerProbability;
          return { probabilities: request.hypotheses.map((hypothesis, index) => {
            const probability = hypothesis.kind === "owner" ? ownerProbability
              : index === request.hypotheses.length - 1 ? 1_000_000 - allocated : each;
            allocated += hypothesis.kind === "owner" ? 0 : probability;
            return { hypothesis_id: hypothesis.hypothesis_id, probability_micros: probability };
          }) };
        },
      }),
    }),
  });
  const exports = [];
  const contexts = [];
  const bundles = [];
  for (const suffix of ["alpha", "bravo"] as const) {
    const sourceSnapshot = snapshot(suffix);
    const set = materializeListenAttributionBeliefInputSet(context(), {
      formation_work_id: sourceSnapshot.work_id,
      source_snapshot_digest: formationWorkInputSnapshotDigest(sourceSnapshot),
      snapshot: sourceSnapshot,
    });
    const selectedOrdinal = suffix === "alpha" ? 0 : 1;
    const selected = set.inputs[selectedOrdinal]!;
    const stored = materializeStoredListenAttributionBeliefInput(
      set, selectedOrdinal, listenAttributionBeliefInputStageRequestDigest(set),
    );
    const source = defineMemoryEvaluationEvidenceSource(async (authorized, request) => ({
      kind: "found", owner_account_id: authorized.account_id, account_epoch: authorized.account_epoch,
      source_kind: request.source_kind, source_ref: request.source_ref,
      input_frontier: request.input_frontier, payload: selected.input,
    }));
    const copied = await source.load(context(), {
      source_kind: "formation_input_snapshot", source_ref: selected.input_ref,
      input_frontier: selected.input.graph_frontier,
    });
    if (copied.kind !== "found") throw new Error("missing copied fixture input");
    const bundle = assigner.assign({
      owner_account_id: owner, unit_ref: `session:blind:${suffix}`, policy, strategies,
    });
    bundles.push(bundle);
    const before = new Set(pairs.keys());
    const outcome = await coordinator.run(context(), {
      assignment_bundle: bundle, evaluation_run_id: `mer1_${hex("8")}`,
      copied_input: copied.copied_input, repeats: 2,
    });
    if (outcome.kind !== "completed") throw new Error("failed paired fixture run");
    const unitPairs = [...pairs.values()].filter((pair) => !before.has(pair.pair_id));
    exports.push(buildMemoryEvaluationExport(context(), unitPairs));
    contexts.push(Object.freeze({
      input_ref: selected.input_ref, stored_input: stored, snapshot: sourceSnapshot,
    }));
  }
  return {
    cohort: buildMemoryEvaluationCohort(exports), results: [...results.values()], contexts, bundles, exports,
  };
};

describe("Listen attribution blind calibration sheet", () => {
  test("renders stable randomized context rows and keeps the hidden join text-free", async () => {
    const value = await fixture();
    const first = buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results, value.contexts, new Uint8Array(32).fill(4),
    );
    const replay = buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results, value.contexts, new Uint8Array(32).fill(4),
    );
    const other = buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results, value.contexts, new Uint8Array(32).fill(5),
    );
    expect(first).toEqual(replay);
    expect(first.sheet.sheet_ref).not.toBe(other.sheet.sheet_ref);
    expect(first.sheet.rows.map((row) => row.row_ref)).not.toEqual(other.sheet.rows.map((row) => row.row_ref));
    expect(first.sheet.rows).toHaveLength(2);
    for (const row of first.sheet.rows) {
      expect(row.segments).toHaveLength(2);
      expect(row.segments.filter((segment) => segment.target)).toHaveLength(1);
    }
    expect(parseListenAttributionBlindSheet(JSON.parse(JSON.stringify(first.sheet)))).toEqual(first.sheet);
    expect(parseListenAttributionBlindKey(JSON.parse(JSON.stringify(first.hidden_key)))).toEqual(first.hidden_key);

    const publicBytes = JSON.stringify(first.sheet);
    expect(publicBytes).toContain("First transcript");
    expect(publicBytes).toContain("Second transcript");
    for (const forbidden of [
      owner, "observed_is_user", "strategy:blind-calibration", "baseline", "candidate",
      "msr1_", "labinput1_", "obsref1_", "probability_micros", "graph_frontier",
    ]) expect(publicBytes).not.toContain(forbidden);
    const hiddenBytes = JSON.stringify(first.hidden_key);
    expect(hiddenBytes).toContain("msr1_");
    expect(hiddenBytes).toContain("obsref1_");
    for (const forbidden of [
      "First transcript", "Second transcript", "probability_micros", "strategy:blind-calibration",
      "baseline", "candidate", "repeat_ordinal", "observed_is_user",
    ]) expect(hiddenBytes).not.toContain(forbidden);
  });

  test("imports one external owner, non-owner, or unclear label per observation", async () => {
    const value = await fixture();
    const artifacts = buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results, value.contexts, new Uint8Array(32).fill(4),
    );
    const grades = artifacts.sheet.rows.map((row, index) => ({
      row_ref: row.row_ref,
      label: index === 0 ? "owner" as const : "unclear" as const,
    }));
    const labels = expandListenAttributionBlindLabels(
      artifacts.sheet, artifacts.hidden_key, `meg1_${hex("c")}`, grades,
    );
    expect(labels.labels).toHaveLength(2);
    expect(labels.labels.map((label) => label.label).sort()).toEqual(["owner", "unclear"]);
    expect(labels.labels.every((label) => label.result_refs.length === 4)).toBe(true);
    expect(parseListenAttributionBlindLabels(JSON.parse(JSON.stringify(labels)))).toEqual(labels);
    expect(() => expandListenAttributionBlindLabels(
      artifacts.sheet, artifacts.hidden_key, `meg1_${hex("c")}`, grades.slice(1),
    )).toThrow("invalid_human_grades");
    expect(() => expandListenAttributionBlindLabels(
      artifacts.sheet, artifacts.hidden_key, `meg1_${hex("c")}`,
      [{ row_ref: grades[0]!.row_ref, label: "owner" }, { row_ref: grades[0]!.row_ref, label: "non_owner" }],
    )).toThrow();
  });

  test("computes exact paired Brier and reliability statistics without choosing a threshold", async () => {
    const value = await fixture();
    const artifacts = buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results, value.contexts, new Uint8Array(32).fill(4),
    );
    const labels = expandListenAttributionBlindLabels(
      artifacts.sheet, artifacts.hidden_key, `meg1_${hex("c")}`,
      artifacts.sheet.rows.map((row, index) => ({
        row_ref: row.row_ref, label: index === 0 ? "owner" as const : "non_owner" as const,
      })),
    );
    const report = analyzeListenAttributionCalibration(
      context(), value.cohort, artifacts.sheet, artifacts.hidden_key, labels, value.results,
    );
    const reordered = analyzeListenAttributionCalibration(
      context(), value.cohort, artifacts.sheet, artifacts.hidden_key, labels, [...value.results].reverse(),
    );
    expect(report).toEqual(reordered);
    expect(report.observation_count).toBe(2);
    expect(report.by_repeat).toHaveLength(2);
    for (const repeat of report.by_repeat) {
      expect(repeat.statistics).toMatchObject({
        labelled_observation_count: 2, owner_count: 1, non_owner_count: 1, unclear_count: 0,
        candidate_minus_baseline_brier_numerator: "-160000000000",
        paired_brier_denominator: "2000000000000",
      });
      expect(repeat.statistics.baseline).toMatchObject({
        included_count: 2, brier_numerator: "680000000000", brier_denominator: "2000000000000",
      });
      expect(repeat.statistics.candidate).toMatchObject({
        included_count: 2, brier_numerator: "520000000000", brier_denominator: "2000000000000",
      });
      expect(repeat.statistics.baseline.reliability_bins[8]).toMatchObject({
        count: 2, predicted_owner_micros_sum: "1600000", owner_truth_count: 1,
      });
      expect(repeat.statistics.candidate.reliability_bins[6]).toMatchObject({
        count: 2, predicted_owner_micros_sum: "1200000", owner_truth_count: 1,
      });
    }
    expect(report.aggregate).toMatchObject({
      labelled_observation_count: 4, owner_count: 2, non_owner_count: 2, unclear_count: 0,
      candidate_minus_baseline_brier_numerator: "-320000000000",
      paired_brier_denominator: "4000000000000",
    });
    const serialized = JSON.stringify(report);
    for (const forbidden of [
      "First transcript", "Second transcript", owner, "msr1_", "strategy:",
      "threshold", "winner", "direct_expression", "qualified_expression",
    ]) expect(serialized).not.toContain(forbidden);
  });

  test("reports unclear coverage without scoring it and rejects artifact drift", async () => {
    const value = await fixture();
    const artifacts = buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results, value.contexts, new Uint8Array(32).fill(4),
    );
    const labels = expandListenAttributionBlindLabels(
      artifacts.sheet, artifacts.hidden_key, `meg1_${hex("c")}`,
      artifacts.sheet.rows.map((row, index) => ({
        row_ref: row.row_ref, label: index === 0 ? "owner" as const : "unclear" as const,
      })),
    );
    const report = analyzeListenAttributionCalibration(
      context(), value.cohort, artifacts.sheet, artifacts.hidden_key, labels, value.results,
    );
    expect(report.aggregate).toMatchObject({
      labelled_observation_count: 4, owner_count: 2, non_owner_count: 0, unclear_count: 2,
    });
    expect(report.aggregate.baseline.included_count).toBe(2);
    expect(report.aggregate.candidate.included_count).toBe(2);
    expect(() => analyzeListenAttributionCalibration(
      context(), value.cohort, artifacts.sheet, artifacts.hidden_key,
      { ...labels, hidden_key_digest: hex("f") }, value.results,
    )).toThrow();
    expect(() => analyzeListenAttributionCalibration(
      context(), value.cohort, artifacts.sheet, artifacts.hidden_key, labels, value.results.slice(1),
    )).toThrow("invalid_results");
    expect(() => parseListenAttributionBlindLabels(new Proxy(labels, {}))).toThrow("invalid_labels");
  });

  test("fails closed on authority, result, context, digest, and hostile drift", async () => {
    const value = await fixture();
    const key = new Uint8Array(32).fill(4);
    expect(() => buildListenAttributionBlindArtifacts(
      context("memories.work.accept"), value.cohort, value.results, value.contexts, key,
    )).toThrow("capability_denied");
    expect(() => buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results.slice(1), value.contexts, key,
    )).toThrow("invalid_results");
    expect(() => buildListenAttributionBlindArtifacts(
      context(), value.cohort, [...value.results.slice(0, -1), value.results[0]!], value.contexts, key,
    )).toThrow("duplicate_result");
    const original = value.results[0]!;
    const originalBelief = parseAttributionBeliefRevision(original.normalized_result["belief"]);
    const expandedBelief = buildAttributionBeliefRevision({
      owner_account_id: originalBelief.owner_account_id,
      belief_kind: originalBelief.belief_kind,
      about_ref: originalBelief.about_ref,
      observation_ref: originalBelief.observation_ref,
      observation_content_digest: originalBelief.observation_content_digest,
      graph_frontier: originalBelief.graph_frontier,
      hypotheses: [
        ...originalBelief.hypotheses.map((item) => ({
          kind: item.kind, target_ref: item.target_ref,
          probability_micros: item.probability_micros,
        })),
        { kind: "entity" as const, target_ref: `attrtarget1_${hex("d")}`, probability_micros: 0 },
      ],
      evidence_factors: originalBelief.evidence_factors,
      attribution_contract_digest: originalBelief.attribution_contract_digest,
      aggregation_contract_digest: originalBelief.aggregation_contract_digest,
      calibration_contract_digest: originalBelief.calibration_contract_digest,
      created_at_event_time: originalBelief.created_at_event_time,
      previous_revision: null,
    });
    const responseDigest = sha256CanonicalRedacted({
      probabilities: expandedBelief.hypotheses.map((item) => ({
        hypothesis_id: item.hypothesis_id, probability_micros: item.probability_micros,
      })),
    });
    const originalReceipt = original.normalized_result["calibration_receipt"] as Record<string, unknown>;
    const normalizedResult = {
      version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
      belief: expandedBelief,
      calibration_receipt: {
        ...originalReceipt,
        response_digest: responseDigest,
        result_digest: sha256CanonicalRedacted(expandedBelief),
        belief_revision_id: expandedBelief.belief_revision_id,
      },
    };
    const bundle = value.bundles.find((item) => item.assignment_bundle_id === original.assignment_bundle_id)!;
    const body = {
      assignment_bundle: bundle, assignment_id: original.assignment_id,
      account_epoch: original.account_epoch, evaluation_role: original.evaluation_role,
      evaluation_mode: original.evaluation_mode, evaluation_run_id: original.evaluation_run_id,
      input_frontier: original.input_frontier, input_digest: original.input_digest,
      repeat_ordinal: original.repeat_ordinal, result_contract_version: original.result_contract_version,
      response_digest: responseDigest,
      normalized_result_digest: durableMemoryWorkNormalizedResultDigest(
        original.result_contract_version, normalizedResult,
      ),
      normalized_result: normalizedResult,
    };
    const expandedResult = materializeMemoryEvaluationResult(context(), {
      ...body, request_digest: memoryEvaluationStageRequestDigest(context(), body),
    });
    const expandedResults = value.results.map((item) => item === original ? expandedResult : item);
    const counterpart = value.results.find((item) => item.assignment_bundle_id === original.assignment_bundle_id
      && item.repeat_ordinal === original.repeat_ordinal && item.evaluation_role !== original.evaluation_role)!;
    const expandedPair = original.evaluation_role === "baseline"
      ? pairMemoryEvaluationResults(expandedResult, counterpart)
      : pairMemoryEvaluationResults(counterpart, expandedResult);
    const expandedExports = value.exports.map((manifest) => {
      const affected = manifest.pairs.some((pair) => pair.baseline_result_ref === original.evaluation_result_id
        || pair.candidate_result_ref === original.evaluation_result_id);
      if (!affected) return manifest;
      const unaffectedPairs = [...value.results]
        .filter((item) => item.assignment_bundle_id === original.assignment_bundle_id
          && item.repeat_ordinal !== original.repeat_ordinal)
        .sort((left, right) => left.evaluation_role === "baseline" ? -1 : right.evaluation_role === "baseline" ? 1 : 0);
      return buildMemoryEvaluationExport(context(), [
        expandedPair, pairMemoryEvaluationResults(unaffectedPairs[0]!, unaffectedPairs[1]!),
      ]);
    });
    expect(() => buildListenAttributionBlindArtifacts(
      context(), buildMemoryEvaluationCohort(expandedExports), expandedResults, value.contexts, key,
    )).toThrow("result_input_mismatch");
    expect(() => buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results,
      [{ ...value.contexts[0]!, snapshot: snapshot("changed") }, value.contexts[1]!], key,
    )).toThrow();
    expect(() => buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results,
      [new Proxy(value.contexts[0]!, {}), value.contexts[1]!], key,
    )).toThrow("invalid_context");
    const artifacts = buildListenAttributionBlindArtifacts(
      context(), value.cohort, value.results, value.contexts, key,
    );
    expect(() => parseListenAttributionBlindSheet({
      ...artifacts.sheet, blind_sheet_digest: hex("f"),
    })).toThrow("invalid_sheet_digest");
    expect(() => parseListenAttributionBlindKey({
      ...artifacts.hidden_key, hidden_key_digest: hex("e"),
    })).toThrow("invalid_hidden_key_digest");
  });
});
