import { expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  authoritativeAppendRequestDigest,
  type AuthoritativeLedgerAppend,
} from "../../apps/service/stores/authoritative-ledger-repository";
import { prepareDerivation, sha256CanonicalRedacted, type AtomicGraphTransition } from "../../core/ledger";
import type { IdentityAuthorization, IdentityConstraint, ProvisionalClaim } from "../../core/schema";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  createPostgresAuthoritativeLedgerRepository,
  createPostgresSuccessfulEmptyLedgerRepository,
} from "./authoritative-ledger-repository";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const authorityRow = (overrides: Partial<AuthorityStateRow> = {}): AuthorityStateRow => ({
  account_id: "account:alice", principal_id: "principal:alice", application_id: "app:desktop",
  credential_id: "credential:one", credential_generation: 4, capability: "memories.write",
  grant_id: "grant:one", grant_version: 9, account_epoch: 12,
  control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 12, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "firebase-id-token", credential_expires_at_epoch_seconds: 300,
  control_revision: 17, control_content_hash: "1".repeat(64),
  credential_content_hash: "2".repeat(64), grant_content_hash: "3".repeat(64),
  db_now_epoch_seconds: 150,
  ...overrides,
});

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1", principal_id: "principal:alice",
  account_id: "account:alice", application_id: "app:desktop", credential_id: "credential:one",
  credential_generation: 4, capability: "memories.write", grant_id: "grant:one", grant_version: 9,
  account_epoch: 12, destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
  authentication_strength: "firebase-id-token", issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200, authorization_state_digest: authorizationStateDigest(authorityRow()),
}, 150);

const plan = (overrides: { idempotencyKey?: string; commitId?: string; parent?: string | null } = {}): AtomicGraphTransition => ({
  placement: { offline_experiment: true, allocations: {}, results: [] },
  derivation: prepareDerivation({
    attempt_id: `attempt:${overrides.commitId ?? "one"}`,
    commit_id: overrides.commitId ?? "commit:one",
    owner_account_id: "account:alice",
    parent_commit: overrides.parent ?? null,
    idempotency_key: overrides.idempotencyKey ?? "append:one",
    input_revisions: [], output_revisions: [],
    versions: {
      strategy_version: "strategy:v1", model_version: "none", prompt_version: "none",
      policy_version: "policy:v1", code_version: "code:v1", schema_version: "schema:v1",
      tokenizer_version: "none", tool_version: "tool:v1",
    },
    success_kind: "successful_empty",
  }),
  revisions: [], adjacency: [], artifacts: [],
});

const request = (transition = plan(), reason: "repair" | "manual_liveness" | "historical_replay" = "repair"): AuthoritativeLedgerAppend => {
  const origin = { kind: "non_formation" as const, reason };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: transition.derivation.commit.parent_commit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin,
    transition,
  };
};

