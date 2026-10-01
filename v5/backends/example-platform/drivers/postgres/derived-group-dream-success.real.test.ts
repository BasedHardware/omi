import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { randomUUID } from "node:crypto";
import postgres, { type Sql } from "postgres";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  authoritativeAppendRequestDigest,
  type AuthoritativeLedgerAppend,
} from "../../apps/service/stores/authoritative-ledger-repository";
import {
  productProjectionWriteRequestDigest,
  type ProductProjectionWriteBody,
} from "../../apps/service/stores/product-projection-repository";
import {
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceRequest,
} from "../../apps/service/stores/durable-memory-work-repository";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  type DurableMemoryWorkResultStageBody,
} from "../../apps/service/stores/durable-memory-work-result-repository";
import {
  durableMemoryWorkSuccessRequestDigest,
  type DurableMemoryWorkSuccessBody,
} from "../../apps/service/stores/durable-memory-work-success-repository";
import {
  createDerivedGroupDreamAuthoritativeAppend,
} from "../../apps/service/workers/derived-group-dream-materialization";
import {
  DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
} from "../../apps/service/workers/derived-group-dream-contract";
import {
  derivedGroupDreamWorkInputManifest,
  parseDerivedGroupDreamInputSnapshot,
} from "../../apps/service/workers/derived-group-dream-work-adapter";
import {
  derivedGroupDreamWorkInputStageRequestDigest,
} from "../../apps/service/workers/derived-group-dream-work-input-repository";
import {
  DERIVED_GROUP_DREAM_VERSION,
  derivedGroupDreamProjectionContractDigest,
  planDerivedGroupDream,
  type DerivedGroupDreamInput,
} from "../../core/consolidate/derived-group-dream";
import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../core/consolidate/execution-policy";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  type AcceptedDurableMemoryWork,
} from "../../core/consolidate/state-machine";
import type { ProvisionalClaim } from "../../core/schema";
import { prepareDerivation, type AtomicGraphTransition, type CanonicalClaim, type GraphRevision } from "../../core/ledger";
import { birthProductProposition } from "../../core/retrieve/product-projection";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import { createPostgresAuthoritativeLedgerRepository } from "./authoritative-ledger-repository";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { createPostgresDerivedGroupDreamWorkInputRepository } from "./derived-group-dream-work-input";
import { createPostgresDurableMemoryWorkExecutionRepository } from "./durable-memory-work-execution";
import { createPostgresDurableMemoryWorkResultRepository } from "./durable-memory-work-result";
import { createPostgresDurableMemoryWorkSuccessRepository } from "./durable-memory-work-success";
import { createPostgresProductProjectionWriteRepository } from "./product-projection-repository";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";
import { runPostgresMigrations } from "./migrations/runner";
import { DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION } from "../../apps/service/workers/derived-group-dream-contract";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const explicitTestUrl = process.env["OMI_TEST_POSTGRES_URL"];
const realTest = explicitTestUrl ? describe : describe.skip;

const QUALIFICATION_DATABASE_GENERATION_DIGEST = "d".repeat(64);
const QUALIFICATION_RESTORE_RELEASE = Object.freeze({
  database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
  restore_release_revision: 1,
  restore_release_content_hash: "9".repeat(64),
});

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;

const dreamWitnessClaim = (
  accountId: string,
  claimRevisionId: string,
  evidenceRef: string,
): CanonicalClaim => ({
  claim_lineage_id: `lineage:${claimRevisionId}`,
  claim_revision_id: claimRevisionId,
  owner_account_id: accountId,
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
  evidence_refs: [evidenceRef],
  policy_labels: [], source_language: "en",
  scope: { locality: "durable", scope_ref: "entity:one" },
  lifecycle: "canonical",
  canonical_claim_id: `canonical:${claimRevisionId}`,
  source_provisional_revision_ids: [`provisional:${claimRevisionId}`],
});

