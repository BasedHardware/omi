#!/usr/bin/env bash
# Apply the prod agent-vm-reaper CronJob + workload-identity bindings.
#
# Refuse-by-default. Safe first apply installs DRY_RUN=true. Live deletes require
# a second apply with AGENT_VM_REAPER_LIVE=1 (sets CronJob DRY_RUN=false).
#
# Usage:
#   # preview / install dry-run CronJob (creates GSA + IAM + ConfigMap + CronJob)
#   AGENT_VM_REAPER_APPLY=1 bash backend/scripts/apply-agent-vm-reaper.sh
#
#   # after reviewing CronJob logs, enable deletes
#   AGENT_VM_REAPER_APPLY=1 AGENT_VM_REAPER_LIVE=1 bash backend/scripts/apply-agent-vm-reaper.sh
#
#   # one-shot local dry-run against live inventory (no cluster mutation)
#   python3 backend/scripts/agent_vm_reaper.py --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT="${GCE_PROJECT:-based-hardware}"
GSA_NAME="${AGENT_VM_REAPER_GSA:-agent-vm-reaper}"
GSA_EMAIL="${GSA_NAME}@${PROJECT}.iam.gserviceaccount.com"
NAMESPACE="${AGENT_VM_REAPER_NAMESPACE:-prod-omi-backend}"
KSA_NAME="${AGENT_VM_REAPER_KSA:-prod-agent-vm-reaper-sa}"
CLUSTER="${AGENT_VM_REAPER_CLUSTER:-prod-omi-gke}"
REGION="${AGENT_VM_REAPER_REGION:-us-central1}"
MANIFEST="${ROOT}/backend/charts/agent-vm-reaper/prod_agent_vm_reaper_cronjob.yaml"
SCRIPT_SRC="${ROOT}/backend/scripts/agent_vm_reaper.py"
WI_MEMBER="serviceAccount:${PROJECT}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]"

if [[ "${AGENT_VM_REAPER_APPLY:-}" != "1" ]]; then
  cat >&2 <<EOF
REFUSED: refusing to mutate GCP/GKE for agent-vm-reaper.

This install creates a GCE-deleting service account and a CronJob. Re-run with:

  AGENT_VM_REAPER_APPLY=1 bash backend/scripts/apply-agent-vm-reaper.sh

Dry-run-only inventory (no apply):

  python3 backend/scripts/agent_vm_reaper.py --dry-run

Enable live deletes only after reviewing CronJob logs:

  AGENT_VM_REAPER_APPLY=1 AGENT_VM_REAPER_LIVE=1 bash backend/scripts/apply-agent-vm-reaper.sh
EOF
  exit 1
fi

DRY_RUN_VALUE="true"
if [[ "${AGENT_VM_REAPER_LIVE:-}" == "1" ]]; then
  DRY_RUN_VALUE="false"
  echo "LIVE MODE: CronJob will set DRY_RUN=false (instances will be deleted hourly)"
else
  echo "SAFE MODE: CronJob will set DRY_RUN=true (log-only until LIVE=1 re-apply)"
fi

command -v gcloud >/dev/null
command -v kubectl >/dev/null
[[ -f "$MANIFEST" ]] || { echo "missing manifest: $MANIFEST" >&2; exit 1; }
[[ -f "$SCRIPT_SRC" ]] || { echo "missing script: $SCRIPT_SRC" >&2; exit 1; }

echo "Ensuring cluster credentials for ${CLUSTER}..."
gcloud container clusters get-credentials "$CLUSTER" --region "$REGION" --project "$PROJECT" >/dev/null

if ! gcloud iam service-accounts describe "$GSA_EMAIL" --project="$PROJECT" >/dev/null 2>&1; then
  echo "Creating GSA ${GSA_EMAIL}..."
  gcloud iam service-accounts create "$GSA_NAME" \
    --project="$PROJECT" \
    --display-name="Omi agent VM reaper" \
    --description="Deletes aged idle omi-agent-* GCE VMs (and autoDelete disks)"
else
  echo "GSA ${GSA_EMAIL} already exists"
fi

echo "Ensuring roles/compute.instanceAdmin.v1 on ${GSA_EMAIL}..."
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${GSA_EMAIL}" \
  --role="roles/compute.instanceAdmin.v1" \
  --condition=None \
  >/dev/null

echo "Ensuring workloadIdentityUser for ${WI_MEMBER}..."
gcloud iam service-accounts add-iam-policy-binding "$GSA_EMAIL" \
  --project="$PROJECT" \
  --role="roles/iam.workloadIdentityUser" \
  --member="$WI_MEMBER" \
  >/dev/null

echo "Syncing reaper script ConfigMap from ${SCRIPT_SRC}..."
kubectl -n "$NAMESPACE" create configmap prod-agent-vm-reaper-script \
  --from-file=agent_vm_reaper.py="$SCRIPT_SRC" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Applying Kubernetes ServiceAccount + CronJob from ${MANIFEST}..."
# Force DRY_RUN via server-side strategic merge after base apply so the checked-in
# default stays explicit in git while apply controls the live switch.
kubectl apply -f "$MANIFEST"

echo "Setting CronJob DRY_RUN=${DRY_RUN_VALUE}..."
kubectl -n "$NAMESPACE" set env cronjob/prod-agent-vm-reaper DRY_RUN="$DRY_RUN_VALUE"

echo "Done. Verify with:"
echo "  kubectl -n ${NAMESPACE} get cronjob prod-agent-vm-reaper"
echo "  kubectl -n ${NAMESPACE} create job --from=cronjob/prod-agent-vm-reaper agent-vm-reaper-manual-\$(date +%s)"
echo "  kubectl -n ${NAMESPACE} logs job/<job-name>"
