import { isProxy } from "node:util/types";

import {
  planPredicateAlignmentQuestions,
  type PredicateAlignmentCoverage,
  type PredicateAlignmentSuccessfulQuestion,
} from "../../../core/consolidate/relations";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  type AcceptedDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { PredicateSchema, type Predicate } from "../../../core/schema";
import { validateStrict } from "../../../core/schema/json";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceOutcome,
  type DurableMemoryWorkAcceptanceRepository,
} from "../stores/durable-memory-work-repository";
import { normalizeDurableMemoryWorkResultJson } from "../stores/durable-memory-work-result-repository";
import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from "./durable-memory-graph-plan";
import {
  PREDICATE_BATCH_PROMPT_BUDGET,
  predicateBatchAdjudicationContract,
  predicateBatchPromptCost,
} from "./predicate-batch-contract";
import {
  PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION,
  predicateBatchWorkInputManifest,
  type PredicateBatchInputSnapshot,
} from "./predicate-batch-work-adapter";

const SCHEDULER_PORT: unique symbol = Symbol("predicate-batch-work-scheduler");
export const PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION =
  "predicate-batch-scheduling-snapshot-v1" as const;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const MAX_PREDICATE_REVISIONS = 1_024;
const MAX_SUCCESSFUL_QUESTIONS = 4_096;
export const MAX_PREDICATE_JOBS_PER_SCHEDULING_CALL = 64;

export interface PredicateBatchSchedulingSnapshot {
  readonly version: typeof PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION;
  readonly owner_account_id: string;
  readonly input_frontier: string;
  readonly predicates: readonly Predicate[];
  readonly successful_questions: readonly PredicateAlignmentSuccessfulQuestion[];
}

export interface PredicateBatchWorkSchedulingRequest {
  readonly snapshot: PredicateBatchSchedulingSnapshot;
  readonly strategy_assignment: Readonly<MemoryStrategyAssignmentBundle>;
  readonly accepted_at_event_time: number;
  readonly max_attempts: number;
  readonly max_jobs_per_invocation: number;
}

export interface ScheduledPredicateBatchWork {
  readonly job_id: string;
  readonly batch_question_digest: string;
  readonly acceptance: "accepted" | "replayed";
}

export type PredicateBatchSchedulingHaltCode =
  | "idempotency_conflict"
  | "serialization_retryable"
  | "stale_context"
  | "authorization_denied"
  | "repository_unavailable";

export interface PredicateBatchSchedulingOutcome {
  readonly kind: "already_complete" | "accepted" | "partial" | "halted";
  readonly planned_jobs: number;
  readonly scheduled: readonly ScheduledPredicateBatchWork[];
  readonly coverage: Readonly<PredicateAlignmentCoverage>;
  readonly halt: Readonly<{
    job_id: string;
    batch_question_digest: string;
    code: PredicateBatchSchedulingHaltCode;
  }> | null;
}

export interface PredicateBatchWorkScheduler {
  readonly [SCHEDULER_PORT]: true;
  schedule(
    context: AuthorizedLedgerWriteContext,
    request: PredicateBatchWorkSchedulingRequest,
  ): Promise<PredicateBatchSchedulingOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`predicate batch scheduler ${code}`); };
const compareStrings = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const objectValue = value as object;
  const actual = Reflect.ownKeys(objectValue);
  if (actual.some((key) => typeof key !== "string")) fail(code);
  const sorted = (actual as string[]).sort();
  const expected = [...keys].sort();
  if (sorted.length !== expected.length || sorted.some((key, index) => key !== expected[index])) fail(code);
  for (const key of sorted) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value as string;
};

const positive = (value: unknown, maximum: number, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1 || (value as number) > maximum) fail(code);
  return value as number;
};

const nonnegative = (value: unknown, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(code);
  return value as number;
};

const successfulQuestion = (value: unknown): Readonly<PredicateAlignmentSuccessfulQuestion> => {
  const item = exactRecord(value, [
    "batch_question_digest", "predicate_frontier", "predicate_ids",
    "response_digest", "result_digest",
  ], "invalid_snapshot");
  if (!Array.isArray(item["predicate_ids"]) || item["predicate_ids"].length < 2
    || item["predicate_ids"].some((id) => typeof id !== "string" || !TOKEN.test(id))
    || new Set(item["predicate_ids"]).size !== item["predicate_ids"].length) fail("invalid_snapshot");
  return Object.freeze({
    batch_question_digest: digest(item["batch_question_digest"], "invalid_snapshot"),
    predicate_frontier: digest(item["predicate_frontier"], "invalid_snapshot"),
    predicate_ids: Object.freeze([...(item["predicate_ids"] as string[])]),
    response_digest: digest(item["response_digest"], "invalid_snapshot"),
    result_digest: digest(item["result_digest"], "invalid_snapshot"),
  });
};

