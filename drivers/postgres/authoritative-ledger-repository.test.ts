import { expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  authoritativeAppendRequestDigest,
  type AuthoritativeLedgerAppend,
} from "../../apps/service/stores/authoritative-ledger-repository";
import { prepareDerivation, type AtomicGraphTransition } from "../../core/ledger";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { createPostgresSuccessfulEmptyLedgerRepository } from "./authoritative-ledger-repository";
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
  authority: Record<string, unknown> = authorityRow();

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
    if (statement.name === "ledger.head_lock") return [this.head as Row];
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (this.failAt === statement.name) throw new Error("private database failure");
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