const dreamProvisionalClaim = (
  accountId: string,
  claimRevisionId: string,
  evidenceRef: string,
  suffix: string,
): ProvisionalClaim => ({
  claim_lineage_id: `lineage:${claimRevisionId}`,
  claim_revision_id: claimRevisionId,
  owner_account_id: accountId,
  predicate: "likes",
  arguments: [{
    slot_id: "subject", role: "subject",
    value: { kind: "source_local_ref", ref: `speaker:${suffix}` },
  }],
  temporal_scope: {
    observed_at: "2026-08-11T20:00:00Z", precision: "instant",
    valid_time: {
      typed_expression: { kind: "absolute", granularity: "instant", value: "2026-08-11T20:00:00Z" },
      resolved_interval: {
        kind: "instant", start: "2026-08-11T20:00:00Z", end: "2026-08-11T20:00:00Z",
        timezone: "UTC", granularity: "instant",
      },
      derivation: { resolver_version: "qualification:v1", timezone: "UTC" },
    },
  },
  evidence_refs: [evidenceRef],
  policy_labels: [], source_language: "en",
  scope: { locality: "source_local", scope_ref: `speaker:${suffix}` },
  lifecycle: "provisional",
  ambiguity_markers: ["source_local"],
  context_packet: null,
});

const dreamSeedGraphAppend = (
  accountId: string,
  suffix: string,
): AuthoritativeLedgerAppend => {
  const evidenceA = ref("atevidence1", "a");
  const evidenceB = ref("atevidence1", "b");
  const eventRevisionId = `event:dream:${suffix}:r1`;
  const claimOne = dreamProvisionalClaim(accountId, "claim:one:r1", evidenceA, suffix);
  const claimTwo = dreamProvisionalClaim(accountId, "claim:two:r1", evidenceB, suffix);
  const revisions: AtomicGraphTransition["revisions"] = [
    {
      kind: "evidence",
      revision_id: `${evidenceA}:r1`,
      evidence: {
        evidence_id: evidenceA,
        event_revision_id: eventRevisionId,
        source_unit_ref: `unit:${suffix}`, range: { start: 0, end: 4 }, excerpt: "test",
        source_identity_ref: {
          namespace_instance_ref: `namespace:${suffix}`, local_key: `speaker:${suffix}`,
          producer: { producer_ref: null, contract_ref: null },
          asserted_identity: { domain: null, scope_ref: null },
        },
        speaker_rendering: null, source_local_mention_ref: null, state: "active" as const,
        source_trust: "owner_attested", policy_labels: [],
        source_independence_key: `root:${suffix}`,
      },
    },
    {
      kind: "evidence",
      revision_id: `${evidenceB}:r1`,
      evidence: {
        evidence_id: evidenceB,
        event_revision_id: eventRevisionId,
        source_unit_ref: `unit:${suffix}`, range: { start: 5, end: 9 }, excerpt: "more",
        source_identity_ref: {
          namespace_instance_ref: `namespace:${suffix}`, local_key: `speaker:${suffix}`,
          producer: { producer_ref: null, contract_ref: null },
          asserted_identity: { domain: null, scope_ref: null },
        },
        speaker_rendering: null, source_local_mention_ref: null, state: "active" as const,
        source_trust: "owner_attested", policy_labels: [],
        source_independence_key: `root:${suffix}`,
      },
    },
    {
      kind: "claim",
      revision_id: claimOne.claim_revision_id,
      claim: claimOne,
      placement_status: "provisional_abstained",
    },
    {
      kind: "claim",
      revision_id: claimTwo.claim_revision_id,
      claim: claimTwo,
      placement_status: "provisional_abstained",
    },
    {
      kind: "event",
      revision_id: eventRevisionId,
      event: {
        event_id: `event:dream:${suffix}`, event_revision_id: eventRevisionId,
        owner_account_id: accountId, capture_session_id: `session:${suffix}`,
        stream_id: `stream:${suffix}`, event_kind: "transcript",
        payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
        payload: { redacted: true }, event_time: "2026-08-11T20:00:00Z",
        ingest_time: null, source_sequence: 1,
        evidence_addressable_refs: [evidenceA, evidenceB], source_trust: "owner_attested",
        policy_labels: [], canonical_redacted_hash: digest("5"),
      },
    },
  ];
  const transition: AtomicGraphTransition = {
    placement: {
      offline_experiment: true,
      allocations: {},
      results: [
        {
          input_provisional_revision_id: claimOne.claim_revision_id,
          disposition: "defer_review",
          operation: null,
          re_resolution_trigger: "new_identity_evidence",
        },
        {
          input_provisional_revision_id: claimTwo.claim_revision_id,
          disposition: "defer_review",
          operation: null,
          re_resolution_trigger: "new_identity_evidence",
        },
      ],
    },
    derivation: prepareDerivation({
      attempt_id: `attempt:dream-seed:${suffix}`,
      commit_id: `commit:dream-seed:${suffix}`,
      owner_account_id: accountId,
      parent_commit: null,
      idempotency_key: `append:dream-seed:${suffix}`,
      input_revisions: [],
      output_revisions: revisions.map((revision) => ({
        revision_id: revision.revision_id,
        content: revision.kind === "event" ? revision.event
          : revision.kind === "evidence" ? revision.evidence
            : revision.kind === "claim" ? revision.claim : {},
      })),
      versions: {
        strategy_version: "qualification-graph-v1", model_version: "none",
        prompt_version: "none", policy_version: "qualification-v1",
        code_version: "qualification-v1", schema_version: "qualification-v1",
        tokenizer_version: "none", tool_version: "qualification-v1",
      },
      success_kind: "success",
    }),
    revisions,
    adjacency: [],
    artifacts: [
      {
        artifact_id: `artifact:dream:${suffix}:one`,
        kind: "abstention_set",
        provisional_revision_id: claimOne.claim_revision_id,
        canonical_claim_revision_id: null,
        margin: "low",
        risk_markers: ["low_margin"],
        unit_boundary_decision: "abstain",
        scope_locality: null,
      },
      {
        artifact_id: `artifact:dream:${suffix}:two`,
        kind: "abstention_set",
        provisional_revision_id: claimTwo.claim_revision_id,
        canonical_claim_revision_id: null,
        margin: "low",
        risk_markers: ["low_margin"],
        unit_boundary_decision: "abstain",
        scope_locality: null,
      },
    ],
  };
  const origin = { kind: "non_formation" as const, reason: "repair" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: null,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin,
    transition,
  };
};

