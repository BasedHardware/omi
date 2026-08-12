import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import { durableMemoryWorkNormalizedResultDigest } from "../../apps/service/stores/durable-memory-work-result-repository";
import { defineMemoryEvaluationEvidenceSource } from "../../apps/service/stores/memory-evaluation-evidence-source";
import { materializeFinalizedMemoryReadGrounding } from "../../apps/service/stores/memory-read-grounding-repository";
import {
  memoryEvaluationStageRequestDigest,
  materializeMemoryEvaluationResult,
  pairMemoryEvaluationResults,
  type MemoryEvaluationStageRequest,
} from "../../apps/service/stores/memory-shadow-result-repository";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import { buildContentSafeRecallTrace } from "../../core/retrieve/recall-integrity";
import { buildMemoryReadEvaluationResult } from "../../apps/service/workers/memory-read-evaluation-result";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  createPostgresMemoryReadGroundingRepository,
  createPostgresMemoryShadowResultRepository,
} from "./memory-experiment-repository";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const hex = (character: string): string => character.repeat(64);

const authority = (): AuthorityStateRow => ({
  account_id: "account:alice", principal_id: "worker:evaluator", application_id: "app:evaluator",
  credential_id: "credential:evaluator", credential_generation: 1,
  capability: "memories.experiments.shadow", grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 7, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 300,
  control_revision: 17, control_content_hash: hex("1"), credential_content_hash: hex("2"),
  grant_content_hash: hex("3"), db_now_epoch_seconds: 150,
});

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1", principal_id: "worker:evaluator",
  account_id: "account:alice", application_id: "app:evaluator",
  credential_id: "credential:evaluator", credential_generation: 1,
  capability: "memories.experiments.shadow", grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: authorizationStateDigest(authority()),
}, 150);

const bundle = () => {
  const strategy = (id: string, prompt: string) => registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION, strategy_id: id, work_kind: "formation",
    coordinates: {
      strategy_version: "formation:v1", model_version: "deepseek:v1", prompt_version: prompt,
      policy_version: "policy:v1", code_version: "code:v1", schema_version: "schema:v1",
      tokenizer_version: "tokenizer:v1", tool_version: "none",
      result_contract_version: "formation-result:v2", speaker_strategy_version: "speaker:v1",
      boundary_strategy_version: "boundary:v1",
    },
  });
  const baseline = strategy("strategy:baseline", "prompt:baseline");
  const candidate = strategy("strategy:candidate", "prompt:candidate");
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:formation:v1", work_kind: "formation", unit_kind: "session",
    key_version: "key:v1", authority_strategy_id: baseline.strategy_id,
    shadow_candidates: [{ strategy_id: candidate.strategy_id, basis_points: 10_000 }],
  }, [baseline, candidate]);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(8)).assign({
    owner_account_id: "account:alice", unit_ref: "session:one",
    policy, strategies: [baseline, candidate],
  });
};

const request = (role: "baseline" | "candidate"): MemoryEvaluationStageRequest => {
  const assignment = bundle();
  const selected = role === "baseline" ? assignment.authority : assignment.shadows[0]!;
  const normalized = Object.freeze({ claims: [{ relation: role }] });
  const body = {
    assignment_bundle: assignment, assignment_id: selected.assignment_id, account_epoch: 7,
    evaluation_role: role, evaluation_mode: "offline_replay" as const,
    evaluation_run_id: `mer1_${hex("a")}`, input_frontier: "frontier:one",
    input_digest: hex("b"), repeat_ordinal: 0, result_contract_version: "formation-result:v2",
    response_digest: sha256CanonicalContent({ role }),
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest("formation-result:v2", normalized),
    normalized_result: normalized,
  };
  return { ...body, request_digest: memoryEvaluationStageRequestDigest(context(), body) };
};

