# x-connector-sync-job runbook

Dedicated Cloud Run Job for X (Twitter) connector incremental sync. Scheduler owns the 6h cadence; the entrypoint always runs `run_x_sync_job()` (no hour-modulo gate).

## Deploy

Manual: `.github/workflows/gcp_x_connector_sync_job.yml` (`workflow_dispatch`, environment `development` or `prod`).

Env contract: `cloud_run.jobs.x-connector-sync-job` in `backend/deploy/runtime_env.yaml` (compose from `_base.yaml` + overlays). Required for `run_x_sync_job()`:

- Secrets: `SERVICE_ACCOUNT_JSON`, `ENCRYPTION_SECRET`, `OPENAI_API_KEY`, `PINECONE_API_KEY`, `X_OAUTH_CLIENT_SECRET`, `RAPID_API_KEY`
- Env: `PINECONE_INDEX_NAME`, `X_OAUTH_CLIENT_ID`, `X_OAUTH_REDIRECT_URI`, `RAPID_API_HOST`, `OMI_ENV_STAGE`

Interactive OAuth connect/callback still lives on the GKE API; this job needs the same OAuth + RapidAPI bindings so incremental sync can refresh expired access tokens and use the public-timeline fallback.

### Rollout order (no sync gap)

Deploying a notifications-job image that no longer runs X sync **before** this job + Scheduler exist stops all incremental sync. Required sequence per environment:

1. Ensure Secret Manager has `X_OAUTH_CLIENT_SECRET` / `RAPID_API_KEY`, and GitHub env vars `X_OAUTH_CLIENT_ID` / `X_OAUTH_REDIRECT_URI` / `RAPID_API_HOST` for the deploy environment.
2. Create Scheduler SA + `x-connector-sync-6h` (below) after the Cloud Run Job resource exists (or create the job stub first).
3. Run `gcp_x_connector_sync_job.yml` until deploy + scheduler validation both pass.
4. Only then deploy the notifications-job revision that dropped X sync.

## Manual execute

```bash
# Dev
gcloud run jobs execute x-connector-sync-job \
  --region=us-central1 \
  --project=based-hardware-dev \
  --wait

# Prod
gcloud run jobs execute x-connector-sync-job \
  --region=us-central1 \
  --project=based-hardware \
  --wait
```

## Cloud Scheduler (6h)

Create once per environment (not done by the deploy workflow; workflow only **validates** an existing job):

```bash
PROJECT=based-hardware-dev   # or based-hardware for prod
REGION=us-central1
SCHEDULER_SA=x-connector-sync-scheduler@${PROJECT}.iam.gserviceaccount.com

gcloud scheduler jobs create http x-connector-sync-6h \
  --location="$REGION" \
  --project="$PROJECT" \
  --schedule="0 */6 * * *" \
  --time-zone="Etc/UTC" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/x-connector-sync-job:run" \
  --http-method=POST \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

Update an existing job:

```bash
gcloud scheduler jobs update http x-connector-sync-6h \
  --location=us-central1 \
  --project="$PROJECT" \
  --schedule="0 */6 * * *" \
  --time-zone="Etc/UTC" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT}/locations/us-central1/jobs/x-connector-sync-job:run" \
  --http-method=POST \
  --oauth-service-account-email="$SCHEDULER_SA"
```

Pattern checklist: [`docs/doc/developer/backend/cloud_run_jobs_checklist.md`](../../../docs/doc/developer/backend/cloud_run_jobs_checklist.md).
