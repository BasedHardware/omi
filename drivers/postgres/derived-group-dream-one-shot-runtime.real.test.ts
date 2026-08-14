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
  durableMemoryWorkInputManifestDigest,
} from "../../apps/service/stores/durable-memory-work-repository";
import {
  DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
} from "../../apps/service/workers/derived-group-dream-contract";
import {
  derivedGroupDreamWorkInputManifest,
  parseDerivedGroupDreamInputSnapshot,
} from "../../apps/service/workers/derived-group-dream-work-adapter";
import {
  defineModelPipelineExclusivity,
  MODEL_PIPELINE_RESOURCE_VERSION,
} from "../../apps/service/workers/model-pipeline-exclusivity";
import {
  bindModelPipelineResourceAdmission,
  defineModelPipelineResourceAdmission,
} from "../../apps/service/workers/model-pipeline-resource-admission";
import {
  derivedGroupDreamProjectionContractDigest,
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
  type AcceptedDurableMemoryWork,
} from "../../core/consolidate/state-machine";
import {
  attributionEvidenceFactorRef,
  attributionHypothesisId,
  buildAttributionBeliefRevision,
} from "../../core/consolidate/attribution-belief";
import {
  buildDerivedGroupRecallCandidates,
  derivedGroupRecallInputFrontierDigest,
  derivedGroupRecallProjectedContentDigest,
} from "../../core/retrieve/derived-group-recall-source";
import {
  identityExpressionLabelsForBeliefs,
} from "../../core/retrieve/identity-expression-label";
import {
  derivedGroupRecallKernelRequest,
} from "../../apps/service/composition/derived-group-recall";
import type { ProvisionalClaim } from "../../core/schema";
import { prepareDerivation, type AtomicGraphTransition } from "../../core/ledger";
import { birthProductProposition } from "../../core/retrieve/product-projection";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlStatement,
} from "./connection";
import { createPostgresAuthoritativeLedgerRepository } from "./authoritative-ledger-repository";
import { createPostgresProductProjectionWriteRepository } from "./product-projection-repository";
import { createPostgresDerivedGroupDreamOneShotRuntime } from "./derived-group-dream-one-shot-runtime";
import { createPostgresDerivedGroupRecallRead } from "./derived-group-recall-read";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";
import { runPostgresMigrations } from "./migrations/runner";
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
const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

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
      attempt_id: `attempt:dream-oneshot:${suffix}`,
      commit_id: `commit:dream-oneshot:${suffix}`,
      owner_account_id: accountId,
      parent_commit: null,
      idempotency_key: `append:dream-oneshot:${suffix}`,
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
  strategy_id: `strategy:dream-one-shot:${suffix}`,
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

const productRequest = (
  body: ProductProjectionWriteBody,
): ProductProjectionWriteBody & { request_digest: string } => ({
  ...body,
  request_digest: productProjectionWriteRequestDigest(body),
});

const resourceDigest = digest("b");
const exclusivity = bindModelPipelineResourceAdmission(
  defineModelPipelineExclusivity(async (_resource, callback) =>
    Object.freeze({ kind: "completed" as const, value: await callback(new AbortController().signal) })),
  defineModelPipelineResourceAdmission([{ resource_digest: resourceDigest, max_concurrency: 1 }]),
);
const resolveModelPipelineResource = async () => Object.freeze({
  version: MODEL_PIPELINE_RESOURCE_VERSION,
  resource_digest: resourceDigest,
});

