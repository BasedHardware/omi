import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { randomUUID } from "node:crypto";
import postgres, { type Sql } from "postgres";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import { authoritativeAppendRequestDigest, type AuthoritativeLedgerAppend } from "../../apps/service/stores/authoritative-ledger-repository";
import { formationCandidateManifestDigest } from "../../core/consolidate/formation-outcome";
import { prepareDerivation, type AtomicGraphTransition } from "../../core/ledger";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { IdentityAuthorization, IdentityConstraint, ProvisionalClaim } from "../../core/schema";
import {
  createPostgresAuthoritativeLedgerRepository,
  createPostgresSuccessfulEmptyLedgerRepository,
} from "./authoritative-ledger-repository";
import { createPostgresAuthoritativeGraphSnapshotRepository } from "./authoritative-graph-snapshot";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlStatement } from "./connection";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";
import { SqliteLedger } from "../sqlite";

const explicitTestUrl = process.env["OMI_TEST_POSTGRES_URL"];
const realTest = explicitTestUrl ? describe : describe.skip;

const nonemptyAppend = (
  accountId: string,
  suffix: string,
  parentCommit: string,
): AuthoritativeLedgerAppend => {
  const event = {
    event_id: `event:${suffix}`, event_revision_id: `event:${suffix}:r1`,
    owner_account_id: accountId, capture_session_id: `session:${suffix}`,
    stream_id: `stream:${suffix}`, event_kind: "transcript",
    payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
    payload: { redacted: true }, event_time: "2026-08-11T20:00:00Z",
    ingest_time: null, source_sequence: 1,
    evidence_addressable_refs: [`evidence:${suffix}`], source_trust: "owner_attested",
    policy_labels: [], canonical_redacted_hash: "5".repeat(64),
  };
  const evidence = {
    evidence_id: `evidence:${suffix}`, event_revision_id: event.event_revision_id,
    source_unit_ref: `unit:${suffix}`, range: { start: 0, end: 4 }, excerpt: "test",
    source_identity_ref: {
      namespace_instance_ref: `namespace:${suffix}`, local_key: `speaker:${suffix}`,
      producer: { producer_ref: null, contract_ref: null },
      asserted_identity: { domain: null, scope_ref: null },
    },
    speaker_rendering: null, source_local_mention_ref: null, state: "active" as const,
    source_trust: "owner_attested", policy_labels: [],
    source_independence_key: `root:${suffix}`,
  };
  const claim: ProvisionalClaim = {
    claim_lineage_id: `lineage:${suffix}`, claim_revision_id: `claim:${suffix}`,
    owner_account_id: accountId, predicate: "noted",
    arguments: [{
      slot_id: "subject", role: "subject",
      value: { kind: "source_local_ref", ref: `speaker:${suffix}` },
    }],
    temporal_scope: {
      observed_at: "2026-08-11T20:00:00Z", precision: "instant",
      valid_time: {
        typed_expression: {
          kind: "absolute", granularity: "instant", value: "2026-08-11T20:00:00Z",
        },
        resolved_interval: {
          kind: "instant", start: "2026-08-11T20:00:00Z",
          end: "2026-08-11T20:00:00Z", timezone: "UTC", granularity: "instant",
        },
        derivation: { resolver_version: "qualification:v1", timezone: "UTC" },
      },
    },
    evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en",
    scope: { locality: "source_local", scope_ref: `speaker:${suffix}` },
    lifecycle: "provisional", ambiguity_markers: ["source_local"], context_packet: null,
  };
  const revisions: AtomicGraphTransition["revisions"] = [
    { kind: "evidence", revision_id: `evidence:${suffix}:r1`, evidence },
    { kind: "claim", revision_id: claim.claim_revision_id, claim, placement_status: "provisional_abstained" },
    { kind: "event", revision_id: event.event_revision_id, event },
  ];
  const transition: AtomicGraphTransition = {
    placement: {
      offline_experiment: true, allocations: {},
      results: [{
        input_provisional_revision_id: claim.claim_revision_id,
        disposition: "defer_review", operation: null,
        re_resolution_trigger: "new_identity_evidence",
      }],
    },
    derivation: prepareDerivation({
      attempt_id: `attempt:graph:${suffix}`, commit_id: `commit:graph:${suffix}`,
      owner_account_id: accountId, parent_commit: parentCommit,
      idempotency_key: `append:graph:${suffix}`, input_revisions: [],
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
    revisions, adjacency: [],
    artifacts: [{
      artifact_id: `artifact:${suffix}`, kind: "abstention_set",
      provisional_revision_id: claim.claim_revision_id,
      canonical_claim_revision_id: null, margin: "low", risk_markers: ["low_margin"],
      unit_boundary_decision: "abstain", scope_locality: null,
    }],
  };
  const origin = { kind: "non_formation" as const, reason: "repair" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: parentCommit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin, transition,
  };
};

const formationAppend = (
  accountId: string,
  suffix: string,
  parentCommit: string,
): AuthoritativeLedgerAppend => {
  const base = nonemptyAppend(accountId, suffix, parentCommit);
  const provisional = base.transition.revisions.find((revision) => revision.kind === "claim");
  const evidence = base.transition.revisions.find((revision) => revision.kind === "evidence");
  if (!provisional || provisional.kind !== "claim"
    || !evidence || evidence.kind !== "evidence") throw new Error("invalid formation fixture");
  const transition: AtomicGraphTransition = {
    ...base.transition,
    derivation: prepareDerivation({
      attempt_id: base.transition.derivation.commit.attempt_id,
      commit_id: base.transition.derivation.commit.commit_id,
      owner_account_id: accountId,
      parent_commit: parentCommit,
      idempotency_key: base.transition.derivation.commit.idempotency_key,
      input_revisions: [{
        revision_id: `formation-input:${suffix}`,
        content: { input_frontier: `frontier:${suffix}` },
      }],
      output_revisions: base.transition.revisions.map((revision) => ({
        revision_id: revision.revision_id,
        content: revision.kind === "event" ? revision.event
          : revision.kind === "evidence" ? revision.evidence
            : revision.kind === "claim" ? revision.claim : {},
      })),
      versions: base.transition.derivation.commit.versions,
      success_kind: "success",
    }),
  };
  const origin = {
    kind: "formation" as const,
    outcome: {
      contract_version: "memory-formation-outcome-v2" as const,
      owner_account_id: accountId,
      work_id: `work:${suffix}`,
      input_frontier: `frontier:${suffix}`,
      response_digest: "6".repeat(64),
      candidate_count: 1,
      candidate_manifest_digest: formationCandidateManifestDigest(1),
      coordinates: {
        contract_version: "memory-formation-outcome-v2" as const,
        strategy_version: "qualification-formation-v1",
        model_version: "none", prompt_version: "none",
        policy_version: "qualification-v1", code_version: "qualification-v1",
        schema_version: "qualification-v1", tokenizer_version: "none",
        tool_version: "qualification-v1", speaker_strategy_version: "none",
        boundary_strategy_version: "qualification-v1",
      },
      extraction_outcomes: [{
        kind: "accepted" as const, candidate_ref: "candidate:1",
        claim_revision_id: provisional.revision_id,
        evidence_ids: [evidence.evidence.evidence_id], repair_codes: [],
      }],
      placement_outcomes: [{
        kind: "abstained" as const,
        input_provisional_revision_id: provisional.revision_id,
        boundary_decision: "abstain" as const,
        reason_code: "subject_unresolved", reconsideration_trigger: null,
      }],
    },
  };
  return {
    ...base, transition,
    append_attempt: {
      ...base.append_attempt,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin,
  };
};

const identityAppend = (
  accountId: string,
  suffix: string,
  parentCommit: string,
): AuthoritativeLedgerAppend => {
  const sourceIdentity = {
    namespace_instance_ref: `namespace:${suffix}`, local_key: `speaker:${suffix}`,
    producer: { producer_ref: null, contract_ref: null },
    asserted_identity: { domain: null, scope_ref: null },
  };
  const entityId = `entity:${suffix}`;
  const authorization: IdentityAuthorization = {
    authorization_id: `authorization:${suffix}`, owner_account_id: accountId,
    endpoints: [
      { kind: "source_identity", source_identity_ref: sourceIdentity },
      { kind: "entity", entity_id: entityId },
    ],
    relation: "same",
    support: { kind: "owner_confirmation", confirmation_ref: `confirmation:${suffix}` },
    standing_policy_ref: null,
    namespace_scope: {
      namespace_instance_ref: sourceIdentity.namespace_instance_ref,
      identity_domain: null, scope_ref: null,
    },
    authority_policy_version: "identity-policy:v1", evaluated_frontier: 1,
    actor_provenance: { actor_ref: accountId, producer_ref: null },
    lifecycle: "active", superseded_by: null,
  };
  const event = {
    event_id: `event:${suffix}`, event_revision_id: `event:${suffix}:r1`,
    owner_account_id: accountId, capture_session_id: `session:${suffix}`,
    stream_id: `stream:${suffix}`, event_kind: "transcript",
    payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
    payload: { redacted: true }, event_time: "2026-08-11T20:00:00Z",
    ingest_time: null, source_sequence: 1,
    evidence_addressable_refs: [`evidence:${suffix}`], source_trust: "owner_attested",
    policy_labels: [], canonical_redacted_hash: "7".repeat(64),
  };
  const evidence = {
    evidence_id: `evidence:${suffix}`, event_revision_id: event.event_revision_id,
    source_unit_ref: `unit:${suffix}`, range: { start: 0, end: 5 }, excerpt: "Alice",
    source_identity_ref: sourceIdentity, speaker_rendering: "Alice",
    source_local_mention_ref: `mention:${suffix}`, state: "active" as const,
    source_trust: "owner_attested", policy_labels: [],
    source_independence_key: `root:${suffix}`,
  };
  const validTime = {
    typed_expression: {
      kind: "absolute" as const, granularity: "instant" as const,
      value: "2026-08-11T20:00:00Z",
    },
    resolved_interval: {
      kind: "instant" as const, start: "2026-08-11T20:00:00Z",
      end: "2026-08-11T20:00:00Z", timezone: "UTC", granularity: "instant" as const,
    },
    derivation: { resolver_version: "qualification:v1", timezone: "UTC" },
  };
  const provisional: ProvisionalClaim = {
    claim_lineage_id: `lineage:${suffix}:provisional`,
    claim_revision_id: `claim:${suffix}:provisional`,
    owner_account_id: accountId, predicate: "is_person",
    arguments: [{
      slot_id: "subject", role: "subject", surface: "Alice", span: { start: 0, end: 5 },
      value: { kind: "entity_ref", ref: entityId },
    }],
    temporal_scope: {
      observed_at: "2026-08-11T20:00:00Z", precision: "instant", valid_time: validTime,
    },
    evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en",
    scope: { locality: "durable", scope_ref: entityId }, lifecycle: "provisional",
    ambiguity_markers: [], context_packet: null,
  };
  const canonical = {
    ...provisional, claim_lineage_id: `lineage:${suffix}:canonical`,
    claim_revision_id: `claim:${suffix}:canonical`, lifecycle: "canonical" as const,
    canonical_claim_id: `canonical:${suffix}`,
    source_provisional_revision_ids: [provisional.claim_revision_id],
  };
  delete (canonical as { ambiguity_markers?: unknown }).ambiguity_markers;
  delete (canonical as { context_packet?: unknown }).context_packet;
  const entity = {
    entity_id: entityId, owner_account_id: accountId,
    entity_revision_id: `${entityId}:r1`, handle: `alice:${suffix}`, labels: ["Alice"],
  };
  const mention = {
    mention_id: `mention:${suffix}`, owner_account_id: accountId,
    claim_revision_id: provisional.claim_revision_id, span: { start: 0, end: 5 },
    evidence_id: evidence.evidence_id, source_identity_ref: sourceIdentity,
    speaker_rendering: "Alice", slot_id: "subject", surface: "Alice",
    antecedent_handle: null, resolution: "resolved" as const, entity_id: entityId,
  };
  const constraint: IdentityConstraint = {
    constraint_id: `constraint:${suffix}`, owner_account_id: accountId,
    endpoints: authorization.endpoints,
    left_handle: `source:${suffix}`, right_handle: `alice:${suffix}`,
    relation: "same", identity_authorization: authorization,
    effective_at: 1, reversed_at: null,
  };
  const revisions: AtomicGraphTransition["revisions"] = [
    { kind: "claim", revision_id: provisional.claim_revision_id, claim: provisional, placement_status: "consumed" },
    { kind: "claim", revision_id: canonical.claim_revision_id, claim: canonical, placement_status: "canonical" },
    { kind: "mention", revision_id: `mention:${suffix}:r1`, mention },
    { kind: "identity_authorization", revision_id: `authorization:${suffix}:r1`, authorization },
    { kind: "entity", revision_id: entity.entity_revision_id, entity },
    { kind: "identity", revision_id: `constraint:${suffix}:r1`, constraint },
    { kind: "event", revision_id: event.event_revision_id, event },
    { kind: "evidence", revision_id: `evidence:${suffix}:r1`, evidence },
  ];
  const content = (revision: AtomicGraphTransition["revisions"][number]) =>
    revision.kind === "claim" ? revision.claim
      : revision.kind === "mention" ? revision.mention
        : revision.kind === "identity_authorization" ? revision.authorization
          : revision.kind === "entity" ? revision.entity
            : revision.kind === "identity" ? revision.constraint
              : revision.kind === "event" ? revision.event
                : revision.kind === "evidence" ? revision.evidence : {};
  const transition: AtomicGraphTransition = {
    placement: {
      offline_experiment: true,
      allocations: { [provisional.claim_revision_id]: canonical.claim_revision_id },
      results: [{
        input_provisional_revision_id: provisional.claim_revision_id,
        disposition: "admit",
        operation: { kind: "identity_linkage", entity_id: entityId },
      }],
    },
    derivation: prepareDerivation({
      attempt_id: `attempt:identity:${suffix}`, commit_id: `commit:identity:${suffix}`,
      owner_account_id: accountId, parent_commit: parentCommit,
      idempotency_key: `append:identity:${suffix}`, input_revisions: [],
      output_revisions: revisions.map((revision) => ({
        revision_id: revision.revision_id, content: content(revision),
      })),
      versions: {
        strategy_version: "qualification-identity-v1", model_version: "none",
        prompt_version: "none", policy_version: "qualification-v1",
        code_version: "qualification-v1", schema_version: "qualification-v1",
        tokenizer_version: "none", tool_version: "qualification-v1",
      },
      success_kind: "success",
    }),
    revisions,
    adjacency: [{
      claim_revision_id: canonical.claim_revision_id,
      entity_id: entityId, role_slot_id: "subject",
    }],
    artifacts: [{
      artifact_id: `artifact:${suffix}`, kind: "auto_placement_log",
      provisional_revision_id: provisional.claim_revision_id,
      canonical_claim_revision_id: canonical.claim_revision_id,
      margin: "high", risk_markers: [], unit_boundary_decision: "accept_ltm",
      scope_locality: "durable",
    }],
    identity_authority_context: {
      owner_confirmations: [{
        confirmation_ref: `confirmation:${suffix}`, owner_account_id: accountId,
        endpoints: authorization.endpoints, relation: "same",
      }],
      producer_assertions: [], standing_policies: [],
    },
  };
  const origin = { kind: "non_formation" as const, reason: "identity_consolidation" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: parentCommit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin, transition,
  };
};

realTest("PostgreSQL 18.4 real adapter qualification scaffold", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(() => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    const parsed = new URL(explicitTestUrl);
    if (parsed.hostname !== "127.0.0.1" || parsed.protocol !== "postgres:") {
      throw new Error("postgres_test_not_loopback_only");
    }
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
  });

  afterAll(async () => {
    await pool?.close();
    await ownerSql?.end({ timeout: 5 });
  });

  test("runs the pinned server, creates only the test role, and reapplies all migrations as no-ops", async () => {
    const version = await ownerSql.unsafe<{ server_version_num: string }[]>("SHOW server_version_num");
    expect(Number(version[0]?.server_version_num)).toBe(180004);
    expect(process.env["OMI_TEST_POSTGRES_IMAGE"]).toBe(
      "postgres:18.4-bookworm@sha256:882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382",
    );
    await ownerSql.unsafe(`
      DO $role$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_application') THEN
          CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
      END
      $role$
    `, [], { prepare: false });

    const first = await runPostgresMigrations(ownerSql);
    const second = await runPostgresMigrations(ownerSql);
    expect([...first.appliedVersions, ...first.skippedVersions].sort((left, right) => left - right)).toEqual(
      POSTGRES_MIGRATIONS.map((entry) => entry.version),
    );
    expect(second.appliedVersions).toEqual([]);
    expect(second.skippedVersions).toEqual(POSTGRES_MIGRATIONS.map((entry) => entry.version));
  }, 120_000);

  test("one reserved connection owns the transaction and SET LOCAL clears after rollback", async () => {
    let firstBackend: number | undefined;
    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number }>({
          name: "qualification.backend_and_local",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        set_config('omi.account_id', $1, true) AS local_account`,
          values: ["account:qualification"],
        });
        firstBackend = rows[0]?.backend_pid;
        throw new Error("force rollback");
      },
    )).rejects.toThrow("force rollback");

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number; local_account: string | null }>({
          name: "qualification.local_cleared",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        nullif(current_setting('omi.account_id', true), '') AS local_account`,
          values: [],
        });
        if (firstBackend === undefined) throw new Error("missing qualification backend");
        expect(rows[0]?.backend_pid).toBe(firstBackend);
        expect(rows[0]?.local_account).toBeNull();
      },
    );
  });

  test("backend termination rolls back the first write and the size-one pool reconnects", async () => {
    const killedAccount = `account:terminated:${randomUUID()}`;
    let killedBackend: number | undefined;

    let terminationError: unknown;
    try {
      await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          const backend = await connection.query<{ backend_pid: number }>({
            name: "qualification.termination_backend",
            text: "SELECT pg_backend_pid() AS backend_pid",
            values: [],
          });
          killedBackend = backend[0]?.backend_pid;
          if (killedBackend === undefined) throw new Error("missing_termination_backend");
          await connection.execute({
            name: "qualification.termination_first_write",
            text: "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)",
            values: [killedAccount],
          });
          const terminated = await ownerSql.unsafe<{ terminated: boolean }[]>(
            "SELECT pg_terminate_backend($1) AS terminated",
            [killedBackend],
          );
          expect(terminated[0]?.terminated).toBe(true);
          // This is the named pre-commit checkpoint: no query is in flight while
          // Postgres.js observes the socket close. The pool must refuse COMMIT on
          // the lost lease and reconnect its size-one slot for the next request.
          await Bun.sleep(100);
        },
      );
    } catch (error) {
      terminationError = error;
    }
    expect(["57P01", "CONNECTION_CLOSED", "CONNECTION_DESTROYED"]).toContain(
      terminationError && typeof terminationError === "object"
        ? Reflect.get(terminationError, "code") : null,
    );

    const rolledBack = await ownerSql.unsafe<{ count: number }[]>(
      "SELECT count(*)::int AS count FROM omi_memory.platform_accounts WHERE account_id = $1",
      [killedAccount],
    );
    expect([...rolledBack]).toEqual([{ count: 0 }]);

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        const recovered = await connection.query<{
          backend_pid: number; local_account: string | null;
        }>({
          name: "qualification.termination_recovered_pool",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        nullif(current_setting('omi.account_id', true), '') AS local_account`,
          values: [],
        });
        if (killedBackend === undefined) throw new Error("missing_termination_backend");
        expect(recovered[0]?.backend_pid).not.toBe(killedBackend);
        expect(recovered[0]?.local_account).toBeNull();
      },
    );
  }, 30_000);

  test("application-role authority adapter commits empty, graph, and formation work with exact replay and rollback", async () => {
    const suffix = randomUUID();
    const accountId = `account:pg-kernel:${suffix}`;
    const principalId = `principal:pg-kernel:${suffix}`;
    const applicationId = "app:qualification";
    const credentialId = `credential:${suffix}`;
    const grantId = `grant:${suffix}`;
    const controlHash = "1".repeat(64);
    const credentialHash = "2".repeat(64);
    const grantHash = "3".repeat(64);
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
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'firebase-id-token',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountId, principalId, applicationId, credentialId, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountId, applicationId, credentialId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, grantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9)`,
      [accountId, applicationId, credentialId, grantId]);
    });

    const authorityRow: AuthorityStateRow = {
      account_id: accountId,
      principal_id: principalId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "memories.write",
      grant_id: grantId,
      grant_version: 9,
      account_epoch: 12,
      control_conflict_reason: null,
      control_conflict_at_revision: null,
      destination_activation_epoch: 12,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      account_generation: "new",
      credential_lifecycle: "active",
      grant_lifecycle: "active",
      grant_enabled: true,
      authentication_strength: "firebase-id-token",
      credential_expires_at_epoch_seconds: now + 7_200,
      control_revision: 17,
      control_content_hash: controlHash,
      credential_content_hash: credentialHash,
      grant_content_hash: grantHash,
      db_now_epoch_seconds: now,
    };
    const context = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalId,
      account_id: accountId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "memories.write",
      grant_id: grantId,
      grant_version: 9,
      account_epoch: 12,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      authentication_strength: "firebase-id-token",
      issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(authorityRow),
    }, now);

    const accountB = `account:pg-kernel-b:${suffix}`;
    const principalB = `principal:pg-kernel-b:${suffix}`;
    const credentialB = `credential:b:${suffix}`;
    const grantB = `grant:b:${suffix}`;
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountB],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountB, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountB]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'firebase-id-token',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountB, principalB, applicationId, credentialB, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountB, applicationId, credentialB]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountB, applicationId, credentialB, grantB, grantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9)`,
      [accountB, applicationId, credentialB, grantB]);
    });
    const authorityRowB: AuthorityStateRow = {
      ...authorityRow, account_id: accountB, principal_id: principalB,
      credential_id: credentialB, grant_id: grantB,
    };
    const contextB = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalB, account_id: accountB, application_id: applicationId,
      credential_id: credentialB, credential_generation: 4, capability: "memories.write",
      grant_id: grantB, grant_version: 9, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "firebase-id-token", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(authorityRowB),
    }, now);

    let lastRepositoryStatement = "none";
    let lastProviderCode = "none";
    let lastProviderConstraint = "none";
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(options: Parameters<PostgresTransactionPool["withTransaction"]>[0], callback: (connection: CheckedOutPostgresConnection) => Promise<Result>) =>
        pool.withTransaction(options, async (connection) => {
          await connection.query({
            name: "qualification.set_application_role",
            text: "SET LOCAL ROLE omi_platform_application",
            values: [],
          });
          const roles = await connection.query<{ current_user: string }>({
            name: "qualification.assert_application_role",
            text: "SELECT current_user",
            values: [],
          });
          expect(roles).toEqual([{ current_user: "omi_platform_application" }]);
          const tracked: CheckedOutPostgresConnection = Object.freeze({
            connectionIdentity: connection.connectionIdentity,
            query: async <Row extends Record<string, unknown>>(statement: Parameters<CheckedOutPostgresConnection["query"]>[0]) => {
              lastRepositoryStatement = statement.name;
              return connection.query<Row>(statement);
            },
            execute: async (statement: SqlStatement) => {
              lastRepositoryStatement = statement.name;
              try {
                return await connection.execute(statement);
              } catch (error) {
                const code = error && typeof error === "object" ? Reflect.get(error, "code") : null;
                const constraint = error && typeof error === "object" ? Reflect.get(error, "constraint_name") : null;
                lastProviderCode = typeof code === "string" ? code : "unknown";
                lastProviderConstraint = typeof constraint === "string" ? constraint : "unknown";
                throw error;
              }
            },
          });
          return callback(tracked);
        }),
    });
    const repository = createPostgresSuccessfulEmptyLedgerRepository({ pool: appRolePool });
    const append = (
      commitId: string,
      key: string,
      parent: string | null,
      ownerAccountId = accountId,
    ): AuthoritativeLedgerAppend => {
      const transition: AtomicGraphTransition = {
        placement: { offline_experiment: true, allocations: {}, results: [] },
        derivation: prepareDerivation({
          attempt_id: `attempt:${commitId}`,
          commit_id: commitId,
          owner_account_id: ownerAccountId,
          parent_commit: parent,
          idempotency_key: key,
          input_revisions: [],
          output_revisions: [],
          versions: {
            strategy_version: "qualification-v1", model_version: "none", prompt_version: "none",
            policy_version: "qualification-v1", code_version: "qualification-v1",
            schema_version: "qualification-v1", tokenizer_version: "none", tool_version: "qualification-v1",
          },
          success_kind: "successful_empty",
        }),
        revisions: [], adjacency: [], artifacts: [],
      };
      const origin = { kind: "non_formation" as const, reason: "repair" as const };
      return {
        append_attempt: {
          idempotency_key: key,
          expected_parent_commit: parent,
          request_digest: authoritativeAppendRequestDigest(transition, origin),
        },
        origin,
        transition,
      };
    };

    const first = append(`commit:${suffix}:one`, `append:${suffix}:same`, null);
    try {
      expect(await repository.append(context, first)).toEqual({
        kind: "committed", commit_id: first.transition.derivation.commit.commit_id, sequence: 1,
      });
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error
        ? String(Reflect.get(error, "code")) : "assertion_or_unknown";
      throw new Error(`kernel_real_failure_at:${lastRepositoryStatement}:${lastProviderCode}:${lastProviderConstraint}:${code}`);
    }
    await expect(repository.append(context, first)).resolves.toEqual({
      kind: "replayed", commit_id: first.transition.derivation.commit.commit_id, sequence: 1,
    });
    const changed = append(`commit:${suffix}:changed`, first.append_attempt.idempotency_key, null);
    await expect(repository.append(context, changed)).resolves.toEqual({ kind: "idempotency_conflict" });
    const stale = append(`commit:${suffix}:stale`, `append:${suffix}:stale`, null);
    await expect(repository.append(context, stale)).resolves.toEqual({ kind: "stale_parent" });

    const persisted = await ownerSql.unsafe<{
      attempts: number; commits: number; receipts: number; head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
        (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
        (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...persisted]).toEqual([{ attempts: 1, commits: 1, receipts: 1, head_sequence: "1" }]);

    const sameKeyOtherAccount = append(
      `commit:${suffix}:account-b`, first.append_attempt.idempotency_key, null, accountB,
    );
    await expect(repository.append(contextB, sameKeyOtherAccount)).resolves.toEqual({
      kind: "committed",
      commit_id: sameKeyOtherAccount.transition.derivation.commit.commit_id,
      sequence: 1,
    });
    const isolatedReceipts = await ownerSql.unsafe<{ account_id: string; count: number }[]>(`
      SELECT account_id, count(*)::int AS count
      FROM omi_memory.memory_idempotency_receipts
      WHERE account_id IN ($1, $2) AND idempotency_key = $3
      GROUP BY account_id ORDER BY account_id
    `, [accountId, accountB, first.append_attempt.idempotency_key]);
    expect(isolatedReceipts).toHaveLength(2);
    expect([...isolatedReceipts]).toEqual(expect.arrayContaining([
      { account_id: accountId, count: 1 },
      { account_id: accountB, count: 1 },
    ]));

    const racePhysicalPool = createPostgresJsTransactionPool({
      connectionString: explicitTestUrl!, maxConnections: 2,
    });
    const raceRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => racePhysicalPool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.race_set_application_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        return callback(connection);
      }),
    });
    try {
      const raceRepository = createPostgresSuccessfulEmptyLedgerRepository({ pool: raceRolePool });
      const raceParent = sameKeyOtherAccount.transition.derivation.commit.commit_id;
      const contenders = [
        append(`commit:${suffix}:race-a`, `append:${suffix}:race-a`, raceParent, accountB),
        append(`commit:${suffix}:race-b`, `append:${suffix}:race-b`, raceParent, accountB),
      ];
      const outcomes = await Promise.all(contenders.map((contender) =>
        raceRepository.append(contextB, contender)));
      expect(outcomes.filter((outcome) => outcome.kind === "committed")).toHaveLength(1);
      expect(outcomes.filter((outcome) =>
        outcome.kind === "stale_parent" || outcome.kind === "serialization_retryable"))
        .toHaveLength(1);
      const raceRows = await ownerSql.unsafe<{
        attempts: number; commits: number; receipts: number; head_sequence: string;
      }[]>(`
        SELECT
          (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
          (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
          (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
          (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
      `, [accountB]);
      expect([...raceRows]).toEqual([{ attempts: 2, commits: 2, receipts: 2, head_sequence: "2" }]);
    } finally {
      await racePhysicalPool.close();
    }

    for (const forbiddenSql of [
      "CREATE TABLE omi_memory.qualification_forbidden (id integer)",
      "DELETE FROM omi_memory.memory_derivation_attempts WHERE account_id = $1",
      "UPDATE omi_memory.memory_derivation_attempts SET success_kind = 'success' WHERE account_id = $1",
    ]) {
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe(forbiddenSql, forbiddenSql.includes("$1") ? [accountId] : []);
      })).rejects.toMatchObject({ code: "42501" });
    }

    const graphRepository = createPostgresAuthoritativeLedgerRepository({ pool: appRolePool });
    const graph = nonemptyAppend(
      accountId, suffix, first.transition.derivation.commit.commit_id,
    );
    await expect(graphRepository.append(context, graph)).resolves.toEqual({
      kind: "committed", commit_id: graph.transition.derivation.commit.commit_id, sequence: 2,
    });
    await expect(graphRepository.append(context, graph)).resolves.toEqual({
      kind: "replayed", commit_id: graph.transition.derivation.commit.commit_id, sequence: 2,
    });
    const graphRows = await ownerSql.unsafe<{
      revisions: number; events: number; evidence: number; claims: number;
      consumed: number; artifacts: number; head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_revisions WHERE account_id = $1) AS revisions,
        (SELECT count(*)::int FROM omi_memory.memory_event_revisions WHERE account_id = $1) AS events,
        (SELECT count(*)::int FROM omi_memory.memory_evidence_revisions WHERE account_id = $1) AS evidence,
        (SELECT count(*)::int FROM omi_memory.memory_claim_revisions WHERE account_id = $1) AS claims,
        (SELECT count(*)::int FROM omi_memory.memory_consumed_markers WHERE account_id = $1) AS consumed,
        (SELECT count(*)::int FROM omi_memory.memory_placement_artifacts WHERE account_id = $1) AS artifacts,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...graphRows]).toEqual([{
      revisions: 3, events: 1, evidence: 1, claims: 1,
      consumed: 1, artifacts: 1, head_sequence: "2",
    }]);

    const formation = formationAppend(
      accountId, `${suffix}:formation`, graph.transition.derivation.commit.commit_id,
    );
    await expect(graphRepository.append(context, formation)).resolves.toEqual({
      kind: "committed",
      commit_id: formation.transition.derivation.commit.commit_id,
      sequence: 3,
    });
    await expect(graphRepository.append(context, formation)).resolves.toEqual({
      kind: "replayed",
      commit_id: formation.transition.derivation.commit.commit_id,
      sequence: 3,
    });
    const formationRows = await ownerSql.unsafe<{
      inputs: number; outcomes: number; extractions: number; evidence: number; placements: number;
      head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_derivation_inputs WHERE account_id = $1) AS inputs,
        (SELECT count(*)::int FROM omi_memory.memory_formation_outcomes WHERE account_id = $1) AS outcomes,
        (SELECT count(*)::int FROM omi_memory.memory_formation_extraction_outcomes WHERE account_id = $1) AS extractions,
        (SELECT count(*)::int FROM omi_memory.memory_formation_extraction_evidence WHERE account_id = $1) AS evidence,
        (SELECT count(*)::int FROM omi_memory.memory_formation_placement_outcomes WHERE account_id = $1) AS placements,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...formationRows]).toEqual([{
      inputs: 1, outcomes: 1, extractions: 1, evidence: 1, placements: 1,
      head_sequence: "3",
    }]);

    const identity = identityAppend(
      accountId, `${suffix}:identity`, formation.transition.derivation.commit.commit_id,
    );
    await expect(graphRepository.append(context, identity)).resolves.toEqual({
      kind: "committed",
      commit_id: identity.transition.derivation.commit.commit_id,
      sequence: 4,
    });
    await expect(graphRepository.append(context, identity)).resolves.toEqual({
      kind: "replayed",
      commit_id: identity.transition.derivation.commit.commit_id,
      sequence: 4,
    });
    const identityRows = await ownerSql.unsafe<{
      authorizations: number; authorization_endpoints: number; mentions: number;
      identities: number; identity_endpoints: number; adjacency: number;
      claim_sources: number; head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_identity_authorization_revisions WHERE account_id = $1) AS authorizations,
        (SELECT count(*)::int FROM omi_memory.memory_identity_authorization_entity_endpoints WHERE account_id = $1) AS authorization_endpoints,
        (SELECT count(*)::int FROM omi_memory.memory_mention_revisions WHERE account_id = $1) AS mentions,
        (SELECT count(*)::int FROM omi_memory.memory_identity_revisions WHERE account_id = $1) AS identities,
        (SELECT count(*)::int FROM omi_memory.memory_identity_constraint_entity_endpoints WHERE account_id = $1) AS identity_endpoints,
        (SELECT count(*)::int FROM omi_memory.memory_generated_adjacency WHERE account_id = $1) AS adjacency,
        (SELECT count(*)::int FROM omi_memory.memory_claim_source_provisionals WHERE account_id = $1) AS claim_sources,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...identityRows]).toEqual([{
      authorizations: 1, authorization_endpoints: 1, mentions: 1,
      identities: 1, identity_endpoints: 1, adjacency: 1,
      claim_sources: 1, head_sequence: "4",
    }]);

    const livenessWitness = identity.transition.revisions.find(
      (revision) => revision.kind === "claim" && revision.placement_status === "canonical",
    )!;
    if (livenessWitness.kind !== "claim") throw new Error("missing liveness claim witness");
    const livenessTransition: AtomicGraphTransition = {
      placement: { offline_experiment: true, allocations: {}, results: [] },
      derivation: prepareDerivation({
        attempt_id: `attempt:liveness:${suffix}`, commit_id: `commit:liveness:${suffix}`,
        owner_account_id: accountId,
        parent_commit: identity.transition.derivation.commit.commit_id,
        idempotency_key: `append:liveness:${suffix}`,
        input_revisions: [{ revision_id: livenessWitness.revision_id, content: livenessWitness.claim }],
        output_revisions: [], versions: identity.transition.derivation.commit.versions,
        success_kind: "success",
      }),
      revisions: [], adjacency: [], artifacts: [], committed_revisions: [livenessWitness],
      liveness_fences: [{ claim_revision_id: livenessWitness.revision_id, cause: "purged" }],
    };
    const livenessOrigin = { kind: "non_formation" as const, reason: "manual_liveness" as const };
    const liveness: AuthoritativeLedgerAppend = {
      append_attempt: {
        idempotency_key: livenessTransition.derivation.commit.idempotency_key,
        expected_parent_commit: livenessTransition.derivation.commit.parent_commit,
        request_digest: authoritativeAppendRequestDigest(livenessTransition, livenessOrigin),
      },
      origin: livenessOrigin, transition: livenessTransition,
    };
    await expect(graphRepository.append(context, liveness)).resolves.toEqual({
      kind: "committed", commit_id: livenessTransition.derivation.commit.commit_id, sequence: 5,
    });
    await expect(graphRepository.append(context, liveness)).resolves.toEqual({
      kind: "replayed", commit_id: livenessTransition.derivation.commit.commit_id, sequence: 5,
    });
    const livenessRows = await ownerSql.unsafe<{
      claim_revision_id: string; cause: string; commit_id: string; head_sequence: string;
    }[]>(`
      SELECT f.claim_revision_id, f.cause, f.commit_id, h.sequence::text AS head_sequence
      FROM omi_memory.memory_claim_liveness_fences AS f
      JOIN omi_memory.memory_graph_heads AS h ON h.account_id = f.account_id
      WHERE f.account_id = $1
    `, [accountId]);
    expect([...livenessRows]).toEqual([{
      claim_revision_id: livenessWitness.revision_id, cause: "purged",
      commit_id: livenessTransition.derivation.commit.commit_id, head_sequence: "5",
    }]);

    const snapshotPhysicalPool = createPostgresJsTransactionPool({
      connectionString: explicitTestUrl!, maxConnections: 1,
    });
    const snapshotRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => snapshotPhysicalPool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.snapshot_set_application_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        return callback(connection);
      }),
    });
    try {
      const reconstructed = await createPostgresAuthoritativeGraphSnapshotRepository({
        pool: snapshotRolePool,
      }).load(context);
      expect(reconstructed.owner_account_id).toBe(accountId);
      expect(reconstructed.graph_generation).toBe(5);
      expect(reconstructed.claims.map((row) => row.revision_id)).toEqual(expect.arrayContaining([
        graph.transition.revisions.find((row) => row.kind === "claim")?.revision_id,
        identity.transition.revisions.find((row) => row.kind === "claim")?.revision_id,
      ]));
      expect(reconstructed.claims).toHaveLength(4);
      expect(reconstructed.events).toHaveLength(3);
      expect(reconstructed.evidence).toHaveLength(3);
      expect(reconstructed.entities).toHaveLength(1);
      expect(reconstructed.identity_authorizations).toHaveLength(1);
      expect(reconstructed.identity_constraints).toHaveLength(1);
      expect(reconstructed.mentions).toHaveLength(1);
      expect(reconstructed.adjacency).toHaveLength(1);
      expect(reconstructed.source_local_roles).toHaveLength(2);
      expect(reconstructed.placement_artifacts).toHaveLength(3);
      expect(reconstructed.liveness_causes).toEqual({
        purged_claim_revision_ids: [livenessWitness.revision_id],
        forgotten_claim_revision_ids: [],
      });
      const sqliteDatabase = new Database(":memory:");
      try {
        const sqlite = new SqliteLedger(sqliteDatabase);
        for (const sharedTransition of [
          first.transition,
          graph.transition,
          formation.transition,
          identity.transition,
          liveness.transition,
        ]) sqlite.append(sharedTransition);
        expect(sha256CanonicalContent(sqlite.snapshot(accountId)))
          .toBe(sha256CanonicalContent(reconstructed));
      } finally {
        sqliteDatabase.close();
      }
      expect(JSON.stringify(await createPostgresAuthoritativeGraphSnapshotRepository({
        pool: snapshotRolePool,
      }).load(context))).toBe(JSON.stringify(reconstructed));
    } finally {
      await snapshotPhysicalPool.close();
    }

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        const cleared = await connection.query<{
          account_id: string | null; principal_id: string | null;
          grant_id: string | null; current_user: string;
        }>({
          name: "qualification.authority_locals_cleared",
          text: `SELECT
              nullif(current_setting('omi.account_id', true), '') AS account_id,
              nullif(current_setting('omi.principal_id', true), '') AS principal_id,
              nullif(current_setting('omi.grant_id', true), '') AS grant_id,
              current_user`,
          values: [],
        });
        expect(cleared).toEqual([{
          account_id: null, principal_id: null, grant_id: null,
          current_user: new URL(explicitTestUrl!).username,
        }]);
      },
    );

    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_kernel_commit()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_kernel_commit ON omi_memory.memory_derivation_commits;
        CREATE TRIGGER reject_kernel_commit
        AFTER INSERT ON omi_memory.memory_derivation_commits
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_kernel_commit()
      `, [], { prepare: false });
      const rollback = append(
        `commit:${suffix}:rollback`,
        `append:${suffix}:rollback`,
        livenessTransition.derivation.commit.commit_id,
      );
      await expect(repository.append(context, rollback)).rejects.toMatchObject({ code: "persistence_failed" });
      const rolledBack = await ownerSql.unsafe<{ attempts: number; commits: number; receipts: number; head_sequence: string }[]>(`
        SELECT
          (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
          (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
          (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
          (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
      `, [accountId]);
      expect([...rolledBack]).toEqual([{ attempts: 5, commits: 5, receipts: 5, head_sequence: "5" }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_kernel_commit ON omi_memory.memory_derivation_commits;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_kernel_commit()
      `, [], { prepare: false }).catch(() => undefined);
    }

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 10, 'revoked', false,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, "4".repeat(64)]);
      await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
        SET grant_version = 10, updated_at = transaction_timestamp()
        WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
          AND credential_generation = 4 AND capability = 'memories.write'`,
      [accountId, applicationId, credentialId]);
    });
    await expect(repository.append(context, first)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });
  }, 120_000);
});
