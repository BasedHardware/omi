import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlStatement } from "./connection";
import { createPostgresDurableMemoryWorkBacklogSource } from "./durable-memory-work-backlog";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const now = 150;
const authorityRow: AuthorityStateRow = {
  account_id: "account:one", principal_id: "worker:one", application_id: "app:worker",
  credential_id: "credential:one", credential_generation: 1,
  capability: "memories.work.execute", grant_id: "grant:one", grant_version: 1,
  account_epoch: 2, control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 2, destination_activation_revision: 3,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 300,
  control_revision: 3, control_content_hash: "a".repeat(64),
  credential_content_hash: "b".repeat(64), grant_content_hash: "c".repeat(64),
  db_now_epoch_seconds: now,
};
const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: authorityRow.principal_id, account_id: authorityRow.account_id,
  application_id: authorityRow.application_id, credential_id: authorityRow.credential_id,
  credential_generation: authorityRow.credential_generation,
  capability: authorityRow.capability, grant_id: authorityRow.grant_id,
  grant_version: authorityRow.grant_version, account_epoch: authorityRow.account_epoch!,
  destination_activation_revision: authorityRow.destination_activation_revision!,
  lifecycle_state: "active", deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 250,
  authorization_state_digest: authorizationStateDigest(authorityRow),
}, now);

const rows = [
  { work_kind: "formation", ready: "2", leased: "1", retry_wait: "3", dead: "4", oldest_ready_event_time: "140" },
  { work_kind: "promotion", ready: "0", leased: "0", retry_wait: "0", dead: "0", oldest_ready_event_time: null },
  { work_kind: "identity_cluster", ready: "0", leased: "0", retry_wait: "0", dead: "0", oldest_ready_event_time: null },
  { work_kind: "predicate_batch", ready: "0", leased: "0", retry_wait: "0", dead: "0", oldest_ready_event_time: null },
];

const pool = (backlogRows: readonly Record<string, unknown>[]) => {
  const statements: string[] = [];
  const connection: CheckedOutPostgresConnection = {
    connectionIdentity: {},
    query: async <Row extends Record<string, unknown>>(statement: SqlStatement) => {
      statements.push(statement.name);
      if (statement.name === "authority.lock_and_revalidate") return [authorityRow] as Row[];
      if (statement.name === "work.backlog.coherent_snapshot") return backlogRows as Row[];
      return [];
    },
    execute: async () => ({ rowCount: 0 }),
  };
  const transactionPool: PostgresTransactionPool = {
    withTransaction: async (_options, callback) => callback(connection),
  };
  return { transactionPool, statements };
};

describe("PostgreSQL durable memory work backlog", () => {
  test("loads all work kinds with database-time age after authority revalidation", async () => {
    const fixture = pool(rows);
    const source = createPostgresDurableMemoryWorkBacklogSource({ pool: fixture.transactionPool });
    await expect(source.snapshot(context())).resolves.toEqual({
      version: "durable-memory-work-backlog-snapshot-v1",
      rows: [
        { work_kind: "formation", ready: 2, leased: 1, retry_wait: 3, dead: 4, oldest_ready_age_ms: 10_000 },
        { work_kind: "promotion", ready: 0, leased: 0, retry_wait: 0, dead: 0, oldest_ready_age_ms: null },
        { work_kind: "identity_cluster", ready: 0, leased: 0, retry_wait: 0, dead: 0, oldest_ready_age_ms: null },
        { work_kind: "predicate_batch", ready: 0, leased: 0, retry_wait: 0, dead: 0, oldest_ready_age_ms: null },
      ],
    });
    expect(fixture.statements).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "work.backlog.coherent_snapshot",
    ]);
  });

  test("fails closed on partial, reordered, malformed, or future-time rows", async () => {
    for (const invalid of [
      rows.slice(0, 3),
      [...rows].reverse(),
      rows.map((row, index) => index === 0 ? { ...row, ready: "01" } : row),
      rows.map((row, index) => index === 0 ? { ...row, oldest_ready_event_time: "151" } : row),
    ]) {
      await expect(createPostgresDurableMemoryWorkBacklogSource({
        pool: pool(invalid).transactionPool,
      }).snapshot(context())).rejects.toMatchObject({ code: "persistence_failed" });
    }
  });
});