const graphPlan = (): AtomicGraphTransition => {
  const event = {
    event_id: "event:one", event_revision_id: "event:one:r1",
    owner_account_id: "account:alice", capture_session_id: "session:one",
    stream_id: "stream:one", event_kind: "transcript",
    payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
    payload: { redacted: true }, event_time: "2026-08-11T20:00:00Z",
    ingest_time: null, source_sequence: 1, evidence_addressable_refs: ["evidence:one"],
    source_trust: "owner_attested", policy_labels: [],
    canonical_redacted_hash: "4".repeat(64),
  };
  const evidence = {
    evidence_id: "evidence:one", event_revision_id: event.event_revision_id,
    source_unit_ref: "unit:one", range: { start: 0, end: 4 }, excerpt: "test",
    source_identity_ref: {
      namespace_instance_ref: "namespace:one", local_key: "speaker:one",
      producer: { producer_ref: null, contract_ref: null },
      asserted_identity: { domain: null, scope_ref: null },
    },
    speaker_rendering: null, source_local_mention_ref: null, state: "active" as const,
    source_trust: "owner_attested", policy_labels: [], source_independence_key: "root:one",
  };
  const claim: ProvisionalClaim = {
    claim_lineage_id: "lineage:one", claim_revision_id: "claim:one",
    owner_account_id: "account:alice", predicate: "noted",
    arguments: [{
      slot_id: "subject", role: "subject",
      value: { kind: "source_local_ref" as const, ref: "speaker:one" },
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
        derivation: { resolver_version: "fixture:v1", timezone: "UTC" },
      },
    },
    evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en",
    scope: { locality: "source_local" as const, scope_ref: "speaker:one" },
    lifecycle: "provisional" as const, ambiguity_markers: ["source_local"],
    context_packet: null,
  };
  const revisions: AtomicGraphTransition["revisions"] = [
    { kind: "evidence", revision_id: "evidence:one:r1", evidence },
    { kind: "claim", revision_id: claim.claim_revision_id, claim, placement_status: "provisional_abstained" },
    { kind: "event", revision_id: event.event_revision_id, event },
  ];
  const outputRevisions = revisions.map((revision) => ({
    revision_id: revision.revision_id,
    content: revision.kind === "event" ? revision.event
      : revision.kind === "evidence" ? revision.evidence
        : revision.kind === "claim" ? revision.claim : {},
  }));
  return {
    placement: {
      offline_experiment: true, allocations: {},
      results: [{
        input_provisional_revision_id: claim.claim_revision_id,
        disposition: "defer_review", operation: null,
        re_resolution_trigger: "new_identity_evidence",
      }],
    },
    derivation: prepareDerivation({
      attempt_id: "attempt:graph", commit_id: "commit:graph",
      owner_account_id: "account:alice", parent_commit: null,
      idempotency_key: "append:graph", input_revisions: [], output_revisions: outputRevisions,
      versions: plan().derivation.attempt.versions, success_kind: "success",
    }),
    revisions, adjacency: [],
    artifacts: [{
      artifact_id: "artifact:one", kind: "abstention_set",
      provisional_revision_id: claim.claim_revision_id,
      canonical_claim_revision_id: null, margin: "low", risk_markers: ["low_margin"],
      unit_boundary_decision: "abstain", scope_locality: null,
    }],
  };
};

const graphRequest = (): AuthoritativeLedgerAppend => {
  const transition = graphPlan();
  const origin = { kind: "non_formation" as const, reason: "repair" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: transition.derivation.commit.parent_commit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin, transition,
  };
};

