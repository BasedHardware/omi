import { isProxy } from "node:util/types";

import {
  invokePredicateAlignment,
  predicateAlignmentBatchDigest,
  preparePredicateAlignmentQuestion,
} from "../../../core/consolidate/relations";
import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkErrorCode,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { CanonicalJson, GraphRevision } from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { PredicateSchema, type Predicate } from "../../../core/schema";
import { validateStrict } from "../../../core/schema/json";
import { bindModelPortAbortSignal, type ModelPort } from "../../../drivers/model/port";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkInputManifestEntry,
} from "../stores/durable-memory-work-repository";
import {
  normalizeDurableMemoryWorkResultJson,
  type StagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import {
  DURABLE_MEMORY_GRAPH_PLAN_VERSION,
  createDurableMemoryGraphPlan,
  durableMemoryGraphPlanIsEmpty,
  materializeDurableMemoryGraphPlan,
} from "./durable-memory-graph-plan";
import type {
  DurableMemoryWorkMaterializeOutcome,
  DurableMemoryWorkProduceOutcome,
} from "./durable-memory-work-runner";
import {
  defineConsolidationWorkAdapter,
  type ConsolidationWorkAdapter,
} from "./consolidation-work-service";
import {
  PREDICATE_BATCH_PROMPT_BUDGET,
  predicateBatchAdjudicationContract,
  predicateBatchPromptCost,
} from "./predicate-batch-contract";

export const PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION = "predicate-batch-input-snapshot-v1" as const;
const MAX_BATCH_PREDICATE_REVISIONS = 10_000;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;

export interface PredicateBatchInputSnapshot {
  readonly version: typeof PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION;
  readonly owner_account_id: string;
  readonly job_id: string;
  readonly input_frontier: string;
  readonly batch_question_digest: string;
  readonly predicates: readonly Predicate[];
}

export type PredicateBatchInputLoadOutcome =
  | Readonly<{ kind: "found"; snapshot: PredicateBatchInputSnapshot }>
  | Readonly<{ kind: "not_found" }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export type PredicateBatchParentLoadOutcome =
  | Readonly<{ kind: "found"; parent_commit: string | null }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export interface PredicateBatchWorkAdapterDependencies {
  readonly load_input: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<PredicateBatchInputLoadOutcome>;
  readonly resolve_model: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ) => Promise<ModelPort | null>;
  readonly load_current_parent: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<PredicateBatchParentLoadOutcome>;
}

export interface PredicateBatchWorkAdapter {
  produce(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
    lossSignal?: AbortSignal,
  ): Promise<DurableMemoryWorkProduceOutcome>;
  materialize(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    staged: StagedDurableMemoryWorkResult,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ): Promise<DurableMemoryWorkMaterializeOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`predicate batch adapter ${code}`); };
const failed = (error_code: DurableMemoryWorkErrorCode): DurableMemoryWorkProduceOutcome =>
  Object.freeze({ kind: "failed" as const, error_code });

const token = (value: unknown): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail("invalid_snapshot");
  return value as string;
};

const digest = (value: unknown): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail("invalid_snapshot");
  return value as string;
};

const exactDependencies = (value: unknown): PredicateBatchWorkAdapterDependencies => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_dependencies");
  const objectValue = value as object;
  const keys = Reflect.ownKeys(objectValue);
  if (keys.length !== 3 || keys.some((key) => typeof key !== "string")
    || !(keys as string[]).every((key) => ["load_input", "resolve_model", "load_current_parent"].includes(key))) {
    fail("invalid_dependencies");
  }
  for (const key of keys as string[]) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
      || typeof descriptor.value !== "function" || isProxy(descriptor.value)) fail("invalid_dependencies");
  }
  return value as PredicateBatchWorkAdapterDependencies;
};

export const parsePredicateBatchInputSnapshot = (
  value: unknown,
): Readonly<PredicateBatchInputSnapshot> => {
  const normalized = normalizeDurableMemoryWorkResultJson(value);
  const keys = Object.keys(normalized).sort();
  const expected = [
    "version", "owner_account_id", "job_id", "input_frontier",
    "batch_question_digest", "predicates",
  ].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
    fail("invalid_snapshot");
  }
  const predicates = normalized["predicates"];
  if (!Array.isArray(predicates) || predicates.length < 2
    || predicates.length > MAX_BATCH_PREDICATE_REVISIONS
    || predicates.some((predicate) => !validateStrict(PredicateSchema, predicate))) {
    fail("invalid_snapshot");
  }
  const snapshot: PredicateBatchInputSnapshot = {
    version: normalized["version"] === PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION
      ? PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION : fail("invalid_snapshot"),
    owner_account_id: token(normalized["owner_account_id"]),
    job_id: token(normalized["job_id"]),
    input_frontier: token(normalized["input_frontier"]),
    batch_question_digest: digest(normalized["batch_question_digest"]),
    predicates: predicates as unknown as readonly Predicate[],
  };
  return Object.freeze(snapshot);
};

