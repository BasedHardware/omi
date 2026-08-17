import { describe, expect, test } from "bun:test";

import {
  formationCandidateManifestDigest,
  parseFormationOutcomeEnvelope,
} from "../../../core/consolidate/formation-outcome";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  materializeStagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import {
  DURABLE_MEMORY_GRAPH_PLAN_VERSION,
  createDurableMemoryGraphPlan,
  materializeDurableMemoryGraphPlan,
  type DurableMemoryGraphPlanTemplate,
} from "./durable-memory-graph-plan";

const digest = (character: string): string => character.repeat(64);

const context = (capability = "memories.work.execute") =>
  createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: "worker:one",
    account_id: "account:alice",
    application_id: "app:worker",
    credential_id: "credential:one",
    credential_generation: 1,
    capability,
    grant_id: "grant:one",
    grant_version: 1,
    account_epoch: 7,
    destination_activation_revision: 17,
    lifecycle_state: "active",
    deletion_epoch: null,
    authentication_strength: "service-workload",
    issued_at_epoch_seconds: 100,
    expires_at_epoch_seconds: 200,
    authorization_state_digest: digest("a"),
  }, 150);

const strategy = (workKind: DurableMemoryWorkKind) => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: `strategy:${workKind}:authority`,
  work_kind: workKind,
  coordinates: {
    strategy_version: `${workKind}:v1`, model_version: "model:v1",
    prompt_version: "prompt:v1", policy_version: "policy:v1",
    code_version: "code:v1", schema_version: "schema:v1",
    tokenizer_version: "tokenizer:v1", tool_version: "tool:v1",
    result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
    speaker_strategy_version: "speaker:v1", boundary_strategy_version: "boundary:v1",
  },
});

const leased = (workKind: DurableMemoryWorkKind) => {
  const registered = strategy(workKind);
  return {
    registered,
    job: leaseDurableMemoryWork(acceptDurableMemoryWork({
      version: DURABLE_MEMORY_WORK_VERSION,
      job_id: `job:${workKind}:one`,
      owner_account_id: "account:alice",
      account_epoch: 7,
      lifecycle_state: "active",
      deletion_epoch: null,
      work_kind: workKind,
      input_frontier: "frontier:one",
      input_digest: digest("b"),
      execution_contract_digest: registered.execution_contract_digest,
      accepted_at_event_time: 100,
      max_attempts: 3,
    }), "worker:one", 101, 20),
  };
};

const formationOutcome = (jobId: string, responseDigest = digest("c")) =>
  parseFormationOutcomeEnvelope({
    contract_version: "memory-formation-outcome-v2",
    owner_account_id: "account:alice",
    work_id: jobId,
    input_frontier: "frontier:one",
    response_digest: responseDigest,
    candidate_count: 0,
    candidate_manifest_digest: formationCandidateManifestDigest(0),
    coordinates: {
      contract_version: "memory-formation-outcome-v2",
      strategy_version: "formation:v1", model_version: "model:v1",
      prompt_version: "prompt:v1", policy_version: "policy:v1",
      code_version: "code:v1", schema_version: "schema:v1",
      tokenizer_version: "tokenizer:v1", tool_version: "tool:v1",
      speaker_strategy_version: "speaker:v1", boundary_strategy_version: "boundary:v1",
    },
    extraction_outcomes: [],
    placement_outcomes: [],
  });

const reasonFor = (workKind: Exclude<DurableMemoryWorkKind, "formation">) =>
  workKind === "promotion" ? "promotion" as const
    : workKind === "identity_cluster" ? "identity_consolidation" as const
      : "predicate_alignment" as const;

const template = (
  workKind: DurableMemoryWorkKind,
  jobId: string,
  responseDigest = digest("c"),
): DurableMemoryGraphPlanTemplate => ({
  origin: workKind === "formation"
    ? { kind: "formation", outcome: formationOutcome(jobId, responseDigest) }
    : { kind: "non_formation", reason: reasonFor(workKind) },
  input_revisions: [],
  placement: { offline_experiment: true, allocations: {}, results: [] },
  revisions: [],
  adjacency: [],
  artifacts: [],
  identity_authority_context: null,
  derived_identity_support: null,
  committed_revisions: null,
});

const staged = (
  workKind: DurableMemoryWorkKind,
  responseDigest = digest("c"),
) => {
  const { job, registered } = leased(workKind);
  const plan = createDurableMemoryGraphPlan(
    context(), job, registered, template(workKind, job.job_id, responseDigest),
  );
  const body = {
    leased_job: job,
    result_contract_version: registered.coordinates.result_contract_version,
    response_digest: responseDigest,
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest(
      registered.coordinates.result_contract_version,
      plan as never,
    ),
    normalized_result: plan as never,
  };
  return {
    job,
    registered,
    plan,
    staged: materializeStagedDurableMemoryWorkResult({
      ...body,
      request_digest: durableMemoryWorkResultStageRequestDigest(body),
    }),
  };
};

