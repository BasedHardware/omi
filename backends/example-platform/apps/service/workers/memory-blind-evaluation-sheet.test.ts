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
import { defineMemoryEvaluationEvidenceSource } from "../stores/memory-evaluation-evidence-source";
import {
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  pairMemoryEvaluationResults,
  type MemoryEvaluationResult,
  type MemoryEvaluationStageRequest,
} from "../stores/memory-shadow-result-repository";
import {
  buildMemoryBlindEvaluationArtifacts,
  expandMemoryBlindEvaluationGrades,
  parseMemoryBlindEvaluationKey,
  parseMemoryBlindEvaluationSheet,
} from "./memory-blind-evaluation-sheet";
import { buildMemoryEvaluationExport } from "./memory-evaluation-export";
import {
  analyzeExternalMemoryEvaluationLabels,
  buildMemoryEvaluationCohort,
} from "./memory-evaluation-statistics";
import { buildMemoryReadEvaluationResult } from "./memory-read-evaluation-result";

const hex = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow", owner = "account:alice") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:blind-sheet", account_id: owner,
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: hex("a"),
}, 150);

const strategies = (["authority", "candidate"] as const).map((role) => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: `strategy:retrieval:${role}:sentinel`,
  work_kind: "retrieval",
  coordinates: {
    strategy_version: `retrieval:${role}:v1`, model_version: "deepseek:v1",
    prompt_version: `prompt:${role}:v1`, policy_version: "policy:v1", code_version: "code:v1",
    schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
    result_contract_version: "memory-read-evaluation-result-v1",
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
}));
const policy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:retrieval:v1", work_kind: "retrieval", unit_kind: "session",
  key_version: "key:v1", authority_strategy_id: strategies[0]!.strategy_id,
  shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
}, strategies);
const assigner = createMemoryStrategyAssigner(new Uint8Array(32).fill(4));

const traceRef = (value: string): `tr1_${string}` => `tr1_${sha256CanonicalContent({ value })}`;
const groundedTrace = (strategyVersion: string, value: string) => {
  const citation = traceRef(`citation:${value}`);
  return {
    citation,
    trace: buildContentSafeRecallTrace({
      version: "recall-trace-v1", traceRef: traceRef(`trace:${value}`), strategyVersion,
      projectionFreshness: "fresh", outcome: "grounded", latencyMs: 5,
      tokenCounts: { input: 20, output: 5 },
      stages: {
        eligible: [citation], selected: [citation], hydrated: [citation],
        policyEligible: [citation], cited: [citation], grounded: [citation],
      },
    }),
  };
};
const emptyTrace = (strategyVersion: string, value: string) => buildContentSafeRecallTrace({
  version: "recall-trace-v1", traceRef: traceRef(`empty:${value}`), strategyVersion,
  projectionFreshness: "fresh", outcome: "no_eligible_candidates", latencyMs: 2,
  tokenCounts: { input: 10, output: 0 },
  stages: { eligible: [], selected: [], hydrated: [], policyEligible: [], cited: [], grounded: [] },
});

interface FixtureOptions {
  readonly queryMismatch?: boolean;
  readonly normalizedRoleMismatch?: boolean;
}

