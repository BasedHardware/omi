import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { buildContentSafeRecallTrace } from "../../../core/retrieve/recall-integrity";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkNormalizedResultDigest } from "../stores/durable-memory-work-result-repository";
import { defineMemoryEvaluationEvidenceSource, type CopiedMemoryEvaluationInput } from "../stores/memory-evaluation-evidence-source";
import {
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  pairMemoryEvaluationResults,
  type MemoryEvaluationResult,
  type MemoryEvaluationStageRequest,
} from "../stores/memory-shadow-result-repository";
import {
  analyzeMemoryContaminationFindings,
  auditMemoryReadContamination,
  defineMemoryReadProvenanceSource,
  type MemoryContaminationFinding,
} from "./memory-contamination-audit";
import { buildMemoryEvaluationExport } from "./memory-evaluation-export";
import { buildMemoryEvaluationCohort } from "./memory-evaluation-statistics";
import { buildMemoryReadEvaluationResult } from "./memory-read-evaluation-result";

const hex = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow", owner = "account:alice") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:contamination", account_id: owner,
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: hex("a"),
}, 150);

const strategies = (["authority", "candidate"] as const).map((role) => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: `strategy:contamination:${role}:must-not-leak`,
  work_kind: "retrieval",
  coordinates: {
    strategy_version: `contamination:${role}:v1`, model_version: "deepseek:v1",
    prompt_version: `prompt:${role}:v1`, policy_version: "policy:v1", code_version: "code:v1",
    schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
    result_contract_version: "memory-read-evaluation-result-v1",
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
}));
const policy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:contamination:v1", work_kind: "retrieval", unit_kind: "session",
  key_version: "key:v1", authority_strategy_id: strategies[0]!.strategy_id,
  shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
}, strategies);
const assigner = createMemoryStrategyAssigner(new Uint8Array(32).fill(5));
const traceRef = (value: string): `tr1_${string}` => `tr1_${sha256CanonicalContent({ value })}`;

interface AssertionSpec {
  readonly text: string;
  readonly classes: readonly string[];
}
type AnswerSpec = readonly AssertionSpec[] | null;
type UnitSpec = readonly (readonly [AnswerSpec, AnswerSpec])[];

interface Fixture {
  readonly results: readonly Readonly<MemoryEvaluationResult>[];
  readonly classesByResult: ReadonlyMap<string, ReadonlyMap<string, readonly string[]>>;
  readonly cohort: ReturnType<typeof buildMemoryEvaluationCohort>;
}

const copiedInput = async (unit: number, frontier: string): Promise<Readonly<CopiedMemoryEvaluationInput>> => {
  const source = defineMemoryEvaluationEvidenceSource(async (sourceContext, request) => ({
    kind: "found", owner_account_id: sourceContext.account_id, account_epoch: sourceContext.account_epoch,
    source_kind: request.source_kind, source_ref: request.source_ref, input_frontier: request.input_frontier,
    payload: { query: `Who am I ${unit}?`, graph: [] },
  }));
  const loaded = await source.load(context(), {
    source_kind: "authorized_graph_snapshot",
    source_ref: `source:raw:${unit}:must-not-leak`,
    input_frontier: frontier,
  });
  if (loaded.kind !== "found") throw new Error("fixture copied input unavailable");
  return loaded.copied_input;
};