const dreamWitnessRevisions = (
  accountId: string,
  suffix: string,
): readonly GraphRevision[] => Object.freeze([
  {
    kind: "claim" as const,
    revision_id: "claim:one:r1",
    claim: dreamProvisionalClaim(accountId, "claim:one:r1", ref("atevidence1", "a"), suffix),
  },
  {
    kind: "claim" as const,
    revision_id: "claim:two:r1",
    claim: dreamProvisionalClaim(accountId, "claim:two:r1", ref("atevidence1", "b"), suffix),
  },
]);

const dreamSnapshot = (accountId: string, jobId: string) => parseDerivedGroupDreamInputSnapshot({
  version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  owner_account_id: accountId,
  job_id: jobId,
  input_frontier: digest("f"),
  projection_contract_digest: derivedGroupDreamProjectionContractDigest({
    strategy_version: "derived-group-dream:v1",
    code_version: "derived-group-dream:v1",
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

const dreamStrategy = (suffix: string) => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: `strategy:dream-success:${suffix}`,
  work_kind: "derived_group_dream",
  coordinates: {
    strategy_version: "derived-group-dream:v1",
    model_version: "none",
    prompt_version: "none",
    policy_version: `dream-policy:${suffix}`,
    code_version: "derived-group-dream:v1",
    schema_version: "derived-group-dream-response:v1",
    tokenizer_version: "none",
    tool_version: "none",
    result_contract_version: DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
    speaker_strategy_version: "none",
    boundary_strategy_version: "none",
  },
});

const acceptanceRequest = (
  accountId: string,
  suffix: string,
  accountEpoch = 12,
  acceptedAt = 100,
): DurableMemoryWorkAcceptanceRequest => {
  const jobId = `job:dream:${suffix}`;
  const snapshot = dreamSnapshot(accountId, jobId);
  const strategy = dreamStrategy(suffix);
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: `policy:dream:${suffix}`,
    work_kind: "derived_group_dream",
    unit_kind: "account",
    key_version: "assignment-key:qualification:v1",
    authority_strategy_id: strategy.strategy_id,
    shadow_candidates: [],
  }, [strategy]);
  const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(31)).assign({
    owner_account_id: accountId,
    unit_ref: accountId,
    policy,
    strategies: [strategy],
  });
  const manifest = derivedGroupDreamWorkInputManifest(snapshot);
  const accepted: AcceptedDurableMemoryWork = {
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: jobId,
    owner_account_id: accountId,
    account_epoch: accountEpoch,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: "derived_group_dream",
    input_frontier: snapshot.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(manifest),
    execution_contract_digest: assignment.authority.execution_contract_digest,
    accepted_at_event_time: acceptedAt,
    max_attempts: 2,
  };
  const pending = acceptDurableMemoryWork(accepted);
  const executionPolicy = registerDurableMemoryWorkExecutionPolicy({
    version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
    policy_id: `execution-policy:dream:${suffix}`,
    work_kind: "derived_group_dream",
    execution_contract_digest: assignment.authority.execution_contract_digest,
    max_attempts: 2,
    lease_duration_seconds: 30,
    retry_delays_seconds: [1],
  });
  return Object.freeze({
    accepted_work: accepted,
    input_manifest: manifest,
    strategy_assignment: assignment,
    execution_policy: executionPolicy,
    request_digest: durableMemoryWorkAcceptanceRequestDigest(
      pending, manifest, assignment, executionPolicy,
    ),
  });
};