const fixture = async (options: FixtureOptions = {}) => {
  const results: Readonly<MemoryEvaluationResult>[] = [];
  const exports = [];
  const answers = [
    [["Alpha answer.", "Beta answer."], ["Alpha answer.", null]],
    [[null, null], [null, null]],
  ] as const;
  for (let unitIndex = 0; unitIndex < answers.length; unitIndex += 1) {
    const bundle = assigner.assign({
      owner_account_id: "account:alice", unit_ref: `session:unit:${unitIndex}`, policy, strategies,
    });
    const inputFrontier = `frontier:raw:unit:${unitIndex}:must-not-leak`;
    const source = defineMemoryEvaluationEvidenceSource(async (sourceContext, request) => ({
      kind: "found", owner_account_id: sourceContext.account_id, account_epoch: sourceContext.account_epoch,
      source_kind: request.source_kind, source_ref: request.source_ref, input_frontier: request.input_frontier,
      payload: { query: `Question ${unitIndex}?`, projection: [] },
    }));
    const loaded = await source.load(context(), {
      source_kind: "authorized_graph_snapshot",
      source_ref: `source:raw:unit:${unitIndex}:must-not-leak`,
      input_frontier: inputFrontier,
    });
    if (loaded.kind !== "found") throw new Error("fixture input unavailable");
    const pairs = [];
    for (let repeat = 0; repeat < 2; repeat += 1) {
      const staged: MemoryEvaluationResult[] = [];
      for (const [roleIndex, role] of (["baseline", "candidate"] as const).entries()) {
        const selected = role === "baseline" ? bundle.authority : bundle.shadows[0]!;
        const normalizedSelected = options.normalizedRoleMismatch && unitIndex === 0 && repeat === 0 && role === "baseline"
          ? bundle.shadows[0]! : selected;
        const strategy = bundle.strategies.find((item) => item.strategy_id === normalizedSelected.strategy_id)!;
        const answer = answers[unitIndex]![repeat]![roleIndex]!;
        const value = `unit:${unitIndex}:repeat:${repeat}:role:${role}`;
        const grounded = answer === null ? null : groundedTrace(strategy.coordinates.strategy_version, value);
        const normalized = buildMemoryReadEvaluationResult(context(), {
          assignment_bundle: bundle,
          assignment_id: normalizedSelected.assignment_id,
          copied_input: loaded.copied_input,
          evaluation_role: options.normalizedRoleMismatch && unitIndex === 0 && repeat === 0 && role === "baseline"
            ? "candidate" : role,
          repeat_ordinal: repeat,
          query_text: options.queryMismatch && unitIndex === 0 && repeat === 0 && role === "candidate"
            ? "Different question?" : `Question ${unitIndex}?`,
          answer_text: answer,
          absence: answer === null ? "query_gap" : null,
          assertions: answer === null ? [] : [{ ordinal: 0, text: answer, citations: [grounded!.citation] }],
          recall_trace: answer === null ? emptyTrace(strategy.coordinates.strategy_version, value) : grounded!.trace,
        });
        const body = {
          assignment_bundle: bundle,
          assignment_id: selected.assignment_id,
          account_epoch: 7,
          evaluation_role: role,
          evaluation_mode: "offline_replay" as const,
          evaluation_run_id: `mer1_${hex("b")}`,
          input_frontier: inputFrontier,
          input_digest: loaded.copied_input.input_digest,
          repeat_ordinal: repeat,
          result_contract_version: normalized.version,
          response_digest: sha256CanonicalContent({ unitIndex, repeat, role, normalized }),
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
      }
      pairs.push(pairMemoryEvaluationResults(staged[0]!, staged[1]!));
    }
    exports.push(buildMemoryEvaluationExport(context(), pairs));
  }
  return { results, cohort: buildMemoryEvaluationCohort(exports) };
};

describe("blind memory evaluation sheets", () => {
  test("randomizes opaque answer references while remaining byte-stable for one key", async () => {
    const value = await fixture();
    const first = buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(32).fill(7));
    const replay = buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(32).fill(7));
    const other = buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(32).fill(8));
    expect(first).toEqual(replay);
    expect(first.sheet.sheet_ref).not.toBe(other.sheet.sheet_ref);
    expect(first.sheet.rows[0]!.answers.map((answer) => answer.answer_ref))
      .not.toEqual(other.sheet.rows[0]!.answers.map((answer) => answer.answer_ref));
    expect(parseMemoryBlindEvaluationSheet(JSON.parse(JSON.stringify(first.sheet)))).toEqual(first.sheet);
    expect(parseMemoryBlindEvaluationKey(JSON.parse(JSON.stringify(first.hidden_key)))).toEqual(first.hidden_key);
  });

  test("nulls need no human click and duplicate answers are graded once", async () => {
    const value = await fixture();
    const artifacts = buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(32).fill(7));
    expect(artifacts.sheet).toMatchObject({
      input_count: 2,
      result_count: 8,
      rendered_row_count: 1,
      human_answer_count: 2,
      machine_empty_count: 5,
      deduplicated_result_count: 1,
    });
    expect(artifacts.sheet.rows[0]!.query_text).toBe("Question 0?");
    expect(artifacts.sheet.rows[0]!.answers.map((answer) => answer.answer_text).sort())
      .toEqual(["Alpha answer.", "Beta answer."]);
    expect(artifacts.hidden_key.machine_empty_labels).toHaveLength(5);
    expect(artifacts.hidden_key.mappings.map((mapping) => mapping.result_refs.length).sort()).toEqual([1, 2]);
  });

  test("public bytes reveal grading content but no arm identity; hidden bytes reveal no content", async () => {
    const value = await fixture();
    const artifacts = buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(32).fill(7));
    const publicBytes = JSON.stringify(artifacts.sheet);
    expect(publicBytes).toContain("Question 0?");
    expect(publicBytes).toContain("Alpha answer.");
    for (const forbidden of [
      "account:alice", "mer1_", "mea1_", "mei1_", "mep1_", "msr1_", "mes1_",
      "strategy:retrieval", "baseline", "candidate", "source:raw", "frontier:raw", "traceRef", "tr1_",
    ]) expect(publicBytes).not.toContain(forbidden);
    const hiddenBytes = JSON.stringify(artifacts.hidden_key);
    expect(hiddenBytes).toContain("msr1_");
    for (const forbidden of [
      "Question 0?", "Alpha answer.", "strategy:retrieval", "account:alice", "source:raw",
      "frontier:raw", "traceRef", "tr1_", "baseline", "candidate", "repeat_ordinal",
    ]) expect(hiddenBytes).not.toContain(forbidden);
  });

  test("human grades expand over duplicate bytes and machine empties into complete paired labels", async () => {
    const value = await fixture();
    const artifacts = buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(32).fill(7));
    const grades = artifacts.sheet.rows.flatMap((row) => row.answers.map((answer) => ({
      answer_ref: answer.answer_ref,
      grade: answer.answer_text === "Alpha answer." ? "correct" as const : "wrong" as const,
    })));
    const labels = expandMemoryBlindEvaluationGrades(
      artifacts.sheet,
      artifacts.hidden_key,
      `meg1_${hex("c")}`,
      grades,
    );
    expect(labels.grades).toHaveLength(8);
    expect(labels.grades.filter((grade) => grade.grade === "empty")).toHaveLength(5);
    expect(labels.grades.filter((grade) => grade.grade === "correct")).toHaveLength(2);
    expect(labels.grades.filter((grade) => grade.grade === "wrong")).toHaveLength(1);
    expect(analyzeExternalMemoryEvaluationLabels(value.cohort, labels)).toMatchObject({
      input_count: 2,
      repeat_count: 2,
      primary_pairs_included: 2,
    });
  });

  test("authority, complete verified results, query agreement, and key safety fail closed", async () => {
    const value = await fixture();
    const key = new Uint8Array(32).fill(7);
    expect(() => buildMemoryBlindEvaluationArtifacts(context("memories.work.execute"), value.cohort, value.results, key))
      .toThrow("capability_denied");
    expect(() => buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(31)))
      .toThrow("invalid_randomization_key");
    expect(() => buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results.slice(1), key))
      .toThrow("invalid_results");
    expect(() => buildMemoryBlindEvaluationArtifacts(context(), value.cohort, [...value.results.slice(0, -1), value.results[0]!], key))
      .toThrow("duplicate_result");
    expect(() => buildMemoryBlindEvaluationArtifacts(context(), value.cohort, [{ ...value.results[0]! }, ...value.results.slice(1)] as never, key))
      .toThrow("unverified_result");
    const mismatched = await fixture({ queryMismatch: true });
    expect(() => buildMemoryBlindEvaluationArtifacts(context(), mismatched.cohort, mismatched.results, key))
      .toThrow("query_mismatch");
    const relabelled = await fixture({ normalizedRoleMismatch: true });
    expect(() => buildMemoryBlindEvaluationArtifacts(context(), relabelled.cohort, relabelled.results, key))
      .toThrow("normalized_result_mismatch");
  });

  test("sheet, key, and human-grade envelopes reject tampering and hostile shapes", async () => {
    const value = await fixture();
    const artifacts = buildMemoryBlindEvaluationArtifacts(context(), value.cohort, value.results, new Uint8Array(32).fill(7));
    expect(() => parseMemoryBlindEvaluationSheet({ ...artifacts.sheet, extra: true })).toThrow("invalid_sheet");
    expect(() => parseMemoryBlindEvaluationSheet({ ...artifacts.sheet, result_count: 9 })).toThrow();
    expect(() => parseMemoryBlindEvaluationKey({ ...artifacts.hidden_key, hidden_key_digest: hex("d") }))
      .toThrow("invalid_hidden_key_digest");
    expect(() => parseMemoryBlindEvaluationSheet(new Proxy({ ...artifacts.sheet }, {}))).toThrow("invalid_sheet");
    expect(() => parseMemoryBlindEvaluationSheet({
      ...artifacts.sheet,
      rows: new Proxy(artifacts.sheet.rows, {}),
    })).toThrow("invalid_sheet");
    expect(() => expandMemoryBlindEvaluationGrades(
      artifacts.sheet,
      artifacts.hidden_key,
      `meg1_${hex("c")}`,
      [],
    )).toThrow("invalid_human_grades");
    const answerRef = artifacts.sheet.rows[0]!.answers[0]!.answer_ref;
    expect(() => expandMemoryBlindEvaluationGrades(
      artifacts.sheet,
      artifacts.hidden_key,
      `meg1_${hex("c")}`,
      [{ answer_ref: answerRef, grade: "empty" } as never, { answer_ref: answerRef, grade: "correct" }],
    )).toThrow();
  });
});
