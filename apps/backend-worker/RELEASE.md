# Worker staging release runbook

This runbook applies the D1-authoritative Tasks, Chat, and Attachments migrations and verifies them through an operator-managed safe evidence endpoint before the Worker is deployed or declared ready.

Shared staging bearer credentials cannot select `x-omi-client-id` values beginning with `firebase:`; that namespace requires a verified Firebase session. If storing a device audio chunk fails, the session becomes `failed` and subsequent append or completion requests return 409. Start a new recording session after resolving the storage failure; failed sessions must not be presented as complete recordings.

Migration `0005_device_session_uploads.sql` adds a persisted successful-upload counter. Completion returns 409 until every claimed chunk has been saved. Existing open sessions with audio are conservatively marked `failed` because older counters do not prove that R2 writes succeeded; their stored audio and metadata are retained. Previously complete or failed sessions retain their historical state, and idempotent completion of an already complete session does not retroactively verify its audio. Empty legacy sessions remain usable. Review the open-session status change before applying the migration remotely.

Chat generation sends at most 40 earlier messages and 32 KiB of UTF-8 history to either configured provider, restricted to the current account, chat session, app, and message position. Cancelled assistant responses are excluded. The current message and its bounded text attachments follow that history.

Account Durable Objects serialize D1 admissions across external database awaits so simultaneous retries return the same generation and parallel requests cannot exceed the chat limit.

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
     "schema_version": "0005_device_session_uploads.sql",
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
