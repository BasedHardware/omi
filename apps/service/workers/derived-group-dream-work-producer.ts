import { isProxy } from "node:util/types";

import {
  DERIVED_GROUP_DREAM_VERSION,
  derivedGroupDreamProjectionContractDigest,
  planDerivedGroupDream,
  type DerivedGroupDreamInput,
} from "../../../core/consolidate/derived-group-dream";
import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import { assertAuthorizedLedgerWriteContext } from "../auth/authorized-context";
import { normalizeDurableMemoryWorkResultJson, type StagedDurableMemoryWorkResult } from "../stores/durable-memory-work-result-repository";
import {
  DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
} from "./derived-group-dream-contract";
import {
  assertDerivedGroupDreamInputSnapshotMatchesJob,
  parseDerivedGroupDreamInputSnapshot,
  type DerivedGroupDreamInputSnapshot,
} from "./derived-group-dream-work-adapter";
import type { DerivedGroupDreamWorkInputLoadOutcome } from "./derived-group-dream-work-input-repository";
import type {
  DurableMemoryWorkMaterializeOutcome,
  DurableMemoryWorkProduceOutcome,
} from "./durable-memory-work-runner";

export interface DerivedGroupDreamWorkAdapterDependencies {
  readonly load_input: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<DerivedGroupDreamWorkInputLoadOutcome>;
}

export interface DerivedGroupDreamWorkAdapter {
  produce(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ): Promise<DurableMemoryWorkProduceOutcome>;
  materialize(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    staged: StagedDurableMemoryWorkResult,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ): Promise<DurableMemoryWorkMaterializeOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`derived group dream work producer ${code}`); };

const failed = (error_code: "dependency_unavailable" | "model_response_invalid"):
DurableMemoryWorkProduceOutcome => Object.freeze({ kind: "failed", error_code });

const exactDependencies = (value: unknown): DerivedGroupDreamWorkAdapterDependencies => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_dependencies");
  const keys = Reflect.ownKeys(value);
  if (keys.length !== 1 || keys[0] !== "load_input") fail("invalid_dependencies");
  const descriptor = Object.getOwnPropertyDescriptor(value, "load_input");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
    || typeof descriptor.value !== "function" || isProxy(descriptor.value)) fail("invalid_dependencies");
  return value as DerivedGroupDreamWorkAdapterDependencies;
};

const dreamInputFromSnapshot = (
  snapshot: Readonly<DerivedGroupDreamInputSnapshot>,
): DerivedGroupDreamInput => Object.freeze({
  version: DERIVED_GROUP_DREAM_VERSION,
  owner_account_id: snapshot.owner_account_id,
  input_frontier: snapshot.input_frontier,
  projection_contract_digest: snapshot.projection_contract_digest,
  original_claims: snapshot.original_claims,
  group_memberships: snapshot.group_memberships,
  people_cluster_beliefs: snapshot.people_cluster_beliefs,
  created_at_event_time: snapshot.created_at_event_time,
});

const assertDreamSnapshot = (
  snapshot: Readonly<DerivedGroupDreamInputSnapshot>,
  job: Readonly<DurableMemoryWorkJob>,
  strategy: Readonly<RegisteredMemoryStrategy>,
): DerivedGroupDreamInput => {
  assertDerivedGroupDreamInputSnapshotMatchesJob(snapshot, job);
  const expectedDigest = derivedGroupDreamProjectionContractDigest({
    strategy_version: strategy.coordinates.strategy_version,
    code_version: strategy.coordinates.code_version,
  });
  if (snapshot.projection_contract_digest !== expectedDigest) fail("invalid_projection_contract");
  return dreamInputFromSnapshot(snapshot);
};

const mapLoadFailure = (loaded: DerivedGroupDreamWorkInputLoadOutcome): DurableMemoryWorkProduceOutcome => {
  if (loaded.kind === "found") return fail("unexpected_found");
  return failed("dependency_unavailable");
};

/**
 * Inert derived-group dream work adapter. It loads the sealed PostgreSQL input
 * snapshot under a leased job and runs the pure planner only. Success commit,
 * model defaults, scheduler wiring, and route activation remain separately gated.
 */
export const defineDerivedGroupDreamWorkAdapter = (
  dependenciesValue: DerivedGroupDreamWorkAdapterDependencies,
): DerivedGroupDreamWorkAdapter => {
  const dependencies = exactDependencies(dependenciesValue);
  return Object.freeze({
    async produce(
      contextValue: AuthorizedLedgerWriteContext,
      jobValue: Readonly<DurableMemoryWorkJob>,
      strategyValue: Readonly<RegisteredMemoryStrategy>,
    ) {
      let context: AuthorizedLedgerWriteContext;
      let job: Readonly<DurableMemoryWorkJob>;
      let strategy: Readonly<RegisteredMemoryStrategy>;
      try {
        context = assertAuthorizedLedgerWriteContext(contextValue);
        job = parseDurableMemoryWorkJob(jobValue);
        strategy = parseRegisteredMemoryStrategy(strategyValue);
        if (context.capability !== "memories.work.execute" || context.account_id !== job.owner_account_id
          || context.account_epoch !== job.account_epoch || job.work_kind !== "derived_group_dream"
          || job.state !== "leased" || strategy.work_kind !== "derived_group_dream"
          || strategy.execution_contract_digest !== job.execution_contract_digest
          || strategy.coordinates.result_contract_version !== DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION) {
          return failed("dependency_unavailable");
        }
      } catch {
        return failed("dependency_unavailable");
      }
      let snapshot: Readonly<DerivedGroupDreamInputSnapshot>;
      try {
        const loaded = await dependencies.load_input(context, job);
        if (loaded.kind !== "found") return mapLoadFailure(loaded);
        snapshot = parseDerivedGroupDreamInputSnapshot(loaded.snapshot);
      } catch {
        return failed("dependency_unavailable");
      }
      try {
        const dreamInput = assertDreamSnapshot(snapshot, job, strategy);
        const outcome = planDerivedGroupDream(dreamInput);
        return Object.freeze({
          kind: "produced" as const,
          result_contract_version: DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
          response_digest: outcome.result_digest,
          normalized_result: normalizeDurableMemoryWorkResultJson(outcome),
        });
      } catch {
        return failed("model_response_invalid");
      }
    },

    async materialize() {
      return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" });
    },
  });
};
