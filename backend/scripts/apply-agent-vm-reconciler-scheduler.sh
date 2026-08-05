#!/usr/bin/env bash
# Create or update the five-minute Cloud Scheduler trigger for the Agent VM
# reconciler.  The Cloud Run Job and its runtime identity are deployed by the
# desktop-backend workflow; this script only installs the external trigger.
set -euo pipefail

if [[ "${AGENT_VM_RECONCILER_SCHEDULER_APPLY:-}" != "1" ]]; then
  echo "REFUSED: set AGENT_VM_RECONCILER_SCHEDULER_APPLY=1 to mutate Cloud Scheduler." >&2
  exit 1
fi
if [[ "${AGENT_VM_RECONCILER_PROXY_LEASES_READY:-}" != "1" ]]; then
  echo "REFUSED: deploy and verify Agent Proxy session leases first; set AGENT_VM_RECONCILER_PROXY_LEASES_READY=1 after that check." >&2
  exit 1
fi

project="${AGENT_VM_RECONCILER_PROJECT:-}"
region="${AGENT_VM_RECONCILER_REGION:-us-central1}"
job="${AGENT_VM_RECONCILER_JOB:-agent-vm-reconciler}"
scheduler_job="${AGENT_VM_RECONCILER_SCHEDULER_JOB:-agent-vm-reconciler-5m}"
scheduler_sa="${AGENT_VM_RECONCILER_SCHEDULER_SA:-}"
if [[ -z "$project" || -z "$scheduler_sa" ]]; then
  echo "AGENT_VM_RECONCILER_PROJECT and AGENT_VM_RECONCILER_SCHEDULER_SA are required." >&2
  exit 2
fi

if [[ "$scheduler_sa" == *@* ]]; then
  scheduler_sa_name="${scheduler_sa%@*}"
else
  scheduler_sa_name="$scheduler_sa"
  scheduler_sa="${scheduler_sa_name}@${project}.iam.gserviceaccount.com"
fi
if ! gcloud iam service-accounts describe "$scheduler_sa" --project="$project" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$scheduler_sa_name" --project="$project" --display-name="Omi Agent VM reconciler scheduler"
fi
gcloud run jobs add-iam-policy-binding "$job" \
  --project="$project" --region="$region" \
  --member="serviceAccount:${scheduler_sa}" --role=roles/run.invoker

uri="https://run.googleapis.com/v2/projects/${project}/locations/${region}/jobs/${job}:run"
common=(
  "--location=$region"
  "--project=$project"
  "--schedule=*/5 * * * *"
  "--time-zone=Etc/UTC"
  "--uri=$uri"
  "--http-method=POST"
  "--oauth-service-account-email=$scheduler_sa"
)

if gcloud scheduler jobs describe "$scheduler_job" "${common[@]:0:2}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$scheduler_job" "${common[@]}"
  # Updating retains a paused state.  Resuming here makes re-apply converge on
  # the required enabled contract instead of silently leaving reconciliation off.
  gcloud scheduler jobs resume "$scheduler_job" "${common[@]:0:2}"
else
  gcloud scheduler jobs create http "$scheduler_job" "${common[@]}"
fi
python3 backend/scripts/validate_agent_vm_reconciler_scheduler.py \
  --state-file <(gcloud scheduler jobs describe "$scheduler_job" "${common[@]:0:2}" --format=json) \
  --project "$project" --region "$region" --scheduler-job "$scheduler_job" --cloud-run-job "$job" \
  --scheduler-service-account "$scheduler_sa"
