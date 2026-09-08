import { expect, test } from "bun:test";
import postgres from "postgres";
import { createHash, randomUUID } from "node:crypto";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool } from "./postgresjs";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseChatReadRuntime } from "./firebase-chat-read-runtime";
import { seedProdLocalFirebaseAuthorizationSql } from "../../scripts/prod-local-identity-seed";
import { CHAT_CAPABILITIES } from "../../apps/service/routes/chat-messages";

const url = process.env.OMI_TEST_POSTGRES_URL;
const realTest = url ? test : test.skip;

realTest("real chat reads require chat.read and never invent empty success", async () => {
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
  const project = "synthetic-chat-project";
  const app = "synthetic-chat-app";
  const uid = `uid-${suffix}`;
  const account = `account-${suffix}`;
  const principal = `principal-${suffix}`;
  const credential = `credential-${suffix}`;
  const humanId = "11111111-1111-4111-8111-111111111111";
  const aiId = "22222222-2222-4222-8222-222222222222";
  const generationId = "gen_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  try {
    await owner.unsafe(`DO $roles$ BEGIN
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_application') THEN CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_cleanup') THEN CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore') THEN CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore_operator') THEN CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
    END $roles$;`);
    await runPostgresMigrations(owner);
    for (const target of [account, `other-${suffix}`]) {
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
      await owner.unsafe(
        `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) VALUES($1,$2,$3,1,$4,$5,1,'active',true,'[]','grant-v1','{}',$6)`,
        [target, app, credential, "chat.read", `chat.read-${suffix}`, "3".repeat(64)],
      );
      await owner.unsafe(
        `INSERT INTO omi_memory.application_grant_heads(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version) VALUES($1,$2,$3,1,$4,$5,1)`,
        [target, app, credential, "chat.read", `chat.read-${suffix}`],
      );
    }
    await owner.unsafe(
      `INSERT INTO omi_memory.postgres_restore_admission_revisions(database_generation_digest,release_revision,state,restore_id,restored_snapshot_digest,checkpoint_candidate_digest,checkpoint_evidence_digest,first_approval_subject_digest,first_approval_receipt_digest,second_approval_subject_digest,second_approval_receipt_digest,manual_release_receipt_digest,previous_release_revision,content_hash) VALUES($1,1,'released',$2,$3,$3,$3,$4,$5,$6,$7,$3,NULL,$3)`,
      [generation, `synthetic-${suffix}`, "9".repeat(64), "4".repeat(64), "5".repeat(64), "6".repeat(64), "7".repeat(64)],
    );
    await owner.unsafe(
      "INSERT INTO omi_memory.postgres_restore_admission_heads(database_generation_digest,release_revision) VALUES($1,1)",
      [generation],
    );
    const appPool: PostgresTransactionPool = {
      withTransaction: (options, callback) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "chat_test.role",
          text: "SET LOCAL ROLE omi_platform_application",
          values: [],
        });
        return callback(connection);
      }),
    };
    const runtime = createPostgresFirebaseChatReadRuntime({
      authorization: {
        pool: appPool,
        project_id: project,
        application_id: app,
        runtime_mode: "deployed",
        context_ttl_seconds: 60,
        database_generation_digest: generation,
        id_token_adapter: {
          verification_source: "firebase_production",
          async verifyIdToken(token) {
            const selected = token.startsWith("other") ? `other-${uid}` : uid;
            return {
              aud: project,
              iss: `https://securetoken.google.com/${project}`,
              sub: selected,
              uid: selected,
              iat: now() - 10,
              auth_time: now() - 10,
              exp: now() + 600,
            };
          },
        },
      },
      codecRootSecret: new Uint8Array(32).fill(7),
      cursorSigningKeyset: {
        active_key_id: "test",
        keys: [{ key_id: "test", secret: new Uint8Array(32).fill(8) }],
      },
    });
    const call = (query = "?limit=50", token = "header.payload.signature", method = "GET") =>
      runtime.executeRequest(new Request(`https://chat.example/v1/chat-messages${query}`, {
        method,
        headers: { authorization: `Bearer ${token}` },
        ...(method === "POST" ? { body: "{}" } : {}),
      }));
    const empty = await call();
    expect(empty.status).toBe(200);
    expect(await empty.json()).toEqual({
      messages: [],
      page: { olderCursor: null, hasOlder: false },
      capabilities: CHAT_CAPABILITIES,
    });
    await owner.unsafe(
      `INSERT INTO omi_memory.chat_messages(account_id,id,text,sender,message_type,created_at,updated_at,chat_session_id,app_id,journal_revision,payload_hash,message_source,rating,reported,server_revision,attachments_json,generation_id) VALUES($1,$2,'hello','human','text',1000,1000,NULL,NULL,0,'sha256:human','desktop_chat',NULL,false,'rev-human','[]'::jsonb,'gen_human')`,
      [account, humanId],
    );
    const human = await call();
    expect(human.status).toBe(200);
    const humanPage = await human.json() as {
      messages: Array<{ sender: string; generationOutcome: unknown; attachments: unknown }>;
      page: { olderCursor: string | null; hasOlder: boolean };
    };
    expect(humanPage.messages).toHaveLength(1);
    expect(humanPage.messages[0]?.sender).toBe("human");
    expect(humanPage.messages[0]?.generationOutcome).toBeNull();
    expect(humanPage.messages[0]?.attachments).toEqual([]);
    expect(humanPage.page).toEqual({ olderCursor: null, hasOlder: false });
    await owner.unsafe(
      `INSERT INTO omi_memory.chat_messages(account_id,id,text,sender,message_type,created_at,updated_at,chat_session_id,app_id,journal_revision,payload_hash,message_source,rating,reported,server_revision,attachments_json,generation_id) VALUES($1,$2,'answer','ai','text',2000,2000,NULL,NULL,0,'sha256:ai','desktop_chat',NULL,false,'rev-ai','[]'::jsonb,$3)`,
      [account, aiId, generationId],
    );
    expect((await call()).status).toBe(503);
    const assistant = {
      id: aiId,
      text: "answer",
      sender: "ai",
      type: "text",
      createdAt: 2000,
      updatedAt: 2000,
      chatSessionId: null,
      appId: null,
      journalRevision: 0,
      payloadHash: "sha256:ai",
      messageSource: "desktop_chat",
      rating: null,
      reported: false,
      revision: "rev-ai",
      attachments: [],
    };
    await owner.unsafe(
      `INSERT INTO omi_memory.chat_generation_events(account_id,generation_id,sequence,event_id,created_at,frame_json) VALUES($1,$2,1,'evt-done',2000,$3::text::jsonb)`,
      [account, generationId, JSON.stringify({ kind: "done", message: assistant })],
    );
    const completed = await call();
    expect(completed.status).toBe(200);
    const completedPage = await completed.json() as {
      messages: Array<{ id: string; sender: string; generationOutcome: unknown }>;
    };
    expect(completedPage.messages.map((row) => [row.id, row.sender, row.generationOutcome])).toEqual([
      [humanId, "human", null],
      [aiId, "ai", "completed"],
    ]);
    const namedId = "33333333-3333-4333-8333-333333333333";
    await owner.unsafe(
      `INSERT INTO omi_memory.chat_messages(account_id,id,text,sender,message_type,created_at,updated_at,chat_session_id,app_id,journal_revision,payload_hash,message_source,rating,reported,server_revision,attachments_json,generation_id) VALUES($1,$2,'named prompt','human','text',3000,3000,'session-alpha',NULL,0,'sha256:named','desktop_chat',NULL,false,'rev-named','[]'::jsonb,'gen_named')`,
      [account, namedId],
    );
    const defaultPage = await call();
    expect(defaultPage.status).toBe(200);
    expect(
      ((await defaultPage.json()) as { messages: Array<{ id: string }> }).messages.map((row) => row.id),
    ).toEqual([humanId, aiId]);
    const named = await call("?limit=50&chatSessionId=session-alpha");
    expect(named.status).toBe(200);
    expect(
      ((await named.json()) as { messages: Array<{ id: string }> }).messages.map((row) => row.id),
    ).toEqual([namedId]);
    const storedMainId = "55555555-5555-4555-8555-555555555555";
    await owner.unsafe(
      `INSERT INTO omi_memory.chat_messages(account_id,id,text,sender,message_type,created_at,updated_at,chat_session_id,app_id,journal_revision,payload_hash,message_source,rating,reported,server_revision,attachments_json,generation_id) VALUES($1,$2,'stored as chat-main','human','text',2500,2500,'chat-main',NULL,0,'sha256:main','desktop_chat',NULL,false,'rev-main','[]'::jsonb,'gen_main')`,
      [account, storedMainId],
    );
    const storedMainDefault = await call();
    expect(storedMainDefault.status).toBe(200);
    expect(
      ((await storedMainDefault.json()) as { messages: Array<{ id: string }> }).messages.map((row) => row.id),
    ).toEqual([humanId, aiId, storedMainId]);
    const aliasedMain = await call("?limit=50&chatSessionId=chat-main");
    expect(aliasedMain.status).toBe(200);
    expect(
      ((await aliasedMain.json()) as { messages: Array<{ id: string }> }).messages.map((row) => row.id),
    ).toEqual([humanId, aiId, storedMainId]);
    const namedAfterStoredMain = await call("?limit=50&chatSessionId=session-alpha");
    expect(namedAfterStoredMain.status).toBe(200);
    expect(
      ((await namedAfterStoredMain.json()) as { messages: Array<{ id: string }> }).messages.map((row) => row.id),
    ).toEqual([namedId]);
    expect((await call("?limit=50&appId=other")).status).toBe(400);
    expect((await call("?limit=50&chatSessionId=")).status).toBe(400);
    expect((await call("", "other.payload.signature")).status).toBe(200);
    expect(await (await call("", "other.payload.signature")).json()).toEqual({
      messages: [],
      page: { olderCursor: null, hasOlder: false },
      capabilities: CHAT_CAPABILITIES,
    });
    await owner.unsafe(
      "DELETE FROM omi_memory.application_grant_heads WHERE account_id=$1 AND capability='chat.read'",
      [account],
    );
    expect((await call()).status).toBe(403);
    expect((await call("", "header.payload.signature", "POST")).status).toBe(404);
  } finally {
    await pool.close();
    await owner.end();
  }
});
