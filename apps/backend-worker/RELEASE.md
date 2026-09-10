# Worker staging release runbook

This runbook applies the D1 Tasks, Chat, Attachments, and Recording migrations and verifies them through an operator-managed safe evidence endpoint before the Worker is deployed or declared ready.

Shared staging bearer credentials cannot select `x-omi-client-id` values beginning with `firebase:`; that namespace requires a verified Firebase session. Audio appends require a stable zero-based `chunkIndex`. A storage failure returns 503 and leaves that packet pending; retry the identical bytes and index. Different bytes at an existing index return 409. Completion returns 409 until every reserved packet is acknowledged.

Migration `0005_device_session_uploads.sql` adds a persisted successful-upload counter. Completion returns 409 until every claimed chunk has been saved. Existing open sessions with audio are conservatively marked `failed` because older counters do not prove that R2 writes succeeded; their stored audio and metadata are retained. Previously complete or failed sessions retain their historical state, and idempotent completion of an already complete session does not retroactively verify its audio. Empty legacy sessions remain usable. Review the open-session status change before applying the migration remotely.

Chat generation sends at most 40 earlier messages and 32 KiB of UTF-8 history to either configured provider, restricted to the current account, chat session, app, and message position. Cancelled assistant responses are excluded. The current message and its bounded text attachments follow that history.

Account Durable Objects serialize D1 admissions across external database awaits so simultaneous retries return the same generation and parallel requests cannot exceed the chat limit.

Migration `0007_device_audio_chunks.sql` adds the per-packet hash and acknowledgment ledger. Database triggers count each claim and successful upload once, including concurrent retries. Existing packets are not backfilled or overwritten. Ship the indexed client and Worker together; old requests without an index are rejected. The app retries transient upload and completion failures at 500, 1000 and 2000 ms, retains the head packet until acknowledgment, and cancels retries on sign-out/unmount. Its aggregate pending-memory ceiling is 8 MiB. Session opening also retries transient failures with the same native-minted capture ID and immutable metadata. This is brief interruption recovery, not persistent offline storage.

Migration `0008_device_capture_id.sql` adds a nullable capture ID and account-scoped unique index. Existing rows retain NULL capture IDs; no historical identity is fabricated. Updated clients require `createRecordingId` on the native backend bridge (or browser cryptographic UUID support). Creation requires the capture ID; coordinate the client and Worker release. Replays return the same server session, and changed device metadata returns 409.

Migration `0009_device_capture_time.sql` adds nullable `captured_at_ms`. Creation accepts optional `capturedAtMs`, a safe integer from 0 through 8,640,000,000,000,000 Unix milliseconds representing native receipt of the first packet. Invalid values, including null, are rejected. Exact replay preserves presence and value; changing either returns 409. Historical values remain unknown and are omitted from session and conversation responses. This display provenance never changes server `startedAt`/`endedAt` (also Unix milliseconds), conversation ordering, audio duration, or billing.

## Recording processing and canonical services

Migration `0006_device_transcriptions.sql` atomically queues transcription when a nonempty recording changes from open to complete with all uploads acknowledged. It does not backfill old completed recordings. The scheduled handler claims one due recording per minute, with a 15-minute lease, at most five provider attempts, and exponential retry delays capped at 15 minutes. Expired owners cannot publish results after another claim. Audio stays in R2 on processing failure. This recovers processing work; it does not recover audio lost before upload.

The processor accepts firmware PCM8 (codec 1) and Opus (20/21), validates packet continuity, and builds WAV or Ogg for `@cf/openai/whisper-large-v3-turbo`. Limits are 8 MiB of input, 65,536 packets, one hour of decoded audio, and 17 MiB of encoded output. An incomplete initial Opus frame is discarded and reported to the app; subsequent gaps fail processing. Reads use six concurrent R2 requests. The configured 70,000 subrequest allowance requires Workers Paid; verify plan support and expected recording volume before deployment. The one-job-per-minute claim rate is the current throughput ceiling.

`GET /v1/device-sessions/:id` returns the stored session projection without R2 or a capture-ownership receipt. Invalid ids stay grammar `not_found`. Missing or foreign sessions are `device_session_not_found`. `GET /v1/device-sessions/:id/transcript` returns account-scoped processing state, text, segments and any discarded-leading-packet count. Conversations project these recordings as private records and the app reads full text through native authenticated transport.

Optional `CANONICAL_SERVICE` is a Worker service binding exposing the ratified `/v1/memories`, `/v1/tasks`, and `/v1/tasks/ops` routes. Configure its actual deployed target only after provisioning the canonical service with production Firebase verification, durable storage, account/control authority, grant authority and persistent codec keys. The target must independently validate the forwarded Firebase bearer. Shared staging credentials never cross this boundary. Both task reads and writes use this binding when present; an upstream outage does not fall back to a different task authority. Without it, memory reads and task writes fail closed, while existing D1 task reads remain available. No target is invented in `wrangler.jsonc`.

## Required operator inputs

