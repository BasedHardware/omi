# Worker staging release runbook

This runbook applies the D1-authoritative Tasks, Chat, and Attachments migrations and verifies them through an operator-managed safe evidence endpoint before the Worker is deployed or declared ready.

## Required operator inputs

- `STAGING_D1_MIGRATION_EVIDENCE_URL`: an HTTPS URL that returns the current migration evidence envelope.
- `STAGING_D1_MIGRATION_EVIDENCE_ID`: an opaque operator-issued identifier that must appear in the evidence envelope.
- `CLOUDFLARE_API_TOKEN`: the API token that owns the Worker and D1 database.
- `CLOUDFLARE_ACCOUNT_ID`: the account that owns the Worker, D1 database, R2 bucket, and Queue.
- Worker secrets set out-of-band: `API_TOKEN`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY`. The attachment route fails closed without all three; never place their values in repository files.
- `STAGING_WORKER_URL`: the public URL used by `verify:release` after the deploy.
- `STAGING_OBSERVABILITY_SINK_MODE`: `cloudflare_only` or `better_stack`.
- `STAGING_BETTER_STACK_EVIDENCE_ID`: an opaque operator evidence identifier required only for `better_stack`.

## Steps

1. Verify the local migration manifest. The `test/migrations.verify.test.ts` gate and the `verify:migrations` script both use `migrations/manifest.ts`, which pins the exact bytes of every migration file. Do not edit migration files after they have been applied to a D1 database.

2. Apply the D1 migrations from the `apps/backend-worker` directory:

   ```bash
   WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false \
     bun x wrangler d1 migrations apply omi-v5-backend-staging-tasks --config wrangler.jsonc
   ```

3. Produce the safe evidence envelope. It must be valid JSON with `cache-control: no-store` and contain only the fields listed below. Do not include database IDs, tokens, D1 row data, or any other host or credential material.

   ```json
   {
     "schema_version": "0003_attachments.sql",
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