export const parsePredicateBatchSchedulingSnapshot = (
  value: unknown,
): Readonly<PredicateBatchSchedulingSnapshot> => {
  const normalized = normalizeDurableMemoryWorkResultJson(value);
  const input = exactRecord(normalized, [
    "version", "owner_account_id", "input_frontier", "predicates", "successful_questions",
  ], "invalid_snapshot");
  if (input["version"] !== PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION
    || !Array.isArray(input["predicates"]) || input["predicates"].length < 2
    || input["predicates"].length > MAX_PREDICATE_REVISIONS
    || input["predicates"].some((predicate) => !validateStrict(PredicateSchema, predicate))
    || !Array.isArray(input["successful_questions"])
    || input["successful_questions"].length > MAX_SUCCESSFUL_QUESTIONS) fail("invalid_snapshot");
  const predicates = [...input["predicates"] as unknown as Predicate[]]
    .sort((left, right) => compareStrings(left.predicate_revision_id, right.predicate_revision_id));
  if (new Set(predicates.map((predicate) => predicate.predicate_revision_id)).size !== predicates.length) {
    fail("invalid_snapshot");
  }
  const successful = (input["successful_questions"] as unknown[]).map(successfulQuestion)
    .sort((left, right) => compareStrings(left.batch_question_digest, right.batch_question_digest));
  if (new Set(successful.map((item) => item.batch_question_digest)).size !== successful.length) {
    fail("invalid_snapshot");
  }
  return Object.freeze({
    version: PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_snapshot"),
    input_frontier: token(input["input_frontier"], "invalid_snapshot"),
    predicates: Object.freeze(predicates),
    successful_questions: Object.freeze(successful),
  });
};

const authorityStrategy = (
  assignment: Readonly<MemoryStrategyAssignmentBundle>,
): Readonly<RegisteredMemoryStrategy> => {
  const strategy = assignment.strategies.find((candidate) =>
    candidate.strategy_id === assignment.authority.strategy_id
    && candidate.execution_contract_digest === assignment.authority.execution_contract_digest);
  if (!strategy) fail("invalid_assignment");
  return strategy as Readonly<RegisteredMemoryStrategy>;
};

export const scheduledPredicateBatchJobId = (
  ownerAccountId: string,
  inputFrontier: string,
  batchQuestionDigest: string,
): string => `pjob1_${sha256CanonicalContent({
  contract_version: "predicate-batch-scheduled-job-v1",
  owner_account_id: token(ownerAccountId, "invalid_job_coordinate"),
  input_frontier: token(inputFrontier, "invalid_job_coordinate"),
  batch_question_digest: digest(batchQuestionDigest, "invalid_job_coordinate"),
})}`;

const haltCode = (outcome: DurableMemoryWorkAcceptanceOutcome): PredicateBatchSchedulingHaltCode => {
  if (outcome.kind === "idempotency_conflict" || outcome.kind === "serialization_retryable"
    || outcome.kind === "stale_context" || outcome.kind === "authorization_denied") return outcome.kind;
  return fail("invalid_acceptance_outcome");
};

