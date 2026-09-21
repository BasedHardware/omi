import { expect, test } from "bun:test";
import postgres from "postgres";
import { createHash, randomUUID } from "node:crypto";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  ATTACHMENT_STAGING_TTL_MS,
  MAIN_CHAT_ATTACHMENT_SCOPE,
} from "../../apps/service/chat/attachment-policy";
import { withAuthorizedChatAttachments } from "./chat-attachment-repository";
import type { PostgresTransactionPool } from "./connection";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool } from "./postgresjs";
import { seedProdLocalFirebaseAuthorizationSql } from "../../scripts/prod-local-identity-seed";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const url = process.env.OMI_TEST_POSTGRES_URL;
const realTest = url ? test : test.skip;

const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00]);

realTest("real chat attachments require chat.write, stay account-scoped, and roll back", async () => {
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
  const project = "synthetic-chat-attachment-project";
  const app = "synthetic-chat-attachment-app";
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
        name: "chat_attachment_test.role",
        text: "SET LOCAL ROLE omi_platform_application",
        values: [],
      });
      return callback(connection);
    }),
  };
  const insertGrant = async (target: string, capability: string) => {
    await owner.unsafe(
      `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) VALUES($1,$2,$3,1,$4,$5,1,'active',true,'[]','grant-v1','{}',$6)`,
      [target, app, credential, capability, `${capability}-${suffix}`, "3".repeat(64)],
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

    await expect(withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.stage({
        id: "att-foreign",
        contentReference: "ref-foreign",
        accountId: other,
        scope: MAIN_CHAT_ATTACHMENT_SCOPE,
        displayName: "note.png",
        mimeType: "image/png",
        content: png,
        stagedAt: 1_000,
        stageExpiresAt: 1_000 + ATTACHMENT_STAGING_TTL_MS,
      }),
    )).rejects.toMatchObject({ code: "authorization_state_denied" });

    await owner.unsafe(
      `INSERT INTO omi_memory.chat_attachments (
        account_id, id, content_reference, attachment_scope, display_name, mime_type,
        size_bytes, attachment_state, scanner_id, scanning_started_at, staged_at,
        stage_expires_at, bound_message_id, bound_at, content_expires_at, content_bytes
      ) VALUES ($1,'att-other','ref-other','main','other.png','image/png',$2,'staged','dev-noop-scanner',NULL,1000,1000+$3,NULL,NULL,NULL,$4)`,
      [other, png.byteLength, ATTACHMENT_STAGING_TTL_MS, png],
    );
    await expect(appPool.withTransaction({ isolationLevel: "serializable", accessMode: "read write" }, async (connection) => {
      await connection.query({
        name: "chat_attachment_test.role",
        text: "SET LOCAL ROLE omi_platform_application",
        values: [],
      });
      await connection.query({
        name: "chat_attachment_test.rls_guc",
        text: `SELECT set_config('omi.account_id', $1, true),
          set_config('omi.principal_id', $2, true),
          set_config('omi.capability', 'chat.write', true)`,
        values: [account, principal],
      });
      const selected = await connection.query({
        name: "chat_attachment_test.rls_select",
        text: "SELECT id FROM omi_memory.chat_attachments WHERE account_id=$1",
        values: [other],
      });
      expect(selected).toEqual([]);
      const updated = await connection.execute({
        name: "chat_attachment_test.rls_update",
        text: "UPDATE omi_memory.chat_attachments SET display_name='hijacked' WHERE account_id=$1 AND id='att-other'",
        values: [other],
      });
      expect(updated.rowCount).toBe(0);
      return connection.execute({
        name: "chat_attachment_test.rls_insert",
        text: `INSERT INTO omi_memory.chat_attachments (
          account_id, id, content_reference, attachment_scope, display_name, mime_type,
          size_bytes, attachment_state, scanner_id, scanning_started_at, staged_at,
          stage_expires_at, bound_message_id, bound_at, content_expires_at, content_bytes
        ) VALUES ($1,'att-rls','ref-rls','main','rls.png','image/png',$2,'staged','dev-noop-scanner',NULL,1000,1000+$3,NULL,NULL,NULL,$4)`,
        values: [other, png.byteLength, ATTACHMENT_STAGING_TTL_MS, png],
      });
    })).rejects.toMatchObject({ code: "42501" });
    const foreignUntouched = await owner.unsafe(
      `SELECT display_name, id FROM omi_memory.chat_attachments WHERE account_id=$1`,
      [other],
    );
    expect(foreignUntouched).toEqual([{ display_name: "other.png", id: "att-other" }]);

    await owner.unsafe(`CREATE FUNCTION omi_memory.review_abort_second_attachment() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.id = 'att-abort' THEN RAISE EXCEPTION 'review attachment abort'; END IF;
        RETURN NEW;
      END $$`);
    await owner.unsafe(`CREATE TRIGGER review_abort_second_attachment BEFORE INSERT
      ON omi_memory.chat_attachments FOR EACH ROW
      EXECUTE FUNCTION omi_memory.review_abort_second_attachment()`);
    try {
      await expect(withAuthorizedChatAttachments(
        appPool,
        context,
        new AbortController().signal,
        async (storage) => {
          await storage.stage({
            id: "att-keep",
            contentReference: "ref-keep",
            accountId: account,
            scope: MAIN_CHAT_ATTACHMENT_SCOPE,
            displayName: "keep.png",
            mimeType: "image/png",
            content: png,
            stagedAt: 1_000,
            stageExpiresAt: 1_000 + ATTACHMENT_STAGING_TTL_MS,
          });
          return storage.stage({
            id: "att-abort",
            contentReference: "ref-abort",
            accountId: account,
            scope: MAIN_CHAT_ATTACHMENT_SCOPE,
            displayName: "note.png",
            mimeType: "image/png",
            content: png,
            stagedAt: 1_000,
            stageExpiresAt: 1_000 + ATTACHMENT_STAGING_TTL_MS,
          });
        },
      )).rejects.toMatchObject({ code: "persistence_failed" });
      const aborted = await owner.unsafe(
        `SELECT count(*)::int AS n FROM omi_memory.chat_attachments WHERE account_id=$1`,
        [account],
      );
      expect(aborted[0]?.n).toBe(0);
    } finally {
      await owner.unsafe("DROP TRIGGER review_abort_second_attachment ON omi_memory.chat_attachments");
      await owner.unsafe("DROP FUNCTION omi_memory.review_abort_second_attachment()");
    }

    const staged = await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.stage({
        id: "att-1",
        contentReference: "ref-1",
        accountId: account,
        scope: MAIN_CHAT_ATTACHMENT_SCOPE,
        displayName: "note.png",
        mimeType: "image/png",
        content: png,
        stagedAt: 1_000,
        stageExpiresAt: 1_000 + ATTACHMENT_STAGING_TTL_MS,
      }),
    );
    expect(staged.state).toBe("staged");
    expect(staged.sizeBytes).toBe(png.byteLength);

    const clock = { now: () => 1_500 };
    const scanned = await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      async (storage) => {
        await storage.advanceScan("att-1", clock);
        return storage.advanceScan("att-1", clock);
      },
    );
    expect(scanned?.state).toBe("clean");
    expect(await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.retryScan("att-1", clock),
    )).toBeNull();

    const bound = await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.bindToMessage({
        accountId: account,
        scope: MAIN_CHAT_ATTACHMENT_SCOPE,
        attachmentIds: ["att-1"],
        messageId: "msg-1",
        nowEpochMilliseconds: 2_000,
        contentExpiresAt: 2_000,
      }),
    );
    expect(bound.kind).toBe("ready");
    expect(await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.removeUnbound("att-1", account),
    )).toBe(false);

    const expired = await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.projectMessageAttachments({
        accountId: account,
        messageId: "msg-1",
        nowEpochMilliseconds: 2_001,
        attachments: [{
          id: "att-1",
          displayName: "note.png",
          mediaType: "image/png",
          sizeBytes: png.byteLength,
          contentReference: "ref-1",
        }],
      }),
    );
    expect(expired[0]?.contentReference).toBeNull();
    const cleared = await owner.unsafe(
      `SELECT content_reference, content_bytes FROM omi_memory.chat_attachments WHERE account_id=$1 AND id='att-1'`,
      [account],
    );
    expect(cleared[0]?.content_reference).toBeNull();
    expect(cleared[0]?.content_bytes).toBeNull();

    const timedOut = await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.stage({
        id: "att-timeout",
        contentReference: "ref-timeout",
        accountId: account,
        scope: MAIN_CHAT_ATTACHMENT_SCOPE,
        displayName: "retry.png",
        mimeType: "image/png",
        content: png,
        stagedAt: 3_000,
        stageExpiresAt: 3_000 + ATTACHMENT_STAGING_TTL_MS,
      }),
    );
    expect(timedOut.state).toBe("staged");
    await owner.unsafe(
      `UPDATE omi_memory.chat_attachments SET attachment_state='timed_out', scanning_started_at=10 WHERE account_id=$1 AND id='att-timeout'`,
      [account],
    );
    const retried = await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.retryScan("att-timeout", clock),
    );
    expect(retried?.state).toBe("clean");
    expect(await withAuthorizedChatAttachments(
      appPool,
      context,
      new AbortController().signal,
      (storage) => storage.removeUnbound("att-timeout", account),
    )).toBe(true);
    const remaining = await owner.unsafe(
      `SELECT id FROM omi_memory.chat_attachments WHERE account_id=$1 ORDER BY id`,
      [account],
    );
    expect(remaining.map((row) => row.id)).toEqual(["att-1"]);
  } finally {
    await pool.close();
    await owner.end();
  }
});
