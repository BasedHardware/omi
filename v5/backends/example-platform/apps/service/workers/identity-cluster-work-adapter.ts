import { isProxy } from "node:util/types";

import {
  parseAttributionBeliefRevision,
  type AttributionBeliefRevision,
} from "../../../core/consolidate/attribution-belief";
import {
  parseDerivedPeopleClusterBeliefInputs,
  planPeopleClusterBeliefs,
  type DerivedPeopleClusterBeliefInput,
} from "../../../core/consolidate/derived-group-dream";
import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkErrorCode,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { CanonicalJson } from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
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
  defineConsolidationWorkAdapter,
  type ConsolidationWorkAdapter,
} from "./consolidation-work-service";
import type {
  DurableMemoryWorkMaterializeOutcome,
  DurableMemoryWorkProduceOutcome,
} from "./durable-memory-work-runner";

export const IDENTITY_PEOPLE_CLUSTER_VERSION = "identity-people-cluster-v1" as const;
export const IDENTITY_PEOPLE_CLUSTER_INPUT_SNAPSHOT_VERSION =
  "identity-people-cluster-input-snapshot-v1" as const;
export const IDENTITY_PEOPLE_CLUSTER_RESULT_CONTRACT_VERSION =
  "identity-people-cluster-result:v1" as const;

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;

export interface IdentityPeopleClusterInputSnapshot {
  readonly version: typeof IDENTITY_PEOPLE_CLUSTER_INPUT_SNAPSHOT_VERSION;
  readonly owner_account_id: string;
  readonly job_id: string;
  readonly input_frontier: string;
  readonly people_cluster_beliefs: readonly DerivedPeopleClusterBeliefInput[];
  readonly created_at_event_time: number;
}

export interface IdentityPeopleClusterOutcome {
  readonly version: typeof IDENTITY_PEOPLE_CLUSTER_VERSION;
  readonly owner_account_id: string;
  readonly input_frontier: string;
  readonly people_cluster_beliefs: readonly AttributionBeliefRevision[];
  readonly result_digest: string;
}

export type IdentityPeopleClusterInputLoadOutcome =
  | Readonly<{ kind: "found"; snapshot: IdentityPeopleClusterInputSnapshot }>
  | Readonly<{ kind: "not_found" }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export interface IdentityPeopleClusterWorkAdapterDependencies {
  readonly load_input: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<IdentityPeopleClusterInputLoadOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`identity people cluster adapter ${code}`); };
const failed = (error_code: DurableMemoryWorkErrorCode): DurableMemoryWorkProduceOutcome =>
  Object.freeze({ kind: "failed" as const, error_code });

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) return fail(code);
  return value;
};

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail(code);
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactDependencies = (value: unknown): IdentityPeopleClusterWorkAdapterDependencies => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_dependencies");
  const keys = Reflect.ownKeys(value as object);
  if (keys.length !== 1 || keys[0] !== "load_input") fail("invalid_dependencies");
  const descriptor = Object.getOwnPropertyDescriptor(value, "load_input");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
    || typeof descriptor.value !== "function" || isProxy(descriptor.value)) fail("invalid_dependencies");
  return value as IdentityPeopleClusterWorkAdapterDependencies;
};

export const parseIdentityPeopleClusterInputSnapshot = (
  value: unknown,
): Readonly<IdentityPeopleClusterInputSnapshot> => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "job_id", "input_frontier",
    "people_cluster_beliefs", "created_at_event_time",
  ], "invalid_snapshot");
  if (input["version"] !== IDENTITY_PEOPLE_CLUSTER_INPUT_SNAPSHOT_VERSION) fail("invalid_snapshot");
  const createdAt = input["created_at_event_time"];
  if (!Number.isSafeInteger(createdAt) || (createdAt as number) < 0) fail("invalid_snapshot");
  return Object.freeze({
    version: IDENTITY_PEOPLE_CLUSTER_INPUT_SNAPSHOT_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_snapshot"),
    job_id: token(input["job_id"], "invalid_snapshot"),
    input_frontier: token(input["input_frontier"], "invalid_snapshot"),
    people_cluster_beliefs: parseDerivedPeopleClusterBeliefInputs(input["people_cluster_beliefs"]),
    created_at_event_time: createdAt as number,
  });
};

export const identityPeopleClusterWorkInputManifest = (
  snapshotValue: IdentityPeopleClusterInputSnapshot,
): readonly Readonly<DurableMemoryWorkInputManifestEntry>[] => {
  const snapshot = parseIdentityPeopleClusterInputSnapshot(snapshotValue);
  return Object.freeze([
    {
      input_kind: "graph_frontier" as const,
      input_ref: snapshot.input_frontier,
      input_digest: sha256CanonicalContent({
        contract_version: IDENTITY_PEOPLE_CLUSTER_INPUT_SNAPSHOT_VERSION,
        owner_account_id: snapshot.owner_account_id,
        job_id: snapshot.job_id,
        input_frontier: snapshot.input_frontier,
        people_cluster_count: snapshot.people_cluster_beliefs.length,
      }),
    },
  ]);
};

