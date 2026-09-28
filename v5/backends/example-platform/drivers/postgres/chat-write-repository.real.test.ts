import { expect, test } from "bun:test";
import postgres from "postgres";
import { createHash, randomUUID } from "node:crypto";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import type { ChatMessageRecord } from "../../apps/service/stores/chat-messages-store";
import { withAuthorizedChatWrite, type ChatAdmissionReservation } from "./chat-write-repository";
import type { PostgresTransactionPool } from "./connection";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool } from "./postgresjs";
import { seedProdLocalFirebaseAuthorizationSql } from "../../scripts/prod-local-identity-seed";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const url = process.env.OMI_TEST_POSTGRES_URL;
const realTest = url ? test : test.skip;

const human = (overrides: Partial<ChatMessageRecord> = {}): ChatMessageRecord => ({
  id: "client-1",
  text: "hello",
  sender: "human",
  type: "text",
  createdAt: 100,
  updatedAt: 100,
  chatSessionId: null,
  appId: null,
  journalRevision: 1,
  payloadHash: "sha256:one",
  messageSource: "desktop_chat",
  rating: null,
  reported: false,
  revision: "revision-1",
  attachments: [],
  ...overrides,
});

const reservation = (): ChatAdmissionReservation => ({
  catalogRevision: "catalog-2",
  subscriptionRevision: "sub-1",
  usagePeriodUtc: "2026-09",
  billingUnit: "chat_message",
});

