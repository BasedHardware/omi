import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import { LISTEN_CAPTURE_OPEN_VERSION, LISTEN_CAPTURE_FINALIZE_VERSION } from
  "../../apps/service/stores/listen-finalization-repository";
import {
  LISTEN_CAPTURE_APPEND_VERSION,
  LISTEN_CAPTURE_INTERRUPT_VERSION,
  LISTEN_CAPTURE_RESUME_VERSION,
} from "../../apps/service/stores/listen-finalization-repository";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { createPostgresListenFinalizationRepository } from "./listen-finalization-repository";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const hash = (character: string): string => character.repeat(64);
const account = "account:alice";

const authorityRow = (): AuthorityStateRow => ({
  account_id: account, principal_id: "principal:listen", application_id: "app:listen",
  credential_id: "credential:listen", credential_generation: 1, capability: "listen.capture.write",
  grant_id: "grant:listen", grant_version: 1, account_epoch: 2,
  control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 2, destination_activation_revision: 3,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 10_000,
  control_revision: 3, control_content_hash: hash("1"), credential_content_hash: hash("2"),
  grant_content_hash: hash("3"), db_now_epoch_seconds: 100,
});

const context = (capability = "listen.capture.write") => {
  const row = authorityRow();
  return createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1", principal_id: row.principal_id,
    account_id: account, application_id: row.application_id, credential_id: row.credential_id,
    credential_generation: row.credential_generation, capability,
    grant_id: row.grant_id, grant_version: row.grant_version, account_epoch: 2,
    destination_activation_revision: 3, lifecycle_state: "active", deletion_epoch: null,
    authentication_strength: row.authentication_strength, issued_at_epoch_seconds: 50,
    expires_at_epoch_seconds: 500, authorization_state_digest: authorizationStateDigest(row),
  }, 100);
};

const openRequest = () => ({
  version: LISTEN_CAPTURE_OPEN_VERSION, session_id: "session:one", conversation_id: "conversation:one",
  client_conversation_id: null, started_at: "1970-01-01T00:01:40.000Z", source: "listen",
  codec: "pcm", sample_rate: 16_000, channels: 1,
} as const);

const finalizeRequest = () => ({
  version: LISTEN_CAPTURE_FINALIZE_VERSION, session_id: "session:one",
  terminal_status: "completed" as const, ended_at: "1970-01-01T00:01:42.000Z",
});

const appendRequest = () => ({
  version: LISTEN_CAPTURE_APPEND_VERSION, session_id: "session:one",
  segment: { id: "segment:one", text: "hello", is_user: true, start: 0, end: 1 },
  appended_at: "1970-01-01T00:01:41.000Z",
});

type Rows = Record<string, readonly Record<string, unknown>[]>;

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "listen-client" });
  readonly statements: SqlStatement[] = [];
  constructor(readonly rows: Rows = {}, readonly failure: string | null = null) {}

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") return [authorityRow() as unknown as Row];
    if (this.failure && statement.name === this.failure) {
      throw Object.assign(new Error("provider detail"), { code: "P1001" });
    }
    if (statement.name === "listen.capture.finalize") {
      return [{
        result: "sealed", finalization_id: String(statement.values[1]), formation_work_id: String(statement.values[2]),
        transcript_digest: String(statement.values[10]), finalization_digest: String(statement.values[11]),
        segment_count: statement.values[9],
      } as unknown as Row];
    }
    return (this.rows[statement.name] ?? []) as readonly Row[];
  }

  async execute(): Promise<{ rowCount: number }> { return { rowCount: 1 }; }
}

class FakePool implements PostgresTransactionPool {
  calls = 0;
  identities: object[] = [];
  constructor(readonly connection: FakeConnection) {}
  async withTransaction<Result>(
    _options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.calls += 1;
    this.identities.push(this.connection.connectionIdentity);
    return callback(this.connection);
  }
}

