import { expect, test } from "bun:test";
import postgres from "postgres";
import { createHash, randomUUID } from "node:crypto";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool } from "./postgresjs";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseConversationReadRuntime } from "./firebase-conversation-read-runtime";
import { seedProdLocalFirebaseAuthorizationSql } from "../../scripts/prod-local-identity-seed";

const url = process.env.OMI_TEST_POSTGRES_URL;
const realTest = url ? test : test.skip;
realTest(
  "real conversation reads expose persisted recordings with account, grant and cursor fences",
  async () => {
    const endpoint = new URL(url!);
    if (endpoint.hostname !== "127.0.0.1" || endpoint.protocol !== "postgres:")
      throw Error("postgres_test_not_loopback_only");
    const owner = postgres(url!, { max: 1 });
    const pool = createPostgresJsTransactionPool({
      connectionString: url!,
      maxConnections: 2,
    });
    const suffix = randomUUID(),
      generation = createHash("sha256").update(suffix).digest("hex"),
      now = () => Math.floor(Date.now() / 1000);
    const project = "synthetic-task-project",
      app = "synthetic-task-app",
      uid = `uid-${suffix}`,
      account = `account-${suffix}`,
      principal = `principal-${suffix}`,
      credential = `credential-${suffix}`;
    try {
      await owner.unsafe(`DO $roles$ BEGIN
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_application') THEN CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_cleanup') THEN CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore') THEN CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore_operator') THEN CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
    END $roles$;`);
      await runPostgresMigrations(owner);
      for (const target of [account, `other-${suffix}`]) {
        for (const statement of seedProdLocalFirebaseAuthorizationSql(
          {
            firebase_project_id: project,
            firebase_uid: target === account ? uid : `other-${uid}`,
            application_id: app,
            account_id: target,
            principal_id: principal,
            credential_id: credential,
            grant_id: `memory-${suffix}`,
          },
          now()
        ))
          await owner.unsafe(statement.text, [...statement.values]);
        for (const capability of ["conversations.read"]) {
          await owner.unsafe(
            `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) VALUES($1,$2,$3,1,$4,$5,1,'active',true,'[]','grant-v1','{}',$6)`,
            [
              target,
              app,
              credential,
              capability,
              `${capability}-${suffix}`,
              "3".repeat(64),
            ]
          );
          await owner.unsafe(
            `INSERT INTO omi_memory.application_grant_heads(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version) VALUES($1,$2,$3,1,$4,$5,1)`,
            [target, app, credential, capability, `${capability}-${suffix}`]
          );
        }
      }
      await owner.unsafe(
        `INSERT INTO omi_memory.postgres_restore_admission_revisions(database_generation_digest,release_revision,state,restore_id,restored_snapshot_digest,checkpoint_candidate_digest,checkpoint_evidence_digest,first_approval_subject_digest,first_approval_receipt_digest,second_approval_subject_digest,second_approval_receipt_digest,manual_release_receipt_digest,previous_release_revision,content_hash) VALUES($1,1,'released',$2,$3,$3,$3,$4,$5,$6,$7,$3,NULL,$3)`,
        [
          generation,
          `synthetic-${suffix}`,
          "9".repeat(64),
          "4".repeat(64),
          "5".repeat(64),
          "6".repeat(64),
          "7".repeat(64),
        ]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.postgres_restore_admission_heads(database_generation_digest,release_revision) VALUES($1,1)",
        [generation]
      );

      const failures: string[] = [];
      const loadedPageSizes: number[] = [];
      const appPool: PostgresTransactionPool = {
        withTransaction: (options, callback) =>
          pool
            .withTransaction(options, async (connection) => {
              await connection.query({
                name: "conversation_test.role",
                text: "SET LOCAL ROLE omi_platform_application",
                values: [],
              });
              return callback({
                ...connection,
                async query(statement) {
                  const rows = await connection.query(statement);
                  if (
                    statement.name === "conversations.read_page" &&
                    rows[0]?.snapshot
                  )
                    loadedPageSizes.push(
                      (rows[0].snapshot as any).records.length
                    );
                  return rows;
                },
              });
            })
            .catch((error) => {
              failures.push(String(error.code ?? error.message));
              throw error;
            }),
      };
      const makeRuntime = () =>
        createPostgresFirebaseConversationReadRuntime({
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
                const selected = token.startsWith("other")
                  ? `other-${uid}`
                  : uid;
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
      let runtime = makeRuntime();
      const call = (query = "", token = "header.payload.signature") =>
        runtime.executeRequest(
          new Request(
            `https://conversations.example/v1/conversations${query}`,
            { headers: { authorization: `Bearer ${token}` } }
          )
        );
      const insert = async (
        target: string,
        state: string | null,
        text: string,
        visible = true
      ) => {
        const id = randomUUID();
        await owner.unsafe(
          "INSERT INTO omi_memory.listen_capture_sessions(account_id,session_id,conversation_id,started_at,source,codec,sample_rate,channels,content_hash) VALUES($1,$2,$3,clock_timestamp()-interval '2 seconds','omi','21',16000,1,$4)",
          [target, id, `conversation:${id}`, "1".repeat(64)]
        );
        await owner.unsafe(
          "INSERT INTO omi_memory.listen_capture_audio_uploads(account_id,session_id,capture_id,device_id,codec_id,upload_completed_at) VALUES($1,$2::text,$2::uuid,'synthetic-device',21,CASE WHEN $3::boolean THEN clock_timestamp() ELSE NULL END)",
          [target, id, visible]
        );
        if (state)
          await owner.unsafe(
            "INSERT INTO omi_memory.listen_audio_transcriptions(account_id,session_id,state,attempts,available_at,updated_at,provider_result) VALUES($1,$2,$3,1,clock_timestamp(),clock_timestamp(),$4::text::jsonb)",
            [
              target,
              id,
              state,
              JSON.stringify({
                durationSeconds: 1,
                segments: text ? [{ text, start: 0, end: 1, speaker: 0 }] : [],
              }),
            ]
          );
        return id;
      };
      await expect(
        Promise.resolve(owner.unsafe("SELECT omi_memory.read_listen_conversation_snapshot()"))
      ).rejects.toMatchObject({ code: "42883" });
      const delayed = await insert(account, null, "", false);
      const queued = await insert(account, null, "");
      const failed = await insert(account, "failed", "must remain hidden");
      const completed = await insert(
        account,
        "completed",
        "Actual persisted transcript " + "z".repeat(1000)
      );
      const silent = await insert(account, "completed", "");
      await insert(`other-${suffix}`, "completed", "Other private transcript");
      const first = await call("?limit=2");
      expect(first.status, failures.join(",")).toBe(200);
      const page = (await first.json()) as any;
      expect(page.items.map((item: any) => item.id)).toEqual([
        `recording:${queued}`,
        `recording:${failed}`,
      ]);
      expect(
        page.items.map((item: any) => [item.status, item.overview])
      ).toEqual([
        ["processing", ""],
        ["failed", ""],
      ]);
      const cursor = page.window.nextCursor;
      runtime = makeRuntime();
      expect(
        (
          await call(
            "?cursor=" + encodeURIComponent(cursor),
            "other.payload.signature"
          )
        ).status
      ).toBe(400);

      const next = (await (
        await call(`?limit=100&cursor=${encodeURIComponent(cursor)}`)
      ).json()) as any;
      expect(next.items.map((item: any) => item.id)).toEqual([
        `recording:${completed}`,
        `recording:${silent}`,
      ]);
      expect(next.items[0].overview.length).toBe(240);
      expect(next.items[0].status).toBe("completed");
      expect(next.items[1].overview).toBe("");
      expect(next.items[1].status).toBe("completed");
      expect(next.items[0].revision).toBe(page.items[0].revision);
      await owner.unsafe(
        "UPDATE omi_memory.listen_capture_audio_uploads SET upload_completed_at=clock_timestamp() WHERE account_id=$1 AND session_id=$2",
        [account, delayed]
      );
      expect((await call(`?cursor=${encodeURIComponent(cursor)}`)).status).toBe(
        400
      );
      const refreshed = (await (await call()).json()) as any;
      expect(refreshed.items[0].id).toBe(`recording:${delayed}`);
      const regrantCursor = ((await (await call("?limit=1")).json()) as any)
        .window.nextCursor;
      const other = (await (
        await call("", "other.payload.signature")
      ).json()) as any;
      expect(other.items).toHaveLength(1);
      expect(other.items[0].overview).toBe("Other private transcript");
      await owner.unsafe(
        "DELETE FROM omi_memory.application_grant_heads WHERE account_id=$1 AND capability='conversations.read'",
        [`other-${suffix}`]
      );
      expect((await call("", "other.payload.signature")).status).toBe(403);
      await owner.unsafe(
        "UPDATE omi_memory.application_grant_revisions SET enabled=false WHERE account_id=$1 AND capability='conversations.read'",
        [account]
      );
      expect((await call()).status).toBe(403);
      await owner.unsafe(
        "UPDATE omi_memory.application_grant_revisions SET enabled=true,content_hash=$2 WHERE account_id=$1 AND capability='conversations.read'",
        [account, "a".repeat(64)]
      );
      expect(
        (await call(`?cursor=${encodeURIComponent(regrantCursor)}`)).status
      ).toBe(400);
      expect((await call()).status).toBe(200);
      const listenId = `listen-${suffix}`;
      await owner.unsafe(
        "INSERT INTO omi_memory.listen_capture_sessions(account_id,session_id,conversation_id,started_at,source,codec,sample_rate,channels,content_hash) VALUES($1,$2,$2,clock_timestamp()-interval '2 seconds','microphone','pcm',16000,1,$3)",
        [account, listenId, "1".repeat(64)]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.listen_capture_segments(account_id,session_id,ordinal,segment_id,text_content,is_user,start_seconds,end_seconds,appended_at,content_hash) VALUES($1,$2,0,$2,'Persisted microphone words',true,0,1,clock_timestamp(),$3)",
        [account, listenId, "1".repeat(64)]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.listen_formation_finalizations(account_id,finalization_id,formation_work_id,session_id,conversation_id,terminal_status,capture_completeness,started_at,ended_at,source,segment_count,transcript_digest,finalization_digest,content_hash) SELECT account_id,session_id,session_id,session_id,conversation_id,'completed','complete',started_at,clock_timestamp(),source,1,$3,$3,$3 FROM omi_memory.listen_capture_sessions WHERE account_id=$1 AND session_id=$2",
        [account, listenId, "1".repeat(64)]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.listen_conversation_finalization_intents(account_id,conversation_id,finalization_id,intent,locked,content_hash) VALUES($1,$2,$2,'process_memories',true,$3)",
        [account, listenId, "1".repeat(64)]
      );
      const withListen = (await (await call()).json()) as any;
      expect(
        withListen.items.find((item: any) => item.id === listenId)
      ).toMatchObject({
        overview: "Persisted microphone words",
        source: "microphone",
        status: "processing",
        isLocked: true,
      });
      await owner.unsafe(
        `WITH inserted AS (INSERT INTO omi_memory.listen_capture_sessions(account_id,session_id,conversation_id,started_at,source,codec,sample_rate,channels,content_hash)
          SELECT $1,id::text,id::text,clock_timestamp()-interval '2 seconds','omi','21',16000,1,$2 FROM (SELECT gen_random_uuid() AS id FROM generate_series(1,10020)) ids RETURNING account_id,session_id)
        INSERT INTO omi_memory.listen_capture_audio_uploads(account_id,session_id,capture_id,device_id,codec_id,upload_completed_at)
        SELECT account_id,session_id,session_id::uuid,'large-account-device',21,clock_timestamp() FROM inserted`,
        [account, "1".repeat(64)]
      );
      loadedPageSizes.length = 0;
      let nextCursor: string | null = null;
      const seen = new Set<string>();
      do {
        const response = await call(
          "?limit=100" +
            (nextCursor === null
              ? ""
              : "&cursor=" + encodeURIComponent(nextCursor))
        );
        expect(response.status, failures.join(",")).toBe(200);
        const result = (await response.json()) as any;
        for (const item of result.items) {
          expect(seen.has(item.id)).toBe(false);
          seen.add(item.id);
        }
        nextCursor = result.window.nextCursor;
      } while (nextCursor !== null);
      expect(seen.size).toBe(10026);
      expect(Math.max(...loadedPageSizes)).toBeLessThanOrEqual(102);
      const tail = await owner.unsafe(
        "SELECT session_id FROM omi_memory.listen_capture_sessions WHERE account_id=$1 ORDER BY conversation_sequence DESC LIMIT 1",
        [account]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.listen_audio_transcriptions(account_id,session_id,state,attempts,available_at,updated_at,provider_result) VALUES($1,$2,'completed',1,clock_timestamp(),clock_timestamp(),NULL)",
        [account, tail[0]!.session_id]
      );
      expect((await call("?limit=100")).status).toBe(200);
      await owner.unsafe(
        "UPDATE omi_memory.listen_audio_transcriptions SET state='queued' WHERE account_id=$1 AND session_id=$2",
        [account, tail[0]!.session_id]
      );
      const expiring = (await (await call("?limit=1")).json()) as any;
      const expiringHash = createHash("sha256")
        .update(expiring.window.nextCursor)
        .digest("hex");
      await owner.unsafe(
        "UPDATE omi_memory.listen_conversation_cursor_positions SET expires_at=0 WHERE account_id=$1 AND cursor_hash=$2",
        [account, expiringHash]
      );
      expect(
        (
          await call(
            "?cursor=" + encodeURIComponent(expiring.window.nextCursor)
          )
        ).status
      ).toBe(400);
      await owner.unsafe(
        "UPDATE omi_memory.listen_conversation_cursor_positions SET expires_at=floor(extract(epoch FROM clock_timestamp()))+900 WHERE account_id=$1",
        [account]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.listen_conversation_cursor_positions(account_id,cursor_hash,binding_digest,revision,sequence,expires_at) SELECT $1,lpad(n::text,64,'a'),repeat('f',64),1,1,floor(extract(epoch FROM clock_timestamp()))+900 FROM generate_series(1,10000-(SELECT count(*)::int FROM omi_memory.listen_conversation_cursor_positions WHERE account_id=$1)) n",
        [account]
      );
      expect((await call("?limit=3")).status).toBe(503);
      await owner.unsafe(
        "UPDATE omi_memory.listen_conversation_cursor_positions SET expires_at=0 WHERE account_id=$1 AND binding_digest=repeat('f',64)",
        [account]
      );
      expect((await call("?limit=3")).status).toBe(200);
      expect((await call("?offset=100&limit=2")).status).toBe(200);
      expect((await call("?limit=0")).status).toBe(400);
      expect((await call("?limit=1&limit=2")).status).toBe(400);
      await owner.unsafe(
        "UPDATE omi_memory.listen_audio_transcriptions SET provider_result=NULL WHERE account_id=$1 AND session_id=$2",
        [account, silent]
      );
      expect((await call()).status).toBe(503);
      await expect(
        appPool.withTransaction(
          { isolationLevel: "serializable", accessMode: "read only" },
          (connection) =>
            connection.query({
              name: "conversation_test.raw",
              text: "SELECT * FROM omi_memory.listen_conversation_read_revisions",
              values: [],
            })
        )
      ).rejects.toMatchObject({ code: "42501" });
    } finally {
      await pool.close();
      await owner.end();
    }
  },
  120000
);

realTest(
  "real conversation reads compose granted chat sessions without inventing empty chat:chat-main",
  async () => {
    const endpoint = new URL(url!);
    if (endpoint.hostname !== "127.0.0.1" || endpoint.protocol !== "postgres:")
      throw Error("postgres_test_not_loopback_only");
    const owner = postgres(url!, { max: 1 });
    const pool = createPostgresJsTransactionPool({
      connectionString: url!,
      maxConnections: 2,
    });
    const suffix = randomUUID(),
      generation = createHash("sha256").update(suffix).digest("hex"),
      now = () => Math.floor(Date.now() / 1000);
    const project = "synthetic-chat-conversation-project",
      app = "synthetic-chat-conversation-app",
      uid = `uid-${suffix}`,
      account = `account-${suffix}`,
      principal = `principal-${suffix}`,
      credential = `credential-${suffix}`;
    try {
      await owner.unsafe(`DO $roles$ BEGIN
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_application') THEN CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_cleanup') THEN CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore') THEN CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore_operator') THEN CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
    END $roles$;`);
      await runPostgresMigrations(owner);
      for (const statement of seedProdLocalFirebaseAuthorizationSql(
        {
          firebase_project_id: project,
          firebase_uid: uid,
          application_id: app,
          account_id: account,
          principal_id: principal,
          credential_id: credential,
          grant_id: `memory-${suffix}`,
        },
        now()
      ))
        await owner.unsafe(statement.text, [...statement.values]);
      for (const capability of ["conversations.read"]) {
        await owner.unsafe(
          `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) VALUES($1,$2,$3,1,$4,$5,1,'active',true,'[]','grant-v1','{}',$6)`,
          [account, app, credential, capability, `${capability}-${suffix}`, "3".repeat(64)]
        );
        await owner.unsafe(
          `INSERT INTO omi_memory.application_grant_heads(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version) VALUES($1,$2,$3,1,$4,$5,1)`,
          [account, app, credential, capability, `${capability}-${suffix}`]
        );
      }
      await owner.unsafe(
        `INSERT INTO omi_memory.postgres_restore_admission_revisions(database_generation_digest,release_revision,state,restore_id,restored_snapshot_digest,checkpoint_candidate_digest,checkpoint_evidence_digest,first_approval_subject_digest,first_approval_receipt_digest,second_approval_subject_digest,second_approval_receipt_digest,manual_release_receipt_digest,previous_release_revision,content_hash) VALUES($1,1,'released',$2,$3,$3,$3,$4,$5,$6,$7,$3,NULL,$3)`,
        [generation, `synthetic-${suffix}`, "9".repeat(64), "4".repeat(64), "5".repeat(64), "6".repeat(64), "7".repeat(64)]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.postgres_restore_admission_heads(database_generation_digest,release_revision) VALUES($1,1)",
        [generation]
      );
      const appPool: PostgresTransactionPool = {
        withTransaction: (options, callback) =>
          pool.withTransaction(options, async (connection) => {
            await connection.query({
              name: "conversation_chat_test.role",
              text: "SET LOCAL ROLE omi_platform_application",
              values: [],
            });
            return callback(connection);
          }),
      };
      const runtime = createPostgresFirebaseConversationReadRuntime({
        authorization: {
          pool: appPool,
          project_id: project,
          application_id: app,
          runtime_mode: "deployed",
          context_ttl_seconds: 60,
          database_generation_digest: generation,
          id_token_adapter: {
            verification_source: "firebase_production",
            async verifyIdToken() {
              return {
                aud: project,
                iss: `https://securetoken.google.com/${project}`,
                sub: uid,
                uid,
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
      const call = (query = "") =>
        runtime.executeRequest(
          new Request(`https://conversations.example/v1/conversations${query}`, {
            headers: { authorization: "Bearer header.payload.signature" },
          })
        );
      const ids = (body: { items: Array<{ id: string }> }) => body.items.map((item) => item.id);
      await owner.unsafe(
        `INSERT INTO omi_memory.chat_messages(account_id,id,text,sender,message_type,created_at,updated_at,chat_session_id,app_id,journal_revision,payload_hash,message_source,rating,reported,server_revision,attachments_json,generation_id) VALUES($1,$2,'saved prompt','human','text',1000,1000,NULL,NULL,0,'sha256:human','desktop_chat',NULL,false,'rev-human','[]'::jsonb,'gen_human')`,
        [account, "11111111-1111-4111-8111-111111111111"]
      );
      const withoutGrant = (await (await call()).json()) as { items: Array<{ id: string }> };
      expect(ids(withoutGrant)).not.toContain("chat:chat-main");
      await owner.unsafe(
        `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) VALUES($1,$2,$3,1,$4,$5,1,'active',true,'[]','grant-v1','{}',$6)`,
        [account, app, credential, "chat.read", `chat.read-${suffix}`, "3".repeat(64)]
      );
      await owner.unsafe(
        `INSERT INTO omi_memory.application_grant_heads(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version) VALUES($1,$2,$3,1,$4,$5,1)`,
        [account, app, credential, "chat.read", `chat.read-${suffix}`]
      );
      const emptyListen = (await (await call()).json()) as {
        items: Array<{ id: string; title: string; source: string; status: string }>;
        absence: unknown;
        window: { nextCursor: string | null };
      };
      expect(emptyListen.absence).toBeNull();
      expect(emptyListen.items).toEqual([
        expect.objectContaining({
          id: "chat:chat-main",
          title: "saved prompt",
          overview: "saved prompt",
          source: "chat",
          status: "in_progress",
        }),
      ]);
      const first = randomUUID();
      const second = randomUUID();
      for (const id of [first, second]) {
        await owner.unsafe(
          "INSERT INTO omi_memory.listen_capture_sessions(account_id,session_id,conversation_id,started_at,source,codec,sample_rate,channels,content_hash) VALUES($1,$2,$3,clock_timestamp()-interval '2 seconds','omi','21',16000,1,$4)",
          [account, id, `conversation:${id}`, "1".repeat(64)]
        );
        await owner.unsafe(
          "INSERT INTO omi_memory.listen_capture_audio_uploads(account_id,session_id,capture_id,device_id,codec_id,upload_completed_at) VALUES($1,$2::text,$2::uuid,'synthetic-device',21,clock_timestamp())",
          [account, id]
        );
        await owner.unsafe(
          "INSERT INTO omi_memory.listen_audio_transcriptions(account_id,session_id,state,attempts,available_at,updated_at,provider_result) VALUES($1,$2,'completed',1,clock_timestamp(),clock_timestamp(),$3::text::jsonb)",
          [
            account,
            id,
            JSON.stringify({
              durationSeconds: 1,
              segments: [{ text: `recording ${id}`, start: 0, end: 1, speaker: 0 }],
            }),
          ]
        );
      }
      const firstPage = (await (await call("?limit=1")).json()) as {
        items: Array<{ id: string }>;
        window: { nextCursor: string | null; hasMore: boolean };
      };
      expect(ids(firstPage)).toContain("chat:chat-main");
      expect(firstPage.items).toHaveLength(2);
      expect(firstPage.window.hasMore).toBe(true);
      expect(firstPage.window.nextCursor).not.toBeNull();
      const secondPage = (await (
        await call(`?limit=1&cursor=${encodeURIComponent(firstPage.window.nextCursor!)}`)
      ).json()) as { items: Array<{ id: string }> };
      expect(ids(secondPage)).not.toContain("chat:chat-main");
      expect(secondPage.items).toHaveLength(1);
      await owner.unsafe(
        "DELETE FROM omi_memory.application_grant_heads WHERE account_id=$1 AND capability='chat.read'",
        [account]
      );
      const revoked = (await (await call("?limit=1")).json()) as { items: Array<{ id: string }> };
      expect(ids(revoked)).not.toContain("chat:chat-main");
      expect(revoked.items).toHaveLength(1);
    } finally {
      await pool.close();
      await owner.end();
    }
  },
  60000
);