realTest("derived group dream PostgreSQL one-shot runtime", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(async () => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 4 });
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
      VALUES ($1, 1, 'released', 'restore:derived-group-dream-one-shot', $2, $3, $4,
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

  /**
   * Seed one account with exactly the capabilities named, and return an issuer
   * for restored contexts bound to that account's authority state.
   */
  const seedAccount = async (
    accountId: string,
    principalId: string,
    accountEpoch: number,
    now: number,
    capabilities: readonly (readonly [string, string, number, string])[],
  ) => {
    const applicationId = "app:qualification";
    const credentialId = `credential:${principalId}`;
    const controlHash = digest("1");
    const credentialHash = digest("2");

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
      for (const [capability, grantId, grantVersion, grantHash] of capabilities) {
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

    const baseAuthority = (
      capability: string, grantId: string, grantVersion: number, grantHash: string,
    ): AuthorityStateRow => ({
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
    return (
      capability: string, grantId: string, grantVersion: number, grantHash: string,
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
  };

  test("accepts, survives a post-staging crash, and yields groups recall can read", async () => {
    const suffix = randomUUID();
    const accountId = `account:dream-one-shot:${suffix}`;
    const accountEpoch = 12;
    const principalId = `principal:dream-one-shot:${suffix}`;
    const now = Math.floor(Date.now() / 1_000);
    const acceptedAt = now - 5;

    const capabilities = [
      ["memories.work.accept", `grant:accept:${suffix}`, 9, digest("3")],
      ["memories.work.execute", `grant:execute:${suffix}`, 1, digest("4")],
      ["memories.write", `grant:write:${suffix}`, 1, digest("5")],
      ["memories.project", `grant:project:${suffix}`, 1, digest("6")],
      ["memories.read", `grant:read:${suffix}`, 1, digest("7")],
    ] as const;

    const issue = await seedAccount(
      accountId, principalId, accountEpoch, now, capabilities,
    );

    const [acceptCap, executeCap, writeCap, projectCap, readCap] = capabilities;
    const acceptContext = issue(...acceptCap);
    const executeContext = issue(...executeCap);
    const writeContext = issue(...writeCap);
    const projectContext = issue(...projectCap);
    const readContext = issue(...readCap);

    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "dream.one_shot.set_role",
          text: "SET LOCAL ROLE omi_platform_application",
          values: [],
        });
        return callback(connection);
      }),
    });

    /**
     * Injects a failure inside the success transaction, after the immutable
     * result has already been staged by an earlier transaction. Everything the
     * success transaction attempted rolls back with it.
     */
    const crashingPool = (failOn: string): PostgresTransactionPool => Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => appRolePool.withTransaction(options, async (connection) => {
        const wrapped: CheckedOutPostgresConnection = Object.freeze({
          connectionIdentity: connection.connectionIdentity,
          query: <Row extends Record<string, unknown>>(statement: SqlStatement) => {
            if (statement.name === failOn) {
              return Promise.reject(new Error("injected_success_commit_failure"));
            }
            return connection.query<Row>(statement);
          },
          execute: (statement: SqlStatement) => {
            if (statement.name === failOn) {
              return Promise.reject(new Error("injected_success_commit_failure"));
            }
            return connection.execute(statement);
          },
        });
        return callback(wrapped);
      }),
    });

    // --- seed an authoritative graph and the two product propositions ---
    const ledger = createPostgresAuthoritativeLedgerRepository({ pool: appRolePool });
    const seedAppend = dreamSeedGraphAppend(accountId, suffix);
    const seedOutcome = await ledger.append(writeContext, seedAppend);
    expect(seedOutcome).toMatchObject({ kind: "committed", sequence: 1 });
    if (seedOutcome.kind !== "committed") throw new Error("dream_seed_missing");
    const graphFrontier = `frontier:dream:${suffix}`;
    const graphCoordinate = {
      owner_account_id: accountId,
      graph_frontier: graphFrontier,
      graph_commit_id: seedOutcome.commit_id,
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

    // --- accept one dream job through the one-shot runtime ---
    const jobId = `job:dream-one-shot:${suffix}`;
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
    const acceptedWork: AcceptedDurableMemoryWork = {
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
    const executionPolicy = registerDurableMemoryWorkExecutionPolicy({
      version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
      policy_id: `execution-policy:dream:${suffix}`,
      work_kind: "derived_group_dream",
      execution_contract_digest: assignment.authority.execution_contract_digest,
      max_attempts: 2,
      lease_duration_seconds: 1,
      retry_delays_seconds: [1],
    });

    const runtimeOptions = {
      strategies: [strategy],
      model_pipeline_exclusivity: exclusivity,
      resolve_model_pipeline_resource: resolveModelPipelineResource,
      max_parent_rematerializations: 2,
    };
    const healthyRuntime = createPostgresDerivedGroupDreamOneShotRuntime({
      pool: appRolePool, ...runtimeOptions,
    });
    const crashingRuntime = createPostgresDerivedGroupDreamOneShotRuntime({
      pool: crashingPool("work.success.state_insert"), ...runtimeOptions,
    });

    const acceptRequest = {
      accepted_work: acceptedWork,
      snapshot,
      strategy_assignment: assignment,
      execution_policy: executionPolicy,
    };
    await expect(healthyRuntime.accept(acceptContext, acceptRequest)).resolves.toMatchObject({
      kind: "accepted",
      job: { job_id: jobId, work_kind: "derived_group_dream", state: "pending" },
    });
    // Accept is idempotent: re-presenting the same request replays it.
    await expect(healthyRuntime.accept(acceptContext, acceptRequest)).resolves.toMatchObject({
      kind: "replayed",
      job: { job_id: jobId },
    });

    // --- crash after result staging ---
    const crashed = await crashingRuntime.runNext(executeContext);
    // An infrastructure failure escapes the runner as a throw, so the dispatch
    // reports the stop without per-step counters. The durable evidence that the
    // producer did run is the staged result asserted immediately below.
    expect(crashed).toMatchObject({
      kind: "stopped", stop_code: "storage_retryable", leased: 1,
    });

    const afterCrash = await ownerSql.unsafe<{
      staged_results: number; successes: number; graph_sequence: string;
      group_projections: number; belief_revisions: number; state: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_staged_results
          WHERE account_id = $1 AND job_id = $2) AS staged_results,
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1 AND job_id = $2) AS successes,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads
          WHERE account_id = $1) AS graph_sequence,
        (SELECT count(*)::int FROM omi_memory.memory_product_group_projections
          WHERE account_id = $1) AS group_projections,
        (SELECT count(*)::int FROM omi_memory.memory_attribution_belief_revisions
          WHERE account_id = $1) AS belief_revisions,
        (SELECT s.state FROM omi_memory.memory_work_heads AS h
          JOIN omi_memory.memory_work_state_revisions AS s
            ON s.account_id = h.account_id AND s.job_id = h.job_id
           AND s.state_revision = h.state_revision
          WHERE h.account_id = $1 AND h.job_id = $2) AS state
    `, [accountId, jobId]);
    expect([...afterCrash]).toEqual([{
      staged_results: 1,
      successes: 0,
      graph_sequence: "1",
      group_projections: 0,
      belief_revisions: 0,
      state: "leased",
    }]);

    // --- explicit lease recovery, then one healthy execution ---
    await sleep(2_000);
    await expect(healthyRuntime.recoverExpired(executeContext, jobId)).resolves.toMatchObject({
      kind: "recovered",
    });
    await sleep(2_000);

    const recovered = await healthyRuntime.runNext(executeContext);
    expect(recovered).toMatchObject({
      kind: "completed",
      result: "succeeded",
      leased: 1,
      // The staged result is reused: recovery costs zero additional producer calls.
      producer_calls: 0,
    });

    const afterSuccess = await ownerSql.unsafe<{
      successes: number; success_outbox: number; graph_sequence: string;
      group_projections: number; group_members: number; belief_revisions: number;
      dream_commits: number; claim_revisions: number;
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
          WHERE account_id = $1 AND non_formation_reason = 'derived_group_dream') AS dream_commits,
        (SELECT count(*)::int FROM omi_memory.memory_claim_revisions
          WHERE account_id = $1) AS claim_revisions
    `, [accountId, jobId]);
    expect([...afterSuccess]).toEqual([{
      successes: 1,
      success_outbox: 1,
      graph_sequence: "2",
      group_projections: 1,
      group_members: 2,
      belief_revisions: 1,
      dream_commits: 1,
      // Dream never rewrites or deletes originals: both seeded claims survive.
      claim_revisions: 2,
    }]);

    // A second dispatch finds no eligible work rather than duplicating output.
    await expect(healthyRuntime.runNext(executeContext)).resolves.toMatchObject({ kind: "idle" });

    // --- consume: recall reads the groups this run actually persisted ---
    const recallRead = createPostgresDerivedGroupRecallRead({ pool: appRolePool });
    const loadedGroups = await recallRead.loadGroupProjections(readContext);
    expect(loadedGroups.kind).toBe("found");
    if (loadedGroups.kind !== "found") throw new Error("dream_groups_unreadable");
    expect(loadedGroups.groups).toHaveLength(1);
    const persistedGroup = loadedGroups.groups[0];
    if (!persistedGroup) throw new Error("dream_group_missing");
    expect(persistedGroup.proposition_ids).toEqual(["proposition:one", "proposition:two"]);
    expect(persistedGroup.input_frontier).toBe(snapshot.input_frontier);

    const loadedBeliefs = await recallRead.loadAttributionBeliefs(readContext);
    expect(loadedBeliefs.kind).toBe("found");
    if (loadedBeliefs.kind !== "found") throw new Error("dream_beliefs_unreadable");
    expect(loadedBeliefs.beliefs).toHaveLength(1);

    // Candidates are built from the persisted projection, not a hand-built fixture.
    const members = loadedGroups.groups.map((group) => Object.freeze({
      group,
      rendered_text: group.proposition_ids.join(" and "),
    }));
    const candidates = buildDerivedGroupRecallCandidates(members);
    expect(candidates).toHaveLength(1);
    expect(candidates[0]?.contributing_subject_classes).toEqual(["derived_group"]);
    expect(candidates[0]?.group_projection_id).toBe(persistedGroup.group_projection_id);
    expect(candidates[0]?.trace_ref).toMatch(/^tr1_[a-f0-9]{64}$/);

    /**
     * The kernel request binds the persisted content and frontier digests.
     * Asserting only the hex shape would pass for a digest of anything, so
     * recompute both from the persisted members and require equality.
     */
    const kernelRequest = derivedGroupRecallKernelRequest({
      question_text: "What happened during launch week?",
      authorization_state_digest: digest("a"),
      reader_projection_digest: digest("c"),
      members,
    });
    expect(kernelRequest.projected_content_digest)
      .toBe(derivedGroupRecallProjectedContentDigest(members));
    expect(kernelRequest.input_frontier_digest)
      .toBe(derivedGroupRecallInputFrontierDigest(members));
    // A different group set must not produce the same content digest.
    expect(derivedGroupRecallProjectedContentDigest([{
      ...members[0]!, rendered_text: "something else entirely",
    }])).not.toBe(kernelRequest.projected_content_digest);

    // Identity-expression labels come from the beliefs this same run persisted.
    const labels = identityExpressionLabelsForBeliefs([...loadedBeliefs.beliefs]);
    expect(labels).toHaveLength(1);
    /**
     * `not.toBe("certain_owner")` alone would be tautological — the emitter has
     * no path that produces it. Assert the substantive facts instead: the label
     * is exactly the one this belief's owner mass earns, and it is bound to the
     * about_ref that was persisted.
     */
    expect(labels[0]?.label).toBe("source_local");
    expect(labels[0]?.owner_probability_micros).toBe(0);
    expect(labels[0]?.about_ref).toBe(loadedBeliefs.beliefs[0]?.about_ref);
    // The dark HTTP/MCP doors stay unmounted; that is asserted without a
    // database in `apps/service/memory-service-app.test.ts`.

    // --- the read seam does not widen an account boundary ---
    const otherSuffix = randomUUID();
    const otherAccountId = `account:dream-bystander:${otherSuffix}`;
    const otherCapabilities = [
      ["memories.read", `grant:read:${otherSuffix}`, 1, digest("7")],
    ] as const;
    const issueOther = await seedAccount(
      otherAccountId, `principal:dream-bystander:${otherSuffix}`,
      accountEpoch, now, otherCapabilities,
    );
    const otherRead = await recallRead.loadGroupProjections(issueOther(...otherCapabilities[0]));
    expect(otherRead).toEqual({ kind: "found", groups: [] });
    const otherBeliefs = await recallRead.loadAttributionBeliefs(issueOther(...otherCapabilities[0]));
    expect(otherBeliefs).toEqual({ kind: "found", beliefs: [] });

    /**
     * `expect(query).rejects` never settles against a postgres.js lazy `Query`,
     * so denial is asserted by driving the call to completion here.
     */
    const denied = async (run: () => Promise<unknown>): Promise<boolean> => {
      try {
        await run();
        return false;
      } catch {
        return true;
      }
    };

    // A capability other than memories.read cannot reach the read functions,
    // even though its own authority fence admits it.
    expect(await denied(() => recallRead.loadGroupProjections(executeContext))).toBe(true);
    expect(await denied(() => recallRead.loadAttributionBeliefs(executeContext))).toBe(true);

    // Without any omi.* authority context the definer functions refuse outright,
    // so no ambient superuser session can read an account's groups.
    expect(await denied(() => ownerSql.unsafe(
      "SELECT * FROM omi_memory.read_derived_group_projections($1)", [accountId],
    ))).toBe(true);
    expect(await denied(() => ownerSql.unsafe(
      "SELECT * FROM omi_memory.read_attribution_belief_revisions($1, $2)", [accountId, 8],
    ))).toBe(true);

    // A valid memories.read context may not name a DIFFERENT account. The
    // repository always passes its own authority, so this branch is only
    // reachable by calling the definer function directly.
    expect(await denied(() => pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        await connection.query({
          name: "dream.one_shot.foreign_read.set_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        await connection.query({
          name: "dream.one_shot.foreign_read.context",
          text: `SELECT set_config('omi.account_id', $1, true),
                        set_config('omi.principal_id', $2, true),
                        set_config('omi.capability', 'memories.read', true)`,
          values: [otherAccountId, `principal:dream-bystander:${otherSuffix}`],
        });
        return connection.query({
          name: "dream.one_shot.foreign_read",
          text: "SELECT * FROM omi_memory.read_derived_group_projections($1, $2)",
          values: [accountId, 8],
        });
      },
    ))).toBe(true);

    /**
     * The module's headline property: a persisted row that no longer rebuilds
     * to the identifier it was stored under must fail closed rather than
     * answer. Tamper each covered surface in turn and require rejection, then
     * restore. Without this the fail-closed claim is an assertion, not
     * evidence.
     */
    const tamper = async (sql: string, values: readonly unknown[]): Promise<void> => {
      await ownerSql.unsafe(sql, [...values] as never[]);
    };

    // 1. A field that feeds the content-addressed group id.
    await tamper(`UPDATE omi_memory.memory_product_group_projections
      SET input_frontier = 'tampered' WHERE account_id = $1`, [accountId]);
    expect(await denied(() => recallRead.loadGroupProjections(readContext))).toBe(true);
    await tamper(`UPDATE omi_memory.memory_product_group_projections
      SET input_frontier = $2 WHERE account_id = $1`, [accountId, snapshot.input_frontier]);
    expect((await recallRead.loadGroupProjections(readContext)).kind).toBe("found");

    // 2. Membership: dropping a member changes the id the group rebuilds to.
    await tamper(`DELETE FROM omi_memory.memory_product_group_members
      WHERE account_id = $1 AND member_ordinal = 1`, [accountId]);
    expect(await denied(() => recallRead.loadGroupProjections(readContext))).toBe(true);
    await tamper(`INSERT INTO omi_memory.memory_product_group_members
        (account_id, group_projection_id, member_ordinal, proposition_id)
      VALUES ($1, $2, 1, 'proposition:two')`,
    [accountId, persistedGroup.group_projection_id]);
    expect((await recallRead.loadGroupProjections(readContext)).kind).toBe("found");

    /**
     * 3. A belief that is INTERNALLY CONSISTENT but owned by another account,
     * filed under this one. Editing `owner_account_id` in place would be caught
     * by the content-addressed revision id long before the owner check — that
     * would be a tautological test. So mint a genuinely valid belief for the
     * bystander account and store it under this account's row, leaving the
     * column/payload owner disagreement as the only defect.
     */
    const persistedBelief = loadedBeliefs.beliefs[0];
    if (!persistedBelief) throw new Error("dream_belief_missing");
    // Hypothesis ids and factor refs are owner-derived, so remap them onto the
    // bystander owner or the builder rejects its own input.
    const foreignHypothesisId = new Map(persistedBelief.hypotheses.map((hypothesis) => [
      hypothesis.hypothesis_id,
      attributionHypothesisId({
        owner_account_id: otherAccountId,
        belief_kind: persistedBelief.belief_kind,
        about_ref: persistedBelief.about_ref,
        kind: hypothesis.kind,
        target_ref: hypothesis.target_ref,
      }),
    ]));
    const foreignFactors = persistedBelief.evidence_factors.map((factor) => {
      const core = {
        evidence_ref: factor.evidence_ref,
        independence_group_ref: factor.independence_group_ref,
        hypothesis_id: foreignHypothesisId.get(factor.hypothesis_id) ?? factor.hypothesis_id,
        direction: factor.direction,
        factor_contract_digest: factor.factor_contract_digest,
      };
      return { factor_ref: attributionEvidenceFactorRef(core), ...core };
    }).sort((left, right) => left.factor_ref < right.factor_ref ? -1
      : left.factor_ref > right.factor_ref ? 1 : 0);

    const foreignBelief = buildAttributionBeliefRevision({
      owner_account_id: otherAccountId,
      belief_kind: persistedBelief.belief_kind,
      about_ref: persistedBelief.about_ref,
      observation_ref: persistedBelief.observation_ref,
      observation_content_digest: persistedBelief.observation_content_digest,
      graph_frontier: persistedBelief.graph_frontier,
      hypotheses: persistedBelief.hypotheses.map(({ hypothesis_id: _id, ...rest }) => rest),
      evidence_factors: foreignFactors,
      attribution_contract_digest: persistedBelief.attribution_contract_digest,
      aggregation_contract_digest: persistedBelief.aggregation_contract_digest,
      calibration_contract_digest: persistedBelief.calibration_contract_digest,
      created_at_event_time: persistedBelief.created_at_event_time,
      previous_revision: null,
    });
    expect(foreignBelief.owner_account_id).toBe(otherAccountId);
    await tamper(`UPDATE omi_memory.memory_attribution_belief_revisions
      SET revision_json = ($2::text)::jsonb,
          belief_revision_id = $3,
          belief_lineage_id = $4
      WHERE account_id = $1`,
    [accountId, JSON.stringify(foreignBelief),
      foreignBelief.belief_revision_id, foreignBelief.belief_lineage_id]);
    expect(await denied(() => recallRead.loadAttributionBeliefs(readContext))).toBe(true);
  }, 180_000);
});
