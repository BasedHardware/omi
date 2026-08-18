# Worker version rollback runbook

This runbook reverts the Cloudflare Worker to a previously uploaded version using Wrangler version management. It requires the `wrangler` CLI, a valid `CLOUDFLARE_API_TOKEN`, and a target `VERSION_ID`.

## Required operator inputs

- `VERSION_ID`: the target version to roll back to, from `wrangler versions list`.
- `CLOUDFLARE_API_TOKEN`: the API token that owns the Worker.
- `CLOUDFLARE_ACCOUNT_ID`: the account that owns the Worker.
- `STAGING_WORKER_URL`: the public URL used by `verify:ready` after the rollback.
- `STAGING_OBSERVABILITY_SINK_MODE`: `cloudflare_only` or `better_stack`.
- `STAGING_BETTER_STACK_EVIDENCE_ID`: an opaque operator evidence identifier required only for `better_stack`.

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

5. Verify the rolled-back worker and release configuration:

   ```bash
   bun run verify:release "${STAGING_WORKER_URL}/ready" \
     --environment staging \
     --observability-sink-mode "${STAGING_OBSERVABILITY_SINK_MODE}"
   ```

   For `better_stack`, append `--better-stack-evidence "${STAGING_BETTER_STACK_EVIDENCE_ID}"`.

`cloudflare_only` means native Workers Observability is the configured sink. `better_stack` requires an operator to provision the external Cloudflare log delivery and verify a matching correlation-safe event in Better Stack before issuing the opaque evidence identifier. This repository never contains the delivery URL or source token, and the release verifier validates the identifier shape only; it does not prove external ingestion.

## First-release no-rollback boundary

Do not roll back a first release. When `wrangler versions list` shows a single version, fix forward or redeploy from the repository instead. The CI `deploy` job also stops and requires operator confirmation because it runs only on `workflow_dispatch`. Preserve the rollback command output, release-gate result, worker version selected, and any Better Stack evidence identifier in the operator change record; none is telemetry proof unless the external sink was verified separately.