export const predicateBatchWorkInputManifest = (
  snapshotValue: PredicateBatchInputSnapshot,
): readonly Readonly<DurableMemoryWorkInputManifestEntry>[] => {
  const snapshot = parsePredicateBatchInputSnapshot(snapshotValue);
  return Object.freeze([
    {
      input_kind: "graph_frontier" as const,
      input_ref: snapshot.input_frontier,
      input_digest: sha256CanonicalContent({
        contract_version: PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION,
        owner_account_id: snapshot.owner_account_id,
        job_id: snapshot.job_id,
        input_frontier: snapshot.input_frontier,
        batch_question_digest: snapshot.batch_question_digest,
        predicate_revision_ids: snapshot.predicates.map((predicate) => predicate.predicate_revision_id).sort(),
      }),
    },
    ...snapshot.predicates.map((predicate) => ({
      input_kind: "predicate_revision" as const,
      input_ref: predicate.predicate_revision_id,
      input_digest: sha256CanonicalContent(predicate),
    })),
  ]);
};

export const assertPredicateBatchInputSnapshotMatchesJob = (
  snapshot: Readonly<PredicateBatchInputSnapshot>,
  job: Readonly<DurableMemoryWorkJob>,
): void => {
  if (snapshot.owner_account_id !== job.owner_account_id || snapshot.job_id !== job.job_id
    || snapshot.input_frontier !== job.input_frontier
    || snapshot.predicates.some((predicate) => predicate.owner_account_id !== job.owner_account_id)
    || durableMemoryWorkInputManifestDigest(predicateBatchWorkInputManifest(snapshot)) !== job.input_digest) {
    fail("input_job_mismatch");
  }
};

const assertSnapshot = (
  snapshot: Readonly<PredicateBatchInputSnapshot>,
  job: Readonly<DurableMemoryWorkJob>,
  strategy: Readonly<RegisteredMemoryStrategy>,
): { request: ReturnType<typeof preparePredicateAlignmentQuestion>["request"]; prompt_cost: number } => {
  assertPredicateBatchInputSnapshotMatchesJob(snapshot, job);
  const prepared = preparePredicateAlignmentQuestion(snapshot.predicates, job.owner_account_id);
  if (prepared.excluded_predicates.length || prepared.request.predicates.length < 2
    || predicateAlignmentBatchDigest(predicateBatchAdjudicationContract(strategy), prepared.request)
      !== snapshot.batch_question_digest) fail("invalid_question");
  return { request: prepared.request, prompt_cost: predicateBatchPromptCost(prepared.request) };
};

const mapRetryable = (code: "batch_prompt_budget_exceeded" | "model_invoke_failed" | "model_response_invalid"):
DurableMemoryWorkErrorCode => {
  if (code === "batch_prompt_budget_exceeded") return "prompt_budget_exceeded";
  if (code === "model_response_invalid") return "model_response_invalid";
  return "dependency_unavailable";
};

