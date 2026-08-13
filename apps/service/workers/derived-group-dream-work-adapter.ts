import { isProxy } from "node:util/types";

import {
  DERIVED_GROUP_DREAM_VERSION,
  parseDerivedGroupDreamInput,
  type DerivedGroupDreamClaimRef,
  type DerivedPeopleClusterBeliefInput,
} from "../../../core/consolidate/derived-group-dream";
import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkInputManifestEntry,
} from "../stores/durable-memory-work-repository";
import {
  DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
} from "./derived-group-dream-contract";

export interface DerivedGroupDreamInputSnapshot {
  readonly version: typeof DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION;
  readonly owner_account_id: string;
  readonly job_id: string;
  readonly input_frontier: string;
  readonly projection_contract_digest: string;
  readonly original_claims: readonly DerivedGroupDreamClaimRef[];
  readonly group_memberships: readonly {
    readonly group_key: string;
    readonly proposition_ids: readonly string[];
  }[];
  readonly people_cluster_beliefs: readonly DerivedPeopleClusterBeliefInput[];
  readonly created_at_event_time: number;
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;

const fail = (code: string): never => { throw new TypeError(`derived group dream adapter ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const sorted = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (sorted.length !== expected.length || sorted.some((key, index) => key !== expected[index])) fail(code);
  for (const key of sorted) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

export const parseDerivedGroupDreamInputSnapshot = (value: unknown): DerivedGroupDreamInputSnapshot => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "job_id", "input_frontier", "projection_contract_digest",
    "original_claims", "group_memberships", "people_cluster_beliefs", "created_at_event_time",
  ], "invalid_snapshot");
  if (input["version"] !== DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION) fail("invalid_snapshot");
  const dreamInput = parseDerivedGroupDreamInput({
    version: DERIVED_GROUP_DREAM_VERSION,
    owner_account_id: input["owner_account_id"],
    input_frontier: input["input_frontier"],
    projection_contract_digest: input["projection_contract_digest"],
    original_claims: input["original_claims"],
    group_memberships: input["group_memberships"],
    people_cluster_beliefs: input["people_cluster_beliefs"],
    created_at_event_time: input["created_at_event_time"],
  });
  const jobId = token(input["job_id"], "invalid_snapshot");
  return Object.freeze({
    version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
    owner_account_id: dreamInput.owner_account_id,
    job_id: jobId,
    input_frontier: dreamInput.input_frontier,
    projection_contract_digest: dreamInput.projection_contract_digest,
    original_claims: dreamInput.original_claims,
    group_memberships: dreamInput.group_memberships,
    people_cluster_beliefs: dreamInput.people_cluster_beliefs,
    created_at_event_time: dreamInput.created_at_event_time,
  });
};

export const derivedGroupDreamWorkInputManifest = (
  snapshotValue: DerivedGroupDreamInputSnapshot,
): readonly Readonly<DurableMemoryWorkInputManifestEntry>[] => {
  const snapshot = parseDerivedGroupDreamInputSnapshot(snapshotValue);
  return Object.freeze([
    {
      input_kind: "graph_frontier" as const,
      input_ref: snapshot.input_frontier,
      input_digest: sha256CanonicalContent({
        contract_version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
        owner_account_id: snapshot.owner_account_id,
        job_id: snapshot.job_id,
        input_frontier: snapshot.input_frontier,
        projection_contract_digest: snapshot.projection_contract_digest,
        original_claim_count: snapshot.original_claims.length,
        group_count: snapshot.group_memberships.length,
        people_cluster_count: snapshot.people_cluster_beliefs.length,
      }),
    },
    ...snapshot.original_claims.map((claim) => ({
      input_kind: "claim_revision" as const,
      input_ref: claim.claim_revision_id,
      input_digest: sha256CanonicalContent({
        contract_version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
        claim_revision_id: claim.claim_revision_id,
        proposition_id: claim.proposition_id,
        evidence_ref: claim.evidence_ref,
      }),
    })),
  ]);
};

export const assertDerivedGroupDreamInputSnapshotMatchesJob = (
  snapshot: Readonly<DerivedGroupDreamInputSnapshot>,
  job: Readonly<DurableMemoryWorkJob>,
): void => {
  const parsed = parseDerivedGroupDreamInputSnapshot(snapshot);
  if (parsed.owner_account_id !== job.owner_account_id || parsed.job_id !== job.job_id
    || parsed.input_frontier !== job.input_frontier
    || durableMemoryWorkInputManifestDigest(derivedGroupDreamWorkInputManifest(parsed)) !== job.input_digest) {
    fail("input_job_mismatch");
  }
};

export const derivedGroupDreamInputSnapshotDigest = (
  snapshotValue: DerivedGroupDreamInputSnapshot,
): string => sha256CanonicalContent({
  contract_version: "derived-group-dream-work-input-snapshot-digest-v1",
  snapshot: parseDerivedGroupDreamInputSnapshot(snapshotValue),
});

export const assertDerivedGroupDreamJob = (jobValue: unknown): DurableMemoryWorkJob => {
  const job = parseDurableMemoryWorkJob(jobValue);
  if (job.work_kind !== "derived_group_dream") fail("invalid_job");
  return job;
};