describe("durable parent-independent memory graph plan", () => {
  test("formation materialization is byte-idempotent per parent and changes only parent-bound derivation", () => {
    const value = staged("formation");
    const first = materializeDurableMemoryGraphPlan(
      context(), value.job, value.staged, value.registered, null,
    );
    const replay = materializeDurableMemoryGraphPlan(
      context(), value.job, value.staged, value.registered, null,
    );
    const advanced = materializeDurableMemoryGraphPlan(
      context(), value.job, value.staged, value.registered, "commit:intervening",
    );
    expect(replay).toEqual(first);
    expect(first.authoritative_append.origin).toEqual({
      kind: "formation", outcome: formationOutcome(value.job.job_id),
    });
    expect(advanced.authoritative_append.append_attempt.expected_parent_commit).toBe("commit:intervening");
    expect(advanced.authoritative_append.append_attempt.request_digest)
      .not.toBe(first.authoritative_append.append_attempt.request_digest);
    expect(advanced.authoritative_append.transition.derivation.commit.commit_id)
      .not.toBe(first.authoritative_append.transition.derivation.commit.commit_id);
    expect(advanced.authoritative_append.transition.revisions)
      .toEqual(first.authoritative_append.transition.revisions);
    expect(advanced.authoritative_append.transition.placement)
      .toEqual(first.authoritative_append.transition.placement);
    expect(Object.keys(first)).toEqual(["kind", "result_kind", "authoritative_append"]);
  });

  test("every non-formation work kind gets only its closed authoritative origin", () => {
    for (const workKind of ["promotion", "identity_cluster", "predicate_batch"] as const) {
      const value = staged(workKind);
      const result = materializeDurableMemoryGraphPlan(
        context(), value.job, value.staged, value.registered, null,
      );
      expect(result.authoritative_append.origin).toEqual({
        kind: "non_formation", reason: reasonFor(workKind),
      });
    }
  });

  test("origin, strategy, owner capability, and response mismatches fail closed", () => {
    const value = staged("formation");
    expect(() => createDurableMemoryGraphPlan(
      context(), value.job, value.registered,
      { ...template("formation", value.job.job_id), origin: { kind: "non_formation", reason: "promotion" } },
    )).toThrow("invalid_origin");
    expect(() => createDurableMemoryGraphPlan(
      context("memories.experiments.shadow"), value.job, value.registered,
      template("formation", value.job.job_id),
    )).toThrow("capability_denied");
    const other = strategy("promotion");
    expect(() => materializeDurableMemoryGraphPlan(
      context(), value.job, value.staged, other, null,
    )).toThrow("job_strategy_mismatch");
    const responseMismatch = staged("formation", digest("d"));
    const forged = { ...responseMismatch.staged, response_digest: digest("e") };
    expect(() => materializeDurableMemoryGraphPlan(
      context(), responseMismatch.job, forged, responseMismatch.registered, null,
    )).toThrow("formation_response_mismatch");
  });

  test("formation outcome work and strategy coordinates are exact", () => {
    const value = leased("formation");
    expect(() => createDurableMemoryGraphPlan(
      context(), value.job, value.registered, template("formation", "job:formation:other"),
    )).toThrow("formation_strategy_mismatch");
    const wrong = template("formation", value.job.job_id);
    const outcome = (wrong.origin as { kind: "formation"; outcome: ReturnType<typeof formationOutcome> }).outcome;
    expect(() => createDurableMemoryGraphPlan(context(), value.job, value.registered, {
      ...wrong,
      origin: {
        kind: "formation",
        outcome: parseFormationOutcomeEnvelope({
          ...outcome,
          coordinates: { ...outcome.coordinates, prompt_version: "prompt:wrong" },
        }),
      },
    })).toThrow("formation_strategy_mismatch");
  });

  test("plan tampering cannot cross the staged-result digest", () => {
    const value = staged("promotion");
    const tamperedPlan = { ...value.plan, input_frontier: "frontier:tampered" };
    const tamperedStage = { ...value.staged, normalized_result: tamperedPlan };
    expect(() => materializeDurableMemoryGraphPlan(
      context(), value.job, tamperedStage as never, value.registered, null,
    )).toThrow("invalid_staged_result");
    const hostile = { ...value.staged, normalized_result: new Proxy({}, {}) };
    expect(() => materializeDurableMemoryGraphPlan(
      context(), value.job, hostile, value.registered, null,
    )).toThrow("invalid_result");
  });
});