const identityRequest = (): AuthoritativeLedgerAppend => {
  const sourceIdentity = {
    namespace_instance_ref: "namespace:identity", local_key: "alice",
    producer: { producer_ref: null, contract_ref: null },
    asserted_identity: { domain: null, scope_ref: null },
  };
  const authorization: IdentityAuthorization = {
    authorization_id: "authorization:alice", owner_account_id: "account:alice",
    endpoints: [
      { kind: "source_identity" as const, source_identity_ref: sourceIdentity },
      { kind: "entity" as const, entity_id: "entity:alice" },
    ],
    relation: "same" as const,
    support: { kind: "owner_confirmation" as const, confirmation_ref: "confirmation:alice" },
    standing_policy_ref: null,
    namespace_scope: {
      namespace_instance_ref: "namespace:identity", identity_domain: null, scope_ref: null,
    },
    authority_policy_version: "identity-policy:v1", evaluated_frontier: 1,
    actor_provenance: { actor_ref: "account:alice", producer_ref: null },
    lifecycle: "active" as const, superseded_by: null,
  };
  const event = {
    event_id: "event:identity", event_revision_id: "event:identity:r1",
    owner_account_id: "account:alice", capture_session_id: "session:identity",
    stream_id: "stream:identity", event_kind: "transcript",
    payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
    payload: { redacted: true }, event_time: "2026-08-11T20:00:00Z",
    ingest_time: null, source_sequence: 1, evidence_addressable_refs: ["evidence:identity"],
    source_trust: "owner_attested", policy_labels: [],
    canonical_redacted_hash: "7".repeat(64),
  };
  const evidence = {
    evidence_id: "evidence:identity", event_revision_id: event.event_revision_id,
    source_unit_ref: "unit:identity", range: { start: 0, end: 5 }, excerpt: "Alice",
    source_identity_ref: sourceIdentity, speaker_rendering: "Alice",
    source_local_mention_ref: "mention:alice", state: "active" as const,
    source_trust: "owner_attested", policy_labels: [],
    source_independence_key: "root:identity",
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
    derivation: { resolver_version: "fixture:v1", timezone: "UTC" },
  };
  const provisional: ProvisionalClaim = {
    claim_lineage_id: "lineage:identity:provisional", claim_revision_id: "claim:identity:provisional",
    owner_account_id: "account:alice", predicate: "is_person",
    arguments: [{
      slot_id: "subject", role: "subject", surface: "Alice", span: { start: 0, end: 5 },
      value: { kind: "entity_ref", ref: "entity:alice" },
    }],
    temporal_scope: { observed_at: "2026-08-11T20:00:00Z", precision: "instant", valid_time: validTime },
    evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en",
    scope: { locality: "durable", scope_ref: "entity:alice" }, lifecycle: "provisional",
    ambiguity_markers: [], context_packet: null,
  };
  const canonical = {
    ...provisional, claim_lineage_id: "lineage:identity:canonical",
    claim_revision_id: "claim:identity:canonical", lifecycle: "canonical" as const,
    canonical_claim_id: "canonical:identity", source_provisional_revision_ids: [provisional.claim_revision_id],
  };
  delete (canonical as { ambiguity_markers?: unknown }).ambiguity_markers;
  delete (canonical as { context_packet?: unknown }).context_packet;
  const entity = {
    entity_id: "entity:alice", owner_account_id: "account:alice",
    entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"],
  };
  const mention = {
    mention_id: "mention:alice", owner_account_id: "account:alice",
    claim_revision_id: provisional.claim_revision_id, span: { start: 0, end: 5 },
    evidence_id: evidence.evidence_id, source_identity_ref: sourceIdentity,
    speaker_rendering: "Alice", slot_id: "subject", surface: "Alice",
    antecedent_handle: null, resolution: "resolved" as const, entity_id: entity.entity_id,
  };
  const constraint: IdentityConstraint = {
    constraint_id: "constraint:alice", owner_account_id: "account:alice",
    endpoints: authorization.endpoints, left_handle: "source:alice", right_handle: "alice",
    relation: "same" as const, identity_authorization: authorization,
    effective_at: 1, reversed_at: null,
  };
  const revisions: AtomicGraphTransition["revisions"] = [
    { kind: "claim", revision_id: provisional.claim_revision_id, claim: provisional, placement_status: "consumed" },
    { kind: "claim", revision_id: canonical.claim_revision_id, claim: canonical, placement_status: "canonical" },
    { kind: "mention", revision_id: "mention:alice:r1", mention },
    { kind: "identity_authorization", revision_id: "authorization:alice:r1", authorization },
    { kind: "entity", revision_id: entity.entity_revision_id, entity },
    { kind: "identity", revision_id: "constraint:alice:r1", constraint },
    { kind: "event", revision_id: event.event_revision_id, event },
    { kind: "evidence", revision_id: "evidence:identity:r1", evidence },
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
        disposition: "admit", operation: { kind: "identity_linkage", entity_id: entity.entity_id },
      }],
    },
    derivation: prepareDerivation({
      attempt_id: "attempt:identity", commit_id: "commit:identity",
      owner_account_id: "account:alice", parent_commit: null,
      idempotency_key: "append:identity", input_revisions: [],
      output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: content(revision) })),
      versions: plan().derivation.attempt.versions, success_kind: "success",
    }),
    revisions,
    adjacency: [{
      claim_revision_id: canonical.claim_revision_id,
      entity_id: entity.entity_id, role_slot_id: "subject",
    }],
    artifacts: [{
      artifact_id: "artifact:identity", kind: "auto_placement_log",
      provisional_revision_id: provisional.claim_revision_id,
      canonical_claim_revision_id: canonical.claim_revision_id,
      margin: "high", risk_markers: [], unit_boundary_decision: "accept_ltm",
      scope_locality: "durable",
    }],
    identity_authority_context: {
      owner_confirmations: [{
        confirmation_ref: "confirmation:alice", owner_account_id: "account:alice",
        endpoints: authorization.endpoints, relation: "same",
      }],
      producer_assertions: [], standing_policies: [],
    },
  };
  const origin = { kind: "non_formation" as const, reason: "identity_consolidation" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: null,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin, transition,
  };
};