const productRequest = (
  body: ProductProjectionWriteBody,
): ProductProjectionWriteBody & { request_digest: string } => ({
  ...body,
  request_digest: productProjectionWriteRequestDigest(body),
});

realTest("derived group dream PostgreSQL success persistence", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(async () => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 2 });
    await ownerSql.unsafe(`
      DO $role$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_application') THEN
          CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_cleanup') THEN
          CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_restore') THEN
          CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_restore_operator') THEN
          CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
      END
      $role$
    `, [], { prepare: false });
    await runPostgresMigrations(ownerSql);
    await ownerSql.unsafe(`INSERT INTO omi_memory.postgres_restore_admission_revisions
        (database_generation_digest, release_revision, state, restore_id,
         restored_snapshot_digest, checkpoint_candidate_digest,
         checkpoint_evidence_digest, first_approval_subject_digest,
         first_approval_receipt_digest, second_approval_subject_digest,
         second_approval_receipt_digest, manual_release_receipt_digest,
         previous_release_revision, content_hash)
      VALUES ($1, 1, 'released', 'restore:derived-group-dream-success', $2, $3, $4,
              $5, $6, $7, $8, $9, NULL, $10)
      ON CONFLICT (database_generation_digest, release_revision) DO NOTHING
    `, [
      QUALIFICATION_DATABASE_GENERATION_DIGEST,
      digest("1"), digest("2"), digest("3"), digest("4"),
      digest("5"), digest("6"), digest("7"), digest("8"), digest("9"),
    ]);
    await ownerSql.unsafe(`INSERT INTO omi_memory.postgres_restore_admission_heads
        (database_generation_digest, release_revision)
      VALUES ($1, 1)
      ON CONFLICT (database_generation_digest) DO UPDATE
        SET release_revision = EXCLUDED.release_revision,
            updated_at = transaction_timestamp()`, [QUALIFICATION_DATABASE_GENERATION_DIGEST]);
  });

  afterAll(async () => {
    await pool?.close();
    await ownerSql?.end({ timeout: 5 });
  });

  test("atomically commits graph witness success with group projections and belief revisions", async () => {
    const suffix = randomUUID();
    const accountId = `account:dream-success:${suffix}`;
    const accountEpoch = 12;
    const principalId = `principal:dream-success:${suffix}`;
    const applicationId = "app:qualification";
    const credentialId = `credential:${suffix}`;
    const acceptGrantId = `grant:accept:${suffix}`;
    const executeGrantId = `grant:execute:${suffix}`;
    const writeGrantId = `grant:write:${suffix}`;
    const projectGrantId = `grant:project:${suffix}`;
    const controlHash = digest("1");
    const credentialHash = digest("2");
    const acceptGrantHash = digest("3");
    const executeGrantHash = digest("4");
    const writeGrantHash = digest("5");
    const projectGrantHash = digest("6");
    const now = Math.floor(Date.now() / 1_000);
    const acceptedAt = now - 5;

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)",
        [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', $2, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $3)`, [accountId, accountEpoch, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, $2, 17)`, [accountId, accountEpoch]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'service-workload',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountId, principalId, applicationId, credentialId, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountId, applicationId, credentialId]);
      for (const [capability, grantId, grantHash, grantVersion] of [
        ["memories.work.accept", acceptGrantId, acceptGrantHash, 9],
        ["memories.work.execute", executeGrantId, executeGrantHash, 1],
        ["memories.write", writeGrantId, writeGrantHash, 1],
        ["memories.project", projectGrantId, projectGrantHash, 1],
      ] as const) {
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version, lifecycle, enabled, scopes,
             record_schema_version, record_json, content_hash)
          VALUES ($1, $2, $3, 4, $4, $5, $6, 'active', true,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $7)`,
        [accountId, applicationId, credentialId, capability, grantId, grantVersion, grantHash]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version)
          VALUES ($1, $2, $3, 4, $4, $5, $6)`,
        [accountId, applicationId, credentialId, capability, grantId, grantVersion]);
      }
    });

    const baseAuthority = (capability: string, grantId: string, grantVersion: number, grantHash: string): AuthorityStateRow => ({
      account_id: accountId, principal_id: principalId, application_id: applicationId,
      credential_id: credentialId, credential_generation: 4,
      capability, grant_id: grantId, grant_version: grantVersion,
      account_epoch: accountEpoch, control_conflict_reason: null, control_conflict_at_revision: null,
      destination_activation_epoch: accountEpoch, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
      credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
      authentication_strength: "service-workload",
      credential_expires_at_epoch_seconds: now + 7_200, control_revision: 17,
      control_content_hash: controlHash, credential_content_hash: credentialHash,
      grant_content_hash: grantHash, db_now_epoch_seconds: now,
    });

    const issuer = createAuthorizedLedgerWriteContextIssuer();
    const issue = (
      capability: string,
      grantId: string,
      grantVersion: number,
      grantHash: string,
    ) => issuer.issueRestored({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalId,
      account_id: accountId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability,
      grant_id: grantId,
      grant_version: grantVersion,
      account_epoch: accountEpoch,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      authentication_strength: "service-workload",
      issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(
        baseAuthority(capability, grantId, grantVersion, grantHash),
        QUALIFICATION_RESTORE_RELEASE,
      ),
    }, QUALIFICATION_RESTORE_RELEASE, now);

    const acceptContext = issue("memories.work.accept", acceptGrantId, 9, acceptGrantHash);
    const executeContext = issue("memories.work.execute", executeGrantId, 1, executeGrantHash);
    const writeContext = issue("memories.write", writeGrantId, 1, writeGrantHash);
    const projectContext = issue("memories.project", projectGrantId, 1, projectGrantHash);

    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "dream.success.set_role",
          text: "SET LOCAL ROLE omi_platform_application",
          values: [],
        });
        return callback(connection);
      }),
    });

    const ledger = createPostgresAuthoritativeLedgerRepository({ pool: appRolePool });
    const seedAppend = dreamSeedGraphAppend(accountId, suffix);
    const seedOutcome = await ledger.append(writeContext, seedAppend);
    expect(seedOutcome).toMatchObject({ kind: "committed", sequence: 1 });
    if (seedOutcome.kind !== "committed") throw new Error("dream_seed_missing");
    const parentCommit = seedOutcome.commit_id;
    const graphFrontier = `frontier:dream:${suffix}`;
    const graphCoordinate = {
      owner_account_id: accountId,
      graph_frontier: graphFrontier,
      graph_commit_id: parentCommit,
      graph_commit_sequence: 1,
    };

    const projector = createPostgresProductProjectionWriteRepository({ pool: appRolePool });
    for (const [propositionId, claimRevisionId] of [
      ["proposition:one", "claim:one:r1"],
      ["proposition:two", "claim:two:r1"],
    ] as const) {
      const born = birthProductProposition({
        owner_account_id: accountId,
        proposition_id: propositionId,
        birth_claim_lineage_id: `lineage:${claimRevisionId}`,
        origin: "native",
        graph_frontier: graphFrontier,
        input_digest: digest("7"),
        result_digest: digest("8"),
        created_at_event_time: 10,
      });
      await expect(projector.append(projectContext, productRequest({
        operation: "birth",
        graph: graphCoordinate,
        identity: born.identity,
        membership: born.membership,
      }))).resolves.toEqual({ kind: "appended" });
    }

    const acceptanceRepository = createPostgresDurableMemoryWorkAcceptanceRepository({ pool: appRolePool });
    const inputRepository = createPostgresDerivedGroupDreamWorkInputRepository({ pool: appRolePool });
    const executionRepository = createPostgresDurableMemoryWorkExecutionRepository({ pool: appRolePool });
    const resultRepository = createPostgresDurableMemoryWorkResultRepository({ pool: appRolePool });
    const successRepository = createPostgresDurableMemoryWorkSuccessRepository({ pool: appRolePool });

    const request = acceptanceRequest(accountId, suffix, accountEpoch, acceptedAt);
    const pending = acceptDurableMemoryWork(request.accepted_work);
    const snapshot = dreamSnapshot(accountId, request.accepted_work.job_id);
    const stageBody = Object.freeze({ pending_job: pending, snapshot });
    await inputRepository.stage(acceptContext, {
      ...stageBody,
      request_digest: derivedGroupDreamWorkInputStageRequestDigest(stageBody),
    });
    await acceptanceRepository.accept(acceptContext, request);

    const lease = await executionRepository.leaseNext(executeContext, {
      work_kinds: ["derived_group_dream"],
    });
    expect(lease).toMatchObject({
      kind: "leased",
      job: { job_id: request.accepted_work.job_id, work_kind: "derived_group_dream" },
    });
    if (lease.kind !== "leased") throw new Error("dream_success_missing_lease");

    const dreamInput: DerivedGroupDreamInput = {
      version: DERIVED_GROUP_DREAM_VERSION,
      owner_account_id: accountId,
      input_frontier: snapshot.input_frontier,
      projection_contract_digest: snapshot.projection_contract_digest,
      original_claims: snapshot.original_claims,
      group_memberships: snapshot.group_memberships,
      people_cluster_beliefs: snapshot.people_cluster_beliefs,
      created_at_event_time: snapshot.created_at_event_time,
    };
    const outcome = planDerivedGroupDream(dreamInput);
    const normalizedResultDigest = durableMemoryWorkNormalizedResultDigest(
      DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
      outcome,
    );
    const stageResultBody: DurableMemoryWorkResultStageBody = {
      leased_job: lease.job,
      result_contract_version: DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
      response_digest: outcome.result_digest,
      normalized_result_digest: normalizedResultDigest,
      normalized_result: outcome,
    };
    const staged = await resultRepository.stage(executeContext, {
      ...stageResultBody,
      request_digest: durableMemoryWorkResultStageRequestDigest(stageResultBody),
    });
    expect(staged).toMatchObject({ kind: "staged" });
    if (staged.kind !== "staged") throw new Error("dream_success_missing_stage");
    const stagedResult = staged.result;
    const strategy = dreamStrategy(suffix);
    const witnesses = dreamWitnessRevisions(accountId, suffix);
    const dreamAppend = createDerivedGroupDreamAuthoritativeAppend(
      executeContext,
      lease.job,
      strategy,
      outcome,
      witnesses,
      parentCommit,
    );
    const successBody: DurableMemoryWorkSuccessBody = {
      leased_job: lease.job,
      result_kind: "successful",
      response_digest: stagedResult.response_digest,
      result_digest: dreamAppend.append_attempt.request_digest,
      staged_result: stagedResult,
      authoritative_append: dreamAppend,
    };
    const successRequest = {
      ...successBody,
      request_digest: durableMemoryWorkSuccessRequestDigest(successBody),
    };

    await expect(successRepository.commit(executeContext, successRequest)).resolves.toMatchObject({
      kind: "committed",
      job: { state: "succeeded" },
      sequence: 2,
    });
    await expect(successRepository.commit(executeContext, successRequest)).resolves.toMatchObject({
      kind: "replayed",
      job: { state: "succeeded" },
    });

    const persisted = await ownerSql.unsafe<{
      successes: number;
      success_outbox: number;
      graph_sequence: string;
      group_projections: number;
      group_members: number;
      belief_revisions: number;
      dream_commits: number;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1 AND job_id = $2) AS successes,
        (SELECT count(*)::int FROM omi_memory.memory_work_outbox_events
          WHERE account_id = $1 AND job_id = $2
            AND event_kind = 'memory_work_succeeded') AS success_outbox,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads
          WHERE account_id = $1) AS graph_sequence,
        (SELECT count(*)::int FROM omi_memory.memory_product_group_projections
          WHERE account_id = $1) AS group_projections,
        (SELECT count(*)::int FROM omi_memory.memory_product_group_members
          WHERE account_id = $1) AS group_members,
        (SELECT count(*)::int FROM omi_memory.memory_attribution_belief_revisions
          WHERE account_id = $1) AS belief_revisions,
        (SELECT count(*)::int FROM omi_memory.memory_derivation_commits
          WHERE account_id = $1 AND non_formation_reason = 'derived_group_dream') AS dream_commits
    `, [accountId, request.accepted_work.job_id]);
    expect([...persisted]).toEqual([{
      successes: 1,
      success_outbox: 1,
      graph_sequence: "2",
      group_projections: 1,
      group_members: 2,
      belief_revisions: 1,
      dream_commits: 1,
    }]);
  }, 60_000);
});