const readRequest = async (): Promise<MemoryEvaluationStageRequest> => {
  const strategy = (id: string, version: string) => registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION, strategy_id: id, work_kind: "retrieval",
    coordinates: {
      strategy_version: version, model_version: "deepseek:v1", prompt_version: "prompt:v1",
      policy_version: "policy:v1", code_version: "code:v1", schema_version: "schema:v1",
      tokenizer_version: "tokenizer:v1", tool_version: "none",
      result_contract_version: "memory-read-evaluation-result-v1",
      speaker_strategy_version: "none", boundary_strategy_version: "none",
    },
  });
  const baseline = strategy("strategy:retrieval:baseline", "retrieval:baseline:v1");
  const candidate = strategy("strategy:retrieval:candidate", "retrieval:candidate:v1");
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:retrieval:v1", work_kind: "retrieval", unit_kind: "session",
    key_version: "key:v1", authority_strategy_id: baseline.strategy_id,
    shadow_candidates: [{ strategy_id: candidate.strategy_id, basis_points: 10_000 }],
  }, [baseline, candidate]);
  const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(6)).assign({
    owner_account_id: "account:alice", unit_ref: "session:read",
    policy, strategies: [baseline, candidate],
  });
  const source = defineMemoryEvaluationEvidenceSource(async (authorized, selected) => ({
    kind: "found", owner_account_id: authorized.account_id, account_epoch: authorized.account_epoch,
    source_kind: selected.source_kind, source_ref: selected.source_ref,
    input_frontier: selected.input_frontier, payload: { query: "Where do I work?" },
  }));
  const copied = await source.load(context(), {
    source_kind: "authorized_graph_snapshot", source_ref: "source:read", input_frontier: "frontier:read",
  });
  if (copied.kind !== "found") throw new Error("unreachable");
  const ref = `tr1_${sha256CanonicalContent({ evidence: "one" })}` as const;
  const trace = buildContentSafeRecallTrace({
    version: "recall-trace-v1", traceRef: `tr1_${sha256CanonicalContent({ root: "one" })}`,
    strategyVersion: baseline.coordinates.strategy_version, projectionFreshness: "fresh",
    outcome: "grounded", latencyMs: 1, tokenCounts: { input: 1, output: 1 },
    stages: { eligible: [ref], selected: [ref], hydrated: [ref], policyEligible: [ref], cited: [ref], grounded: [ref] },
  });
  const normalized = buildMemoryReadEvaluationResult(context(), {
    assignment_bundle: assignment, assignment_id: assignment.authority.assignment_id,
    copied_input: copied.copied_input, evaluation_role: "baseline", repeat_ordinal: 0,
    query_text: "Where do I work?", answer_text: "You work at Omi.", absence: null,
    assertions: [{ ordinal: 0, text: "You work at Omi.", citations: [ref] }], recall_trace: trace,
  });
  const body = {
    assignment_bundle: assignment, assignment_id: assignment.authority.assignment_id,
    account_epoch: 7, evaluation_role: "baseline" as const, evaluation_mode: "offline_replay" as const,
    evaluation_run_id: `mer1_${hex("d")}`, input_frontier: "frontier:read",
    input_digest: copied.copied_input.input_digest, repeat_ordinal: 0,
    result_contract_version: normalized.version, response_digest: sha256CanonicalContent(normalized),
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest(normalized.version, normalized),
    normalized_result: normalized,
  };
  return { ...body, request_digest: memoryEvaluationStageRequestDigest(context(), body) };
};

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ id: "experiment-connection" });
  readonly statements: SqlStatement[] = [];
  readonly hashes = new Map<string, string>();
  readonly results = new Map<string, Record<string, unknown>>();
  readonly pairs = new Map<string, Record<string, unknown>>();
  readonly groundings = new Map<string, Record<string, unknown>>();

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") return [authority() as unknown as Row];
    if (statement.name.endsWith(".verify")) {
      const key = `${statement.name}:${statement.values.join(":")}`;
      return [{ content_hash: this.hashes.get(key) } as unknown as Row];
    }
    if (statement.name.endsWith("_result_load")) {
      const row = this.results.get(String(statement.values[1]));
      return row ? [row as Row] : [];
    }
    if (statement.name === "experiment.pair_load") {
      const row = this.pairs.get(String(statement.values[1]));
      return row ? [row as Row] : [];
    }
    if (statement.name.endsWith("_grounding_load")) {
      const row = this.groundings.get(String(statement.values[1]));
      return row ? [row as Row] : [];
    }
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (statement.name.endsWith(".insert") && statement.name.startsWith("work.")) {
      const verifyName = statement.name.replace(/\.insert$/, ".verify");
      let selectValues: readonly unknown[];
      if (verifyName === "work.strategy_shadow_assignment.verify") {
        selectValues = [statement.values[0], statement.values[1], statement.values[2]];
      } else {
        selectValues = [statement.values[0], statement.values[1]];
      }
      this.hashes.set(`${verifyName}:${selectValues.join(":")}`, String(statement.values.at(-1)));
    }
    if (statement.name.endsWith("_result_insert")) {
      const values = statement.values;
      this.results.set(String(values[1]), {
        account_id: values[0], evaluation_result_id: values[1], result_version: values[2],
        account_epoch: values[3], assignment_bundle_id: values[4], assignment_bundle_digest: values[5],
        assignment_id: values[6], strategy_id: values[7], execution_contract_digest: values[8],
        evaluation_role: statement.name.includes("baseline") ? "baseline" : "candidate",
        evaluation_mode: values[10], evaluation_run_id: values[11], input_frontier: values[12],
        input_digest: values[13], repeat_ordinal: values[14], result_contract_version: values[15],
        response_digest: values[16], normalized_result_digest: values[17],
        normalized_result_json: JSON.parse(String(values[18])), stage_request_digest: values[19],
        content_hash: values[20],
      });
    }
    if (statement.name === "experiment.pair_insert") {
      this.pairs.set(String(statement.values[1]), {
        pair_digest: statement.values[3], content_hash: statement.values[17],
      });
    }
    if (statement.name.endsWith("_grounding_insert")) {
      const values = statement.values;
      this.groundings.set(String(values[2]), {
        artifact_version: values[3], grounding_artifact_id: values[1], evaluation_result_id: values[2],
        copied_input_digest: values[5], input_frontier_digest: values[6], strategy_id: values[7],
        execution_contract_digest: values[8], normalized_result_digest: values[10], response_digest: values[11],
        projection_authorization_digest: values[12], reader_projection_digest: values[13],
        projected_content_digest: values[14], grounded_reference_count: values[15],
        rows_json: JSON.parse(String(values[16])), artifact_digest: values[17],
      });
    }
    return { rowCount: 1 };
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];
  constructor(readonly connection: FakeConnection) {}
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.options.push(options);
    return callback(this.connection);
  }
}

