# x-connector-sync-job runbook

Dedicated Cloud Run Job for X (Twitter) connector incremental sync. Scheduler owns the 6h cadence; the entrypoint always runs `run_x_sync_job()` (no hour-modulo gate).

## Deploy

Manual: `.github/workflows/gcp_x_connector_sync_job.yml` (`workflow_dispatch`, environment `development` or `prod`).

Env contract: `cloud_run.jobs.x-connector-sync-job` in `backend/deploy/runtime_env.yaml` (compose from `_base.yaml` + overlays). Secrets match the former X path on notifications-job: `SERVICE_ACCOUNT_JSON`, `ENCRYPTION_SECRET`, `OPENAI_API_KEY`, `PINECONE_API_KEY`, plus `PINECONE_INDEX_NAME`. Interactive OAuth (`X_OAUTH_*`) stays on the API / GKE backend; add those bindings to this job later if token refresh or RapidAPI fallback must run in-job.

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