describe("PostgreSQL Listen finalization repository", () => {
  test("preflights capability before checking out a pool connection", async () => {
    const pool = new FakePool(new FakeConnection());
    const repository = createPostgresListenFinalizationRepository({ pool });
    const wrong = context("memories.work.accept");
    await expect(repository.open(wrong, openRequest())).rejects.toMatchObject({ code: "capability_denied" });
    expect(pool.calls).toBe(0);
  });

  test("open uses one authorized connection and reports replay distinctly", async () => {
    const connection = new FakeConnection({
      "listen.capture.open": [{ result: "replayed", session_id: "session:one", conversation_id: "conversation:one" }],
    });
    const pool = new FakePool(connection);
    const outcome = await createPostgresListenFinalizationRepository({ pool }).open(context(), openRequest());
    expect(outcome).toEqual({ kind: "replayed", session_id: "session:one", conversation_id: "conversation:one" });
    expect(pool.calls).toBe(1);
    expect(new Set(pool.identities).size).toBe(1);
  });

  test("rejects an empty finalization before seal/outbox SQL", async () => {
    const connection = new FakeConnection({
      "listen.capture.read_finalization_input": [{
        session_id: "session:one", conversation_id: "conversation:one", client_conversation_id: null,
        started_at: "1970-01-01T00:01:40.000Z", source: "listen", codec: "pcm", sample_rate: 16_000,
        channels: 1, current_state: "active", segment_ordinal: null, segment_id: null,
        text_content: null, is_user: null, start_seconds: null, end_seconds: null,
      }],
    });
    const repository = createPostgresListenFinalizationRepository({ pool: new FakePool(connection) });
    await expect(repository.finalize(context(), finalizeRequest())).rejects.toMatchObject({ code: "transition_invalid" });
    expect(connection.statements.some((statement) => statement.name === "listen.capture.finalize")).toBe(false);
  });

  test("append, interrupt, and resume return fixed-function outcomes", async () => {
    const connection = new FakeConnection({
      "listen.capture.append": [{ result: "appended", segment_id: "segment:one", ordinal: "0" }],
      "listen.capture.interrupt": [{ result: "interrupted", state_sequence: "1" }],
      "listen.capture.resume": [{ result: "replayed", state_sequence: "1" }],
    });
    const repository = createPostgresListenFinalizationRepository({ pool: new FakePool(connection) });
    await expect(repository.append(context(), appendRequest())).resolves.toEqual({
      kind: "appended", session_id: "session:one", segment_id: "segment:one", ordinal: 0,
    });
    await expect(repository.interrupt(context(), {
      version: LISTEN_CAPTURE_INTERRUPT_VERSION, session_id: "session:one",
      interrupted_at: "1970-01-01T00:01:42.000Z",
    })).resolves.toEqual({ kind: "interrupted", session_id: "session:one", state_sequence: 1 });
    await expect(repository.resume(context(), {
      version: LISTEN_CAPTURE_RESUME_VERSION, session_id: "session:one",
      resumed_at: "1970-01-01T00:01:43.000Z",
    })).resolves.toEqual({ kind: "replayed", session_id: "session:one", state_sequence: 1 });
  });

  test("seals a non-empty finalization from ordered rows on the same connection", async () => {
    const connection = new FakeConnection({
      "listen.capture.read_finalization_input": [
        { session_id: "session:one", conversation_id: "conversation:one", client_conversation_id: null,
          started_at: "1970-01-01T00:01:40.000Z", source: "listen", codec: "pcm", sample_rate: 16_000,
          channels: 1, current_state: "active", segment_ordinal: "0", segment_id: "segment:one",
          text_content: "hello", is_user: true, start_seconds: 0, end_seconds: 1 },
      ],
    });
    const pool = new FakePool(connection);
    const outcome = await createPostgresListenFinalizationRepository({ pool }).finalize(context(), finalizeRequest());
    expect(outcome.kind).toBe("sealed");
    expect(connection.statements.map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "listen.capture.read_finalization_input",
      "listen.capture.finalize",
    ]);
    expect(pool.identities.every((identity) => identity === connection.connectionIdentity)).toBe(true);
  });

  test("maps fixed-function provider conflicts to a content-safe repository error", async () => {
    const connection = new FakeConnection({}, "listen.capture.open");
    const repository = createPostgresListenFinalizationRepository({ pool: new FakePool(connection) });
    await expect(repository.open(context(), openRequest())).rejects.toMatchObject({ code: "idempotency_conflict" });
    await expect(repository.open(context(), openRequest())).rejects.not.toThrow("provider detail");
  });
});