export const definePredicateBatchWorkAdapter = (
  dependenciesValue: PredicateBatchWorkAdapterDependencies,
): PredicateBatchWorkAdapter => {
  const dependencies = exactDependencies(dependenciesValue);
  return Object.freeze({
    async produce(
      contextValue: AuthorizedLedgerWriteContext,
      jobValue: Readonly<DurableMemoryWorkJob>,
      strategyValue: Readonly<RegisteredMemoryStrategy>,
      lossSignal?: AbortSignal,
    ) {
      let context: AuthorizedLedgerWriteContext;
      let job: Readonly<DurableMemoryWorkJob>;
      let strategy: Readonly<RegisteredMemoryStrategy>;
      try {
        context = assertAuthorizedLedgerWriteContext(contextValue);
        job = parseDurableMemoryWorkJob(jobValue);
        strategy = parseRegisteredMemoryStrategy(strategyValue);
        if (context.capability !== "memories.work.execute" || context.account_id !== job.owner_account_id
          || context.account_epoch !== job.account_epoch || job.work_kind !== "predicate_batch"
          || job.state !== "leased" || strategy.work_kind !== "predicate_batch"
          || strategy.execution_contract_digest !== job.execution_contract_digest
          || strategy.coordinates.result_contract_version !== DURABLE_MEMORY_GRAPH_PLAN_VERSION) {
          return failed("dependency_unavailable");
        }
      } catch {
        return failed("dependency_unavailable");
      }
      let snapshot: Readonly<PredicateBatchInputSnapshot>;
      let request: ReturnType<typeof preparePredicateAlignmentQuestion>["request"];
      try {
        const loaded = await dependencies.load_input(context, job);
        if (loaded.kind === "failed") return failed(loaded.error_code);
        if (loaded.kind !== "found") return failed("dependency_unavailable");
        snapshot = parsePredicateBatchInputSnapshot(loaded.snapshot);
        const prepared = assertSnapshot(snapshot, job, strategy);
        if (prepared.prompt_cost > PREDICATE_BATCH_PROMPT_BUDGET) return failed("prompt_budget_exceeded");
        request = prepared.request;
      } catch {
        return failed("dependency_unavailable");
      }
      let model: ModelPort | null;
      try {
        model = await dependencies.resolve_model(context, job, strategy);
        if (model === null) return failed("dependency_unavailable");
        if (lossSignal !== undefined) model = bindModelPortAbortSignal(model, lossSignal);
      } catch {
        return failed("dependency_unavailable");
      }
      try {
        const alignment = await invokePredicateAlignment(model, snapshot.predicates, {
          owner_account_id: job.owner_account_id,
          batch_prompt_budget: PREDICATE_BATCH_PROMPT_BUDGET,
          model_concurrency: 1,
          max_questions_per_invocation: 1,
          prompt_cost: predicateBatchPromptCost,
          adjudication_contract: predicateBatchAdjudicationContract(strategy),
        });
        if (alignment.excluded_predicates.length || alignment.batch_outcomes.length !== 1
          || alignment.coverage.remaining_pairs_after_plan !== 0) {
          return failed("model_response_invalid");
        }
        const outcome = alignment.batch_outcomes[0]!;
        if (outcome.kind === "retryable_error") return failed(mapRetryable(outcome.error_code));
        if (outcome.batch_question_digest !== snapshot.batch_question_digest
          || outcome.predicate_frontier !== request.predicate_frontier
          || JSON.stringify(outcome.predicate_ids) !== JSON.stringify(request.predicates.map((item) => item.predicate_id))) {
          return failed("model_response_invalid");
        }
        const committed = snapshot.predicates.map((predicate): GraphRevision => ({
          kind: "predicate",
          revision_id: predicate.predicate_revision_id,
          predicate: structuredClone(predicate),
        }));
        const revisions = outcome.assertions.map((assertion): GraphRevision => ({
          kind: "predicate_assertion",
          revision_id: `predicate-assertion:${assertion.assertion_id}`,
          assertion,
        }));
        const plan = createDurableMemoryGraphPlan(context, job, strategy, {
          origin: { kind: "non_formation", reason: "predicate_alignment" },
          input_revisions: snapshot.predicates.map((predicate) => ({
            revision_id: predicate.predicate_revision_id,
            content: structuredClone(predicate) as unknown as CanonicalJson,
          })),
          placement: { offline_experiment: true, allocations: {}, results: [] },
          revisions,
          adjacency: [],
          artifacts: [],
          identity_authority_context: null,
          derived_identity_support: null,
          committed_revisions: committed,
        });
        return Object.freeze({
          kind: "produced" as const,
          result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
          response_digest: outcome.response_digest,
          normalized_result: plan as unknown as Readonly<Record<string, CanonicalJson>>,
        });
      } catch {
        return failed("model_response_invalid");
      }
    },

    async materialize(
      context: AuthorizedLedgerWriteContext,
      job: Readonly<DurableMemoryWorkJob>,
      staged: StagedDurableMemoryWorkResult,
      strategy: Readonly<RegisteredMemoryStrategy>,
    ) {
      try {
        if (durableMemoryGraphPlanIsEmpty(context, job, staged, strategy)) {
          return Object.freeze({
            kind: "ready" as const,
            result_kind: "successful_empty" as const,
            authoritative_append: null,
          });
        }
      } catch {
        return Object.freeze({ kind: "failed" as const, error_code: "model_response_invalid" });
      }
      let loaded: PredicateBatchParentLoadOutcome;
      try { loaded = await dependencies.load_current_parent(context, job); }
      catch { return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" }); }
      if (loaded.kind === "failed") return Object.freeze({ kind: "failed" as const, error_code: loaded.error_code });
      try {
        return materializeDurableMemoryGraphPlan(context, job, staged, strategy, loaded.parent_commit);
      } catch {
        return Object.freeze({ kind: "failed" as const, error_code: "model_response_invalid" });
      }
    },
  });
};

/** The single sealed predicate semantic adapter for consolidation composition. */
export const definePredicateBatchConsolidationWorkAdapter = (
  dependencies: PredicateBatchWorkAdapterDependencies,
): ConsolidationWorkAdapter => {
  const adapter = definePredicateBatchWorkAdapter(dependencies);
  return defineConsolidationWorkAdapter("predicate_batch", adapter);
};