const buildFixture = async (units: readonly UnitSpec[]): Promise<Fixture> => {
  const results: MemoryEvaluationResult[] = [];
  const classesByResult = new Map<string, ReadonlyMap<string, readonly string[]>>();
  const exports = [];
  for (let unit = 0; unit < units.length; unit += 1) {
    const bundle = assigner.assign({
      owner_account_id: "account:alice", unit_ref: `session:contamination:${unit}`, policy, strategies,
    });
    const frontier = `frontier:raw:${unit}:must-not-leak`;
    const copied = await copiedInput(unit, frontier);
    const pairs = [];
    for (let repeat = 0; repeat < units[unit]!.length; repeat += 1) {
      const staged: MemoryEvaluationResult[] = [];
      for (const [roleIndex, role] of (["baseline", "candidate"] as const).entries()) {
        const selected = role === "baseline" ? bundle.authority : bundle.shadows[0]!;
        const strategy = bundle.strategies.find((value) => value.strategy_id === selected.strategy_id)!;
        const specs = units[unit]![repeat]![roleIndex];
        const rows = specs ?? [];
        const refs = rows.map((_, ordinal) => traceRef(`unit:${unit}:repeat:${repeat}:role:${role}:assertion:${ordinal}`));
        const trace = rows.length === 0
          ? buildContentSafeRecallTrace({
            version: "recall-trace-v1", traceRef: traceRef(`empty:${unit}:${repeat}:${role}`),
            strategyVersion: strategy.coordinates.strategy_version, projectionFreshness: "fresh",
            outcome: "no_eligible_candidates", latencyMs: 0, tokenCounts: { input: 0, output: 0 },
            stages: { eligible: [], selected: [], hydrated: [], policyEligible: [], cited: [], grounded: [] },
          })
          : buildContentSafeRecallTrace({
            version: "recall-trace-v1", traceRef: traceRef(`trace:${unit}:${repeat}:${role}`),
            strategyVersion: strategy.coordinates.strategy_version, projectionFreshness: "fresh",
            outcome: "grounded", latencyMs: 0, tokenCounts: { input: 0, output: 0 },
            stages: { eligible: refs, selected: refs, hydrated: refs, policyEligible: refs, cited: refs, grounded: refs },
          });
        const normalized = buildMemoryReadEvaluationResult(context(), {
          assignment_bundle: bundle,
          assignment_id: selected.assignment_id,
          copied_input: copied,
          evaluation_role: role,
          repeat_ordinal: repeat,
          query_text: `Who am I ${unit}?`,
          answer_text: specs === null ? null : rows.map((row) => row.text).join(" "),
          absence: specs === null ? "query_gap" : null,
          assertions: rows.map((row, ordinal) => ({ ordinal, text: row.text, citations: [refs[ordinal]!] })),
          recall_trace: trace,
        });
        const body = {
          assignment_bundle: bundle,
          assignment_id: selected.assignment_id,
          account_epoch: 7,
          evaluation_role: role,
          evaluation_mode: "offline_replay" as const,
          evaluation_run_id: `mer1_${hex("b")}`,
          input_frontier: frontier,
          input_digest: copied.input_digest,
          repeat_ordinal: repeat,
          result_contract_version: normalized.version,
          response_digest: sha256CanonicalContent({ unit, repeat, role, normalized }),
          normalized_result_digest: durableMemoryWorkNormalizedResultDigest(normalized.version, normalized as never),
          normalized_result: normalized,
        };
        const request: MemoryEvaluationStageRequest = {
          ...body,
          request_digest: memoryEvaluationStageRequestDigest(context(), body),
        };
        const result = materializeMemoryEvaluationResult(context(), request);
        results.push(result);
        staged.push(result);
        classesByResult.set(result.evaluation_result_id, new Map(refs.map((ref, index) => [ref, rows[index]!.classes])));
      }
      pairs.push(pairMemoryEvaluationResults(staged[0]!, staged[1]!));
    }
    exports.push(buildMemoryEvaluationExport(context(), pairs));
  }
  return { results, classesByResult, cohort: buildMemoryEvaluationCohort(exports) };
};

const loadFindings = async (fixture: Fixture): Promise<readonly Readonly<MemoryContaminationFinding>[]> => {
  const source = defineMemoryReadProvenanceSource(async (_context, result, read) => ({
    kind: "found",
    evaluation_result_ref: result.evaluation_result_id,
    normalized_result_digest: result.normalized_result_digest,
    rows: [...read.recall_trace.stages.grounded].sort().map((ref) => ({
      trace_ref: ref,
      contributing_subject_classes: fixture.classesByResult.get(result.evaluation_result_id)!.get(ref),
    })),
  }));
  const output = [];
  for (const result of fixture.results) {
    const loaded = await source.load(context(), result);
    if (loaded.kind !== "found") throw new Error("fixture provenance unavailable");
    output.push(auditMemoryReadContamination(result, loaded.manifest));
  }
  return output;
};

const defaultUnits = (): readonly UnitSpec[] => [
  [
    [
      [{ text: "You work at Omi.", classes: ["bystander"] }, { text: "She founded it.", classes: ["owner"] }],
      [{ text: "You work at Omi.", classes: ["bystander", "owner"] }],
    ],
    [
      [{ text: "She works at Omi.", classes: ["bystander"] }],
      [{ text: "Your role is founder.", classes: ["owner_context"] }, { text: "She spoke.", classes: ["bystander"] }],
    ],
  ],
  [
    [null, null],
    [null, null],
  ],
];