export const definePredicateBatchWorkScheduler = (
  repository: DurableMemoryWorkAcceptanceRepository,
): PredicateBatchWorkScheduler => Object.freeze({
  [SCHEDULER_PORT]: true as const,
  async schedule(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: PredicateBatchWorkSchedulingRequest,
  ) {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    if (context.capability !== "memories.work.accept") fail("capability_denied");
    const request = exactRecord(requestValue, [
      "snapshot", "strategy_assignment", "accepted_at_event_time",
      "max_attempts", "max_jobs_per_invocation",
    ], "invalid_request");
    const snapshot = parsePredicateBatchSchedulingSnapshot(request["snapshot"]);
    const assignment = assertMintedMemoryStrategyAssignment(request["strategy_assignment"]);
    const acceptedAt = nonnegative(request["accepted_at_event_time"], "invalid_schedule");
    const maxAttempts = positive(request["max_attempts"], 100, "invalid_schedule");
    const maxJobs = positive(
      request["max_jobs_per_invocation"], MAX_PREDICATE_JOBS_PER_SCHEDULING_CALL, "invalid_schedule",
    );
    if (snapshot.owner_account_id !== context.account_id
      || assignment.owner_account_id !== context.account_id
      || assignment.work_kind !== "predicate_batch"
      || assignment.unit_kind !== "account"
      || assignment.authority.mode !== "authority") fail("coordinate_mismatch");
    const strategy = authorityStrategy(assignment);
    if (strategy.work_kind !== "predicate_batch"
      || strategy.coordinates.result_contract_version !== DURABLE_MEMORY_GRAPH_PLAN_VERSION) {
      fail("invalid_assignment");
    }
    const plan = planPredicateAlignmentQuestions(snapshot.predicates, {
      owner_account_id: context.account_id,
      batch_prompt_budget: PREDICATE_BATCH_PROMPT_BUDGET,
      max_questions_per_invocation: maxJobs,
      prompt_cost: predicateBatchPromptCost,
      adjudication_contract: predicateBatchAdjudicationContract(strategy),
      successful_questions: snapshot.successful_questions,
    });
    if (plan.excluded_predicates.length
      || plan.valid_successful_questions.length !== snapshot.successful_questions.length) {
      fail("invalid_source_snapshot");
    }
    if (plan.questions.some((question) => question.prompt_cost > PREDICATE_BATCH_PROMPT_BUDGET)) {
      fail("unplannable_prompt");
    }
    const byPredicateId = new Map<string, Predicate[]>();
    for (const predicate of snapshot.predicates) {
      const revisions = byPredicateId.get(predicate.predicate_id) ?? [];
      revisions.push(predicate);
      byPredicateId.set(predicate.predicate_id, revisions);
    }
    const scheduled: ScheduledPredicateBatchWork[] = [];
    for (const question of plan.questions) {
      const jobId = scheduledPredicateBatchJobId(
        context.account_id, snapshot.input_frontier, question.batch_question_digest,
      );
      const predicates = question.predicate_ids.flatMap((predicateId) => byPredicateId.get(predicateId) ?? [])
        .sort((left, right) => compareStrings(left.predicate_revision_id, right.predicate_revision_id));
      const input: PredicateBatchInputSnapshot = {
        version: PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION,
        owner_account_id: context.account_id,
        job_id: jobId,
        input_frontier: snapshot.input_frontier,
        batch_question_digest: question.batch_question_digest,
        predicates,
      };
      const manifest = predicateBatchWorkInputManifest(input);
      const acceptedWork: AcceptedDurableMemoryWork = {
        version: DURABLE_MEMORY_WORK_VERSION,
        job_id: jobId,
        owner_account_id: context.account_id,
        account_epoch: context.account_epoch,
        lifecycle_state: "active",
        deletion_epoch: null,
        work_kind: "predicate_batch",
        input_frontier: snapshot.input_frontier,
        input_digest: durableMemoryWorkInputManifestDigest(manifest),
        execution_contract_digest: assignment.authority.execution_contract_digest,
        accepted_at_event_time: acceptedAt,
        max_attempts: maxAttempts,
      };
      const pending = acceptDurableMemoryWork(acceptedWork);
      let outcome: DurableMemoryWorkAcceptanceOutcome;
      try {
        outcome = await repository.accept(context, {
          accepted_work: acceptedWork,
          input_manifest: manifest,
          strategy_assignment: assignment,
          request_digest: durableMemoryWorkAcceptanceRequestDigest(pending, manifest, assignment),
        });
      } catch {
        return Object.freeze({
          kind: "halted" as const,
          planned_jobs: plan.questions.length,
          scheduled: Object.freeze([...scheduled]),
          coverage: plan.coverage,
          halt: Object.freeze({
            job_id: jobId,
            batch_question_digest: question.batch_question_digest,
            code: "repository_unavailable" as const,
          }),
        });
      }
      if (outcome.kind !== "accepted" && outcome.kind !== "replayed") {
        return Object.freeze({
          kind: "halted" as const,
          planned_jobs: plan.questions.length,
          scheduled: Object.freeze([...scheduled]),
          coverage: plan.coverage,
          halt: Object.freeze({
            job_id: jobId,
            batch_question_digest: question.batch_question_digest,
            code: haltCode(outcome),
          }),
        });
      }
      scheduled.push(Object.freeze({
        job_id: jobId,
        batch_question_digest: question.batch_question_digest,
        acceptance: outcome.kind,
      }));
    }
    const kind = plan.questions.length === 0 ? "already_complete"
      : plan.coverage.remaining_pairs_after_plan > 0 ? "partial" : "accepted";
    return Object.freeze({
      kind,
      planned_jobs: plan.questions.length,
      scheduled: Object.freeze(scheduled),
      coverage: plan.coverage,
      halt: null,
    });
  },
});
