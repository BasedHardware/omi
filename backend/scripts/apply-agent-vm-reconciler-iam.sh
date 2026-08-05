#!/usr/bin/env bash
# Provision the dedicated Cloud Run Job identity. Refuse by default.
set -euo pipefail

if [[ "${AGENT_VM_RECONCILER_IAM_APPLY:-}" != "1" ]]; then
  echo "REFUSED: set AGENT_VM_RECONCILER_IAM_APPLY=1 to mutate Agent VM reconciler IAM." >&2
  exit 1
fi

project="${AGENT_VM_RECONCILER_PROJECT:-}"
bucket="${AGENT_VM_RECONCILER_BUCKET:-}"
deployer="${AGENT_VM_RECONCILER_DEPLOYER:-}"
if [[ -z "$project" || -z "$bucket" || -z "$deployer" ]]; then
  echo "AGENT_VM_RECONCILER_PROJECT, AGENT_VM_RECONCILER_BUCKET, and AGENT_VM_RECONCILER_DEPLOYER are required." >&2
  exit 2
fi
if [[ "$deployer" != *@*.iam.gserviceaccount.com ]]; then
  echo "AGENT_VM_RECONCILER_DEPLOYER must be a full Google service-account email." >&2
  exit 2
fi

gsa_name="${AGENT_VM_RECONCILER_GSA:-agent-vm-reconciler}"
gsa="${gsa_name}@${project}.iam.gserviceaccount.com"
role_id="omiAgentVmReconciler"
role="projects/${project}/roles/${role_id}"
operations_role_id="omiAgentVmReconcilerOperations"
operations_role="projects/${project}/roles/${operations_role_id}"
permissions="compute.disks.get,compute.instances.get,compute.instances.setMetadata,compute.instances.setServiceAccount,compute.instances.start,compute.instances.stop"
operations_permissions="compute.globalOperations.get,compute.zoneOperations.get"
zone="us-central1-a"

if ! gcloud iam service-accounts describe "$gsa" --project="$project" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$gsa_name" --project="$project" --display-name="Omi Agent VM reconciler"
fi
# The CI deploy identity needs actAs only on this dedicated runtime identity to
# attach it to the Cloud Run Job. Do not grant Service Account User at project
# scope: that would let the deployer impersonate unrelated service accounts.
gcloud iam service-accounts add-iam-policy-binding "$gsa" --project="$project" \
  --member="serviceAccount:${deployer}" --role=roles/iam.serviceAccountUser
if gcloud iam roles describe "$role_id" --project="$project" >/dev/null 2>&1; then
  gcloud iam roles update "$role_id" --project="$project" --title="Omi Agent VM reconciler" --permissions="$permissions" --stage=GA
else
  gcloud iam roles create "$role_id" --project="$project" --title="Omi Agent VM reconciler" --permissions="$permissions" --stage=GA
fi
if gcloud iam roles describe "$operations_role_id" --project="$project" >/dev/null 2>&1; then
  gcloud iam roles update "$operations_role_id" --project="$project" --title="Omi Agent VM reconciler operation polling" --permissions="$operations_permissions" --stage=GA
else
  gcloud iam roles create "$operations_role_id" --project="$project" --title="Omi Agent VM reconciler operation polling" --permissions="$operations_permissions" --stage=GA
fi

gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role="$role" \
  --condition="title=Agent VM reconciler instance scope,description=Only omi-agent instances in the Agent VM zone,expression=resource.type == 'compute.googleapis.com/Instance' && resource.name.startsWith('projects/${project}/zones/${zone}/instances/omi-agent-')"
# Boot-image drift verification reads each VM's boot disk via compute.disks.get.
# Disk reads are evaluated as compute.googleapis.com/Disk resources, so the
# instance-scoped condition above does not cover them.  Agent VM boot disks are
# auto-generated from the instance name, so the same omi-agent- prefix applies.
gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role="$role" \
  --condition="title=Agent VM reconciler disk scope,description=Boot disk reads for omi-agent instances in the Agent VM zone,expression=resource.type == 'compute.googleapis.com/Disk' && resource.name.startsWith('projects/${project}/zones/${zone}/disks/omi-agent-')"
gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role="$operations_role"
gcloud projects add-iam-policy-binding "$project" --member="serviceAccount:${gsa}" --role=roles/datastore.user
gcloud storage buckets add-iam-policy-binding "gs://${bucket}" --member="serviceAccount:${gsa}" --role=roles/storage.objectViewer

bootstrap="omi-agent-vm-bootstrap@${project}.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$bootstrap" --project="$project" \
  --member="serviceAccount:${gsa}" --role=roles/iam.serviceAccountUser
echo "Configured ${gsa}; deploy the Cloud Run Job with this service account."
