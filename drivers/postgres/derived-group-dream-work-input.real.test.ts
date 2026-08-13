import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { randomUUID } from "node:crypto";
import postgres, { type Sql } from "postgres";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceRequest,
} from "../../apps/service/stores/durable-memory-work-repository";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../core/consolidate/execution-policy";
import {
  derivedGroupDreamProjectionContractDigest,
} from "../../core/consolidate/derived-group-dream";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  type AcceptedDurableMemoryWork,
} from "../../core/consolidate/state-machine";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { createPostgresDerivedGroupDreamWorkInputRepository } from "./derived-group-dream-work-input";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";
import { runPostgresMigrations } from "./migrations/runner";
import { DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION } from "../../apps/service/workers/derived-group-dream-contract";
import {
  derivedGroupDreamWorkInputManifest,
  parseDerivedGroupDreamInputSnapshot,
} from "../../apps/service/workers/derived-group-dream-work-adapter";
import {
  derivedGroupDreamWorkInputStageRequestDigest,
} from "../../apps/service/workers/derived-group-dream-work-input-repository";
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

const dreamSnapshot = (accountId: string, jobId: string) => parseDerivedGroupDreamInputSnapshot({
  version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  owner_account_id: accountId,
  job_id: jobId,
  input_frontier: digest("f"),
  projection_contract_digest: derivedGroupDreamProjectionContractDigest({
    strategy_version: "dream:v1",
    code_version: "code:v1",
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

const acceptanceRequest = (
  accountId: string,
  suffix: string,
  accountEpoch = 12,
  acceptedAt = 100,
): DurableMemoryWorkAcceptanceRequest => {
  const jobId = `job:dream:${suffix}`;
  const snapshot = dreamSnapshot(accountId, jobId);
  const strategy = registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: `strategy:dream:${suffix}`,
    work_kind: "derived_group_dream",
    coordinates: {
      strategy_version: "derived-group-dream:v1",
      model_version: "none",
      prompt_version: "none",
      policy_version: "dream-policy:v1",
      code_version: "derived-group-dream:v1",
      schema_version: "derived-group-dream-response:v1",
      tokenizer_version: "none",
      tool_version: "none",
      result_contract_version: "derived-group-dream-result:v1",
      speaker_strategy_version: "none",
      boundary_strategy_version: "none",
    },
  });
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

realTest("derived group dream PostgreSQL input persistence", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(async () => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
    await ownerSql.unsafe(`
      DO $role$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_application') THEN
          CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
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
      VALUES ($1, 1, 'released', 'restore:derived-group-dream-input', $2, $3, $4,
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

  test("rejects acceptance without staged input and accepts once after staging", async () => {
    const suffix = randomUUID();
    const accountId = `account:dream-input:${suffix}`;
    const accountEpoch = 12;
    const principalId = `principal:dream:${suffix}`;
    const applicationId = "app:qualification";
    const credentialId = `credential:${suffix}`;
    const grantId = `grant:${suffix}`;
    const controlHash = digest("1");
    const credentialHash = digest("2");
    const grantHash = digest("3");
    const now = Math.floor(Date.now() / 1_000);

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
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.work.accept', $4, 9, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, grantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.work.accept', $4, 9)`,
      [accountId, applicationId, credentialId, grantId]);
    });

    const authority: AuthorityStateRow = {
      account_id: accountId, principal_id: principalId, application_id: applicationId,
      credential_id: credentialId, credential_generation: 4,
      capability: "memories.work.accept", grant_id: grantId, grant_version: 9,
      account_epoch: accountEpoch, control_conflict_reason: null, control_conflict_at_revision: null,
      destination_activation_epoch: accountEpoch, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
      credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
      authentication_strength: "service-workload",
      credential_expires_at_epoch_seconds: now + 7_200, control_revision: 17,
      control_content_hash: controlHash, credential_content_hash: credentialHash,
      grant_content_hash: grantHash, db_now_epoch_seconds: now,
    };
    const context = createAuthorizedLedgerWriteContextIssuer().issueRestored({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalId,
      account_id: accountId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "memories.work.accept",
      grant_id: grantId,
      grant_version: 9,
      account_epoch: accountEpoch,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      authentication_strength: "service-workload",
      issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(authority, QUALIFICATION_RESTORE_RELEASE),
    }, QUALIFICATION_RESTORE_RELEASE, now);

    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "dream.input.set_role",
          text: "SET LOCAL ROLE omi_platform_application",
          values: [],
        });
        return callback(connection);
      }),
    });

    const acceptanceRepository = createPostgresDurableMemoryWorkAcceptanceRepository({ pool: appRolePool });
    const inputRepository = createPostgresDerivedGroupDreamWorkInputRepository({ pool: appRolePool });
    const request = acceptanceRequest(accountId, suffix, accountEpoch, now - 5);
    const pending = acceptDurableMemoryWork(request.accepted_work);
    const snapshot = dreamSnapshot(accountId, request.accepted_work.job_id);

    await expect(acceptanceRepository.accept(context, request)).rejects.toMatchObject({
      code: "persistence_failed",
    });

    const stageBody = Object.freeze({ pending_job: pending, snapshot });
    await expect(inputRepository.stage(context, {
      ...stageBody,
      request_digest: derivedGroupDreamWorkInputStageRequestDigest(stageBody),
    })).resolves.toMatchObject({ kind: "staged", input: { job_id: request.accepted_work.job_id } });

    await expect(acceptanceRepository.accept(context, request)).resolves.toMatchObject({
      kind: "accepted",
      job: { job_id: request.accepted_work.job_id, work_kind: "derived_group_dream", state: "pending" },
    });

    const counts = await ownerSql.unsafe<{
      staged_inputs: number; acceptances: number; manifest_rows: number;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_derived_group_dream_work_inputs
          WHERE account_id = $1 AND job_id = $2) AS staged_inputs,
        (SELECT count(*)::int FROM omi_memory.memory_work_acceptances
          WHERE account_id = $1 AND job_id = $2) AS acceptances,
        (SELECT count(*)::int FROM omi_memory.memory_work_input_manifest
          WHERE account_id = $1 AND job_id = $2) AS manifest_rows
    `, [accountId, request.accepted_work.job_id]);
    expect([...counts]).toEqual([{ staged_inputs: 1, acceptances: 1, manifest_rows: 3 }]);

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.memory_derived_group_dream_work_inputs WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 60_000);
});