describe("PostgreSQL isolated memory experiment repository", () => {
  test("persists exact baseline/candidate results, replays, loads, and pairs after authority", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresMemoryShadowResultRepository({ pool: new FakePool(connection) });
    const baselineRequest = request("baseline");
    const candidateRequest = request("candidate");
    const baseline = await repository.stage(context(), baselineRequest);
    const candidate = await repository.stage(context(), candidateRequest);
    expect(baseline.kind).toBe("staged");
    expect(candidate.kind).toBe("staged");
    if (baseline.kind !== "staged" || candidate.kind !== "staged") throw new Error("unreachable");
    await expect(repository.stage(context(), baselineRequest)).resolves.toEqual({
      kind: "replayed", result: baseline.result,
    });
    await expect(repository.load(context(), {
      assignment_bundle: baselineRequest.assignment_bundle,
      assignment_id: baselineRequest.assignment_id,
      account_epoch: baselineRequest.account_epoch,
      evaluation_role: baselineRequest.evaluation_role,
      evaluation_mode: baselineRequest.evaluation_mode,
      evaluation_run_id: baselineRequest.evaluation_run_id,
      input_frontier: baselineRequest.input_frontier,
      input_digest: baselineRequest.input_digest,
      repeat_ordinal: baselineRequest.repeat_ordinal,
    })).resolves.toEqual({ kind: "found", result: baseline.result });
    const pair = pairMemoryEvaluationResults(baseline.result, candidate.result);
    await expect(repository.recordPair(context(), pair)).resolves.toEqual({ kind: "recorded", pair });
    await expect(repository.recordPair(context(), pair)).resolves.toEqual({ kind: "replayed", pair });
    expect(connection.statements.slice(0, 3).map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "experiment.baseline_result_load",
    ]);
    expect(connection.statements.some((statement) => /memory_(?:graph|product|work_acceptances)/.test(statement.text)))
      .toBe(false);
  });

  test("corrupt persisted result is masked as a content-safe persistence failure", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresMemoryShadowResultRepository({ pool: new FakePool(connection) });
    const staged = request("baseline");
    const outcome = await repository.stage(context(), staged);
    if (outcome.kind !== "staged") throw new Error("unreachable");
    connection.results.get(outcome.result.evaluation_result_id)!.content_hash = hex("f");
    await expect(repository.load(context(), {
      assignment_bundle: staged.assignment_bundle, assignment_id: staged.assignment_id,
      account_epoch: staged.account_epoch, evaluation_role: staged.evaluation_role,
      evaluation_mode: staged.evaluation_mode, evaluation_run_id: staged.evaluation_run_id,
      input_frontier: staged.input_frontier, input_digest: staged.input_digest,
      repeat_ordinal: staged.repeat_ordinal,
    })).rejects.toEqual(expect.objectContaining({ code: "persistence_failed" }));
  });

  test("stages and reloads total grounding against the exact persisted read result", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const groundings = createPostgresMemoryReadGroundingRepository({ pool });
    const request = await readRequest();
    const result = materializeMemoryEvaluationResult(context(), request);
    const read = result.normalized_result as {
      recall_trace: { stages: { grounded: readonly string[] } };
    };
    const artifact = materializeFinalizedMemoryReadGrounding({
      evaluation_result: result, projection_authorization_digest: hex("7"),
      reader_projection_digest: hex("8"), projected_content_digest: hex("9"),
      rows: [{
        trace_ref: read.recall_trace.stages.grounded[0] as `tr1_${string}`,
        contributing_subject_classes: ["owner"],
      }],
    });
    await expect(groundings.stage(context(), result, artifact, request)).resolves.toEqual({ kind: "staged", artifact });
    await expect(groundings.load(context(), result)).resolves.toEqual({ kind: "found", artifact });
    await expect(groundings.stage(context(), result, artifact, request)).resolves.toEqual({ kind: "replayed", artifact });
    expect(connection.results.has(result.evaluation_result_id)).toBe(true);
    expect(connection.statements.filter((statement) => statement.name.endsWith("grounding_insert"))).toHaveLength(1);
  });
});
