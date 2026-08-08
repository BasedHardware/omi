#!/usr/bin/env bash
# Transitional compatibility only: older Agent VM startup artifacts used this
# direct self-stop permission. New artifacts call the backend stop broker and
# operators should revoke this binding after broker-capable rollout evidence.
#
# Refuse by default. Apply only after reviewing the target projects:
#   AGENT_VM_BOOTSTRAP_IAM_APPLY=1 bash backend/scripts/apply-agent-vm-bootstrap-iam.sh
set -euo pipefail

if [[ "${AGENT_VM_BOOTSTRAP_IAM_APPLY:-}" != "1" ]]; then
  echo "REFUSED: set AGENT_VM_BOOTSTRAP_IAM_APPLY=1 to mutate Agent VM IAM." >&2
  exit 1
fi

ROLE_ID="omiAgentVmSelfStop"
ROLE_TITLE="Omi Agent VM self-stop"
ROLE_PERMISSIONS="compute.instances.stop"
ZONE="us-central1-a"

for project in based-hardware-dev based-hardware; do
  service_account="omi-agent-vm-bootstrap@${project}.iam.gserviceaccount.com"
  role="projects/${project}/roles/${ROLE_ID}"
  condition_title="Agent VM prefix self-stop"
  condition_description="Allow the bootstrap identity to stop only Agent VMs in ${ZONE}."
  condition_expression="resource.type == 'compute.googleapis.com/Instance' && resource.name.startsWith('projects/${project}/zones/${ZONE}/instances/omi-agent-')"

  if gcloud iam roles describe "${ROLE_ID}" --project="${project}" >/dev/null 2>&1; then
    gcloud iam roles update "${ROLE_ID}" \
      --project="${project}" \
      --title="${ROLE_TITLE}" \
      --permissions="${ROLE_PERMISSIONS}" \
      --stage=GA >/dev/null
  else
    gcloud iam roles create "${ROLE_ID}" \
      --project="${project}" \
      --title="${ROLE_TITLE}" \
      --permissions="${ROLE_PERMISSIONS}" \
      --stage=GA >/dev/null
  fi

  gcloud projects remove-iam-policy-binding "${project}" \
    --member="serviceAccount:${service_account}" \
    --role="${role}" \
    --condition=None >/dev/null 2>&1 || true
  gcloud projects add-iam-policy-binding "${project}" \
    --member="serviceAccount:${service_account}" \
    --role="${role}" \
    --condition="title=${condition_title},description=${condition_description},expression=${condition_expression}" >/dev/null
  echo "Configured conditional ${role} for ${service_account} in ${project}."
done