const vocabularyRequest = (): AuthoritativeLedgerAppend => {
  const left = {
    predicate_id: "predicate:left", owner_account_id: "account:alice",
    predicate_revision_id: "predicate:left:r1", identity_name: "likes",
    display_name: "likes", lifecycle: "canonical" as const,
    identity_version: "name-v2" as const, slot_ids: [] as [], observed_roles: ["subject"],
  };
  const right = {
    predicate_id: "predicate:right", owner_account_id: "account:alice",
    predicate_revision_id: "predicate:right:r1", identity_name: "enjoys",
    display_name: "enjoys", lifecycle: "canonical" as const,
    identity_version: "name-v2" as const, slot_ids: [] as [], observed_roles: ["subject"],
  };
  const assertion = {
    assertion_id: "assertion:alias", owner_account_id: "account:alice",
    predicate_id: left.predicate_id, relation: "alias_of" as const,
    target_predicate_id: right.predicate_id,
    slot_aliases: [{ from_slot_id: "subject", to_slot_id: "subject" }],
    alias_frontier: "frontier:vocabulary", admission: "accepted" as const,
    lifecycle: "active" as const, supersedes_assertion_id: null,
  };
  const entity = {
    entity_id: "entity:candidate", owner_account_id: "account:alice",
    entity_revision_id: "entity:candidate:r1", handle: "candidate", labels: [],
  };
  const revisions: AtomicGraphTransition["revisions"] = [
    { kind: "predicate_assertion", revision_id: "assertion:alias:r1", assertion },
    { kind: "predicate", revision_id: left.predicate_revision_id, predicate: left },
    { kind: "entity", revision_id: entity.entity_revision_id, entity },
    { kind: "predicate", revision_id: right.predicate_revision_id, predicate: right },
  ];
  const transition: AtomicGraphTransition = {
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation: prepareDerivation({
      attempt_id: "attempt:vocabulary", commit_id: "commit:vocabulary",
      owner_account_id: "account:alice", parent_commit: null,
      idempotency_key: "append:vocabulary", input_revisions: [],
      output_revisions: revisions.map((revision) => ({
        revision_id: revision.revision_id,
        content: revision.kind === "predicate" ? revision.predicate
          : revision.kind === "predicate_assertion" ? revision.assertion
            : revision.kind === "entity" ? revision.entity : {},
      })),
      versions: plan().derivation.attempt.versions, success_kind: "success",
    }),
    revisions, adjacency: [],
    artifacts: [{
      artifact_id: "candidate:vocabulary", kind: "candidate_derivation",
      owner_account_id: "account:alice", source_ref: "source:vocabulary",
      candidate_entity_id: entity.entity_id, strategy_ref: "strategy:vocabulary",
      input_refs: [left.predicate_id, right.predicate_id],
    }],
  };
  const origin = { kind: "non_formation" as const, reason: "predicate_alignment" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: null,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin, transition,
  };
};

const witnessedEventRequest = (): { request: AuthoritativeLedgerAppend; event: Record<string, unknown> } => {
  const event = {
    event_id: "event:witness", event_revision_id: "event:witness:r1",
    owner_account_id: "account:alice", capture_session_id: "session:witness",
    stream_id: "stream:witness", event_kind: "transcript",
    payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
    payload: {}, event_time: "2026-08-11T20:00:00Z", ingest_time: null,
    source_sequence: null, evidence_addressable_refs: [], source_trust: "owner_attested",
    policy_labels: [], canonical_redacted_hash: "8".repeat(64),
  };
  const transition = plan();
  transition.committed_revisions = [{
    kind: "event", revision_id: event.event_revision_id, event,
  }];
  const origin = { kind: "non_formation" as const, reason: "historical_replay" as const };
  return {
    event,
    request: {
      append_attempt: {
        idempotency_key: transition.derivation.commit.idempotency_key,
        expected_parent_commit: null,
        request_digest: authoritativeAppendRequestDigest(transition, origin),
      },
      origin, transition,
    },
  };
};