- `STAGING_D1_MIGRATION_EVIDENCE_URL`: an HTTPS URL that returns the current migration evidence envelope.
- `STAGING_D1_MIGRATION_EVIDENCE_ID`: an opaque operator-issued identifier that must appear in the evidence envelope.
- `CLOUDFLARE_API_TOKEN`: the API token that owns the Worker and D1 database.
- `CLOUDFLARE_ACCOUNT_ID`: the account that owns the Worker, D1 database, R2 bucket, and Queue.
- Worker secrets set out-of-band: `API_TOKEN`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY`. The attachment route fails closed without all three; never place their values in repository files.
- `STAGING_WORKER_URL`: the public URL used by `verify:release` after the deploy. Native capture (`/v1/device-sessions`) reads this origin from `OMI_V5_BACKEND_URL` (https only; loopback, `api.omi.me`, or `*.workers.dev`). The repository does not record a `workers.dev` default. Settings and connector reads stay on `https://api.omi.me` unless a loopback `OMI_LOCAL_BACKEND_URL` is selected.
- `STAGING_OBSERVABILITY_SINK_MODE`: `cloudflare_only` or `better_stack`.
- `STAGING_BETTER_STACK_EVIDENCE_ID`: an opaque operator evidence identifier required only for `better_stack`.

The checked-in `account_id` and `R2_ACCOUNT_ID` must identify that same account. The attachment contract test checks the real configuration against the signed URL host and bound bucket. Account selection alone does not provision the R2 signing secrets.

## Steps

1. Verify the local migration manifest. The `test/migrations.verify.test.ts` gate and the `verify:migrations` script both use `migrations/manifest.ts`, which pins the exact bytes of every migration file. Do not edit migration files after they have been applied to a D1 database.

2. Apply the D1 migrations from the `apps/backend-worker` directory:

   ```bash
   WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false \
     bun x wrangler d1 migrations apply omi-v5-backend-staging-tasks --remote --config wrangler.jsonc
   ```

3. Produce the safe evidence envelope. It must be valid JSON with `cache-control: no-store` and contain only the fields listed below. Do not include database IDs, tokens, D1 row data, or any other host or credential material.

   ```json
   {
     "schema_version": "0009_device_capture_time.sql",
     "migrations": [
       {
         "name": "0001_tasks.sql",
         "sha256": "e9b4df967b8becc1406c35b5cfed4f893b4b0640cd0daa58ab37255e93fe12d1"
       },
       {
         "name": "0002_chat.sql",
         "sha256": "f1b3da76a9d949198e066af5320d2b684e32ecc4112896e8cd2ffdad75a824d1"
       },
       {
         "name": "0003_attachments.sql",
         "sha256": "ee4efd8d61929ba0155753de9b6c5784f657b6264b90964c1c6dd34d9fc98fa3"
       },
       {
         "name": "0004_device_sessions.sql",
         "sha256": "51989ee2f63cfc36614b56cf8ca6433a41441004109ab3aa38ead02f9a2e580e"
       },
       {
         "name": "0005_device_session_uploads.sql",
         "sha256": "2652bf96d0183899970167de5527c46300910782cdef3c139ac29e02d6ee78f1"
       },
       {
         "name": "0006_device_transcriptions.sql",
         "sha256": "1e64b3a13ff926fa1e50d959625a830a09320d8c40a66ecae9a250675b1060a0"
       },
       {
         "name": "0007_device_audio_chunks.sql",
         "sha256": "57bae0f17f4ee8bdfcbd92dbf4daa713c83ea6850280b06d5cb25cfa8426060c"
       },
       {
         "name": "0008_device_capture_id.sql",
         "sha256": "4bedaeb4a22ac0a9e08fdc14bce9030135a10ccf4ec8746403a9fa0d748ef918"
       },
       {
         "name": "0009_device_capture_time.sql",
         "sha256": "d4aa1e8b83636fb5d9b49807b2a21fa511b729fb669e1bc1a1958adc3cd46fd4"
       }
     ],
     "evidence_id": "ops-20260818-1"
   }
   ```

   The verifier expects `schema_version` to match the name of the latest migration in `migrations/manifest.ts` and expects every migration to be present with the exact pinned SHA-256. Extra top-level or per-migration fields cause the preflight to fail closed.

4. Publish the evidence at `STAGING_D1_MIGRATION_EVIDENCE_URL` and run the preflight:

   ```bash
   bun run verify:migrations "${STAGING_D1_MIGRATION_EVIDENCE_URL}" \
     --evidence "${STAGING_D1_MIGRATION_EVIDENCE_ID}"
   ```

5. If the preflight passes, deploy the Worker:

   ```bash
   WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false \
     bun x wrangler deploy --strict --config wrangler.jsonc
   ```

6. Verify the release gate as described in `ROLLBACK.md`:

   ```bash
   bun run verify:release "${STAGING_WORKER_URL}/ready" \
     --environment staging \
     --observability-sink-mode "${STAGING_OBSERVABILITY_SINK_MODE}"
   ```

   For `better_stack`, append `--better-stack-evidence "${STAGING_BETTER_STACK_EVIDENCE_ID}"`.

## No deploy without verified migrations

The `backend-worker-staging` deploy job runs the D1 migration apply and the migration preflight before `wrangler deploy` and before the `/ready` release gate. If the evidence endpoint is unreachable, malformed, missing a migration, or contains a checksum mismatch, the deploy and readiness checks are refused.

The preflight script redacts the evidence URL in logs and never reads or emits database IDs, API tokens, or raw D1 rows. The migration SHA-256 values are the only database-related material in the evidence envelope.
