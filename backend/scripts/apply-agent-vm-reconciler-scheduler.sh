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
install_paused="${AGENT_VM_RECONCILER_SCHEDULER_PAUSED:-0}"
if [[ -z "$project" || -z "$scheduler_sa" ]]; then
  echo "AGENT_VM_RECONCILER_PROJECT and AGENT_VM_RECONCILER_SCHEDULER_SA are required." >&2
  exit 2
fi
if [[ "$install_paused" != "0" && "$install_paused" != "1" ]]; then
  echo "AGENT_VM_RECONCILER_SCHEDULER_PAUSED must be 0 or 1." >&2
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
scope=(
  "--location=$region"
  "--project=$project"
)
target=(
  "--schedule=*/5 * * * *"
  "--time-zone=Etc/UTC"
  "--uri=$uri"
  "--http-method=POST"
  "--oauth-service-account-email=$scheduler_sa"
)

if gcloud scheduler jobs describe "$scheduler_job" "${scope[@]}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$scheduler_job" "${scope[@]}" "${target[@]}"
else
  if [[ "$install_paused" == "1" ]]; then
    # Cloud Scheduler does not offer an atomic create-paused operation. Create
    # with a valid cron expression that can never match, pause it, verify the
    # state, then install the live schedule while it remains paused.
    paused_target=(
      "--schedule=0 0 31 2 *"
      "${target[@]:1}"
    )
    gcloud scheduler jobs create http "$scheduler_job" "${scope[@]}" "${paused_target[@]}"
    gcloud scheduler jobs pause "$scheduler_job" "${scope[@]}"
    [[ "$(gcloud scheduler jobs describe "$scheduler_job" "${scope[@]}" --format='value(state)')" == "PAUSED" ]]
    gcloud scheduler jobs update http "$scheduler_job" "${scope[@]}" "${target[@]}"
  else
    gcloud scheduler jobs create http "$scheduler_job" "${scope[@]}" "${target[@]}"
  fi
fi
current_state="$(gcloud scheduler jobs describe "$scheduler_job" "${scope[@]}" --format='value(state)')"
if [[ "$install_paused" == "1" ]]; then
  if [[ "$current_state" == "ENABLED" ]]; then
    gcloud scheduler jobs pause "$scheduler_job" "${scope[@]}"
  elif [[ "$current_state" != "PAUSED" ]]; then
    echo "ERROR: scheduler is in unsupported state ${current_state}." >&2
    exit 1
  fi
  expected_state="PAUSED"
else
  if [[ "$current_state" == "PAUSED" ]]; then
    gcloud scheduler jobs resume "$scheduler_job" "${scope[@]}"
  elif [[ "$current_state" != "ENABLED" ]]; then
    echo "ERROR: scheduler is in unsupported state ${current_state}." >&2
    exit 1
  fi
  expected_state="ENABLED"
fi
python3 backend/scripts/validate_agent_vm_reconciler_scheduler.py \
  --state-file <(gcloud scheduler jobs describe "$scheduler_job" "${scope[@]}" --format=json) \
  --project "$project" --region "$region" --scheduler-job "$scheduler_job" --cloud-run-job "$job" \
  --scheduler-service-account "$scheduler_sa" --expected-state "$expected_state"