const committedReceipt = (
  append: AuthoritativeLedgerAppend,
  overrides: Readonly<Record<string, unknown>> = {},
): Readonly<Record<string, unknown>> => {
  const commit = append.transition.derivation.commit;
  return {
    request_digest: append.append_attempt.request_digest,
    state: "finalized",
    commit_id: commit.commit_id,
    sequence: "1",
    attempt_id: commit.attempt_id,
    parent_commit_id: commit.parent_commit,
    input_digest: commit.input_digest,
    input_version_digest: commit.input_version_digest,
    output_digest: commit.output_digest,
    success_kind: commit.success_kind,
    origin_kind: "non_formation",
    formation_work_id: null,
    non_formation_reason: append.origin.kind === "non_formation" ? append.origin.reason : null,
    record_json: { ...commit, sequence: 1 },
    ...overrides,
  };
};

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "one" });
  readonly statements: SqlStatement[] = [];
  receipt: Readonly<Record<string, unknown>> | null = null;
  head: Readonly<Record<string, unknown>> = { commit_id: null, sequence: "0" };
  failAt: string | null = null;
  zeroAt: string | null = null;
  predicateIdentityVersion = "name-v2";
  authority: Record<string, unknown> = authorityRow();
  witness: Readonly<Record<string, unknown>> | null = null;

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") {
      const row = this.authority;
      return [{ ...row,
        credential_generation: "4", grant_version: "9", account_epoch: "12",
        destination_activation_epoch: "12", destination_activation_revision: "17",
        credential_expires_at_epoch_seconds: "300", control_revision: "17",
        db_now_epoch_seconds: "150",
      } as unknown as Row];
    }
    if (statement.name === "ledger.receipt_lookup") return (this.receipt ? [this.receipt] : []) as Row[];
    if (statement.name === "ledger.witness_verify") return (this.witness ? [this.witness] : []) as Row[];
    if (statement.name === "ledger.predicate_identity_verify") {
      return [{ identity_version: this.predicateIdentityVersion } as unknown as Row];
    }
    if (statement.name === "ledger.head_lock") return [this.head as Row];
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (this.failAt === statement.name) throw new Error("private database failure");
    if (this.zeroAt === statement.name) return { rowCount: 0 };
    return { rowCount: 1 };
  }
}

class FakePool implements PostgresTransactionPool {
  constructor(readonly connection: FakeConnection) {}
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    expect(options).toEqual({ isolationLevel: "serializable", accessMode: "read write" });
    return callback(this.connection);
  }
}

test("qualification kernel commits successful-empty on one authorized serializable connection", async () => {
  const connection = new FakeConnection();
  const repository = createPostgresSuccessfulEmptyLedgerRepository({ pool: new FakePool(connection) });
  await expect(repository.append(context(), request())).resolves.toEqual({
    kind: "committed", commit_id: "commit:one", sequence: 1,
  });
  expect(connection.statements.map((statement) => statement.name)).toEqual([
    "authority.set_local", "authority.lock_and_revalidate", "ledger.receipt_lookup",
    "ledger.receipt_reserve", "ledger.head_lock", "ledger.attempt_insert",
    "ledger.commit_insert", "ledger.head_advance", "ledger.receipt_finalize",
  ]);
  expect(new Set(connection.statements.map(() => connection.connectionIdentity)).size).toBe(1);
});

test("revalidates authority before exact replay, conflict, or stale-parent outcome", async () => {
  const append = request();
  for (const [receipt, expected] of [
    [committedReceipt(append),
      { kind: "replayed", commit_id: "commit:one", sequence: 1 }],
    [committedReceipt(append, { request_digest: "f".repeat(64) }),
      { kind: "idempotency_conflict" }],
  ] as const) {
    const connection = new FakeConnection();
    connection.receipt = receipt;
    const repository = createPostgresSuccessfulEmptyLedgerRepository({ pool: new FakePool(connection) });
    await expect(repository.append(context(), append)).resolves.toEqual(expected);
    expect(connection.statements.slice(0, 3).map((item) => item.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "ledger.receipt_lookup",
    ]);
  }

  const stale = new FakeConnection();
  stale.head = { commit_id: "commit:other", sequence: "1" };
  await expect(createPostgresSuccessfulEmptyLedgerRepository({ pool: new FakePool(stale) })
    .append(context(), request())).resolves.toEqual({ kind: "stale_parent" });
  expect(stale.statements.map((item) => item.name)).not.toContain("ledger.attempt_insert");
});

