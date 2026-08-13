import {
  DERIVED_GROUP_DREAM_VERSION,
  DERIVED_GROUP_DREAM_WORK_KIND,
  derivedGroupDreamProjectionContractDigest,
} from "../../../core/consolidate/derived-group-dream";

export const DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION =
  "derived-group-dream-input-snapshot-v1" as const;

/**
 * Future durable-work kind for belief-native derived-group dream. The slot is
 * named here for preregistration only; it is not admitted to the live
 * consolidation service, worker lease loop, or PostgreSQL acceptance tables.
 */
export const DERIVED_GROUP_DREAM_DURABLE_WORK_KIND = DERIVED_GROUP_DREAM_WORK_KIND;

export const derivedGroupDreamInputManifest = (input: Readonly<{
  owner_account_id: string;
  job_id: string;
  input_frontier: string;
  projection_contract_digest: string;
  original_claim_count: number;
  group_count: number;
  people_cluster_count: number;
}>): Readonly<Record<string, string | number>> => Object.freeze({
  contract_version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  dream_contract_version: DERIVED_GROUP_DREAM_VERSION,
  owner_account_id: input.owner_account_id,
  job_id: input.job_id,
  input_frontier: input.input_frontier,
  projection_contract_digest: input.projection_contract_digest,
  original_claim_count: input.original_claim_count,
  group_count: input.group_count,
  people_cluster_count: input.people_cluster_count,
});

export const derivedGroupDreamStrategyContractDigest = (
  coordinates: Readonly<{ strategy_version: string; code_version: string }>,
): string => derivedGroupDreamProjectionContractDigest(coordinates);
