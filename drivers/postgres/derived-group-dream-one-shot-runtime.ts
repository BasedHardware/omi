import { isProxy } from "node:util/types";

import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineConsolidationWorkAdapter,
  defineConsolidationWorkService,
  type ConsolidationWorkAdapter,
  type ConsolidationWorkKind,
} from "../../apps/service/workers/consolidation-work-service";
import {
  defineDerivedGroupDreamConsolidationAdapter,
} from "../../apps/service/workers/derived-group-dream-work-producer";
import {
  defineDerivedGroupDreamWorkDispatch,
  type DerivedGroupDreamWorkDispatchOutcome,
} from "../../apps/service/workers/derived-group-dream-work-dispatch";
import {
  derivedGroupDreamWorkInputManifest,
  type DerivedGroupDreamInputSnapshot,
} from "../../apps/service/workers/derived-group-dream-work-adapter";
import {
  derivedGroupDreamWorkInputStageRequestDigest,
} from "../../apps/service/workers/derived-group-dream-work-input-repository";
import type { DerivedGroupDreamWitnessLoadOutcome } from
  "../../apps/service/workers/derived-group-dream-materialization";
import {
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceRequest,
  type DurableMemoryWorkRecoveryOutcome,
} from "../../apps/service/stores/durable-memory-work-repository";
import type { MemoryStrategyAssignmentBundle } from "../../core/consolidate/strategy-assignment";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import type { RegisteredDurableMemoryWorkExecutionPolicy } from "../../core/consolidate/execution-policy";
import {
  acceptDurableMemoryWork,
  type AcceptedDurableMemoryWork,
  type DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import type { ClaimRevision } from "../../core/ledger";
import type { ModelPipelineResource } from "../../apps/service/workers/model-pipeline-exclusivity";
import {
  assertAdmittedModelPipelineExclusivity,
  type AdmittedModelPipelineExclusivity,
} from "../../apps/service/workers/model-pipeline-resource-admission";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresAuthoritativeGraphSnapshotRepository } from "./authoritative-graph-snapshot";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { createPostgresDurableMemoryWorkExecutionRepository } from "./durable-memory-work-execution";
import { createPostgresDurableMemoryWorkResultRepository } from "./durable-memory-work-result";
import { createPostgresDurableMemoryWorkSuccessRepository } from "./durable-memory-work-success";
import { createPostgresDerivedGroupDreamWorkInputRepository } from "./derived-group-dream-work-input";
import type { PostgresTransactionObservability } from "./transaction";

const RUNTIME_PORT: unique symbol = Symbol("postgres-derived-group-dream-one-shot-runtime");
const MAX_STRATEGIES = 32;

export interface PostgresDerivedGroupDreamOneShotRuntimeOptions {
  readonly pool: PostgresTransactionPool;
  readonly strategies: readonly Readonly<RegisteredMemoryStrategy>[];
  readonly model_pipeline_exclusivity: AdmittedModelPipelineExclusivity;
  readonly resolve_model_pipeline_resource: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ) => Promise<Readonly<ModelPipelineResource> | null>;
  readonly max_parent_rematerializations: number;
  readonly observability?: PostgresTransactionObservability;
}

export interface DerivedGroupDreamOneShotAcceptRequest {
  readonly accepted_work: AcceptedDurableMemoryWork;
  readonly snapshot: Readonly<DerivedGroupDreamInputSnapshot>;
  readonly strategy_assignment: Readonly<MemoryStrategyAssignmentBundle>;
  readonly execution_policy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>;
}

export type DerivedGroupDreamOneShotAcceptOutcome =
  | Readonly<{ kind: "accepted" | "replayed"; job: Readonly<DurableMemoryWorkJob> }>
  | Readonly<{ kind: "halted"; stage: "input" | "acceptance"; code: string }>;

export interface PostgresDerivedGroupDreamOneShotRuntime {
  readonly [RUNTIME_PORT]: true;
  accept(
    context: AuthorizedLedgerWriteContext,
    request: DerivedGroupDreamOneShotAcceptRequest,
  ): Promise<DerivedGroupDreamOneShotAcceptOutcome>;
  runNext(context: AuthorizedLedgerWriteContext): Promise<DerivedGroupDreamWorkDispatchOutcome>;
  recoverExpired(
    context: AuthorizedLedgerWriteContext,
    job_id: string,
  ): Promise<DurableMemoryWorkRecoveryOutcome>;
}

