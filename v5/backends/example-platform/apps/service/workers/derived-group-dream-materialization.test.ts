import { describe, expect, test } from "bun:test";

import {
  DERIVED_GROUP_DREAM_VERSION,
  derivedGroupDreamProjectionContractDigest,
  planDerivedGroupDream,
} from "../../../core/consolidate/derived-group-dream";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { CanonicalClaim } from "../../../core/schema";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import {
  DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
} from "./derived-group-dream-contract";
import {
  createDerivedGroupDreamAuthoritativeAppend,
} from "./derived-group-dream-materialization";
import {
  derivedGroupDreamWorkInputManifest,
  parseDerivedGroupDreamInputSnapshot,
} from "./derived-group-dream-work-adapter";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;
const owner = "account:alice";
const context = createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:one",
  account_id: owner, application_id: "app:dream", credential_id: "credential:one",
  credential_generation: 1, capability: "memories.work.execute", grant_id: "grant:one",
  grant_version: 1, account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const strategyCoordinates = Object.freeze({
  strategy_version: "derived-group-dream:v1",
  model_version: "none",
  prompt_version: "none",
  policy_version: "dream-policy:v1",
  code_version: "derived-group-dream:v1",
  schema_version: "derived-group-dream-response:v1",
  tokenizer_version: "none",
  tool_version: "none",
  result_contract_version: DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
  speaker_strategy_version: "none",
  boundary_strategy_version: "none",
});

const strategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:dream:materialization",
  work_kind: "derived_group_dream",
  coordinates: strategyCoordinates,
});

const snapshot = () => parseDerivedGroupDreamInputSnapshot({
  version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  owner_account_id: owner,
  job_id: "job:dream:materialization",
  input_frontier: digest("f"),
  projection_contract_digest: derivedGroupDreamProjectionContractDigest({
    strategy_version: strategyCoordinates.strategy_version,
    code_version: strategyCoordinates.code_version,
  }),
  original_claims: [
    {
      claim_revision_id: "claim:one:r1",
      proposition_id: "proposition:one",
      evidence_ref: ref("atevidence1", "a"),
    },
    {
      claim_revision_id: "claim:two:r1",
      proposition_id: "proposition:two",
      evidence_ref: ref("atevidence1", "b"),
    },
  ],
  group_memberships: [{
    group_key: "group:launch-week",
    proposition_ids: ["proposition:one", "proposition:two"],
  }],
  people_cluster_beliefs: [{
    cluster_about_ref: ref("about1", "a"),
    cluster_entity_target_ref: ref("attrtarget1", "a"),
    member_evidence_refs: [ref("atevidence1", "a"), ref("atevidence1", "b")],
    belief_contract_digest: digest("1"),
    aggregation_contract_digest: digest("2"),
    calibration_contract_digest: digest("3"),
  }],
  created_at_event_time: 1_700_000_000,
});

const leasedJob = () => leaseDurableMemoryWork(
  acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: snapshot().job_id,
    owner_account_id: owner,
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: "derived_group_dream",
    input_frontier: snapshot().input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(derivedGroupDreamWorkInputManifest(snapshot())),
    execution_contract_digest: strategy.execution_contract_digest,
    accepted_at_event_time: 100,
    max_attempts: 2,
  }),
  "worker:one",
  101,
  20,
);

const witnessClaim = (claimRevisionId: string, propositionId: string): CanonicalClaim => ({
  claim_lineage_id: `lineage:${claimRevisionId}`,
  claim_revision_id: claimRevisionId,
  owner_account_id: owner,
  predicate: "likes",
  arguments: [{
    slot_id: "subject", role: "subject", surface: "topic", span: { start: 0, end: 5 },
    value: { kind: "entity_ref", ref: "entity:one" },
  }],
  temporal_scope: {
    observed_at: "2026-08-11T20:00:00Z", precision: "instant",
    valid_time: {
      typed_expression: { kind: "absolute", granularity: "instant", value: "2026-08-11T20:00:00Z" },
      resolved_interval: {
        kind: "instant", start: "2026-08-11T20:00:00Z", end: "2026-08-11T20:00:00Z",
        timezone: "UTC", granularity: "instant",
      },
      derivation: { resolver_version: "fixture:v1", timezone: "UTC" },
    },
  },
  evidence_refs: [ref("atevidence1", "a")],
  policy_labels: [], source_language: "en",
  scope: { locality: "durable", scope_ref: "entity:one" },
  lifecycle: "canonical",
  canonical_claim_id: `canonical:${claimRevisionId}`,
  source_provisional_revision_ids: [`provisional:${claimRevisionId}`],
});

describe("derived group dream materialization", () => {
  test("binds witness claims and derived views without graph claim rewrites", () => {
    const input = {
      version: DERIVED_GROUP_DREAM_VERSION,
      owner_account_id: owner,
      input_frontier: snapshot().input_frontier,
      projection_contract_digest: snapshot().projection_contract_digest,
      original_claims: snapshot().original_claims,
      group_memberships: snapshot().group_memberships,
      people_cluster_beliefs: snapshot().people_cluster_beliefs,
      created_at_event_time: snapshot().created_at_event_time,
    };
    const outcome = planDerivedGroupDream(input);
    const witnesses = [
      { kind: "claim" as const, revision_id: "claim:one:r1", claim: witnessClaim("claim:one:r1", "proposition:one") },
      { kind: "claim" as const, revision_id: "claim:two:r1", claim: witnessClaim("claim:two:r1", "proposition:two") },
    ];
    const append = createDerivedGroupDreamAuthoritativeAppend(
      context, leasedJob(), strategy, outcome, witnesses, null,
    );
    expect(append.origin).toEqual({ kind: "non_formation", reason: "derived_group_dream" });
    expect(append.transition.revisions).toHaveLength(0);
    expect(append.transition.committed_revisions).toHaveLength(2);
    expect(append.transition.derivation.commit.success_kind).toBe("success");
    expect(append.transition.derivation.commit.output_revisions).toHaveLength(0);
  });
});