describe("zero-model memory contamination audit", () => {
  test("classifies exact assertion-local second-person over bystander-only support", async () => {
    const fixture = await buildFixture(defaultUnits());
    const findings = await loadFindings(fixture);
    expect(findings[0]).toMatchObject({
      answered: true,
      assertion_count: 2,
      second_person_assertion_count: 1,
      conflicting_grounded_reference_count: 1,
      contaminated_assertion_count: 1,
      contaminated: true,
    });
    expect(findings[1]).toMatchObject({ contaminated: false, conflicting_grounded_reference_count: 0 });
    expect(findings[2]).toMatchObject({ contaminated: false, second_person_assertion_count: 0 });
    expect(findings[3]).toMatchObject({
      contaminated: false,
      second_person_assertion_count: 1,
      conflicting_grounded_reference_count: 1,
    });
    for (const finding of findings.slice(4)) expect(finding).toMatchObject({ answered: false, contaminated: false });
  });

  test("source facade requires total exact grounded provenance and safe subject classes", async () => {
    const fixture = await buildFixture(defaultUnits());
    const result = fixture.results[0]!;
    const source = (rows: unknown) => defineMemoryReadProvenanceSource(async (_context, selected) => ({
      kind: "found", evaluation_result_ref: selected.evaluation_result_id,
      normalized_result_digest: selected.normalized_result_digest, rows,
    }));
    await expect(source([]).load(context(), result)).rejects.toThrow("incomplete_provenance");
    const refs = [...fixture.classesByResult.get(result.evaluation_result_id)!.keys()].sort();
    await expect(source(refs.map((trace_ref) => ({ trace_ref, contributing_subject_classes: [] }))).load(context(), result))
      .rejects.toThrow("invalid_provenance_row");
    await expect(source(refs.map((trace_ref) => ({ trace_ref, contributing_subject_classes: ["owner", "bystander"] }))).load(context(), result))
      .rejects.toThrow("invalid_provenance_row");
    await expect(source([...refs, traceRef("extra")].sort().map((trace_ref) => ({
      trace_ref, contributing_subject_classes: ["bystander"],
    }))).load(context(), result)).rejects.toThrow("incomplete_provenance");
    await expect(source(new Proxy([], {})).load(context(), result)).rejects.toThrow("invalid_provenance_rows");
    await expect(source([]).load(context("memories.work.execute"), result)).rejects.toThrow("capability_denied");
    await expect(source([]).load(context(), { ...result } as never)).rejects.toThrow("unverified_result");
  });

  test("findings and aggregate report are content-safe and repeats do not inflate primary N", async () => {
    const fixture = await buildFixture(defaultUnits());
    const findings = await loadFindings(fixture);
    const findingBytes = JSON.stringify(findings[0]);
    expect(findingBytes).toContain('"contaminated":true');
    for (const forbidden of [
      "Who am I", "You work", "tr1_", "bystander", "owner", "source:raw", "frontier:raw",
      "strategy:contamination", "baseline", "candidate", "repeat_ordinal",
    ]) expect(findingBytes).not.toContain(forbidden);
    const report = analyzeMemoryContaminationFindings(fixture.cohort, findings);
    expect(report).toMatchObject({
      input_count: 2,
      repeat_count: 2,
      result_count: 8,
      both_contaminated: 0,
      baseline_only_contaminated: 1,
      candidate_only_contaminated: 0,
      neither_contaminated: 1,
      net_removed: 1,
      baseline_self_noise: { comparisons: 2, contamination_flips: 1, flip_rate: 0.5 },
      candidate_self_noise: { comparisons: 2, contamination_flips: 0, flip_rate: 0 },
    });
    const reportBytes = JSON.stringify(report);
    for (const forbidden of ["msr1_", "strategy:contamination", "Who am I", "tr1_", "bystander", "owner"] ) {
      expect(reportBytes).not.toContain(forbidden);
    }
  });

  test("14 candidate cleanups versus one regression reproduce exact paired probability", async () => {
    const units: UnitSpec[] = [];
    for (let index = 0; index < 15; index += 1) {
      const baselineContaminated = index < 14;
      const baseline: AnswerSpec = [{
        text: "You have a role.",
        classes: [baselineContaminated ? "bystander" : "owner"],
      }];
      const candidate: AnswerSpec = [{
        text: "You have a role.",
        classes: [baselineContaminated ? "owner" : "bystander"],
      }];
      units.push([[baseline, candidate], [baseline, candidate]]);
    }
    const fixture = await buildFixture(units);
    const report = analyzeMemoryContaminationFindings(fixture.cohort, await loadFindings(fixture));
    expect(report).toMatchObject({
      input_count: 15,
      repeat_count: 2,
      baseline_only_contaminated: 14,
      candidate_only_contaminated: 1,
      net_removed: 13,
      mcnemar_exact_two_sided: {
        numerator: "1",
        denominator_power_of_two: 10,
        approximate: 0.0009765625,
      },
    });
  });

  test("forged, incomplete, duplicated, and hostile findings fail closed", async () => {
    const fixture = await buildFixture(defaultUnits());
    const findings = await loadFindings(fixture);
    expect(() => analyzeMemoryContaminationFindings(fixture.cohort, findings.slice(1))).toThrow("invalid_findings");
    expect(() => analyzeMemoryContaminationFindings(fixture.cohort, [...findings.slice(0, -1), findings[0]!]))
      .toThrow("duplicate_finding");
    expect(() => analyzeMemoryContaminationFindings(fixture.cohort, [{ ...findings[0]! }, ...findings.slice(1)] as never))
      .toThrow("unverified_finding");
    expect(() => analyzeMemoryContaminationFindings(fixture.cohort, new Proxy(findings, {})))
      .toThrow("invalid_findings");
  });
});