test("same-digest replay rejects a receipt linked to different commit coordinates", async () => {
  const append = request();
  for (const corruption of [
    { commit_id: "commit:other" },
    { attempt_id: "attempt:other" },
    { parent_commit_id: "commit:other" },
    { origin_kind: "formation" },
    { non_formation_reason: "historical_replay" },
    { record_json: { idempotency_key: "append:other" } },
  ]) {
    const connection = new FakeConnection();
    connection.receipt = committedReceipt(append, corruption);
    await expect(createPostgresSuccessfulEmptyLedgerRepository({ pool: new FakePool(connection) })
      .append(context(), append)).rejects.toMatchObject({ code: "persistence_failed" });
  }
});

test("fails closed on every graph-bearing or unsupported transition before database work", async () => {
  const connection = new FakeConnection();
  const repository = createPostgresSuccessfulEmptyLedgerRepository({ pool: new FakePool(connection) });
  const graphBearing = plan();
  graphBearing.artifacts = [{
    artifact_id: "artifact:one", kind: "abstention_set", provisional_revision_id: "claim:one",
    canonical_claim_revision_id: null, margin: null, risk_markers: [],
    unit_boundary_decision: "abstain", scope_locality: null,
  }];
  const graphBase = request(graphBearing);
  const graphRequest: AuthoritativeLedgerAppend = { ...graphBase,
    append_attempt: { ...graphBase.append_attempt,
      request_digest: authoritativeAppendRequestDigest(graphBearing, graphBase.origin) } };
  await expect(repository.append(context(), graphRequest)).rejects.toThrow("transition is invalid");

  const unsupportedOrigin = { kind: "non_formation" as const, reason: "promotion" as const };
  const unsupportedBase = request(plan(), "repair");
  const unsupported: AuthoritativeLedgerAppend = {
    ...unsupportedBase,
    origin: unsupportedOrigin,
    append_attempt: { ...unsupportedBase.append_attempt,
      request_digest: authoritativeAppendRequestDigest(unsupportedBase.transition, unsupportedOrigin) },
  };
  await expect(repository.append(context(), unsupported)).rejects.toMatchObject({ code: "transition_invalid" });
  expect(connection.statements).toEqual([]);
});

test("maps provider errors content-safely and leaves activation semantics outside the kernel", async () => {
  const connection = new FakeConnection();
  connection.failAt = "ledger.commit_insert";
  const repository = createPostgresSuccessfulEmptyLedgerRepository({ pool: new FakePool(connection) });
  await expect(repository.append(context(), request())).rejects.toMatchObject({
    code: "persistence_failed", message: "persistence_failed",
  });
});

test("does not mislabel a generic authority-state denial as a credential failure", async () => {
  const connection = new FakeConnection();
  connection.authority = authorityRow({
    control_conflict_reason: "control_conflict",
    control_conflict_at_revision: 17,
  });
  await expect(createPostgresSuccessfulEmptyLedgerRepository({ pool: new FakePool(connection) })
    .append(context(), request())).rejects.toEqual(
      expect.objectContaining({ code: "authorization_state_denied" }),
    );
  expect(connection.statements.map((statement) => statement.name)).toEqual([
    "authority.set_local", "authority.lock_and_revalidate",
  ]);
});

test("full inert adapter persists a nonempty graph in dependency order", async () => {
  const connection = new FakeConnection();
  const repository = createPostgresAuthoritativeLedgerRepository({ pool: new FakePool(connection) });
  await expect(repository.append(context(), graphRequest())).resolves.toEqual({
    kind: "committed", commit_id: "commit:graph", sequence: 1,
  });
  const names = connection.statements.map((statement) => statement.name);
  expect(names).toContain("ledger.event_identity");
  expect(names).toContain("ledger.evidence_identity");
  expect(names).toContain("ledger.claim_lineage");
  expect(names.filter((name) => name === "ledger.revision_insert")).toHaveLength(3);
  expect(names.indexOf("ledger.event_revision_insert"))
    .toBeLessThan(names.indexOf("ledger.evidence_revision_insert"));
  expect(names).toContain("ledger.claim_evidence_insert");
  expect(names).toContain("ledger.source_local_role_insert");
  expect(names).toContain("ledger.consumed_marker_insert");
  expect(names).toContain("ledger.placement_artifact_insert");
  expect(names.at(-2)).toBe("ledger.head_advance");
  expect(names.at(-1)).toBe("ledger.receipt_finalize");
});

