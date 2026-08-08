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
if [[ ! "$deployer" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com$ ]]; then
  echo "AGENT_VM_RECONCILER_DEPLOYER must be a full Google service-account email." >&2
  exit 2
fi

gsa_name="${AGENT_VM_RECONCILER_GSA:-agent-vm-reconciler}"
gsa="${gsa_name}@${project}.iam.gserviceaccount.com"
role_id="omiAgentVmReconciler"
role="projects/${project}/roles/${role_id}"
operations_role_id="omiAgentVmReconcilerOperations"
operations_role="projects/${project}/roles/${operations_role_id}"
# State-disk creation/clone and attachment are carried by the same narrow
# custom role as the existing VM lifecycle permissions. The project bindings
# below still constrain Disk and Instance resources to omi-agent-* names.
permissions="compute.disks.create,compute.disks.delete,compute.disks.get,compute.disks.use,compute.disks.useReadOnly,compute.images.useReadOnly,compute.instances.attachDisk,compute.instances.create,compute.instances.delete,compute.instances.detachDisk,compute.instances.get,compute.instances.setDiskAutoDelete,compute.instances.setLabels,compute.instances.setMetadata,compute.instances.setServiceAccount,compute.instances.setTags,compute.instances.start,compute.instances.stop"
subnetwork_role_id="omiAgentVmReconcilerSubnetwork"
subnetwork_role="projects/${project}/roles/${subnetwork_role_id}"
subnetwork_permissions="compute.subnetworks.use,compute.subnetworks.useExternalIp"
operations_permissions="compute.globalOperations.get,compute.zoneOperations.get"
zone="us-central1-a"
region="${zone%-*}"

if ! gcloud iam service-accounts describe "$gsa" --project="$project" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$gsa_name" --project="$project" --display-name="Omi Agent VM reconciler"
fi
# The CI deploy identity needs actAs only on this dedicated runtime identity to
# attach it to the Cloud Run Job. Do not grant Service Account User at project
# scope: that would let the deployer impersonate unrelated service accounts.
gcloud iam service-accounts add-iam-policy-binding "$gsa" --project="$project" \
  --member="serviceAccount:${deployer}" --role=roles/iam.serviceAccountUser --condition=None
if gcloud iam roles describe "$role_id" --project="$project" >/dev/null 2>&1; then
  gcloud iam roles update "$role_id" --project="$project" --title="Omi Agent VM reconciler" --permissions="$permissions" --stage=GA
else
  gcloud iam roles create "$role_id" --project="$project" --title="Omi Agent VM reconciler" --permissions="$permissions" --stage=GA
fi
if gcloud iam roles describe "$subnetwork_role_id" --project="$project" >/dev/null 2>&1; then
  gcloud iam roles update "$subnetwork_role_id" --project="$project" --title="Omi Agent VM reconciler subnet" --permissions="$subnetwork_permissions" --stage=GA
else
  gcloud iam roles create "$subnetwork_role_id" --project="$project" --title="Omi Agent VM reconciler subnet" --permissions="$subnetwork_permissions" --stage=GA
fi
if gcloud iam roles describe "$operations_role_id" --project="$project" >/dev/null 2>&1; then
  gcloud iam roles update "$operations_role_id" --project="$project" --title="Omi Agent VM reconciler operation polling" --permissions="$operations_permissions" --stage=GA
else
  gcloud iam roles create "$operations_role_id" --project="$project" --title="Omi Agent VM reconciler operation polling" --permissions="$operations_permissions" --stage=GA
fi

gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role="$role" \
  --condition="title=Agent VM reconciler instance scope,description=Only omi-agent instances in the Agent VM zone,expression=resource.type == 'compute.googleapis.com/Instance' && resource.name.startsWith('projects/${project}/zones/${zone}/instances/omi-agent-')"
# Boot-image drift verification and the persistent state-disk/clone path use
# compute.googleapis.com/Disk permissions. Disk permissions are evaluated as
# Disk resources, so the instance-scoped condition above does not cover them.
# Agent VM disks are named from the owner/migration identity, so the same
# omi-agent- prefix applies to boot, state, and temporary clone disks.
disk_condition="title=Agent VM reconciler disk scope,description=Agent VM boot and state disk lifecycle operations in the Agent VM zone,expression=resource.type == 'compute.googleapis.com/Disk' && resource.name.startsWith('projects/${project}/zones/${zone}/disks/omi-agent-')"
legacy_disk_condition="title=Agent VM reconciler disk scope,description=Boot disk reads for omi-agent instances in the Agent VM zone,expression=resource.type == 'compute.googleapis.com/Disk' && resource.name.startsWith('projects/${project}/zones/${zone}/disks/omi-agent-')"
gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role="$role" \
  --condition="$disk_condition"
# IAM condition metadata is part of binding identity. Add the accurate binding
# first, then remove the exact legacy description without creating a permission
# gap. A failed policy read or removal aborts under set -e instead of being
# mistaken for an absent legacy binding.
legacy_disk_description="$(
  gcloud projects get-iam-policy "$project" --flatten='bindings[]' \
    --filter="bindings.role=${role} AND bindings.members=serviceAccount:${gsa} AND bindings.condition.title='Agent VM reconciler disk scope' AND bindings.condition.description='Boot disk reads for omi-agent instances in the Agent VM zone'" \
    --format='value(bindings.condition.description)'
)"
if [[ "$legacy_disk_description" == "Boot disk reads for omi-agent instances in the Agent VM zone" ]]; then
  gcloud projects remove-iam-policy-binding "$project" \
    --member="serviceAccount:${gsa}" --role="$role" --condition="$legacy_disk_condition"
fi
# An explicit dev migration may create a replacement only from the immutable
# Agent VM image family.  Image use is evaluated against the Image resource,
# not the instance/disk scopes above.
gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role="$role" \
  --condition="title=Agent VM reconciler image scope,description=Immutable omi-agent images only,expression=resource.type == 'compute.googleapis.com/Image' && resource.name.startsWith('projects/${project}/global/images/omi-agent-')"
# Replacement VMs preserve the predecessor's default subnet and external NAT.
# Bind the two network permissions directly on that subnetwork: Compute IAM
# Conditions do not make the project-level instance/disk/image bindings apply
# to a Subnetwork resource.
gcloud compute networks subnets add-iam-policy-binding default --project="$project" --region="$region" \
  --member="serviceAccount:${gsa}" --role="$subnetwork_role"
gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role="$operations_role" --condition=None
# Project IAM policies containing scoped bindings require unconditional bindings
# to say so explicitly.  The operations and datastore roles are intentionally
# unconditioned because neither permission supports the instance resource
# condition used above.
gcloud projects add-iam-policy-binding "$project" \
  --member="serviceAccount:${gsa}" --role=roles/datastore.user --condition=None
gcloud storage buckets add-iam-policy-binding "gs://${bucket}" \
  --member="serviceAccount:${gsa}" --role=roles/storage.objectViewer --condition=None

bootstrap="omi-agent-vm-bootstrap@${project}.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$bootstrap" --project="$project" \
  --member="serviceAccount:${gsa}" --role=roles/iam.serviceAccountUser --condition=None
echo "Configured ${gsa}; deploy the Cloud Run Job with this service account."