export const parseIdentityPeopleClusterOutcome = (
  value: unknown,
): Readonly<IdentityPeopleClusterOutcome> => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "input_frontier", "people_cluster_beliefs", "result_digest",
  ], "invalid_outcome");
  if (input["version"] !== IDENTITY_PEOPLE_CLUSTER_VERSION) fail("invalid_outcome");
  const beliefs = (Array.isArray(input["people_cluster_beliefs"])
    ? input["people_cluster_beliefs"] : fail("invalid_outcome"))
    .map((item) => parseAttributionBeliefRevision(item));
  if (beliefs.some((belief) => belief.hypotheses.some((hypothesis) => hypothesis.kind === "owner"))) {
    fail("owner_authority_forbidden");
  }
  const withoutDigest = {
    version: IDENTITY_PEOPLE_CLUSTER_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_outcome"),
    input_frontier: token(input["input_frontier"], "invalid_outcome"),
    people_cluster_beliefs: Object.freeze(beliefs),
  };
  const resultDigest = input["result_digest"];
  if (typeof resultDigest !== "string" || !DIGEST.test(resultDigest)) fail("invalid_outcome");
  if (sha256CanonicalContent({
    contract_version: IDENTITY_PEOPLE_CLUSTER_VERSION,
    ...withoutDigest,
  }) !== resultDigest) fail("invalid_outcome");
  return Object.freeze({ ...withoutDigest, result_digest: resultDigest as string });
};

const planOutcome = (
  snapshot: Readonly<IdentityPeopleClusterInputSnapshot>,
): Readonly<IdentityPeopleClusterOutcome> => {
  const peopleBeliefs = planPeopleClusterBeliefs({
    owner_account_id: snapshot.owner_account_id,
    input_frontier: snapshot.input_frontier,
    created_at_event_time: snapshot.created_at_event_time,
  }, snapshot.people_cluster_beliefs);
  const withoutDigest = {
    version: IDENTITY_PEOPLE_CLUSTER_VERSION,
    owner_account_id: snapshot.owner_account_id,
    input_frontier: snapshot.input_frontier,
    people_cluster_beliefs: peopleBeliefs,
  };
  return Object.freeze({
    ...withoutDigest,
    result_digest: sha256CanonicalContent({
      contract_version: IDENTITY_PEOPLE_CLUSTER_VERSION,
      ...withoutDigest,
    }),
  });
};

/**
 * Dark identity-cluster adapter. It plans probabilistic people beliefs only
 * and never mints owner identity authority, grants, or graph identity
 * revisions. Scheduler and activation remain separately gated.
 */
export const defineIdentityPeopleClusterConsolidationAdapter = (
  dependenciesValue: IdentityPeopleClusterWorkAdapterDependencies,
): ConsolidationWorkAdapter => {
  const dependencies = exactDependencies(dependenciesValue);
  return defineConsolidationWorkAdapter("identity_cluster", {
    async produce(contextValue, jobValue, strategyValue) {
      let context: AuthorizedLedgerWriteContext;
      let job: Readonly<DurableMemoryWorkJob>;
      let strategy: Readonly<RegisteredMemoryStrategy>;
      try {
        context = assertAuthorizedLedgerWriteContext(contextValue);
        job = parseDurableMemoryWorkJob(jobValue);
        strategy = parseRegisteredMemoryStrategy(strategyValue);
        if (context.capability !== "memories.work.execute" || context.account_id !== job.owner_account_id
          || context.account_epoch !== job.account_epoch || job.work_kind !== "identity_cluster"
          || job.state !== "leased" || strategy.work_kind !== "identity_cluster"
          || strategy.execution_contract_digest !== job.execution_contract_digest
          || strategy.coordinates.result_contract_version !== IDENTITY_PEOPLE_CLUSTER_RESULT_CONTRACT_VERSION) {
          return failed("dependency_unavailable");
        }
      } catch {
        return failed("dependency_unavailable");
      }
      let snapshot: Readonly<IdentityPeopleClusterInputSnapshot>;
      try {
        const loaded = await dependencies.load_input(context, job);
        if (loaded.kind !== "found") return failed("dependency_unavailable");
        snapshot = parseIdentityPeopleClusterInputSnapshot(loaded.snapshot);
        if (snapshot.owner_account_id !== job.owner_account_id || snapshot.job_id !== job.job_id
          || snapshot.input_frontier !== job.input_frontier
          || durableMemoryWorkInputManifestDigest(identityPeopleClusterWorkInputManifest(snapshot))
            !== job.input_digest) {
          return failed("dependency_unavailable");
        }
      } catch {
        return failed("dependency_unavailable");
      }
      try {
        const outcome = planOutcome(snapshot);
        return Object.freeze({
          kind: "produced" as const,
          result_contract_version: IDENTITY_PEOPLE_CLUSTER_RESULT_CONTRACT_VERSION,
          response_digest: outcome.result_digest,
          normalized_result: normalizeDurableMemoryWorkResultJson(outcome as unknown as CanonicalJson),
        });
      } catch {
        return failed("model_response_invalid");
      }
    },
    async materialize(contextValue, jobValue, stagedValue, strategyValue) {
      try {
        const context = assertAuthorizedLedgerWriteContext(contextValue);
        const job = parseDurableMemoryWorkJob(jobValue);
        const strategy = parseRegisteredMemoryStrategy(strategyValue);
        if (context.capability !== "memories.work.execute" || job.work_kind !== "identity_cluster"
          || strategy.work_kind !== "identity_cluster") {
          return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const });
        }
        parseIdentityPeopleClusterOutcome(stagedValue.normalized_result);
      } catch {
        return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" as const });
      }
      return Object.freeze({
        kind: "ready" as const,
        result_kind: "successful_empty" as const,
        authoritative_append: null,
      });
    },
  });
};