const strategyRegistry = (
  values: readonly Readonly<RegisteredMemoryStrategy>[],
): ReadonlyMap<string, Readonly<RegisteredMemoryStrategy>> => {
  if (!Array.isArray(values) || values.length === 0 || values.length > MAX_STRATEGIES) {
    throw new TypeError("postgres derived group dream runtime invalid_strategy_registry");
  }
  const byContract = new Map<string, Readonly<RegisteredMemoryStrategy>>();
  for (const value of values) {
    const strategy = parseRegisteredMemoryStrategy(value);
    if (strategy.work_kind !== "derived_group_dream"
      || byContract.has(strategy.execution_contract_digest)) {
      throw new TypeError("postgres derived group dream runtime invalid_strategy_registry");
    }
    byContract.set(strategy.execution_contract_digest, strategy);
  }
  return byContract;
};

const unsupportedAdapter = (
  kind: Exclude<ConsolidationWorkKind, "derived_group_dream">,
): ConsolidationWorkAdapter => defineConsolidationWorkAdapter(kind, {
  produce: async () => Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const }),
  materialize: async () => Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const }),
});

const halted = (
  stage: "input" | "acceptance",
  code: string,
): DerivedGroupDreamOneShotAcceptOutcome => Object.freeze({ kind: "halted" as const, stage, code });

/**
 * Route-free PostgreSQL derived-group-dream composition.
 *
 * Construction adds no timer, polling loop, scheduler, route, credential, model
 * default, or query door. The dream planner is deterministic, so no model
 * resolver is accepted here: a model default would be an activation this seam
 * is not permitted to make. Every public call is one explicitly invoked bounded
 * operation under a separately issued context.
 */
