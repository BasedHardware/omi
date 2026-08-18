# Worker version rollback runbook

This runbook reverts the Cloudflare Worker to a previously uploaded version using Wrangler version management. It requires the `wrangler` CLI, a valid `CLOUDFLARE_API_TOKEN`, and a target `VERSION_ID`.

## Required operator inputs

- `VERSION_ID`: the target version to roll back to, from `wrangler versions list`.
- `CLOUDFLARE_API_TOKEN`: the API token that owns the Worker.
- `CLOUDFLARE_ACCOUNT_ID`: the account that owns the Worker.
- `STAGING_WORKER_URL`: the public URL used by `verify:ready` after the rollback.

## Steps

1. List deployable versions from the `apps/backend-worker` directory:

   ```bash
   WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false \
     bun x wrangler versions list --config wrangler.jsonc
   ```

2. Check the first-release no-rollback boundary. If the list contains only one version, the current one, stop. There is no previous safe version to roll back to. Rolling back would take the Worker offline.

3. Set the target version and dry-run the rollback:

   ```bash
   VERSION_ID="..."
   WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false \
     bun x wrangler versions deploy "${VERSION_ID}@100" --config wrangler.jsonc --dry-run
   ```

4. If the dry-run is correct, deploy the version:

   ```bash
   WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false \
     bun x wrangler versions deploy "${VERSION_ID}@100" --config wrangler.jsonc
   ```

5. Verify the rolled-back worker:

   ```bash
   bun run verify:ready "${STAGING_WORKER_URL}/ready"
   ```

## First-release no-rollback boundary

Do not roll back a first release. When `wrangler versions list` shows a single version, fix forward or redeploy from the repository instead. The CI `deploy` job also stops and requires operator confirmation because it runs only on `workflow_dispatch`.