realTest("real chat writes require chat.write, grant tables, and refuse missing reservation", async () => {
  const endpoint = new URL(url!);
  if (endpoint.hostname !== "127.0.0.1" || endpoint.protocol !== "postgres:") {
    throw Error("postgres_test_not_loopback_only");
  }
  const owner = postgres(url!, { max: 1 });
  const pool = createPostgresJsTransactionPool({
    connectionString: url!,
    maxConnections: 2,
  });
  const suffix = randomUUID();
  const generation = createHash("sha256").update(suffix).digest("hex");
  const now = () => Math.floor(Date.now() / 1000);
  const project = "synthetic-chat-write-project";
  const app = "synthetic-chat-write-app";
  const uid = `uid-${suffix}`;
  const account = `account-${suffix}`;
  const other = `other-${suffix}`;
  const principal = `principal-${suffix}`;
  const credential = `credential-${suffix}`;
  const grantId = `chat.write-${suffix}`;
  const restoreRelease = Object.freeze({
    database_generation_digest: generation,
    restore_release_revision: 1,
    restore_release_content_hash: "9".repeat(64),
  });
  const appPool: PostgresTransactionPool = {
    withTransaction: (options, callback) => pool.withTransaction(options, async (connection) => {
      await connection.query({
        name: "chat_write_test.role",
        text: "SET LOCAL ROLE omi_platform_application",
        values: [],
      });
      return callback(connection);
    }),
  };
  const insertGrant = async (target: string, capability: string, lifecycle = "active") => {
    await owner.unsafe(
      `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) VALUES($1,$2,$3,1,$4,$5,1,$6,true,'[]','grant-v1','{}',$7)`,
      [target, app, credential, capability, `${capability}-${suffix}`, lifecycle, "3".repeat(64)],
    );
    await owner.unsafe(
      `INSERT INTO omi_memory.application_grant_heads(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version) VALUES($1,$2,$3,1,$4,$5,1)`,
      [target, app, credential, capability, `${capability}-${suffix}`],
    );
  };
  try {
    await owner.unsafe(`DO $roles$ BEGIN
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_application') THEN CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_cleanup') THEN CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore') THEN CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore_operator') THEN CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
    END $roles$;`);
    await runPostgresMigrations(owner);
    for (const target of [account, other]) {
      for (const statement of seedProdLocalFirebaseAuthorizationSql({
        firebase_project_id: project,
        firebase_uid: target === account ? uid : `other-${uid}`,
        application_id: app,
        account_id: target,
        principal_id: principal,
        credential_id: credential,
        grant_id: `memory-${suffix}`,
      }, now())) {
        await owner.unsafe(statement.text, [...statement.values]);
      }
      await insertGrant(target, "chat.write");
    }
    await owner.unsafe(
      `INSERT INTO omi_memory.postgres_restore_admission_revisions(database_generation_digest,release_revision,state,restore_id,restored_snapshot_digest,checkpoint_candidate_digest,checkpoint_evidence_digest,first_approval_subject_digest,first_approval_receipt_digest,second_approval_subject_digest,second_approval_receipt_digest,manual_release_receipt_digest,previous_release_revision,content_hash) VALUES($1,1,'released',$2,$3,$3,$3,$4,$5,$6,$7,$3,NULL,$3)`,
      [generation, `synthetic-${suffix}`, "9".repeat(64), "4".repeat(64), "5".repeat(64), "6".repeat(64), "7".repeat(64)],
    );
    await owner.unsafe(
      "INSERT INTO omi_memory.postgres_restore_admission_heads(database_generation_digest,release_revision) VALUES($1,1)",
      [generation],
    );

    const authority: AuthorityStateRow = {
      account_id: account,
      principal_id: principal,
      application_id: app,
      credential_id: credential,
      credential_generation: 1,
      capability: "chat.write",
      grant_id: grantId,
      grant_version: 1,
      account_epoch: 1,
      control_conflict_reason: null,
      control_conflict_at_revision: null,
      destination_activation_epoch: 1,
      destination_activation_revision: 1,
      lifecycle_state: "active",
      deletion_epoch: null,
      account_generation: "new",
      credential_lifecycle: "active",
      grant_lifecycle: "active",
      grant_enabled: true,
      authentication_strength: "firebase-id-token",
      credential_expires_at_epoch_seconds: now() + 31_536_000,
      control_revision: 1,
      control_content_hash: "1".repeat(64),
      credential_content_hash: "2".repeat(64),
      grant_content_hash: "3".repeat(64),
      db_now_epoch_seconds: now(),
    };
    const context = createAuthorizedLedgerWriteContextIssuer().issueRestored({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principal,
      account_id: account,
      application_id: app,
      credential_id: credential,
      credential_generation: 1,
      capability: "chat.write",
      grant_id: grantId,
      grant_version: 1,
      account_epoch: 1,
      destination_activation_revision: 1,
      lifecycle_state: "active",
      deletion_epoch: null,
      authentication_strength: "firebase-id-token",
      issued_at_epoch_seconds: now() - 10,
      expires_at_epoch_seconds: now() + 600,
      authorization_state_digest: authorizationStateDigest(authority, restoreRelease),
    }, restoreRelease, now());

    const input = {
      accountId: account,
      message: human(),
      generationId: "generation-1",
      acceptedEventId: "event-1",
      admittedAt: 200,
      attachmentIds: [] as const,
    };

    await expect(withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.admit(input, null),
    )).resolves.toEqual({ kind: "entitlement" });

    await owner.unsafe(`CREATE FUNCTION omi_memory.review_abort_accepted() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'review accepted event abort'; END $$`);
    await owner.unsafe(`CREATE TRIGGER review_abort_accepted BEFORE INSERT
      ON omi_memory.chat_generation_events FOR EACH ROW
      EXECUTE FUNCTION omi_memory.review_abort_accepted()`);
    try {
      await expect(withAuthorizedChatWrite(
        appPool, context, new AbortController().signal,
        storage => storage.admit(input, reservation()),
      )).rejects.toMatchObject({ code: "persistence_failed" });
      for (const table of ["chat_messages", "chat_admission_reservations", "chat_generation_events"]) {
        const rows = await owner.unsafe(
          `SELECT count(*)::int AS n FROM omi_memory.${table} WHERE account_id=$1`,
          [account],
        );
        expect(rows[0]?.n).toBe(0);
      }
    } finally {
      await owner.unsafe("DROP TRIGGER review_abort_accepted ON omi_memory.chat_generation_events");
      await owner.unsafe("DROP FUNCTION omi_memory.review_abort_accepted()");
    }

    const created = await withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.admit(input, reservation()),
    );
    expect(created.kind).toBe("created");
    if (created.kind !== "created") throw new Error("expected created");
    expect(created.stored.message.createdAt).toBe(100);
    expect(created.stored.message.journalRevision).toBe(1);
    const reserved = await owner.unsafe(
      `SELECT payload_hash, catalog_revision, usage_period_utc FROM omi_memory.chat_admission_reservations WHERE account_id=$1 AND message_id=$2`,
      [account, "client-1"],
    );
    expect(reserved).toHaveLength(1);
    expect(reserved[0]?.payload_hash).toBe("sha256:one");

    const replay = await withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.admit(input, reservation()),
    );
    expect(replay.kind).toBe("replay");
    const reservedAgain = await owner.unsafe(
      `SELECT count(*)::text AS n FROM omi_memory.chat_admission_reservations WHERE account_id=$1`,
      [account],
    );
    expect(reservedAgain[0]?.n).toBe("1");

    const conflict = await withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.admit({
        ...input,
        message: human({ text: "mutated", payloadHash: "sha256:two" }),
      }, reservation()),
    );
    expect(conflict.kind).toBe("conflict");

    const assistant = human({
      id: "assistant-1",
      sender: "ai",
      text: "answer",
      payloadHash: "sha256:assistant",
    });
    await expect(withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      async (storage) => {
        await storage.finalize({
          accountId: account,
          generationId: "generation-1",
          eventId: "event-crash",
          createdAt: 300,
          frame: { kind: "done", message: assistant },
        });
        throw new Error("injected post-write abort");
      },
    )).rejects.toMatchObject({ code: "persistence_failed" });
    const rolledBack = await owner.unsafe(
      `SELECT count(*)::int AS n FROM omi_memory.chat_messages WHERE account_id=$1 AND id='assistant-1'`,
      [account],
    );
    expect(rolledBack[0]?.n).toBe(0);

    const done = await withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.finalize({
        accountId: account,
        generationId: "generation-1",
        eventId: "event-done",
        createdAt: 300,
        frame: { kind: "done", message: assistant },
      }),
    );
    expect(done.frame.kind).toBe("done");

    await owner.unsafe(
      `UPDATE omi_memory.application_grant_revisions SET lifecycle='revoked' WHERE account_id=$1 AND capability='chat.write'`,
      [account],
    );
    await expect(withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.admit({
        ...input,
        message: human({ id: "client-revoked", payloadHash: "sha256:revoked" }),
        generationId: "generation-revoked",
        acceptedEventId: "event-revoked",
      }, reservation()),
    )).rejects.toMatchObject({ code: "grant_inactive" });

    await owner.unsafe(
      `UPDATE omi_memory.application_grant_revisions SET lifecycle='active' WHERE account_id=$1 AND capability='chat.write'`,
      [account],
    );
    await expect(withAuthorizedChatWrite(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.admit({
        ...input,
        accountId: other,
        message: human({ id: "client-foreign", payloadHash: "sha256:foreign" }),
        generationId: "generation-foreign",
        acceptedEventId: "event-foreign",
      }, reservation()),
    )).rejects.toMatchObject({ code: "authorization_state_denied" });
  } finally {
    await pool.close();
    await owner.end();
  }
});
