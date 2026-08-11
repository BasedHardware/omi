import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
  type MemoryStrategyAssignmentBundle,
} from "../../../core/consolidate/strategy-assignment";
import {
  buildContentSafeRecallTrace,
  type ContentSafeRecallTrace,
} from "../../../core/retrieve/recall-integrity";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkNormalizedResultDigest } from "../stores/durable-memory-work-result-repository";
import {
  defineMemoryEvaluationEvidenceSource,
  type CopiedMemoryEvaluationInput,
} from "../stores/memory-evaluation-evidence-source";
import {
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  pairMemoryEvaluationResults,
  type MemoryEvaluationRole,
  type MemoryEvaluationStageRequest,
} from "../stores/memory-shadow-result-repository";
import { buildMemoryEvaluationExport } from "./memory-evaluation-export";
import {
  buildMemoryReadEvaluationResult,
  parseMemoryReadEvaluationResult,
  type MemoryReadEvaluationAssertion,
} from "./memory-read-evaluation-result";

const digest = (character: string): string => character.repeat(64);
const traceRef = (value: string): `tr1_${string}` => `tr1_${sha256CanonicalContent({ value })}`;
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow", owner = "account:alice") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:evaluator", account_id: owner,
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const assignment = (kind: "retrieval" | "composition" | "formation" = "retrieval") => {
  const strategy = (role: "authority" | "candidate") => registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: `strategy:${kind}:${role}`,
    work_kind: kind,
    coordinates: {
      strategy_version: `${kind}:${role}:v1`, model_version: "deepseek:v1",
      prompt_version: `prompt:${role}:v1`, policy_version: "policy:v1", code_version: "code:v1",
      schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
      result_contract_version: "memory-read-evaluation-result-v1",
      speaker_strategy_version: "none", boundary_strategy_version: "none",
    },
  });
  const strategies = [strategy("authority"), strategy("candidate")];
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: `policy:${kind}:v1`, work_kind: kind, unit_kind: "session",
    key_version: "key:v1", authority_strategy_id: strategies[0]!.strategy_id,
    shadow_candidates: [{ strategy_id: strategies[1]!.strategy_id, basis_points: 10_000 }],
  }, strategies);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(4)).assign({
    owner_account_id: "account:alice", unit_ref: `session:${kind}:one`, policy, strategies,
  });
};

const copiedInput = async (
  authorized = context(),
): Promise<Readonly<CopiedMemoryEvaluationInput>> => {
  const source = defineMemoryEvaluationEvidenceSource(async (sourceContext, request) => ({
    kind: "found",
    owner_account_id: sourceContext.account_id,
    account_epoch: sourceContext.account_epoch,
    source_kind: request.source_kind,
    source_ref: request.source_ref,
    input_frontier: request.input_frontier,
    payload: { query: "Where do I work?", authorized_projection: [] },
  }));
  const outcome = await source.load(authorized, {
    source_kind: "authorized_graph_snapshot",
    source_ref: "source:raw:must-not-leak",
    input_frontier: "frontier:raw:must-not-leak",
  });
  if (outcome.kind !== "found") throw new Error("test copied input unavailable");
  return outcome.copied_input;
};

const groundedRefs = [traceRef("one"), traceRef("two")];
const groundedTrace = (strategyVersion = "retrieval:authority:v1") => buildContentSafeRecallTrace({
  version: "recall-trace-v1",
  traceRef: traceRef("trace"),
  strategyVersion,
  projectionFreshness: "fresh",
  outcome: "grounded",
  latencyMs: 12,
  tokenCounts: { input: 100, output: 20 },
  stages: {
    eligible: groundedRefs,
    selected: groundedRefs,
    hydrated: groundedRefs,
    policyEligible: groundedRefs,
    cited: groundedRefs,
    grounded: groundedRefs,
  },
});
const emptyTrace = (strategyVersion = "retrieval:authority:v1") => buildContentSafeRecallTrace({
  version: "recall-trace-v1",
  traceRef: traceRef("empty-trace"),
  strategyVersion,
  projectionFreshness: "fresh",
  outcome: "no_eligible_candidates",
  latencyMs: 3,
  tokenCounts: { input: 20, output: 0 },
  stages: { eligible: [], selected: [], hydrated: [], policyEligible: [], cited: [], grounded: [] },
});
const assertionRows = (): readonly MemoryReadEvaluationAssertion[] => [
  { ordinal: 0, text: "You work at Omi.", citations: [groundedRefs[0]!] },
  { ordinal: 1, text: "You are a co-founder.", citations: [groundedRefs[1]!] },
];