test("full inert adapter covers identity authority, mention lineage, and adjacency", async () => {
  const connection = new FakeConnection();
  const repository = createPostgresAuthoritativeLedgerRepository({ pool: new FakePool(connection) });
  await expect(repository.append(context(), identityRequest())).resolves.toEqual({
    kind: "committed", commit_id: "commit:identity", sequence: 1,
  });
  const names = connection.statements.map((statement) => statement.name);
  for (const required of [
    "ledger.authorization_identity", "ledger.entity_identity",
    "ledger.authorization_revision_insert", "ledger.authorization_entity_endpoint_insert",
    "ledger.mention_revision_insert", "ledger.identity_revision_insert",
    "ledger.identity_entity_endpoint_insert", "ledger.adjacency_insert",
    "ledger.claim_source_provisional_insert",
  ]) expect(names).toContain(required);
  expect(names.indexOf("ledger.authorization_revision_insert"))
    .toBeLessThan(names.indexOf("ledger.identity_revision_insert"));
});

test("full inert adapter covers predicate vocabulary and candidate artifacts", async () => {
  const connection = new FakeConnection();
  const repository = createPostgresAuthoritativeLedgerRepository({ pool: new FakePool(connection) });
  await expect(repository.append(context(), vocabularyRequest())).resolves.toEqual({
    kind: "committed", commit_id: "commit:vocabulary", sequence: 1,
  });
  const names = connection.statements.map((statement) => statement.name);
  expect(names.filter((name) => name === "ledger.predicate_identity")).toHaveLength(2);
  expect(names.filter((name) => name === "ledger.predicate_revision_insert")).toHaveLength(2);
  expect(names).toContain("ledger.predicate_assertion_insert");
  expect(names).toContain("ledger.candidate_artifact_insert");
});

test("predicate identity reuse verifies its immutable semantic version", async () => {
  const same = new FakeConnection();
  same.zeroAt = "ledger.predicate_identity";
  await expect(createPostgresAuthoritativeLedgerRepository({ pool: new FakePool(same) })
    .append(context(), vocabularyRequest())).resolves.toMatchObject({ kind: "committed" });
  expect(same.statements.map((statement) => statement.name))
    .toContain("ledger.predicate_identity_verify");

  const changed = new FakeConnection();
  changed.zeroAt = "ledger.predicate_identity";
  changed.predicateIdentityVersion = "name-slots-v1";
  await expect(createPostgresAuthoritativeLedgerRepository({ pool: new FakePool(changed) })
    .append(context(), vocabularyRequest())).rejects.toMatchObject({ code: "transition_invalid" });
});

test("full inert adapter verifies committed witnesses before reserving a receipt", async () => {
  const fixture = witnessedEventRequest();
  const valid = new FakeConnection();
  valid.witness = {
    content_hash: sha256CanonicalRedacted(fixture.event as never),
    lifecycle: null, head_revision_id: null,
  };
  await expect(createPostgresAuthoritativeLedgerRepository({ pool: new FakePool(valid) })
    .append(context(), fixture.request)).resolves.toEqual({
      kind: "committed", commit_id: "commit:one", sequence: 1,
    });
  expect(valid.statements.map((statement) => statement.name).indexOf("ledger.witness_verify"))
    .toBeLessThan(valid.statements.map((statement) => statement.name).indexOf("ledger.receipt_reserve"));

  const changed = new FakeConnection();
  changed.witness = {
    content_hash: "f".repeat(64), lifecycle: null, head_revision_id: null,
  };
  await expect(createPostgresAuthoritativeLedgerRepository({ pool: new FakePool(changed) })
    .append(context(), fixture.request)).rejects.toMatchObject({ code: "transition_invalid" });
  expect(changed.statements.map((statement) => statement.name)).not.toContain("ledger.receipt_reserve");
});