export const createPostgresDerivedGroupDreamOneShotRuntime = (
  options: PostgresDerivedGroupDreamOneShotRuntimeOptions,
): PostgresDerivedGroupDreamOneShotRuntime => {
  const modelPipelineExclusivity = assertAdmittedModelPipelineExclusivity(
    options.model_pipeline_exclusivity,
  );
  if (typeof options.resolve_model_pipeline_resource !== "function"
    || isProxy(options.resolve_model_pipeline_resource)) {
    throw new TypeError("postgres derived group dream runtime invalid_model_pipeline_resource_resolver");
  }
  const strategies = strategyRegistry(options.strategies);
  const repositoryOptions = {
    pool: options.pool,
    ...(options.observability ? { observability: options.observability } : {}),
  };
  const acceptanceRepository = createPostgresDurableMemoryWorkAcceptanceRepository(repositoryOptions);
  const executionRepository = createPostgresDurableMemoryWorkExecutionRepository(repositoryOptions);
  const resultRepository = createPostgresDurableMemoryWorkResultRepository(repositoryOptions);
  const successRepository = createPostgresDurableMemoryWorkSuccessRepository(repositoryOptions);
  const inputRepository = createPostgresDerivedGroupDreamWorkInputRepository(repositoryOptions);
  const graphRepository = createPostgresAuthoritativeGraphSnapshotRepository(repositoryOptions);

  const dreamAdapter = defineDerivedGroupDreamConsolidationAdapter({
    load_input: (context, job) => inputRepository.load(context, job),
    load_current_parent: (context) => graphRepository.loadCurrentParent(context),
    /**
     * Witness claims are re-read from the authoritative graph, never from the
     * staged snapshot: the success append re-verifies each witness against the
     * committed revision content hash, so a snapshot-sourced body could not be
     * trusted. A requested revision that is absent fails closed.
     */
    load_witness_claims: async (
      context: AuthorizedLedgerWriteContext,
      _job: Readonly<DurableMemoryWorkJob>,
      claimRevisionIds: readonly string[],
    ): Promise<DerivedGroupDreamWitnessLoadOutcome> => {
      let byRevision: Map<string, ClaimRevision>;
      try {
        const snapshot = await graphRepository.load(context);
        byRevision = new Map(snapshot.claims.map((entry) => [
          entry.revision_id,
          {
            kind: "claim" as const,
            revision_id: entry.revision_id,
            claim: entry.claim,
            placement_status: entry.placement_status,
          },
        ]));
      } catch {
        return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const });
      }
      const committed: ClaimRevision[] = [];
      for (const revisionId of claimRevisionIds) {
        const revision = byRevision.get(revisionId);
        if (!revision) {
          return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const });
        }
        committed.push(revision);
      }
      return Object.freeze({
        kind: "found" as const,
        committed_revisions: Object.freeze(committed),
      });
    },
  });

  const service = defineConsolidationWorkService({
    execution_repository: executionRepository,
    result_repository: resultRepository,
    success_repository: successRepository,
    resolve_strategy: async (job) => strategies.get(job.execution_contract_digest) ?? null,
    adapters: {
      derived_group_dream: dreamAdapter,
      identity_cluster: unsupportedAdapter("identity_cluster"),
      predicate_batch: unsupportedAdapter("predicate_batch"),
      promotion: unsupportedAdapter("promotion"),
    },
    produce_exclusive: async (context, job, strategy, produce) => {
      let resource: Readonly<ModelPipelineResource> | null;
      try {
        resource = await options.resolve_model_pipeline_resource(context, job, strategy);
      } catch {
        return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const });
      }
      if (resource === null) {
        return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const });
      }
      const outcome = await modelPipelineExclusivity.runExclusive(resource, produce);
      if (outcome.kind === "completed") return outcome.value;
      return Object.freeze({
        kind: "failed" as const,
        error_code: outcome.kind === "busy" ? "model_rate_limited" as const : "dependency_unavailable" as const,
      });
    },
    max_parent_rematerializations: options.max_parent_rematerializations,
    ...(options.observability ? { worker_observability: options.observability } : {}),
  });

  const dispatch = defineDerivedGroupDreamWorkDispatch({
    execution_repository: executionRepository,
    derived_group_dream: service,
  });

  return Object.freeze({
    [RUNTIME_PORT]: true as const,

    /**
     * Stage the exact sensitive input before accepting the immutable job, in
     * that order, so a crash between the two leaves an inert staged input
     * rather than an unbacked job.
     */
    async accept(
      context: AuthorizedLedgerWriteContext,
      request: DerivedGroupDreamOneShotAcceptRequest,
    ): Promise<DerivedGroupDreamOneShotAcceptOutcome> {
      const pending = acceptDurableMemoryWork(request.accepted_work);
      const manifest = derivedGroupDreamWorkInputManifest(request.snapshot);
      if (request.accepted_work.input_digest !== durableMemoryWorkInputManifestDigest(manifest)) {
        return halted("input", "input_manifest_mismatch");
      }
      const stageBody = Object.freeze({ pending_job: pending, snapshot: request.snapshot });
      let staged: Awaited<ReturnType<typeof inputRepository.stage>>;
      try {
        staged = await inputRepository.stage(context, {
          ...stageBody,
          request_digest: derivedGroupDreamWorkInputStageRequestDigest(stageBody),
        });
      } catch {
        return halted("input", "repository_unavailable");
      }
      if (staged.kind !== "staged" && staged.kind !== "replayed") {
        return halted("input", staged.kind);
      }
      const acceptanceRequest: DurableMemoryWorkAcceptanceRequest = {
        accepted_work: request.accepted_work,
        input_manifest: manifest,
        strategy_assignment: request.strategy_assignment,
        execution_policy: request.execution_policy,
        request_digest: durableMemoryWorkAcceptanceRequestDigest(
          pending, manifest, request.strategy_assignment, request.execution_policy,
        ),
      };
      let accepted: Awaited<ReturnType<typeof acceptanceRepository.accept>>;
      try {
        accepted = await acceptanceRepository.accept(context, acceptanceRequest);
      } catch {
        return halted("acceptance", "repository_unavailable");
      }
      if (accepted.kind !== "accepted" && accepted.kind !== "replayed") {
        return halted("acceptance", accepted.kind);
      }
      return Object.freeze({ kind: accepted.kind, job: accepted.job });
    },

    runNext: (context: AuthorizedLedgerWriteContext) => dispatch.runNext(context),

    recoverExpired: async (
      context: AuthorizedLedgerWriteContext,
      job_id: string,
    ): Promise<DurableMemoryWorkRecoveryOutcome> => {
      const loaded = await executionRepository.load(context, { job_id });
      if (loaded.kind !== "found") {
        if (loaded.kind === "not_found") return Object.freeze({ kind: "ineligible_state" as const });
        return loaded;
      }
      if (loaded.job.work_kind !== "derived_group_dream") {
        return Object.freeze({ kind: "ineligible_state" as const });
      }
      return executionRepository.recoverExpired(context, { job_id });
    },
  });
};