const readResult = async (
  overrides: Record<string, unknown> = {},
  bundle: Readonly<MemoryStrategyAssignmentBundle> = assignment(),
) => buildMemoryReadEvaluationResult(context(), {
  assignment_bundle: bundle,
  assignment_id: bundle.authority.assignment_id,
  copied_input: await copiedInput(),
  evaluation_role: "baseline",
  repeat_ordinal: 0,
  query_text: "Where do I work?",
  answer_text: "You work at Omi. You are a co-founder.",
  absence: null,
  assertions: assertionRows(),
  recall_trace: groundedTrace(bundle.strategies[0]!.coordinates.strategy_version),
  ...overrides,
} as never);

describe("sensitive memory read evaluation result", () => {
  test("binds an exact grounded answer to copied input, strategy, assertions, and trace", async () => {
    const result = await readResult();
    expect(result).toMatchObject({
      version: "memory-read-evaluation-result-v1",
      strategy_kind: "retrieval",
      evaluation_role: "baseline",
      repeat_ordinal: 0,
      query_text: "Where do I work?",
      answer_text: "You work at Omi. You are a co-founder.",
      absence: null,
    });
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.assertions)).toBe(true);
    expect(Object.isFrozen(result.assertions[0]!.citations)).toBe(true);
    expect(parseMemoryReadEvaluationResult(JSON.parse(JSON.stringify(result)))).toEqual(result);
    const originalDigest = durableMemoryWorkNormalizedResultDigest(result.version, result as never);
    for (const changed of [
      { ...result, query_text: "Where did I work?" },
      { ...result, answer_text: "You work at Omi." },
      { ...result, repeat_ordinal: 1 },
      { ...result, evaluation_role: "candidate" },
    ]) expect(durableMemoryWorkNormalizedResultDigest(result.version, changed as never)).not.toBe(originalDigest);
  });

  test("unmanifested prose and incomplete or foreign grounding fail closed", async () => {
    await expect(readResult({ answer_text: "You work at Omi. Extra prose. You are a co-founder." }))
      .rejects.toThrow("answer_manifest_mismatch");
    await expect(readResult({ assertions: [assertionRows()[0]] }))
      .rejects.toThrow("answer_manifest_mismatch");
    await expect(readResult({
      answer_text: assertionRows()[0]!.text,
      assertions: [assertionRows()[0]],
    })).rejects.toThrow("unused_grounded_reference");
    await expect(readResult({
      assertions: [{ ordinal: 0, text: "You work at Omi.", citations: [traceRef("foreign")] }],
      answer_text: "You work at Omi.",
    })).rejects.toThrow("citation_not_grounded");
    const descending = [...groundedRefs].sort().reverse();
    await expect(readResult({
      assertions: [{ ordinal: 0, text: "You work at Omi.", citations: descending }],
      answer_text: "You work at Omi.",
    })).rejects.toThrow("invalid_assertion");
  });

  test("qualified no-answer is exact and cannot claim grounded recall", async () => {
    const bundle = assignment();
    const result = await readResult({
      answer_text: null,
      absence: "query_gap",
      assertions: [],
      recall_trace: emptyTrace(bundle.strategies[0]!.coordinates.strategy_version),
    }, bundle);
    expect(result).toMatchObject({ answer_text: null, absence: "query_gap", assertions: [] });
    await expect(readResult({ answer_text: null, absence: "query_gap", assertions: [] }))
      .rejects.toThrow("invalid_no_answer");
    await expect(readResult({ answer_text: null, absence: null, assertions: [], recall_trace: emptyTrace() }))
      .rejects.toThrow("invalid_no_answer");
  });

  test("authority, source, strategy, role, repeat, trace, and hostile shapes fail before output", async () => {
    await expect(readResult({}, assignment("formation"))).rejects.toThrow("not_read_strategy");
    const validBundle = assignment();
    expect(() => buildMemoryReadEvaluationResult(context("memories.work.execute"), {
      assignment_bundle: validBundle,
    } as never)).toThrow("capability_denied");
    const foreign = await copiedInput(context("memories.experiments.shadow", "account:bob"));
    await expect(readResult({ copied_input: foreign })).rejects.toThrow("copied_input_authority_mismatch");
    const copied = await copiedInput();
    await expect(readResult({ copied_input: { ...copied } })).rejects.toThrow("unverified_copied_input");
    await expect(readResult({ evaluation_role: "control" })).rejects.toThrow("invalid_role");
    await expect(readResult({ repeat_ordinal: 20 })).rejects.toThrow("invalid_repeat");
    await expect(readResult({ recall_trace: { ...groundedTrace() } })).rejects.toThrow("unverified_trace");
    await expect(readResult({ query_text: "bad\nquery" })).rejects.toThrow("invalid_query");
    await expect(readResult({ assertions: new Proxy(assertionRows(), {}) })).rejects.toThrow("invalid_assertions");
  });

  test("result is intentionally sensitive but excludes raw provenance and operational text", async () => {
    const serialized = JSON.stringify(await readResult());
    expect(serialized).toContain("Where do I work?");
    expect(serialized).toContain("You work at Omi.");
    for (const forbidden of [
      "source:raw:must-not-leak", "frontier:raw:must-not-leak", "evidence:raw",
      "claim:raw", "tool_args", "provider error", "account:alice",
    ]) expect(serialized).not.toContain(forbidden);
  });

  test("stored JSON is strictly reparsed and hostile or inconsistent rows fail closed", async () => {
    const result = await readResult();
    expect(() => parseMemoryReadEvaluationResult({ ...result, extra: true })).toThrow("invalid_stored_result");
    expect(() => parseMemoryReadEvaluationResult({ ...result, answer_text: "Invented prose." }))
      .toThrow("answer_manifest_mismatch");
    expect(() => parseMemoryReadEvaluationResult({ ...result, recall_trace: { ...result.recall_trace } }))
      .not.toThrow();
    expect(() => parseMemoryReadEvaluationResult(new Proxy({ ...result }, {}))).toThrow("invalid_stored_result");
  });

  test("opaque export cannot reveal staged read query, answer, assertions, or trace", async () => {
    const bundle = assignment();
    const make = async (role: MemoryEvaluationRole) => {
      const selected = role === "baseline" ? bundle.authority : bundle.shadows[0]!;
      const normalized = await readResult({
        assignment_id: selected.assignment_id,
        evaluation_role: role,
        recall_trace: groundedTrace(bundle.strategies.find(
          (strategy) => strategy.strategy_id === selected.strategy_id,
        )!.coordinates.strategy_version),
      }, bundle);
      const body = {
        assignment_bundle: bundle,
        assignment_id: selected.assignment_id,
        account_epoch: 7,
        evaluation_role: role,
        evaluation_mode: "offline_replay" as const,
        evaluation_run_id: `mer1_${digest("b")}`,
        input_frontier: "frontier:raw:must-not-leak",
        input_digest: normalized.copied_input_digest,
        repeat_ordinal: 0,
        result_contract_version: normalized.version,
        response_digest: sha256CanonicalContent({ role, normalized }),
        normalized_result_digest: durableMemoryWorkNormalizedResultDigest(normalized.version, normalized as never),
        normalized_result: normalized,
      };
      const request: MemoryEvaluationStageRequest = {
        ...body,
        request_digest: memoryEvaluationStageRequestDigest(context(), body),
      };
      return materializeMemoryEvaluationResult(context(), request);
    };
    const pair = pairMemoryEvaluationResults(await make("baseline"), await make("candidate"));
    const exported = JSON.stringify(buildMemoryEvaluationExport(context(), [pair]));
    for (const forbidden of [
      "Where do I work?", "You work at Omi.", "assertions", "recall_trace", "traceRef",
    ]) expect(exported).not.toContain(forbidden);
  });
});
